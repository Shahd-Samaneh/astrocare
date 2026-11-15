"""SQLite storage (standard library sqlite3). One file: data/astrocare.db.

Every contract type has a table. Column names are the snake_case field names of
the Pydantic models in core/models.py; list/dict fields are stored as JSON text
and decoded automatically by the helpers below.

Typical use in a router:
    from server.core import db
    rows = db.query("readings", "metric = ?", ("heart_rate",), order_by="ts DESC", limit=50)
    db.insert("checkins", model.model_dump())
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from .config import db_path

# table -> {column: SQL type}. "JSON" columns are stored as TEXT and (de)serialized.
TABLES: dict[str, dict[str, str]] = {
    "readings": {
        "id": "TEXT PRIMARY KEY", "astronaut_id": "TEXT", "metric": "TEXT", "value": "REAL",
        "unit": "TEXT", "ts": "TEXT", "source": "TEXT", "quality": "TEXT",
    },
    "cabin_readings": {
        "id": "TEXT PRIMARY KEY", "metric": "TEXT", "value": "REAL", "unit": "TEXT",
        "ts": "TEXT", "source": "TEXT",
    },
    "sensors": {
        "id": "TEXT PRIMARY KEY", "name": "TEXT", "location": "TEXT", "metrics": "JSON",
        "status": "TEXT", "last_seen": "TEXT",
    },
    "profiles": {
        "id": "TEXT PRIMARY KEY", "name": "TEXT", "mission_day": "INTEGER", "allergies": "JSON",
        "current_meds": "JSON", "history": "JSON", "baseline": "JSON",
    },
    "sleep_sessions": {
        "id": "TEXT PRIMARY KEY", "start": "TEXT", "end": "TEXT", "duration_min": "INTEGER",
        "awakenings": "INTEGER", "self_quality": "INTEGER", "source": "TEXT",
    },
    "cognitive_tests": {
        "id": "TEXT PRIMARY KEY", "ts": "TEXT", "trials_ms": "JSON", "median_ms": "REAL",
        "lapses": "INTEGER", "false_starts": "INTEGER",
    },
    "checkins": {
        "id": "TEXT PRIMARY KEY", "ts": "TEXT", "mood": "INTEGER", "stress": "INTEGER",
        "note_private": "TEXT", "skipped": "BOOL",
    },
    "exercise_plans": {
        "id": "TEXT PRIMARY KEY", "day": "INTEGER", "type": "TEXT", "duration_min": "INTEGER",
        "equipment_id": "TEXT", "alternatives": "JSON",
    },
    "exercise_logs": {
        "id": "TEXT PRIMARY KEY", "plan_id": "TEXT", "ts": "TEXT", "status": "TEXT",
        "reason": "TEXT", "alternative_id": "TEXT",
    },
    "resources": {
        "id": "TEXT PRIMARY KEY", "kind": "TEXT", "name": "TEXT", "qty": "REAL", "unit": "TEXT",
        "expiry": "TEXT", "status": "TEXT", "contraindicated_allergies": "JSON",
    },
    "alerts": {
        "id": "TEXT PRIMARY KEY", "rule_id": "TEXT", "level": "TEXT", "ts": "TEXT", "title": "TEXT",
        "what_changed": "TEXT", "data_used": "JSON", "missing": "JSON", "possible_factors": "JSON",
        "next_steps": "JSON", "status": "TEXT", "sources": "JSON",
        # internal (not in the contract): lets the engine avoid duplicate open alerts
        "dedupe_key": "TEXT",
    },
    "relax_sessions": {
        "id": "TEXT PRIMARY KEY", "ts": "TEXT", "scene_id": "TEXT", "audio_mode": "TEXT",
        "duration_min": "INTEGER", "stress_before": "INTEGER", "stress_after": "INTEGER",
    },
    "reports": {
        "id": "TEXT PRIMARY KEY", "created_ts": "TEXT", "status": "TEXT", "sections": "JSON",
        "file_path": "TEXT",
    },
    "action_log": {
        "id": "TEXT PRIMARY KEY", "ts": "TEXT", "actor": "TEXT", "action": "TEXT", "ref_id": "TEXT",
    },
    # key/value store for app metadata (seed time, mission clock anchor, ...)
    "meta": {"key": "TEXT PRIMARY KEY", "value": "TEXT"},
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_readings_metric_ts ON readings(metric, ts)",
    "CREATE INDEX IF NOT EXISTS ix_cabin_metric_ts ON cabin_readings(metric, ts)",
    "CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status)",
]


def _json_cols(table: str) -> set[str]:
    return {c for c, t in TABLES[table].items() if t == "JSON"}


def _bool_cols(table: str) -> set[str]:
    return {c for c, t in TABLES[table].items() if t == "BOOL"}


def _sql_type(t: str) -> str:
    return {"JSON": "TEXT", "BOOL": "INTEGER"}.get(t, t)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create every table if missing. Called on startup."""
    with connect() as conn:
        for table, cols in TABLES.items():
            cols_sql = ", ".join(f'"{c}" {_sql_type(t)}' for c, t in cols.items())
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols_sql})')
        for stmt in INDEXES:
            conn.execute(stmt)


# Tables created by feature code (CREATE TABLE IF NOT EXISTS), not in TABLES. A reset empties
# them so a reseed gives a clean demo state (empty outbox items, default assistant permissions,
# no open simulated comm window). `assistant_chunks` (the reference index) is kept on purpose:
# rebuilding it needs Ollama.
FEATURE_TABLES_CLEARED_ON_RESET = (
    "report_items", "comms_windows",
    "assistant_permissions", "assistant_log",
    "daily_test_context", "daily_test_meta",
)


def reset_db() -> None:
    with connect() as conn:
        for table in TABLES:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in FEATURE_TABLES_CLEARED_ON_RESET:
            if table in existing:
                conn.execute(f'DELETE FROM "{table}"')  # keep the schema, drop the rows
    init_db()


# ---- (de)serialization ----------------------------------------------------
def _encode(table: str, row: dict[str, Any]) -> dict[str, Any]:
    cols = TABLES[table]
    jc = _json_cols(table)
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k not in cols:
            continue  # ignore extra fields
        out[k] = json.dumps(v) if k in jc and v is not None else v
    return out


def _decode(table: str, row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for c in _json_cols(table):
        if d.get(c) is not None:
            d[c] = json.loads(d[c])
    for c in _bool_cols(table):
        if d.get(c) is not None:
            d[c] = bool(d[c])
    return d


# ---- helpers -------------------------------------------------------------
def insert(table: str, row: dict[str, Any], *, replace: bool = False) -> None:
    insert_many(table, [row], replace=replace)


def insert_many(table: str, rows: Iterable[dict[str, Any]], *, replace: bool = False) -> int:
    rows = [_encode(table, r) for r in rows]
    if not rows:
        return 0
    present = set().union(*(r.keys() for r in rows))
    cols = [c for c in TABLES[table] if c in present]
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    col_sql = ", ".join(f'"{c}"' for c in cols)
    sql = f'{verb} INTO "{table}" ({col_sql}) VALUES ({", ".join("?" for _ in cols)})'
    with connect() as conn:
        conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
    return len(rows)


def query(
    table: str,
    where: str = "",
    params: tuple[Any, ...] = (),
    *,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql = f'SELECT * FROM "{table}"'
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with connect() as conn:
        return [_decode(table, r) for r in conn.execute(sql, params).fetchall()]


def get(table: str, id_: str) -> dict[str, Any] | None:
    rows = query(table, "id = ?", (id_,))
    return rows[0] if rows else None


def update(table: str, id_: str, fields: dict[str, Any]) -> None:
    enc = _encode(table, fields)
    if not enc:
        return
    sets = ", ".join(f'"{k}" = ?' for k in enc)
    with connect() as conn:
        conn.execute(f'UPDATE "{table}" SET {sets} WHERE id = ?', (*enc.values(), id_))


def count(table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
    sql = f'SELECT COUNT(*) FROM "{table}"' + (f" WHERE {where}" if where else "")
    with connect() as conn:
        return int(conn.execute(sql, params).fetchone()[0])


def new_id(prefix: str) -> str:
    """Short unique id, e.g. new_id('ci') -> 'ci-3f9a1c2b7e'."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def log_action(actor: str, action: str, ref_id: str | None = None) -> None:
    """Append to the action log (who did what, for the audit trail)."""
    from .config import iso, utcnow

    insert("action_log", {"id": new_id("act"), "ts": iso(utcnow()), "actor": actor, "action": action, "ref_id": ref_id})


def get_meta(key: str, default: str | None = None) -> str | None:
    with connect() as conn:
        row = conn.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
    return row[0] if row else default


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', (key, value))
