import json
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import scanner

logging.getLogger("apscheduler").setLevel(logging.WARNING)

_DATA_DIR = os.path.dirname(os.getenv("DB_PATH", "/app/data/vodlink.db"))
_SETTINGS_PATH = os.path.join(_DATA_DIR, "schedule.json")

_DEFAULTS = {
    "enabled": False,
    "frequency": "daily",
    "hour": 3,
    "day_of_week": 0,   # 0=Mon … 6=Sun
    "day_of_month": 1,
    "scan_type": "all",
    "full": False,
}

import os as _os
_tz = _os.getenv("TZ", "UTC")
_scheduler = BackgroundScheduler(timezone=_tz)
_scheduler.start()


def _load() -> dict:
    try:
        with open(_SETTINGS_PATH) as f:
            return {**_DEFAULTS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def _save(cfg: dict):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _build_trigger(cfg: dict) -> CronTrigger:
    hour = int(cfg.get("hour", 3))
    freq = cfg.get("frequency", "daily")
    if freq == "weekly":
        return CronTrigger(day_of_week=int(cfg.get("day_of_week", 0)), hour=hour, minute=0)
    if freq == "monthly":
        return CronTrigger(day=int(cfg.get("day_of_month", 1)), hour=hour, minute=0)
    return CronTrigger(hour=hour, minute=0)  # daily


def _run(cfg: dict):
    if scanner.scan_state["running"]:
        return
    t = cfg.get("scan_type", "all")
    full = cfg.get("full", False)
    if t == "all":
        scanner.start_scan_all(full=full)
    else:
        scanner.start_scan(t, full=full)


def _apply(cfg: dict):
    _scheduler.remove_all_jobs()
    if cfg.get("enabled"):
        _scheduler.add_job(
            lambda: _run(cfg),
            trigger=_build_trigger(cfg),
            id="scan_job",
            replace_existing=True,
        )


def get_schedule() -> dict:
    cfg = _load()
    # Include next run time if scheduled
    job = _scheduler.get_job("scan_job")
    cfg["next_run"] = job.next_run_time.isoformat() if job and job.next_run_time else None
    return cfg


def set_schedule(cfg: dict) -> dict:
    merged = {**_DEFAULTS, **cfg}
    _save(merged)
    _apply(merged)
    return get_schedule()


def init():
    _apply(_load())
