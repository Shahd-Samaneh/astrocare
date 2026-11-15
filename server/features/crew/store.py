# Owner: Shahd
"""Crew emergencies: the Watch -> emergency -> acknowledged -> resolved state machine.

One row per R-LOC-01 alert (table `crew_emergencies`, created here). Every step is appended
to the row's timeline and written to the action log.

    watch       R-LOC-01 fired. "Are you OK?" is on the crew member's screen, countdown running.
      |-- "I'm OK" in time        -> resolved (outcome 'responded'), alert closed
      '-- deadline passed         -> emergency (red banner, Earth report item if the API takes it)
    emergency   CMO / Commander acknowledge, then resolve with an outcome.

The state moves forward lazily in `sync(now)`: every read (the app polls about once a second
while a watch is open) opens watches for new R-LOC-01 alerts and escalates the ones whose
deadline has passed. All functions take `now`, so tests use a fake clock.

Wrist motion samples live in `crew_motion` (the shared Metric type has no motion metric;
see docs/loc-notes.md). Both tables are emptied when the database is reseeded: we keep the
`seeded_at` value we last saw in `meta` and wipe our rows when it changes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, get_args

from server.core import db
from server.core.config import app_config, iso, parse_ts, utcnow

from .thresholds import loc_threshold

log = logging.getLogger("astrocare.crew")

RULE_ID = "R-LOC-01"
SEED_MARKER_KEY = "crew_seed_marker"
REPORTS_PROPOSAL = "docs/proposals/loc.md"
REPORT_PENDING_NOTE = "will be queued when reporting is available"

Outcome = str  # 'responded' | 'sensor_issue' | 'medical_event' | 'other'
OUTCOME_TEXT = {
    "responded": "Crew member responded",
    "sensor_issue": "Sensor issue",
    "medical_event": "Medical event",
    "other": "Other",
}
ROLE_TEXT = {"cmo": "CMO", "commander": "Commander"}

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS crew_emergencies (
        id TEXT PRIMARY KEY, alert_id TEXT UNIQUE, astronaut_id TEXT, crew_name TEXT, status TEXT,
        detected_ts TEXT, opened_ts TEXT, deadline_ts TEXT, responded_ts TEXT, escalated_ts TEXT,
        ack_cmo_ts TEXT, ack_commander_ts TEXT, resolved_ts TEXT, outcome TEXT, note TEXT,
        signals TEXT, missing TEXT, timeline TEXT, report_item_id TEXT, report_note TEXT)""",
    """CREATE TABLE IF NOT EXISTS crew_motion (
        id TEXT PRIMARY KEY, astronaut_id TEXT, sensor_id TEXT, ts TEXT, value_g REAL,
        quality TEXT, source TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_crew_motion_ts ON crew_motion(astronaut_id, ts)",
)
_JSON_COLS = ("signals", "missing", "timeline")


def clock() -> datetime:
    """Current time. Tests replace it (monkeypatch) to move time forward."""
    return utcnow()


def crew_member() -> tuple[str, str]:
    crew = app_config().get("crew", {})
    return str(crew.get("astronaut_id", "c2")), str(crew.get("name", "Crew Member 2"))


def demo_enabled() -> bool:
    return bool(app_config().get("demo", False))


# ---- tables ---------------------------------------------------------------------------
def ensure_tables() -> None:
    with db.connect() as conn:
        for stmt in _SCHEMA:
            conn.execute(stmt)
    seeded = db.get_meta("seeded_at")
    if seeded is not None and db.get_meta(SEED_MARKER_KEY) != seeded:
        # A (re)seed happened since we last looked: no watch, emergency or demo motion survives it.
        with db.connect() as conn:
            conn.execute("DELETE FROM crew_emergencies")
            conn.execute("DELETE FROM crew_motion")
        db.set_meta(SEED_MARKER_KEY, seeded)


def _decode(row: Any) -> dict[str, Any]:
    d = dict(row)
    for c in _JSON_COLS:
        d[c] = json.loads(d[c]) if d.get(c) else []
    return d


def _rows(where: str = "", params: tuple = (), order: str = "detected_ts DESC", limit: int | None = None):
    sql = "SELECT * FROM crew_emergencies" + (f" WHERE {where}" if where else "") + f" ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with db.connect() as conn:
        return [_decode(r) for r in conn.execute(sql, params).fetchall()]


def get(em_id: str) -> Optional[dict[str, Any]]:
    rows = _rows("id = ?", (em_id,))
    return rows[0] if rows else None


def _save(em: dict[str, Any]) -> None:
    row = {k: (json.dumps(v) if k in _JSON_COLS else v) for k, v in em.items()}
    cols = list(row)
    with db.connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO crew_emergencies ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            tuple(row[c] for c in cols),
        )


def _step(em: dict[str, Any], ts: datetime | str, step: str, actor: str, text: str) -> None:
    em["timeline"].append({"ts": ts if isinstance(ts, str) else iso(ts), "step": step, "actor": actor, "text": text})
    db.log_action(actor, f"crew_loc:{step}", em["id"])


def _set_alert_status(alert_id: str, status: str) -> None:
    if db.get("alerts", alert_id):
        db.update("alerts", alert_id, {"status": status})


# ---- wrist motion ---------------------------------------------------------------------
def add_motion(samples: list[dict[str, Any]]) -> None:
    ensure_tables()
    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO crew_motion (id, astronaut_id, sensor_id, ts, value_g, quality, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(s["id"], s["astronaut_id"], s["sensor_id"], s["ts"], s["value_g"], s["quality"], s["source"]) for s in samples],
        )


def motion_samples(astronaut_id: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """Wrist motion samples, oldest first. Read-only: [] if the table doesn't exist yet."""
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM crew_motion WHERE astronaut_id = ? AND ts >= ? AND ts <= ? ORDER BY ts",
                (astronaut_id, iso(since), iso(until)),
            ).fetchall()
    except Exception:  # table not created yet
        return []
    return [dict(r) for r in rows]


# ---- Earth report outbox ----------------------------------------------------------------
def _reports_accept_crew() -> bool:
    """True once the reports API accepts sourceFeature 'crew' (Noura's file; proposal in docs/proposals/loc.md)."""
    try:
        from server.features.reports.router import ReportItem, ReportItemIn
    except Exception:
        return False
    return all("crew" in get_args(m.model_fields["source_feature"].annotation) for m in (ReportItemIn, ReportItem))


def _queue_report_item(em: dict[str, Any], now: datetime) -> None:
    if not _reports_accept_crew():
        # The card only says it will be queued; the technical reason goes to the action log (and docs).
        em["report_note"] = REPORT_PENDING_NOTE
        db.log_action(
            "system",
            "crew_loc:report_skipped: reports API does not accept sourceFeature 'crew' yet "
            f"(see {REPORTS_PROPOSAL})",
            em["id"],
        )
        return
    from server.features.reports import service

    signals = "; ".join(f"{s['label']} at {s['ts']}" for s in em["signals"]) or "see alert"
    item = service.add_report_item(
        "note",
        f"Emergency: possible loss of consciousness, {em['crew_name']}",
        f"R-LOC-01 at {em['detected_ts']}. Signals: {signals}. No response to \"Are you OK?\" within "
        f"{loc_threshold('response_seconds')} s, escalated to CMO and Commander at {em['escalated_ts']}. "
        "Unconfirmed: not a diagnosis.",
        "crew",
        em["alert_id"],
    )
    em["report_item_id"] = item["id"]
    em["report_note"] = "added to the outbox, sent at the next comm window"
    _step(em, now, "report_queued", "system", "Added to the Earth report outbox (sent at the next comm window).")


# ---- state machine --------------------------------------------------------------------
def _signals_for(alert: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Structured signals for the card, re-derived from the same data the rule saw."""
    from server.rules.base import RuleContext
    from server.rules.r_loc_01_possible_loc import find_signals

    astronaut_id, _ = crew_member()
    try:
        # ISO times in the texts: the Crew alerts page shows them in local time.
        signals, missing = find_signals(
            RuleContext(now=parse_ts(alert["ts"])), astronaut_id, ignore_before=None, fmt_time=iso
        )
    except Exception:
        log.exception("Could not re-derive R-LOC-01 signals")
        return [], list(alert.get("missing") or [])
    return [s.to_json() for s in signals], missing


def _open_watch(alert: dict[str, Any], now: datetime) -> dict[str, Any]:
    astronaut_id, name = crew_member()
    response_s = int(loc_threshold("response_seconds"))
    signals, missing = _signals_for(alert)
    em = {
        "id": db.new_id("em"), "alert_id": alert["id"], "astronaut_id": astronaut_id, "crew_name": name,
        "status": "watch", "detected_ts": alert["ts"], "opened_ts": iso(now),
        "deadline_ts": iso(now + timedelta(seconds=response_s)), "responded_ts": None, "escalated_ts": None,
        "ack_cmo_ts": None, "ack_commander_ts": None, "resolved_ts": None, "outcome": None, "note": None,
        "signals": signals, "missing": missing, "timeline": [], "report_item_id": None, "report_note": None,
    }
    labels = ", ".join(s["label"] for s in signals) or alert["what_changed"]
    _step(em, alert["ts"], "detected", "system", f"R-LOC-01: possible loss of consciousness ({labels}).")
    _step(em, now, "check_shown", "system",
          f"“Are you OK?” shown on {name}'s screen, {response_s} s to respond. CMO and Commander on watch.")
    _save(em)
    return em


def _escalate(em: dict[str, Any], now: datetime) -> None:
    em["status"] = "emergency"
    em["escalated_ts"] = iso(now)
    response_s = int(loc_threshold("response_seconds"))
    _step(em, em["deadline_ts"], "no_response", "system", f"No response to “Are you OK?” within {response_s} s.")
    _step(em, now, "escalated", "system", "Emergency: escalated to the CMO and the Commander.")
    _queue_report_item(em, now)
    _save(em)


def _close(em: dict[str, Any], now: datetime, outcome: str, note: str, actor: str) -> None:
    em["status"] = "resolved"
    em["resolved_ts"] = iso(now)
    em["outcome"] = outcome
    em["note"] = note
    _step(em, now, "resolved", actor, f"Resolved: {OUTCOME_TEXT[outcome]}. {note}".strip())
    _set_alert_status(em["alert_id"], "closed")
    _save(em)


def sync(now: datetime | None = None) -> None:
    """Open watches for new R-LOC-01 alerts, escalate overdue watches, drop orphans."""
    now = now or clock()
    ensure_tables()
    for em in _rows("status != 'resolved'", order="detected_ts"):
        alert = db.get("alerts", em["alert_id"])
        if alert is None:  # the alert is gone (data reset): the watch can't stay open
            with db.connect() as conn:
                conn.execute("DELETE FROM crew_emergencies WHERE id = ?", (em["id"],))
            continue
        if alert["status"] == "closed":
            _close(em, now, "other", "The alert was closed on the Alerts page.", "system")
            continue
        if em["status"] == "watch" and now >= parse_ts(em["deadline_ts"]):
            _escalate(em, now)
    known = {e["alert_id"] for e in _rows()}
    for alert in db.query("alerts", "rule_id = ? AND status != 'closed'", (RULE_ID,), order_by="ts"):
        if alert["id"] not in known:
            _open_watch(alert, now)


class CrewError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _require(em_id: str) -> dict[str, Any]:
    em = get(em_id)
    if em is None:
        raise CrewError(404, "Emergency not found")
    return em


def respond(em_id: str, now: datetime | None = None) -> dict[str, Any]:
    """The crew member's "I'm OK"."""
    now = now or clock()
    sync(now)
    em = _require(em_id)
    if em["status"] == "resolved":
        raise CrewError(409, "This event is already resolved")
    em["responded_ts"] = iso(now)
    secs = round((now - parse_ts(em["opened_ts"])).total_seconds())
    if em["status"] == "watch":
        _step(em, now, "responded", "crew", f"{em['crew_name']} answered “I'm OK” after {secs} s. Escalation cancelled.")
        _close(em, now, "responded", f"“I'm OK” after {secs} s.", "crew")
    else:  # already escalated: record it, the CMO / Commander still close the emergency
        _step(em, now, "responded", "crew",
              f"{em['crew_name']} answered “I'm OK” after {secs} s (after escalation). CMO and Commander still resolve it.")
        _save(em)
    return em


def ack(em_id: str, role: str, note: Optional[str] = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or clock()
    sync(now)
    em = _require(em_id)
    if em["status"] == "resolved":
        raise CrewError(409, "This event is already resolved")
    key = f"ack_{role}_ts"
    if em.get(key):
        return em  # already acknowledged by this role
    em[key] = iso(now)
    _step(em, now, f"ack_{role}", role, f"Acknowledged by the {ROLE_TEXT[role]}." + (f" {note}" if note else ""))
    alert = db.get("alerts", em["alert_id"])
    if alert and alert["status"] == "new":
        _set_alert_status(em["alert_id"], "ack")
    _save(em)
    return em


def resolve(em_id: str, outcome: str, note: str, now: datetime | None = None, actor: str = "cmo") -> dict[str, Any]:
    now = now or clock()
    sync(now)
    em = _require(em_id)
    if em["status"] == "resolved":
        raise CrewError(409, "This event is already resolved")
    _close(em, now, outcome, note.strip(), actor)
    return em


def listing(now: datetime | None = None, history_limit: int = 20) -> dict[str, Any]:
    now = now or clock()
    sync(now)
    return {
        "server_ts": iso(now),
        "demo": demo_enabled(),
        "response_seconds": int(loc_threshold("response_seconds")),
        "open": _rows("status != 'resolved'"),
        "history": _rows("status = 'resolved'", order="resolved_ts DESC", limit=history_limit),
    }
