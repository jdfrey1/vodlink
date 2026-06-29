"""
VodLink FUSE virtual filesystem for Plex.

Mounts at PLEX_MOUNT (/vod/plex by default) and mirrors /vod/dest/ with one
change: .strm files are replaced by virtual .mkv files of the same base name.
When Plex reads a .mkv, this module makes ranged HTTP requests to the URL
stored in the corresponding .strm (VodLink proxy → Dispatcharr).
.nfo files and directories pass through unmodified.

Requires:
  - fusepy (pip) + libfuse2 (apt)
  - Container run with --privileged (or --device /dev/fuse --cap-add SYS_ADMIN)
  - /etc/fuse.conf must contain "user_allow_other"
  - Mount volume must have bind-propagation=shared so the mount is visible on host
"""
import errno
import logging
import os
import re
import stat
import time

import httpx

try:
    from fuse import FUSE, FuseOSError, Operations
    _FUSE_AVAILABLE = True
except ImportError:
    _FUSE_AVAILABLE = False
    Operations = object  # fallback so class definition doesn't fail

log = logging.getLogger(__name__)

DEST_ROOT = "/vod/dest"
SRC_ROOT = "/vod/src"   # fallback for NFO symlinks that point to host absolute paths
_SIZE_CACHE: dict[str, tuple[int, float]] = {}
_SIZE_TTL = 3600.0


def _read_strm(strm_path: str) -> str | None:
    try:
        content = open(strm_path).read().strip()
        return content if content.startswith("http") else None
    except OSError:
        return None


def _get_stream_size(url: str | None) -> int:
    if not url:
        return 0
    cached = _SIZE_CACHE.get(url)
    if cached and time.monotonic() - cached[1] < _SIZE_TTL:
        return cached[0]
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as c:
            r = c.get(url, headers={"Range": "bytes=0-0"})
            m = re.search(r"/(\d+)$", r.headers.get("content-range", ""))
            size = int(m.group(1)) if m else 0
    except Exception:
        size = 0
    _SIZE_CACHE[url] = (size, time.monotonic())
    return size


class VodLinkFS(Operations):

    def _real(self, path: str) -> str:
        return DEST_ROOT + path

    def _src(self, path: str) -> str:
        return SRC_ROOT + path

    def _strm_for_mkv(self, path: str) -> str:
        return self._real(path[:-4] + ".strm")

    def _resolve(self, path: str) -> str | None:
        """Return a readable real path, following symlinks via /vod/src/ fallback."""
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
            size = _get_stream_size(_read_strm(strm))
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
    try:
        os.makedirs(mountpoint, exist_ok=True)
        log.info("VodLink Plex FS mounting at %s", mountpoint)
        FUSE(
            VodLinkFS(),
            mountpoint,
            nothreads=False,   # allow parallel reads for faster Plex scanning
            foreground=True,   # run in foreground (caller manages thread)
            allow_other=True,  # Plex user can access files mounted by VodLink user
        )
    except Exception as e:
        log.error("VodLink Plex FS failed: %s", e)
