import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import database as db
import scanner
import schedule_manager
import backup as bk

APP_VERSION = os.getenv("APP_VERSION", "dev")

MOVIES_DEST = os.getenv("MOVIES_DEST", "/volume1/SSD/VOD/Movies")
SERIES_DEST = os.getenv("SERIES_DEST", "/volume1/SSD/VOD/Series")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    schedule_manager.init()
    bk.init()
    # Auto-trigger full scan for any type with no data in DB
    movies_count = db.count_by_type("movie")
    series_count = db.count_by_type("series")
    if movies_count == 0 and series_count == 0:
        scanner.start_scan_all(full=True)
    elif movies_count == 0:
        scanner.start_scan("movie", full=True)
    elif series_count == 0:
        scanner.start_scan("series", full=True)
    yield


app = FastAPI(lifespan=lifespan)


def _dest_path(media_type: str, dir_name: str) -> str:
    base = MOVIES_DEST if media_type == "movie" else SERIES_DEST
    return os.path.join(base, dir_name)


def _enrich(item: dict, media_type: str) -> dict:
    dp = _dest_path(media_type, item["dir_name"])
    return {**item, "linked": os.path.islink(dp)}


def _linked_dir_names(media_type: str) -> list[str]:
    dest = MOVIES_DEST if media_type == "movie" else SERIES_DEST
    try:
        return [d for d in os.listdir(dest) if os.path.islink(os.path.join(dest, d))]
    except OSError:
        return []


# --- Version ---

@app.get("/api/version")
def get_version():
    return {"version": APP_VERSION}


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


# --- Link / unlink movies ---

@app.post("/api/movies/{tmdb_id}/link")
def link_movie(tmdb_id: str):
    item = db.get_by_tmdb("movie", tmdb_id)
    if not item:
        raise HTTPException(404, "Movie not found")
    dp = _dest_path("movie", item["dir_name"])
    if os.path.islink(dp):
        return {"linked": True, "message": "Already linked"}
    try:
        os.symlink(item["source_path"], dp)
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"linked": True}


@app.delete("/api/movies/{tmdb_id}/link")
def unlink_movie(tmdb_id: str):
    item = db.get_by_tmdb("movie", tmdb_id)
    if not item:
        raise HTTPException(404, "Movie not found")
    dp = _dest_path("movie", item["dir_name"])
    if not os.path.islink(dp):
        return {"linked": False, "message": "Not linked"}
    try:
        os.unlink(dp)
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"linked": False}


# --- Link / unlink series ---

@app.post("/api/series/{tmdb_id}/link")
def link_series(tmdb_id: str):
    item = db.get_by_tmdb("series", tmdb_id)
    if not item:
        raise HTTPException(404, "Series not found")
    dp = _dest_path("series", item["dir_name"])
    if os.path.islink(dp):
        return {"linked": True, "message": "Already linked"}
    try:
        os.symlink(item["source_path"], dp)
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"linked": True}


@app.delete("/api/series/{tmdb_id}/link")
def unlink_series(tmdb_id: str):
    item = db.get_by_tmdb("series", tmdb_id)
    if not item:
        raise HTTPException(404, "Series not found")
    dp = _dest_path("series", item["dir_name"])
    if not os.path.islink(dp):
        return {"linked": False, "message": "Not linked"}
    try:
        os.unlink(dp)
    except OSError as e:
        raise HTTPException(500, str(e))
    return {"linked": False}


# --- Sync check ---

def _check_dest(media_type: str, dest: str) -> list[dict]:
    issues = []
    try:
        entries = os.listdir(dest)
    except OSError:
        return issues
    for name in entries:
        path = os.path.join(dest, name)
        is_link = os.path.islink(path)
        target = os.readlink(path) if is_link else None
        db_item = db.get_by_dir_name(media_type, name)

        if not is_link:
            issues.append({"dir_name": name, "issue": "real_dir", "target": None, "expected": db_item["source_path"] if db_item else None})
        elif not os.path.exists(path):
            issues.append({"dir_name": name, "issue": "broken_symlink", "target": target, "expected": db_item["source_path"] if db_item else None})
        elif not db_item:
            issues.append({"dir_name": name, "issue": "orphaned", "target": target, "expected": None})
        elif target != db_item["source_path"]:
            issues.append({"dir_name": name, "issue": "wrong_target", "target": target, "expected": db_item["source_path"]})
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
            if issue["issue"] == "real_dir":
                continue  # never auto-delete real directories
            path = os.path.join(dest, issue["dir_name"])
            try:
                os.unlink(path)
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
    scanner.start_scan("movie", full=full)
    return {"started": True, "type": "movie", "full": full}


@app.post("/api/scan/series")
def scan_series_route(full: bool = False):
    scanner.start_scan("series", full=full)
    return {"started": True, "type": "series", "full": full}


@app.post("/api/scan/all")
def scan_all(full: bool = False):
    scanner.start_scan_all(full=full)
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
# html=True makes StaticFiles return index.html for unknown paths (SPA routing)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
