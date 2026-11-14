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
from pathlib import Path

from server.core.config import DATA_DIR, app_config, iso, parse_ts, utcnow
from server.core.status import mission_clock, next_comm_window

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

    

# ---- permissions (Marah's, read only) ---------------------------------------------
def report_checkins_allowed() -> bool:
    """report.checkins from Marah's permissions. Missing or error -> False (private by default)."""
    try:
        from server.features.assistant.permissions import get_permissions
        return bool(get_permissions().get("report", {}).get("checkins", False))
    except Exception:  # noqa: BLE001 - never leak check-ins because of an error
        return False


# ---- report sections (fixed ids, contracts §2) -------------------------------------
REPORTS_DIR = DATA_DIR / "reports"

SECTION_TITLES: dict[str, str] = {
    "summary": "Summary",
    "alerts": "Alerts",
    "vitals": "Vital signs (latest)",
    "cabin": "Cabin conditions (latest)",
    "sleep": "Sleep (last 7 nights)",
    "attention": "Attention checks (last 5)",
    "exercise": "Exercise",
    "checkins": "Check-ins",
    "relax": "Relaxation sessions",
    "items": "Items for the flight surgeon / CMO",
    "radiation": "Radiation",
}
SECTION_IDS = tuple(SECTION_TITLES)

REPORT_SOURCES: list[str] = [
    "NASA Human Research Program, Hazards: Distance from Earth; Isolation and confinement (nasa.gov/hrp/hazards)",
    "NASA Human Research Program, Risks: Inadequate Sleep and Irregular Schedules; "
    "Behavioral Changes and Psychiatric Disorders (nasa.gov/hrp/risks)",
    "NASA Human Research Program, Ongoing research: ARCHeR, Artemis II (nasa.gov/hrp/ongoing-hrp-research)",
    "Canadian Space Agency, Monitoring radiation and astronaut health, 2026 (asc-csa.gc.ca)",
]
SIMULATED_LINE = "All data is simulated (SIMULATED). This report is a hackathon demo, not medical advice."


def _fmt_ts(ts: Optional[str]) -> str:
    return parse_ts(ts).strftime("%Y-%m-%d %H:%M UTC") if ts else "-"


def _lines(items: list[str], empty: str) -> str:
    return "\n".join(f"- {x}" for x in items) if items else empty


def _section_summary() -> str:
    _, day = mission_clock()
    open_alerts = db.count("alerts", "status IN ('new', 'recheck')")
    sleep = db.query("sleep_sessions", order_by="start DESC", limit=1)
    test = db.query("cognitive_tests", order_by="ts DESC", limit=1)
    parts = [f"Mission day {day}. Open alerts: {open_alerts}."]
    if sleep:
        parts.append(f"Last sleep: {sleep[0]['duration_min'] / 60:.1f} h.")
    if test:
        parts.append(f"Last attention check: median {test[0]['median_ms']:.0f} ms.")
    parts.append("Possible links are not confirmed causes.")
    return " ".join(parts)


def _section_alerts() -> str:
    return _lines(
        [f"[{a['level'].upper()}] {a['rule_id']}: {a['title']} ({a['status']}, {_fmt_ts(a['ts'])}). {a['what_changed']}"
         for a in db.query("alerts", order_by="ts DESC", limit=10)],
        "No alerts.",
    )


def _section_vitals() -> str:
    from server.features.monitoring.router import latest_readings  # read only, Monitoring's code
    out = []
    for x in latest_readings():
        r = x.reading
        val = f"{r.value:g} {r.unit} at {_fmt_ts(r.ts)}" if r else "no reading"
        out.append(f"{x.metric}: {val} [quality: {x.quality}]")
    return _lines(out, "No vital sign data.")


def _section_cabin() -> str:
    out = []
    for metric in ("co2", "cabin_temp", "humidity", "noise"):
        rows = db.query("cabin_readings", "metric = ?", (metric,), order_by="ts DESC", limit=1)
        if rows:
            out.append(f"{metric}: {rows[0]['value']:g} {rows[0]['unit']} at {_fmt_ts(rows[0]['ts'])}")
    return _lines(out, "No cabin data.")


def _section_sleep() -> str:
    return _lines(
        [f"{_fmt_ts(s['start'])}: {s['duration_min'] / 60:.1f} h, {s['awakenings']} awakenings"
         for s in db.query("sleep_sessions", order_by="start DESC", limit=7)],
        "No sleep data.",
    )


def _section_attention() -> str:
    return _lines(
        [f"{_fmt_ts(t['ts'])}: median {t['median_ms']:.0f} ms, {t['lapses']} lapses, {t['false_starts']} false starts"
         for t in db.query("cognitive_tests", order_by="ts DESC", limit=5)],
        "No attention checks.",
    ) + "\nExperimental measure; it does not decide fitness for tasks."


def _section_exercise() -> str:
    return _lines(
        [f"{_fmt_ts(e['ts'])}: plan {e['plan_id']} {e['status']}" + (f" (reason: {e['reason']})" if e.get("reason") else "")
         for e in db.query("exercise_logs", order_by="ts DESC", limit=7)],
        "No exercise logs.",
    )


def _section_checkins() -> str:
    if not report_checkins_allowed():
        return "Not included: permission required."
    # notePrivate is never copied into a report.
    return _lines(
        [f"{_fmt_ts(c['ts'])}: skipped" if c.get("skipped")
         else f"{_fmt_ts(c['ts'])}: mood {c.get('mood')}/5, stress {c.get('stress')}/5"
         for c in db.query("checkins", order_by="ts DESC", limit=7)],
        "No check-ins.",
    )


def _section_relax() -> str:
    out = []
    for s in db.query("relax_sessions", order_by="ts DESC", limit=7):
        after = s.get("stress_after")
        out.append(f"{_fmt_ts(s['ts'])}: {s['scene_id']}, {s['duration_min']} min, stress "
                   f"{s['stress_before']} -> {after if after is not None else 'not rated (ended early)'}")
    return _lines(out, "No relaxation sessions.")


def _section_items(items: list[dict[str, Any]]) -> str:
    labels = {"alert": "Alert", "cmo_question": "Question for CMO", "note": "Crew note"}
    return _lines(
        [f"{labels.get(i['kind'], i['kind'])} ({i['source_feature']}): {i['title']}. {i['text']}" for i in items],
        "No items.",
    )


def _section_radiation() -> str:
    return ("Radiation card not available yet in this build. Reference limits: 600 mSv career "
            "(NASA-STD-3001); neutrons are about 30% of the ISS dose (CSA, CANS).")


_BUILDERS = {
    "summary": _section_summary, "alerts": _section_alerts, "vitals": _section_vitals,
    "cabin": _section_cabin, "sleep": _section_sleep, "attention": _section_attention,
    "exercise": _section_exercise, "checkins": _section_checkins, "relax": _section_relax,
    "radiation": _section_radiation,
}


def _safe(builder) -> str:
    try:
        return builder()
    except Exception as e:  # noqa: BLE001 - one broken source must not break the whole report
        return f"Data not available ({type(e).__name__})."


# ---- reports -------------------------------------------------------------------------
def create_report(section_ids: list[str], item_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Build the sections, write PDF + JSON to data/reports/, return the report row.

    item_ids: pending items to include (None = all pending). Used only when 'items' is selected.
    Status: draft while building -> ready once both files exist.
    """
    from .pdf import write_pdf

    wanted = [s for s in SECTION_IDS if s in set(section_ids)]
    now = utcnow()
    rep_id = db.new_id("rep")
    db.insert("reports", {"id": rep_id, "created_ts": iso(now), "status": "draft", "sections": [], "file_path": None})

    pending = list_report_items(pending_only=True)
    if item_ids is not None:
        pending = [i for i in pending if i["id"] in set(item_ids)]

    sections = [
        {"id": sid, "title": SECTION_TITLES[sid],
         "body": _section_items(pending) if sid == "items" else _safe(_BUILDERS[sid])}
        for sid in wanted
    ]

    met, day = mission_clock(now)
    doc = {
        "id": rep_id, "createdTs": iso(now), "missionDay": day, "met": met,
        "mission": app_config()["mission"]["name"], "crew": app_config()["crew"]["name"],
        "simulated": True, "notice": SIMULATED_LINE,
        "sections": sections, "sources": REPORT_SOURCES,
        "checkinsIncluded": "checkins" in wanted and report_checkins_allowed(),
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{rep_id}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    write_pdf(REPORTS_DIR / f"{rep_id}.pdf", doc)

    if "items" in wanted:
        for i in pending:
            _exec("UPDATE report_items SET report_id = ? WHERE id = ?", (rep_id, i["id"]))

    db.update("reports", rep_id, {"status": "ready", "sections": sections,
                                  "file_path": f"data/reports/{rep_id}.pdf"})
    db.log_action("crew", "create_report", rep_id)
    return db.get("reports", rep_id)  # type: ignore[return-value]


def report_file(rep_id: str, fmt: str) -> Optional[Path]:
    path = REPORTS_DIR / f"{rep_id}.{fmt}"
    return path if path.is_file() else None


def queue_report(rep_id: str) -> Optional[dict[str, Any]]:
    """ready -> queued. None if the report doesn't exist; ValueError if it isn't ready."""
    rep = db.get("reports", rep_id)
    if not rep:
        return None
    if rep["status"] == "queued":
        return rep
    if rep["status"] != "ready":
        raise ValueError(f"Only a ready report can be queued (this one is {rep['status']}).")
    db.update("reports", rep_id, {"status": "queued"})
    db.log_action("crew", "queue_report", rep_id)
    return db.get("reports", rep_id)