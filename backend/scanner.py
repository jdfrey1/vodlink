import os
import time
import threading
import xml.etree.ElementTree as ET
import database as db

_VOD_SRC = os.getenv("VOD_SRC", "/vod/src")
MOVIES_SRC = os.path.join(_VOD_SRC, "Movies")
SERIES_SRC = os.path.join(_VOD_SRC, "Series")

scan_state: dict = {
    "running": False,
    "current_type": None,
    "progress": 0,
    "total": 0,
    "last_scan_movies": None,
    "last_scan_series": None,
    "error": None,
}
_lock = threading.Lock()


def parse_nfo(nfo_path: str) -> dict:
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        genres = [g.text for g in root.findall("genre") if g.text]
        thumb = root.find("thumb")
        return {
            "title": root.findtext("title") or "",
            "year": int(root.findtext("year") or 0),
            "genres": ",".join(genres),
            "rating": float(root.findtext("rating") or 0),
            "tmdb_id": root.findtext("tmdbid") or "",
            "thumb_url": (thumb.text if thumb is not None else "") or "",
        }
    except Exception:
        return {}


def _find_nfo(dir_path: str, media_type: str) -> str | None:
    if media_type == "series":
        p = os.path.join(dir_path, "tvshow.nfo")
        return p if os.path.exists(p) else None

    # Movie: dir name is "Title (Year) {tmdb-ID}" — find matching .nfo
    dir_base = os.path.basename(dir_path)
    name_part = dir_base.split(" {")[0] if " {" in dir_base else dir_base
    p = os.path.join(dir_path, name_part + ".nfo")
    if os.path.exists(p):
        return p

    # Fallback: any top-level .nfo that isn't an episode file
    try:
        nfos = [
            f for f in os.listdir(dir_path)
            if f.endswith(".nfo") and not f[0].isdigit()
        ]
        return os.path.join(dir_path, nfos[0]) if nfos else None
    except OSError:
        return None


def _scan(media_type: str, full: bool = False):
    src = MOVIES_SRC if media_type == "movie" else SERIES_SRC

    with _lock:
        if scan_state["running"]:
            return
        scan_state.update(
            running=True,
            current_type=media_type,
            progress=0,
            total=0,
            error=None,
        )

    try:
        existing = {} if full else db.get_all_source_paths(media_type)

        try:
            entries = sorted(os.listdir(src))
        except OSError as e:
            scan_state["error"] = str(e)
            return

        dirs = [
            os.path.join(src, d) for d in entries
            if os.path.isdir(os.path.join(src, d))
        ]
        scan_state["total"] = len(dirs)
        processed: set[str] = set()
        to_upsert: list[dict] = []

        for i, dir_path in enumerate(dirs):
            scan_state["progress"] = i + 1
            try:
                mtime = os.stat(dir_path).st_mtime
            except OSError:
                continue

            processed.add(dir_path)

            # Skip unchanged entries (mtime check)
            if not full and dir_path in existing and existing[dir_path] == mtime:
                continue

            nfo_path = _find_nfo(dir_path, media_type)
            if not nfo_path:
                continue

            parsed = parse_nfo(nfo_path)
            if not parsed.get("tmdb_id") or not parsed.get("title"):
                continue

            to_upsert.append({
                "type": media_type,
                **parsed,
                "source_path": dir_path,
                "dir_name": os.path.basename(dir_path),
                "dir_mtime": mtime,
                "scanned_at": time.time(),
            })

            if len(to_upsert) >= 500:
                db.upsert_media_batch(to_upsert)
                to_upsert.clear()

        if to_upsert:
            db.upsert_media_batch(to_upsert)

        # Remove DB rows for directories that no longer exist
        removed = [p for p in existing if p not in processed]
        if removed:
            db.delete_by_paths(removed)

        key = "last_scan_movies" if media_type == "movie" else "last_scan_series"
        scan_state[key] = time.time()

    except Exception as e:
        scan_state["error"] = str(e)
    finally:
        scan_state["running"] = False
        scan_state["current_type"] = None


def start_scan(media_type: str, full: bool = False, on_complete=None):
    def run():
        _scan(media_type, full)
        if on_complete:
            on_complete(media_type)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def start_scan_all(full: bool = False, on_complete=None):
    def _all():
        _scan("movie", full)
        if on_complete:
            on_complete("movie")
        _scan("series", full)
        if on_complete:
            on_complete("series")

    t = threading.Thread(target=_all, daemon=True)
    t.start()
    return t
