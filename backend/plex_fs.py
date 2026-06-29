"""
VodLink FUSE virtual filesystem for Plex.

Mounts at PLEX_MOUNT (/vod/plex by default) and mirrors /vod/dest/ with one
change: .strm files are replaced by virtual .mkv files of the same base name.
When Plex reads a .mkv, this module makes ranged HTTP requests to the URL
stored in the corresponding .strm (VodLink proxy → Dispatcharr).
.nfo files and directories pass through unmodified.

File sizes are NOT probed during directory scans (that would hammer Dispatcharr
with short-lived connections). Instead a persistent cache in /app/data/plex_sizes.json
is populated lazily the first time each file is actually read. Until then, a
large placeholder size is reported so Plex adds the item to the library.

Requires:
  - fusepy (pip) + libfuse2 (apt)
  - Container run with --privileged (or --device /dev/fuse --cap-add SYS_ADMIN)
  - /etc/fuse.conf must contain "user_allow_other"
  - Mount volume must have bind-propagation=shared so the mount is visible on host
"""
import errno
import json
import logging
import os
import re
import stat
import threading

import httpx

try:
    from fuse import FUSE, FuseOSError, Operations
    _FUSE_AVAILABLE = True
except ImportError:
    _FUSE_AVAILABLE = False
    Operations = object

log = logging.getLogger(__name__)

DEST_ROOT = "/vod/dest"
SRC_ROOT = "/vod/src"

# Placeholder reported to Plex during scan before the real size is known.
# Large enough that Plex treats it as a real file; seek bar corrects itself
# once actual Content-Range arrives during playback.
_PLACEHOLDER_SIZE = 50 * 1024 * 1024 * 1024  # 50 GB

_SIZE_CACHE_PATH = "/app/data/plex_sizes.json"
_size_cache: dict[str, int] = {}   # strm_path -> bytes
_size_lock = threading.Lock()


def _load_size_cache() -> None:
    try:
        with open(_SIZE_CACHE_PATH) as f:
            _size_cache.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_size(strm_path: str, size: int) -> None:
    with _size_lock:
        if _size_cache.get(strm_path) == size:
            return
        _size_cache[strm_path] = size
        try:
            with open(_SIZE_CACHE_PATH, "w") as f:
                json.dump(_size_cache, f)
        except OSError:
            pass


def _cached_size(strm_path: str) -> int:
    return _size_cache.get(strm_path, _PLACEHOLDER_SIZE)


def _read_strm(strm_path: str) -> str | None:
    try:
        content = open(strm_path).read().strip()
        return content if content.startswith("http") else None
    except OSError:
        return None


class VodLinkFS(Operations):

    def _real(self, path: str) -> str:
        return DEST_ROOT + path

    def _src(self, path: str) -> str:
        return SRC_ROOT + path

    def _strm_for_mkv(self, path: str) -> str:
        return self._real(path[:-4] + ".strm")

    def _resolve(self, path: str) -> str | None:
        """Return a readable path, with /vod/src/ fallback for broken NFO symlinks."""
        real = self._real(path)
        if os.path.exists(real):
            return real
        src = self._src(path)
        if os.path.exists(src):
            return src
        return None

    # --- Filesystem metadata ---

    def getattr(self, path, fh=None):
        if path.endswith(".mkv"):
            strm = self._strm_for_mkv(path)
            if not os.path.exists(strm):
                raise FuseOSError(errno.ENOENT)
            st = os.stat(strm)
            # Use cached real size if we have it; otherwise placeholder.
            # Never probe Dispatcharr here — that would hammer it during scans.
            size = _cached_size(strm)
            return dict(
                st_mode=stat.S_IFREG | 0o444,
                st_nlink=1,
                st_size=size,
                st_atime=st.st_atime,
                st_mtime=st.st_mtime,
                st_ctime=st.st_ctime,
                st_uid=st.st_uid,
                st_gid=st.st_gid,
            )

        resolved = self._resolve(path)
        if resolved:
            st = os.stat(resolved)
            return dict(
                st_mode=st.st_mode,
                st_nlink=st.st_nlink,
                st_size=st.st_size,
                st_atime=st.st_atime,
                st_mtime=st.st_mtime,
                st_ctime=st.st_ctime,
                st_uid=st.st_uid,
                st_gid=st.st_gid,
            )

        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        yield "."
        yield ".."
        real = self._real(path)
        try:
            for name in os.listdir(real):
                if name.endswith(".strm"):
                    yield name[:-5] + ".mkv"
                else:
                    yield name
        except OSError:
            pass

    # --- File operations ---

    def open(self, path, flags):
        return 0

    def release(self, path, fh):
        return 0

    def read(self, path, size, offset, fh):
        if path.endswith(".mkv"):
            strm = self._strm_for_mkv(path)
            url = _read_strm(strm)
            if not url:
                raise FuseOSError(errno.EIO)
            try:
                with httpx.Client(timeout=120, follow_redirects=True) as c:
                    r = c.get(url, headers={"Range": f"bytes={offset}-{offset + size - 1}"})
                    if r.status_code not in (200, 206):
                        raise FuseOSError(errno.EIO)
                    # Cache the real file size from Content-Range on first successful read.
                    cr = r.headers.get("content-range", "")
                    m = re.search(r"/(\d+)$", cr)
                    if m:
                        real_size = int(m.group(1))
                        if _size_cache.get(strm) != real_size:
                            _save_size(strm, real_size)
                    return r.content
            except FuseOSError:
                raise
            except Exception as e:
                log.warning("plex_fs read error %s: %s", path, e)
                raise FuseOSError(errno.EIO)

        # Passthrough for .nfo and other real files (with /vod/src/ fallback)
        resolved = self._resolve(path)
        if not resolved:
            raise FuseOSError(errno.ENOENT)
        try:
            with open(resolved, "rb") as f:
                f.seek(offset)
                return f.read(size)
        except OSError as e:
            raise FuseOSError(e.errno)


def mount(mountpoint: str) -> None:
    if not _FUSE_AVAILABLE:
        log.error("fusepy not installed — Plex filesystem unavailable")
        return
    _load_size_cache()
    try:
        os.makedirs(mountpoint, exist_ok=True)
        log.info("VodLink Plex FS mounting at %s", mountpoint)
        FUSE(
            VodLinkFS(),
            mountpoint,
            nothreads=False,
            foreground=True,
            allow_other=True,
        )
    except Exception as e:
        log.error("VodLink Plex FS failed: %s", e)
