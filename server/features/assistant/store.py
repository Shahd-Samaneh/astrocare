"""SQLite tables owned by the assistant: assistant_chunks, assistant_log, assistant_permissions.

They are created here (not in core/db.TABLES) so the assistant doesn't edit core.
Every function calls ensure_tables() first, so it works on a fresh or reset DB.
"""
from __future__ import annotations

import json
from typing import Any

from server.core import db
from server.core.config import iso, utcnow

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS assistant_chunks (
        id TEXT PRIMARY KEY,          -- source_id + chunk index
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        content_hash TEXT NOT NULL,   -- sha1 of text + embed model: skip re-embedding unchanged chunks
        embed_model TEXT NOT NULL,
        embedding TEXT NOT NULL       -- JSON list of floats
    )""",
    "CREATE INDEX IF NOT EXISTS ix_assistant_chunks_source ON assistant_chunks(source_id)",
    """CREATE TABLE IF NOT EXISTS assistant_log (
        id TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        question TEXT NOT NULL,
        latency_ms INTEGER NOT NULL,
        mode TEXT NOT NULL,
        refused INTEGER NOT NULL,
        refusal_reason TEXT,
        eval_count INTEGER,           -- tokens generated (Ollama), for measured tokens/s
        eval_duration_ns INTEGER,
        first_token_ms INTEGER,       -- time to the first streamed token
        model TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS assistant_permissions (
        key TEXT PRIMARY KEY,         -- 'current'
        value TEXT NOT NULL           -- JSON
    )""",
]


# columns added after the first version: added to existing databases on the fly
_ADDED_COLUMNS = {"assistant_log": {"first_token_ms": "INTEGER", "model": "TEXT"}}


def ensure_tables() -> None:
    with db.connect() as conn:
        for stmt in _SCHEMA:
            conn.execute(stmt)
        for table, cols in _ADDED_COLUMNS.items():
            have = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            for col, sql_type in cols.items():
                if col not in have:
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {sql_type}')


# ---- permissions ------------------------------------------------------------
def load_permissions() -> dict[str, Any] | None:
    ensure_tables()
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM assistant_permissions WHERE key = 'current'").fetchone()
    return json.loads(row[0]) if row else None


def save_permissions(value: dict[str, Any]) -> None:
    ensure_tables()
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO assistant_permissions (key, value) VALUES ('current', ?)",
            (json.dumps(value),),
        )


# ---- log --------------------------------------------------------------------
def log_answer(
    question: str,
    latency_ms: int,
    mode: str,
    refused: bool,
    refusal_reason: str | None = None,
    eval_count: int | None = None,
    eval_duration_ns: int | None = None,
    first_token_ms: int | None = None,
    model: str | None = None,
) -> None:
    ensure_tables()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO assistant_log (id, ts, question, latency_ms, mode, refused, refusal_reason,"
            " eval_count, eval_duration_ns, first_token_ms, model) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.new_id("alog"), iso(utcnow()), question, int(latency_ms), mode, int(refused),
             refusal_reason, eval_count, eval_duration_ns, first_token_ms, model),
        )


def log_rows(limit: int = 200) -> list[dict[str, Any]]:
    ensure_tables()
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM assistant_log ORDER BY rowid DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(r) for r in rows]


# ---- chunks -----------------------------------------------------------------
def all_chunks() -> list[dict[str, Any]]:
    ensure_tables()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, source_id, title, url, chunk_index, text, content_hash, embed_model, embedding"
            " FROM assistant_chunks ORDER BY source_id, chunk_index"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["embedding"] = json.loads(d["embedding"])
        out.append(d)
    return out


def chunk_count() -> int:
    ensure_tables()
    with db.connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM assistant_chunks").fetchone()[0])


def source_meta() -> dict[str, tuple[str, str | None]]:
    """source_id -> (title, url) of every indexed reference."""
    ensure_tables()
    with db.connect() as conn:
        rows = conn.execute("SELECT DISTINCT source_id, title, url FROM assistant_chunks").fetchall()
    return {r["source_id"]: (r["title"], r["url"]) for r in rows}
