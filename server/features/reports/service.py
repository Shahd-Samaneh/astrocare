"""Report items: "Add to report" (owner: Noura).

Other features call this from Python or through POST /api/reports/items:

    from server.features.reports.service import add_report_item
    add_report_item("alert", "R-FAT-01", "Possible fatigue pattern", "monitoring", ref_id=alert_id)

Our tables are created here (CREATE TABLE IF NOT EXISTS), so server/core/db.py is untouched.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from server.core import db
from server.core.config import iso, utcnow

ReportItemKind = Literal["alert", "cmo_question", "note"]
SourceFeature = Literal["monitoring", "daily", "assistant", "relax"]

_TABLES = {
    "report_items": (
        "id TEXT PRIMARY KEY, kind TEXT, ref_id TEXT, title TEXT, text TEXT, "
        "source_feature TEXT, created_ts TEXT, report_id TEXT"
    ),
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