import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/app/data/vodlink.db")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    tmdb_id TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    genres TEXT,
    rating REAL,
    thumb_url TEXT,
    source_path TEXT NOT NULL,
    dir_name TEXT NOT NULL,
    dir_mtime REAL NOT NULL,
    scanned_at REAL NOT NULL,
    UNIQUE(type, tmdb_id)
)
"""

CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_media_type_title ON media(type, title)"


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(CREATE_TABLE)
        conn.execute(CREATE_INDEX)
        conn.commit()


def upsert_media_batch(entries: list[dict]):
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO media
               (type, tmdb_id, title, year, genres, rating, thumb_url,
                source_path, dir_name, dir_mtime, scanned_at)
               VALUES (:type, :tmdb_id, :title, :year, :genres, :rating, :thumb_url,
                       :source_path, :dir_name, :dir_mtime, :scanned_at)
               ON CONFLICT(type, tmdb_id) DO UPDATE SET
                 title=excluded.title,
                 year=excluded.year,
                 genres=excluded.genres,
                 rating=excluded.rating,
                 thumb_url=excluded.thumb_url,
                 source_path=excluded.source_path,
                 dir_name=excluded.dir_name,
                 dir_mtime=excluded.dir_mtime,
                 scanned_at=excluded.scanned_at""",
            entries,
        )
        conn.commit()


def delete_by_paths(paths: list[str]):
    with get_conn() as conn:
        conn.executemany(
            "DELETE FROM media WHERE source_path = ?", [(p,) for p in paths]
        )
        conn.commit()


def get_all_source_paths(media_type: str) -> dict[str, float]:
    """Returns {source_path: dir_mtime} for change detection."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source_path, dir_mtime FROM media WHERE type = ?", (media_type,)
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def get_genres(media_type: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT genres FROM media WHERE type=? AND genres != ''", (media_type,)
        ).fetchall()
    genres: set[str] = set()
    for row in rows:
        for g in row[0].split(","):
            g = g.strip()
            if g:
                genres.add(g)
    return sorted(genres)


def _order_clause(sort_by: str, sort_dir: str = "asc") -> str:
    col = {"year": "year", "rating": "rating"}.get(sort_by, "title")
    return f"{col} {'DESC' if sort_dir == 'desc' else 'ASC'}"


def search_media(
    media_type: str, query: str, page: int, limit: int, genre: str = "", sort_by: str = "title", sort_dir: str = "asc"
) -> tuple[list[dict], int]:
    offset = (page - 1) * limit
    pattern = f"%{query}%" if query else "%"
    conditions = ["type = ?", "title LIKE ?"]
    params: list = [media_type, pattern]
    if genre:
        conditions.append("(',' || genres || ',') LIKE ?")
        params.append(f"%,{genre},%")
    where = " AND ".join(conditions)
    order = _order_clause(sort_by, sort_dir)
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM media WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM media WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def search_media_by_dir_names(
    media_type: str, dir_names: list[str], query: str, page: int, limit: int,
    genre: str = "", sort_by: str = "title", sort_dir: str = "asc"
) -> tuple[list[dict], int]:
    if not dir_names:
        return [], 0
    offset = (page - 1) * limit
    pattern = f"%{query}%" if query else "%"
    placeholders = ",".join("?" * len(dir_names))
    conditions = [f"type=?", f"dir_name IN ({placeholders})", "title LIKE ?"]
    params: list = [media_type, *dir_names, pattern]
    if genre:
        conditions.append("(',' || genres || ',') LIKE ?")
        params.append(f"%,{genre},%")
    where = " AND ".join(conditions)
    order = _order_clause(sort_by, sort_dir)
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM media WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM media WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def get_by_dir_name(media_type: str, dir_name: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM media WHERE type = ? AND dir_name = ?",
            (media_type, dir_name),
        ).fetchone()
    return dict(row) if row else None


def get_by_tmdb(media_type: str, tmdb_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM media WHERE type = ? AND tmdb_id = ?",
            (media_type, tmdb_id),
        ).fetchone()
    return dict(row) if row else None


def count_by_type(media_type: str) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM media WHERE type = ?", (media_type,)
        ).fetchone()[0]
