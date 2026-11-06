"""SQLite storage: the source of truth for the index.

The database is disposable (rebuildable from the sources) but the enrichment
cache inside it is valuable, because Gemini's free tier has a daily quota. The
cache is therefore exported to data/enrichment-cache.json and re-imported when a
fresh database is created in CI.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT,
    sources TEXT,
    kind TEXT,
    name TEXT,
    url TEXT,
    homepage TEXT,
    description TEXT,
    license TEXT,
    license_open INTEGER DEFAULT 0,
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    open_issues INTEGER DEFAULT 0,
    language TEXT,
    topics TEXT,
    pushed_at TEXT,
    created_at TEXT,
    archived INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    discussion_url TEXT,
    category TEXT,
    tags TEXT,
    self_hostable INTEGER DEFAULT 0,
    maturity TEXT,
    target_user TEXT,
    difficulty INTEGER,
    summary TEXT,
    free_tier_notes TEXT,
    score REAL DEFAULT 0,
    score_parts TEXT,
    raw TEXT,
    content_hash TEXT,
    enriched_at TEXT,
    enrichment_model TEXT,
    enrichment_prompt_version TEXT,
    first_seen TEXT,
    last_seen TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_enriched ON items(enriched_at);

CREATE TABLE IF NOT EXISTS enrichment_cache (
    content_hash TEXT,
    model TEXT,
    prompt_version TEXT,
    payload TEXT,
    created_at TEXT,
    PRIMARY KEY (content_hash, model, prompt_version)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    collected INTEGER,
    inserted INTEGER,
    updated INTEGER,
    enriched INTEGER,
    notes TEXT
);
"""

JSON_FIELDS = ("sources", "topics", "tags", "score_parts", "raw")

# Every column that can be written by an item dict, in schema order.
FIELDS: Tuple[str, ...] = (
    "source", "sources", "kind", "name", "url", "homepage", "description",
    "license", "license_open", "stars", "forks", "open_issues", "language",
    "topics", "pushed_at", "created_at", "archived", "points", "comments",
    "discussion_url", "category", "tags", "self_hostable", "maturity",
    "target_user", "difficulty", "summary", "free_tier_notes", "score",
    "score_parts", "raw", "content_hash", "enriched_at", "enrichment_model",
    "enrichment_prompt_version",
)


def utcnow() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    target = Path(path) if path else config.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def content_hash(item: Dict[str, Any]) -> str:
    parts = [
        str(item.get("name") or ""),
        str(item.get("description") or ""),
        ",".join(sorted(item.get("topics") or [])),
        str(item.get("url") or ""),
        str(item.get("stars") or 0),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _encode(value: Any) -> Any:
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _decode_row(row: sqlite3.Row) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if key in JSON_FIELDS and isinstance(value, str) and value:
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = None
        if key in ("license_open", "self_hostable", "archived") and value is not None:
            value = bool(value)
        item[key] = value
    return item


def upsert_items(conn: sqlite3.Connection, items: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    """Insert or merge items. Returns (inserted, updated)."""
    inserted = 0
    updated = 0
    now = utcnow()
    placeholders = ", ".join("?" for _ in FIELDS)
    updates = ", ".join("%s=excluded.%s" % (field, field) for field in FIELDS if field != "id")
    sql = (
        "INSERT INTO items (id, %s, first_seen, last_seen) VALUES (?, %s, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET %s, last_seen=excluded.last_seen"
        % (", ".join(FIELDS), placeholders, updates)
    )
    for item in items:
        item_id = item.get("id")
        if not item_id:
            continue
        exists = conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone()
        values = [item_id]
        for field in FIELDS:
            values.append(_encode(item.get(field)))
        values.extend([now, now])
        conn.execute(sql, values)
        if exists:
            updated += 1
        else:
            inserted += 1
    conn.commit()
    return inserted, updated


def all_items(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM items ORDER BY score DESC, stars DESC").fetchall()
    return [_decode_row(row) for row in rows]


def get_item(conn: sqlite3.Connection, item_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _decode_row(row) if row else None


def items_needing_enrichment(
    conn: sqlite3.Connection,
    model: str,
    prompt_version: str,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE enriched_at IS NULL
           OR enrichment_model IS NOT ? 
           OR enrichment_prompt_version IS NOT ?
        ORDER BY (stars IS NULL) ASC, stars DESC
        LIMIT ?
        """,
        (model, prompt_version, int(limit)),
    ).fetchall()
    return [_decode_row(row) for row in rows]


def apply_enrichment(conn: sqlite3.Connection, item_id: str, payload: Dict[str, Any]) -> None:
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]
    conn.execute(
        """
        UPDATE items SET
            summary = COALESCE(NULLIF(?, ''), summary),
            category = COALESCE(NULLIF(?, ''), category),
            tags = ?,
            self_hostable = COALESCE(?, self_hostable),
            maturity = COALESCE(NULLIF(?, ''), maturity),
            target_user = COALESCE(NULLIF(?, ''), target_user),
            difficulty = COALESCE(?, difficulty),
            free_tier_notes = COALESCE(NULLIF(?, ''), free_tier_notes),
            enriched_at = ?,
            enrichment_model = ?,
            enrichment_prompt_version = ?
        WHERE id = ?
        """,
        (
            payload.get("summary") or "",
            payload.get("category") or "",
            json.dumps(tags, ensure_ascii=False),
            None if payload.get("self_hostable") is None else (1 if payload.get("self_hostable") else 0),
            payload.get("maturity") or "",
            payload.get("target_user") or "",
            payload.get("difficulty"),
            payload.get("free_tier_notes") or "",
            utcnow(),
            payload.get("_model") or "",
            payload.get("_prompt_version") or "",
            item_id,
        ),
    )


def mark_enrichment_attempt(conn: sqlite3.Connection, item_id: str, model: str, prompt_version: str) -> None:
    """Record an attempt so a failing item is not retried forever in one run."""
    conn.execute(
        "UPDATE items SET enrichment_model = ?, enrichment_prompt_version = ?, "
        "enriched_at = COALESCE(enriched_at, ?) WHERE id = ?",
        (model, prompt_version, utcnow(), item_id),
    )


def commit(conn: sqlite3.Connection) -> None:
    conn.commit()


# --- enrichment cache -------------------------------------------------------

def cache_put(
    conn: sqlite3.Connection,
    item_hash: str,
    model: str,
    prompt_version: str,
    payload: Dict[str, Any],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO enrichment_cache (content_hash, model, prompt_version, payload, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (item_hash, model, prompt_version, json.dumps(payload, ensure_ascii=False), utcnow()),
    )


def cache_get(
    conn: sqlite3.Connection,
    item_hash: str,
    model: str,
    prompt_version: str,
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT payload FROM enrichment_cache WHERE content_hash = ? AND model = ? AND prompt_version = ?",
        (item_hash, model, prompt_version),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        return None


def export_cache_json(conn: sqlite3.Connection, path: Optional[Path] = None) -> Path:
    target = Path(path) if path else config.cache_json_path()
    rows = conn.execute(
        "SELECT content_hash, model, prompt_version, payload, created_at FROM enrichment_cache"
    ).fetchall()
    entries = [dict(row) for row in rows]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"version": 1, "entries": entries}, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )
    return target


def import_cache_json(conn: sqlite3.Connection, path: Optional[Path] = None) -> int:
    source = Path(path) if path else config.cache_json_path()
    if not source.exists():
        return 0
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return 0
    count = 0
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("content_hash"):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO enrichment_cache (content_hash, model, prompt_version, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                entry.get("content_hash"),
                entry.get("model") or "",
                entry.get("prompt_version") or "",
                entry.get("payload") or "{}",
                entry.get("created_at") or utcnow(),
            ),
        )
        count += 1
    conn.commit()
    return count


# --- runs -------------------------------------------------------------------

def record_run(conn: sqlite3.Connection, started_at: str, stats: Dict[str, Any], notes: str = "") -> None:
    conn.execute(
        "INSERT INTO runs (started_at, finished_at, collected, inserted, updated, enriched, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            started_at,
            utcnow(),
            stats.get("collected"),
            stats.get("inserted"),
            stats.get("updated"),
            stats.get("enriched"),
            notes,
        ),
    )
    conn.commit()


def last_run(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None
