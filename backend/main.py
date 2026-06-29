import os
import re
import shutil
import time
import urllib.parse
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
import scanner
import schedule_manager
import backup as bk

APP_VERSION = os.getenv("APP_VERSION", "dev").lstrip("v")
PLEX_MOUNT = os.getenv("PLEX_MOUNT", "")
MOVIES_DEST = "/vod/dest/Movies"
SERIES_DEST = "/vod/dest/Series"

# Cache Dispatcharr session URLs from HEAD probes so GET redirects can use the
# same session URL, avoiding the extra redirect hop and a new 301 from Dispatcharr.
# key = "movie:TMDB_ID" or "series:TMDB_ID:rel_path", value = (session_url, expires_at)
_session_cache: dict[str, tuple[str, float]] = {}
_SESSION_TTL = 3600.0  # 1 hour

# Stored so background threads (refresh after scan) can rewrite series .strm files.
_vodlink_base_url: str = ""


def _store_base_url(url: str) -> None:
    global _vodlink_base_url
    if url:
        _vodlink_base_url = url


def _get_base_url() -> str:
    if _vodlink_base_url:
        return _vodlink_base_url
    # Derive from existing linked movie .strm files on startup / before first link op.
    try:
        for d in os.listdir(MOVIES_DEST):
            for f in os.listdir(os.path.join(MOVIES_DEST, d)):
                if f.endswith(".strm"):
                    content = open(os.path.join(MOVIES_DEST, d, f)).read().strip()
                    if "/stream/movie/" in content:
                        return content[:content.find("/stream/movie/")]
    except OSError:
        pass
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    schedule_manager.init()
    bk.init()
    movies_count = db.count_by_type("movie")
    series_count = db.count_by_type("series")
    if movies_count == 0 and series_count == 0:
        scanner.start_scan_all(full=True, on_complete=_refresh_linked_files)
    elif movies_count == 0:
        scanner.start_scan("movie", full=True, on_complete=_refresh_linked_files)
    elif series_count == 0:
        scanner.start_scan("series", full=True, on_complete=_refresh_linked_files)
    if PLEX_MOUNT:
        import atexit
        import subprocess
        import threading
        import plex_fs
        atexit.register(lambda: subprocess.run(["fusermount", "-u", PLEX_MOUNT], capture_output=True))
        threading.Thread(target=plex_fs.mount, args=(PLEX_MOUNT,), daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


def _dest_path(media_type: str, dir_name: str) -> str:
    base = MOVIES_DEST if media_type == "movie" else SERIES_DEST
    return os.path.join(base, dir_name)


def _is_linked(dp: str) -> bool:
    return os.path.exists(dp) or os.path.islink(dp)


def _enrich(item: dict, media_type: str) -> dict:
    dp = _dest_path(media_type, item["dir_name"])
    return {**item, "linked": _is_linked(dp)}


def _linked_dir_names(media_type: str) -> list[str]:
    dest = MOVIES_DEST if media_type == "movie" else SERIES_DEST
    try:
        return [d for d in os.listdir(dest)
                if _is_linked(os.path.join(dest, d))]
    except OSError:
        return []


def _find_strm_url(src_dir: str) -> str | None:
    """Read the Dispatcharr URL from the .strm file in the source directory."""
    try:
        for f in os.listdir(src_dir):
            if f.endswith(".strm"):
                content = open(os.path.join(src_dir, f)).read().strip()
                if content.startswith("http"):
                    return content
    except OSError:
        pass
    return None


def _find_nfo_files(src_dir: str) -> list[str]:
    """Top-level .nfo files (not episode nfos which start with a digit)."""
    try:
        return [f for f in os.listdir(src_dir)
                if f.endswith(".nfo") and not f[0].isdigit()]
    except OSError:
        return []


def _strm_filename(src_dir: str, dir_name: str) -> str:
    """Return the .strm filename from the source dir, or fall back to dir_name."""
    try:
        for f in os.listdir(src_dir):
            if f.endswith(".strm"):
                return f
    except OSError:
        pass
    return dir_name + ".strm"


# --- Version ---

@app.get("/api/version")
def get_version():
    return {"version": APP_VERSION}


# --- Stream endpoint ---

_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=5.0)
# No keepalive — connections close after each request so Dispatcharr sees a clean
# disconnect rather than an idle connection sitting in a pool.
_NO_KEEPALIVE = httpx.Limits(max_keepalive_connections=0, max_connections=20)


async def _do_proxy(request: Request, dispatcharr_url: str, cache_key: str):
    """Shared proxy logic for movie and series episode streams."""
    fwd_headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in ("host", "connection", "transfer-encoding")}

    now = time.monotonic()
    cached = _session_cache.get(cache_key)
    session_url = cached[0] if (cached and cached[1] > now) else None

    # One-shot client — no keepalive pool, TCP closes after each response.
    client = httpx.AsyncClient(timeout=_STREAM_TIMEOUT, limits=_NO_KEEPALIVE,
                               follow_redirects=(session_url is None))
    target = session_url or dispatcharr_url

    if request.method == "HEAD":
        # Dispatcharr returns 405 for HEAD — use GET Range:0-0 to get headers.
        try:
            req = client.build_request("GET", target, headers={"range": "bytes=0-0"})
            resp = await client.send(req, stream=True)
            if session_url is None:
                landed = str(resp.url)
                if landed != dispatcharr_url:
                    _session_cache[cache_key] = (landed, now + _SESSION_TTL)
            probe_status = resp.status_code
            probe_headers = dict(resp.headers)
            await resp.aclose()
        finally:
            await client.aclose()

        # Stale cached session → retry once with a fresh probe.
        if probe_status not in (200, 206) and session_url is not None:
            _session_cache.pop(cache_key, None)
            return await _do_proxy(request, dispatcharr_url, cache_key)

        headers: dict[str, str] = {}
        for h in ("content-type", "accept-ranges", "last-modified", "etag"):
            if h in probe_headers:
                headers[h] = probe_headers[h]
        cr = probe_headers.get("content-range", "")
        m = re.search(r"/(\d+)$", cr)
        if m:
            headers["content-length"] = m.group(1)
            headers["accept-ranges"] = "bytes"
        return Response(status_code=200, headers=headers)

    # GET: proxy so Emby uses a stable URL for all Range/seek requests.
    try:
        req = client.build_request("GET", target, headers=fwd_headers)
        resp = await client.send(req, stream=True)

        if session_url is None:
            landed = str(resp.url)
            if landed != dispatcharr_url:
                _session_cache[cache_key] = (landed, now + _SESSION_TTL)

        if resp.status_code not in (200, 206):
            await resp.aclose()
            await client.aclose()
            if session_url is not None:
                # Cached session URL expired — retry once with a fresh probe.
                _session_cache.pop(cache_key, None)
                return await _do_proxy(request, dispatcharr_url, cache_key)
            raise HTTPException(resp.status_code, "Upstream error")

        resp_headers = {k: v for k, v in resp.headers.items()
                        if k.lower() not in ("transfer-encoding", "connection")}

        async def body_gen():
            try:
                async for chunk in resp.aiter_bytes(chunk_size=524288):  # 512 KB
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(body_gen(), status_code=resp.status_code,
                                 headers=resp_headers)
    except Exception:
        await client.aclose()
        raise


@app.api_route("/stream/series/{tmdb_id}/{file_path:path}", methods=["GET", "HEAD"])
async def stream_series_episode(tmdb_id: str, file_path: str, request: Request):
    item = db.get_by_tmdb("series", tmdb_id)
    if not item:
        raise HTTPException(404, "Not found")
    strm_path = os.path.join(item["source_path"], file_path + ".strm")
    dispatcharr_url = None
    try:
        content = open(strm_path).read().strip()
        if content.startswith("http"):
            dispatcharr_url = content
    except OSError:
        pass
    if not dispatcharr_url:
        raise HTTPException(503, "No stream URL found")
    return await _do_proxy(request, dispatcharr_url, f"series:{tmdb_id}:{file_path}")


@app.api_route("/stream/{media_type}/{tmdb_id}", methods=["GET", "HEAD"])
async def stream_media(media_type: str, tmdb_id: str, request: Request):
    item = db.get_by_tmdb(media_type, tmdb_id)
    if not item:
        raise HTTPException(404, "Not found")
    dispatcharr_url = _find_strm_url(item["source_path"])
    if not dispatcharr_url:
        raise HTTPException(503, "No stream URL found in source")
    return await _do_proxy(request, dispatcharr_url, f"{media_type}:{tmdb_id}")


# --- List / search ---

@app.get("/api/movies/genres")
def movie_genres():
    return db.get_genres("movie")


@app.get("/api/series/genres")
def series_genres():
    return db.get_genres("series")


@app.get("/api/movies")
def list_movies(
    q: str = "", page: int = 1, limit: int = 50,
    linked_only: bool = False, genre: str = "", sort_by: str = "title", sort_dir: str = "asc"
):
    if linked_only:
        rows, total = db.search_media_by_dir_names(
            "movie", _linked_dir_names("movie"), q, page, limit, genre, sort_by, sort_dir
        )
    else:
        rows, total = db.search_media("movie", q, page, limit, genre, sort_by, sort_dir)
    return {
        "items": [_enrich(r, "movie") for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


@app.get("/api/series")
def list_series(
    q: str = "", page: int = 1, limit: int = 50,
    linked_only: bool = False, genre: str = "", sort_by: str = "title", sort_dir: str = "asc"
):
    if linked_only:
        rows, total = db.search_media_by_dir_names(
            "series", _linked_dir_names("series"), q, page, limit, genre, sort_by, sort_dir
        )
    else:
        rows, total = db.search_media("series", q, page, limit, genre, sort_by, sort_dir)
    return {
        "items": [_enrich(r, "series") for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


# --- Link / unlink movies (proxy .strm approach) ---

def _link_movie_item(item: dict, base_url: str) -> dict:
    dest_dir = _dest_path("movie", item["dir_name"])
    if _is_linked(dest_dir):
        return {"linked": True, "message": "Already linked"}
    src_dir = item["source_path"]
    try:
        os.makedirs(dest_dir)
        strm_name = _strm_filename(src_dir, item["dir_name"])
        proxy_url = f"{base_url}/stream/movie/{item['tmdb_id']}"
        with open(os.path.join(dest_dir, strm_name), "w") as f:
            f.write(proxy_url)
        for nfo in _find_nfo_files(src_dir):
            shutil.copy2(os.path.join(src_dir, nfo), os.path.join(dest_dir, nfo))
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"linked": True}


def _unlink_item(dest_dir: str) -> dict:
    try:
        if os.path.islink(dest_dir):
            os.unlink(dest_dir)
        elif os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        else:
            return {"linked": False, "message": "Not linked"}
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"linked": False}


@app.post("/api/movies/{tmdb_id}/link")
def link_movie(tmdb_id: str, request: Request):
    item = db.get_by_tmdb("movie", tmdb_id)
    if not item:
        raise HTTPException(404, "Movie not found")
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "")
    base_url = f"{scheme}://{host}"
    _store_base_url(base_url)
    return _link_movie_item(item, base_url)


@app.delete("/api/movies/{tmdb_id}/link")
def unlink_movie(tmdb_id: str):
    item = db.get_by_tmdb("movie", tmdb_id)
    if not item:
        raise HTTPException(404, "Movie not found")
    return _unlink_item(_dest_path("movie", item["dir_name"]))


# --- Link / unlink series ---

@app.post("/api/series/{tmdb_id}/link")
def link_series(tmdb_id: str, request: Request):
    item = db.get_by_tmdb("series", tmdb_id)
    if not item:
        raise HTTPException(404, "Series not found")
    dp = _dest_path("series", item["dir_name"])
    if _is_linked(dp):
        return {"linked": True, "message": "Already linked"}
    try:
        shutil.copytree(item["source_path"], dp)
    except OSError as e:
        raise HTTPException(500, str(e))
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "")
    base_url = f"{scheme}://{host}"
    _store_base_url(base_url)
    _rewrite_series_strm_files(dp, item["tmdb_id"], base_url)
    return {"linked": True}


@app.delete("/api/series/{tmdb_id}/link")
def unlink_series(tmdb_id: str):
    item = db.get_by_tmdb("series", tmdb_id)
    if not item:
        raise HTTPException(404, "Series not found")
    return _unlink_item(_dest_path("series", item["dir_name"]))


# --- File refresh (run after scan to sync copied .nfo / series files) ---

def _sync_dir(src: str, dest: str) -> None:
    """Copy new/changed files from src into dest; remove files absent from src."""
    os.makedirs(dest, exist_ok=True)
    src_names: set[str] = set()
    for entry in os.scandir(src):
        src_names.add(entry.name)
        dest_path = os.path.join(dest, entry.name)
        if entry.is_dir(follow_symlinks=False):
            _sync_dir(entry.path, dest_path)
        else:
            try:
                src_mtime = entry.stat(follow_symlinks=False).st_mtime
                dst_mtime = os.stat(dest_path).st_mtime if os.path.exists(dest_path) else 0
                if src_mtime > dst_mtime:
                    shutil.copy2(entry.path, dest_path)
            except OSError:
                pass
    try:
        for entry in os.scandir(dest):
            if entry.name not in src_names:
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path, ignore_errors=True)
                else:
                    try:
                        os.unlink(entry.path)
                    except OSError:
                        pass
    except OSError:
        pass


def _rewrite_series_strm_files(dest_dir: str, tmdb_id: str, base_url: str) -> None:
    """Rewrite series episode .strm files to route through VodLink proxy."""
    for root, _dirs, files in os.walk(dest_dir):
        for f in files:
            if not f.endswith(".strm"):
                continue
            path = os.path.join(root, f)
            try:
                content = open(path).read().strip()
                if "/stream/series/" in content:
                    continue  # already a proxy URL
                if not content.startswith("http"):
                    continue
                rel = os.path.relpath(path, dest_dir)[:-5]  # strip ".strm"
                encoded = urllib.parse.quote(rel, safe="/")
                with open(path, "w") as fp:
                    fp.write(f"{base_url}/stream/series/{tmdb_id}/{encoded}")
            except OSError:
                pass


def _refresh_linked_files(media_type: str) -> None:
    for dir_name in _linked_dir_names(media_type):
        item = db.get_by_dir_name(media_type, dir_name)
        if not item:
            continue
        src_dir = item["source_path"]
        dest_dir = _dest_path(media_type, dir_name)
        if os.path.islink(dest_dir):
            continue  # old-style symlink — skip until user relinks
        if media_type == "movie":
            for nfo in _find_nfo_files(src_dir):
                src_nfo = os.path.join(src_dir, nfo)
                dst_nfo = os.path.join(dest_dir, nfo)
                try:
                    src_mtime = os.stat(src_nfo).st_mtime
                    dst_mtime = os.stat(dst_nfo).st_mtime if os.path.exists(dst_nfo) else 0
                    if src_mtime > dst_mtime:
                        shutil.copy2(src_nfo, dst_nfo)
                except OSError:
                    pass
        else:
            _sync_dir(src_dir, dest_dir)
            base_url = _get_base_url()
            if base_url:
                _rewrite_series_strm_files(dest_dir, item["tmdb_id"], base_url)


# --- Sync check ---

def _check_dest(media_type: str, dest: str) -> list[dict]:
    issues = []
    try:
        entries = os.listdir(dest)
    except OSError:
        return issues
    for name in entries:
        path = os.path.join(dest, name)
        if not (os.path.isdir(path) or os.path.islink(path)):
            continue
        if not db.get_by_dir_name(media_type, name):
            issues.append({"dir_name": name, "issue": "orphaned"})
    return issues


@app.get("/api/sync/check")
def sync_check():
    return {
        "movies": _check_dest("movie", MOVIES_DEST),
        "series": _check_dest("series", SERIES_DEST),
    }


@app.post("/api/sync/fix")
def sync_fix():
    removed = []
    errors = []
    for media_type, dest in [("movie", MOVIES_DEST), ("series", SERIES_DEST)]:
        for issue in _check_dest(media_type, dest):
            path = os.path.join(dest, issue["dir_name"])
            try:
                if os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                removed.append({"dir_name": issue["dir_name"], "type": media_type, "reason": issue["issue"]})
            except OSError as e:
                errors.append({"dir_name": issue["dir_name"], "error": str(e)})
    return {"removed": removed, "errors": errors}


# --- Scan control ---

@app.get("/api/scan/status")
def scan_status():
    return {
        **scanner.scan_state,
        "movie_count": db.count_by_type("movie"),
        "series_count": db.count_by_type("series"),
    }


@app.post("/api/scan/movies")
def scan_movies(full: bool = False):
    scanner.start_scan("movie", full=full, on_complete=_refresh_linked_files)
    return {"started": True, "type": "movie", "full": full}


@app.post("/api/scan/series")
def scan_series_route(full: bool = False):
    scanner.start_scan("series", full=full, on_complete=_refresh_linked_files)
    return {"started": True, "type": "series", "full": full}


@app.post("/api/scan/all")
def scan_all(full: bool = False):
    scanner.start_scan_all(full=full, on_complete=_refresh_linked_files)
    return {"started": True, "type": "all", "full": full}


# --- Schedule ---

class ScheduleConfig(BaseModel):
    enabled: bool = False
    frequency: str = "daily"
    hour: int = 3
    day_of_week: int = 0
    day_of_month: int = 1
    scan_type: str = "all"
    full: bool = False


@app.get("/api/schedule")
def get_schedule():
    return schedule_manager.get_schedule()


@app.post("/api/schedule")
def set_schedule(cfg: ScheduleConfig):
    return schedule_manager.set_schedule(cfg.model_dump())


# --- Backups ---

class BackupSettings(BaseModel):
    keep_n: int = 7
    schedule_enabled: bool = False
    schedule_frequency: str = "daily"
    schedule_hour: int = 2
    schedule_day_of_week: int = 0
    schedule_day_of_month: int = 1


@app.get("/api/backup/settings")
def get_backup_settings():
    return bk.get_settings()


@app.post("/api/backup/settings")
def set_backup_settings(s: BackupSettings):
    return bk.set_settings(s.model_dump())


@app.get("/api/backups")
def list_backups():
    return bk.list_backups()


@app.post("/api/backups")
def create_backup():
    return bk.create_backup()


@app.post("/api/backups/upload")
async def upload_backup(file: UploadFile = File(...)):
    data = await file.read()
    try:
        info = bk.save_upload(file.filename or "upload.db", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return info


@app.get("/api/backups/{filename}")
def download_backup(filename: str):
    path = bk.backup_path(filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Backup not found")
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@app.post("/api/backups/{filename}/restore")
def restore_backup(filename: str):
    ok = bk.restore_backup(filename)
    if not ok:
        raise HTTPException(404, "Backup not found or invalid")
    return {"restored": True}


@app.delete("/api/backups/{filename}")
def delete_backup(filename: str):
    ok = bk.delete_backup(filename)
    if not ok:
        raise HTTPException(404, "Backup not found")
    return {"deleted": True}


# --- Serve React frontend ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")
