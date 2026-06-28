import json
import logging
import os
import shutil
import sqlite3
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import database

logging.getLogger("apscheduler").setLevel(logging.WARNING)

_DB_PATH = database.DB_PATH
_DATA_DIR = os.path.dirname(_DB_PATH)
_BACKUP_DIR = os.path.join(_DATA_DIR, "backups")
_SETTINGS_PATH = os.path.join(_DATA_DIR, "backup_settings.json")

_DEFAULTS = {
    "keep_n": 7,
    "schedule_enabled": False,
    "schedule_frequency": "daily",
    "schedule_hour": 2,
    "schedule_day_of_week": 0,
    "schedule_day_of_month": 1,
}

_scheduler = BackgroundScheduler()
_scheduler.start()


def _load_settings() -> dict:
    try:
        with open(_SETTINGS_PATH) as f:
            return {**_DEFAULTS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def get_settings() -> dict:
    s = _load_settings()
    job = _scheduler.get_job("backup_job")
    s["next_run"] = job.next_run_time.isoformat() if job and job.next_run_time else None
    return s


def set_settings(updates: dict) -> dict:
    current = _load_settings()
    merged = {**current, **updates}
    merged["keep_n"] = max(1, int(merged["keep_n"]))
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(merged, f, indent=2)
    _apply_schedule(merged)
    return get_settings()


def _build_trigger(s: dict) -> CronTrigger:
    hour = int(s.get("schedule_hour", 2))
    freq = s.get("schedule_frequency", "daily")
    if freq == "weekly":
        return CronTrigger(day_of_week=int(s.get("schedule_day_of_week", 0)), hour=hour, minute=0)
    if freq == "monthly":
        return CronTrigger(day=int(s.get("schedule_day_of_month", 1)), hour=hour, minute=0)
    return CronTrigger(hour=hour, minute=0)


def _apply_schedule(s: dict):
    _scheduler.remove_all_jobs()
    if s.get("schedule_enabled"):
        _scheduler.add_job(
            create_backup,
            trigger=_build_trigger(s),
            id="backup_job",
            replace_existing=True,
        )


def init():
    _apply_schedule(_load_settings())


def list_backups() -> list[dict]:
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    items = []
    for name in os.listdir(_BACKUP_DIR):
        if not name.endswith(".db"):
            continue
        path = os.path.join(_BACKUP_DIR, name)
        stat = os.stat(path)
        items.append({"filename": name, "size": stat.st_size, "created_at": stat.st_mtime})
    return sorted(items, key=lambda x: x["created_at"], reverse=True)


def create_backup() -> dict:
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(_BACKUP_DIR, f"vodlink_{ts}.db")
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.close()
    except Exception:
        pass
    shutil.copy2(_DB_PATH, dest)
    _prune(_load_settings()["keep_n"])
    stat = os.stat(dest)
    return {"filename": os.path.basename(dest), "size": stat.st_size, "created_at": stat.st_mtime}


def _prune(keep_n: int):
    for b in list_backups()[keep_n:]:
        try:
            os.unlink(os.path.join(_BACKUP_DIR, b["filename"]))
        except OSError:
            pass


def delete_backup(filename: str) -> bool:
    path = _safe_path(filename)
    if not os.path.exists(path):
        return False
    os.unlink(path)
    return True


def restore_backup(filename: str) -> bool:
    path = _safe_path(filename)
    if not os.path.exists(path):
        return False
    try:
        conn = sqlite3.connect(path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
    except Exception:
        return False
    try:
        curr = sqlite3.connect(_DB_PATH)
        curr.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        curr.close()
    except Exception:
        pass
    shutil.copy2(path, _DB_PATH)
    return True


def save_upload(filename: str, data: bytes) -> dict:
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    if not data[:16].startswith(b"SQLite format 3"):
        raise ValueError("Not a valid SQLite database file")
    safe = os.path.basename(filename)
    if not safe.endswith(".db"):
        safe = safe + ".db"
    dest = os.path.join(_BACKUP_DIR, safe)
    with open(dest, "wb") as f:
        f.write(data)
    stat = os.stat(dest)
    return {"filename": safe, "size": stat.st_size, "created_at": stat.st_mtime}


def backup_path(filename: str) -> str:
    return _safe_path(filename)


def _safe_path(filename: str) -> str:
    return os.path.join(_BACKUP_DIR, os.path.basename(filename))
