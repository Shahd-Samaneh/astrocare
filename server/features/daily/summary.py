# Owner: Shahd
"""Daily summary: GET /api/daily/summary?days=7.

One JSON object for the assistant (Marah), reports (Noura) and our own pages:
    { sleep, attention, exercise, checkins, activeDailyAlerts }
It NEVER contains a private check-in note.

`sleep_summary` and `exercise_summary` are Nadia's (sleep.py / exercise.py). Until
she pushes them, we fall back to the small stubs below, and every stub result
says so (`"stub": true`).
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

from fastapi import APIRouter, Query

from server.core import db
from server.core.config import parse_ts
from server.core.status import mission_clock

from .attention import attention_summary
from .attention_stats import DailyAlert
from .checkins import checkins_summary

router = APIRouter()

DAILY_RULE_PREFIXES = ("R-SLP", "R-FAT", "R-EX")


# ---- fallbacks until Nadia's service functions exist ---------------------------
def _sleep_summary_stub(days: int) -> dict[str, Any]:
    rows = db.query("sleep_sessions", order_by="start DESC", limit=days)
    nights = [
        {
            "id": r["id"], "missionDay": mission_clock(parse_ts(r["end"]))[1],
            "hours": round(r["duration_min"] / 60, 2), "awakenings": r["awakenings"],
            "selfQuality": r["self_quality"],
        }
        for r in reversed(rows)
    ]
    avg = round(sum(n["hours"] for n in nights) / len(nights), 2) if nights else None
    return {"nights": nights, "personalAvgHours": avg, "lastNight": nights[-1] if nights else None, "stub": True}


def _exercise_summary_stub(days: int) -> dict[str, Any]:
    logs = db.query("exercise_logs", order_by="ts DESC", limit=days)
    return {"logs": [{"planId": r["plan_id"], "ts": r["ts"], "status": r["status"], "reason": r["reason"]} for r in logs],
            "stub": True}


def _load_service(module: str, name: str, fallback: Callable[[int], dict]) -> Callable[[int], dict]:
    try:
        return getattr(importlib.import_module(f"server.features.daily.{module}"), name)
    except (ImportError, AttributeError):
        return fallback


def active_daily_alerts() -> list[DailyAlert]:
    rows = db.query("alerts", "status != 'closed'", order_by="ts DESC")
    return [DailyAlert.model_validate(r) for r in rows if r["rule_id"].startswith(DAILY_RULE_PREFIXES)]


def daily_summary(days: int = 7) -> dict[str, Any]:
    sleep_summary = _load_service("sleep", "sleep_summary", _sleep_summary_stub)
    exercise_summary = _load_service("exercise", "exercise_summary", _exercise_summary_stub)
    return {
        "days": days,
        "sleep": sleep_summary(days),
        "attention": attention_summary(10),
        "exercise": exercise_summary(days),
        "checkins": checkins_summary(days),  # no private notes, by construction
        "activeDailyAlerts": [a.model_dump(by_alias=True) for a in active_daily_alerts()],
    }


@router.get("/daily/summary")
def get_daily_summary(days: int = Query(7, gt=0, le=60)) -> dict[str, Any]:
    return daily_summary(days)
