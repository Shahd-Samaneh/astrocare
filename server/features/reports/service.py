"""Report items and the comms window (owner: Noura).

Other features call these from Python or through the HTTP API:

    from server.features.reports.service import add_report_item, get_comms_status
    add_report_item("alert", "R-FAT-01", "Possible fatigue pattern", "monitoring", ref_id=alert_id)

Our tables are created here (CREATE TABLE IF NOT EXISTS), so server/core/db.py is untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from server.core import db
from server.core.config import app_config, iso, parse_ts, utcnow
from server.core.status import next_comm_window

ReportItemKind = Literal["alert", "cmo_question", "note"]
SourceFeature = Literal["monitoring", "daily", "assistant", "relax"]

_TABLES = {
    "report_items": (
        "id TEXT PRIMARY KEY, kind TEXT, ref_id TEXT, title TEXT, text TEXT, "
        "source_feature TEXT, created_ts TEXT, report_id TEXT"
    ),
    # One row per opened window (simulated for the demo) and the reports it sent.
    "comms_windows": "id TEXT PRIMARY KEY, opened_ts TEXT, duration_min INTEGER, simulated INTEGER, report_ids TEXT",
}


def ensure_tables() -> None:
    with db.connect() as conn:
        for name, cols in _TABLES.items():
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{name}" ({cols})')


def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_tables()
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _exec(sql: str, params: tuple[Any, ...] = ()) -> None:
    ensure_tables()
    with db.connect() as conn:
        conn.execute(sql, params)


# ---- report items ----------------------------------------------------------------
def add_report_item(kind: str, title: str, text: str, source_feature: str,
                    ref_id: Optional[str] = None) -> dict[str, Any]:
    """Add an item to the next report. Returns the item (snake_case keys)."""
    item = {
        "id": db.new_id("item"), "kind": kind, "ref_id": ref_id, "title": title, "text": text,
        "source_feature": source_feature, "created_ts": iso(utcnow()), "report_id": None,
    }
    _exec(
        "INSERT INTO report_items (id, kind, ref_id, title, text, source_feature, created_ts, report_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(item.values()),
    )
    db.log_action("crew", f"report_item:{kind}", item["id"])
    return item


def list_report_items(pending_only: bool = False) -> list[dict[str, Any]]:
    """pending = not yet included in a report."""
    where = " WHERE report_id IS NULL" if pending_only else ""
    return _rows(f"SELECT * FROM report_items{where} ORDER BY created_ts DESC")


def get_report_item(item_id: str) -> Optional[dict[str, Any]]:
    rows = _rows("SELECT * FROM report_items WHERE id = ?", (item_id,))
    return rows[0] if rows else None


def delete_report_item(item_id: str) -> bool:
    if not get_report_item(item_id):
        return False
    _exec("DELETE FROM report_items WHERE id = ?", (item_id,))
    return True


# ---- comms window ------------------------------------------------------------------
def _window_minutes() -> int:
    return int(app_config()["comms"]["window"]["duration_minutes"])


def _last_window() -> Optional[dict[str, Any]]:
    rows = _rows("SELECT * FROM comms_windows ORDER BY opened_ts DESC LIMIT 1")
    return rows[0] if rows else None


def get_comms_status(now: Optional[datetime] = None) -> dict[str, Any]:
    """Same shape as GET /api/comms (snake_case).

    The schedule is NOT duplicated here: it comes from config/app.yaml through
    core/status.next_comm_window(). A simulated window stays open for its duration.
    """
    now = now or utcnow()
    dur = _window_minutes()
    next_ts = next_comm_window(now)
    start = parse_ts(next_ts)
    scheduled_open = start <= now <= start + timedelta(minutes=dur)

    last = _last_window()
    simulated_open = False
    if last and last["simulated"]:
        opened = parse_ts(last["opened_ts"])
        simulated_open = opened <= now <= opened + timedelta(minutes=int(last["duration_min"]))

    return {
        "connected": scheduled_open or simulated_open,
        "simulated_window": simulated_open,
        "next_window_ts": next_ts,
        "window_duration_min": dur,
        "queued_count": db.count("reports", "status = 'queued'"),
        "signal_delay_sec": int(app_config()["comms"]["signal_delay_sec"]),
        "last_window_ts": last["opened_ts"] if last else None,
    }


def simulate_window(now: Optional[datetime] = None) -> dict[str, Any]:
    """Demo only: open a comm window now. Every queued report becomes sent."""
    now = now or utcnow()
    queued = db.query("reports", "status = 'queued'", order_by="created_ts")
    for rep in queued:
        db.update("reports", rep["id"], {"status": "sent"})
    sent_ids = [r["id"] for r in queued]
    win_id = db.new_id("win")
    _exec(
        "INSERT INTO comms_windows (id, opened_ts, duration_min, simulated, report_ids) VALUES (?, ?, ?, ?, ?)",
        (win_id, iso(now), _window_minutes(), 1, json.dumps(sent_ids)),
    )
    db.log_action("system", "comms_window_simulated", win_id)
    return {"window_id": win_id, "opened_ts": iso(now), "sent_report_ids": sent_ids}


def sent_ts_by_report() -> dict[str, str]:
    """report id -> when it was sent (from the window log). Used by the outbox screen."""
    out: dict[str, str] = {}
    for w in _rows("SELECT opened_ts, report_ids FROM comms_windows ORDER BY opened_ts"):
        for rid in json.loads(w["report_ids"] or "[]"):
            out[rid] = w["opened_ts"]
    return out