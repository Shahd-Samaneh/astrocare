"""Today plan (owner: Nadia). Contract: docs/daily-contract.md §2.

    GET /api/today/plan -> { missionDay, items: [{kind, title, status, route}], fatigueFlag }

Every status comes from the real data (check-ins, tests, exercise logs, sleep sessions),
never from a flag stored by the UI. `fatigueFlag` is true while an R-FAT-01 alert is open.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from server.core import db
from server.core.config import iso
from server.core.status import mission_clock, mission_day_start

from .exercise import latest_log, plan_for_day

router = APIRouter(tags=["daily"])

FATIGUE_RULE_ID = "R-FAT-01"


def fatigue_flag() -> bool:
    return db.count("alerts", "rule_id = ? AND status != 'closed'", (FATIGUE_RULE_ID,)) > 0


def _checkin_status(since: str) -> str:
    rows = db.query("checkins", "ts >= ?", (since,))
    if any(not r["skipped"] for r in rows):
        return "done"
    return "skipped" if rows else "todo"


def _exercise_item(day: int) -> dict[str, Any] | None:
    plan = plan_for_day(day)
    if not plan:
        return None  # no session scheduled today: nothing to tick off
    log = latest_log(plan["id"])
    status = "todo" if not log else "skipped" if log["status"] == "skipped" else "done"
    return {
        "kind": "exercise", "title": f"Exercise: {plan['type']}, {plan['durationMin']} min (example plan)",
        "status": status, "route": "/daily#exercise",
    }


def _sleep_item() -> dict[str, Any]:
    rows = db.query("sleep_sessions", order_by="start DESC", limit=1)
    if not rows:
        return {"kind": "sleep_rating", "title": "Log last night's sleep", "status": "todo", "route": "/daily#sleep"}
    rated = rows[0].get("self_quality") is not None
    return {
        "kind": "sleep_rating", "title": "Rate last night's sleep",
        "status": "done" if rated else "todo", "route": "/daily#sleep",
    }


@router.get("/today/plan")
def today_plan() -> dict:
    day = mission_clock()[1]
    since = iso(mission_day_start())
    items: list[dict[str, Any]] = [
        {"kind": "checkin", "title": "Daily check-in", "status": _checkin_status(since), "route": "/daily#checkin"},
        {
            "kind": "attention", "title": "Attention test",
            "status": "done" if db.count("cognitive_tests", "ts >= ?", (since,)) > 0 else "todo",
            "route": "/attention",
        },
    ]
    exercise = _exercise_item(day)
    if exercise:
        items.append(exercise)
    items.append(_sleep_item())
    return {"missionDay": day, "items": items, "fatigueFlag": fatigue_flag()}
