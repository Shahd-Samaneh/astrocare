# Owner: Nadia
"""Today plan endpoint (stub moved from router.py, behaviour unchanged)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from server.core import db
from server.core.config import iso
from server.core.models import ApiModel, ExercisePlan, SleepSession
from server.core.status import mission_clock, mission_day_start

router = APIRouter()


def _mission_day() -> int:
    return mission_clock()[1]


class TodayPlan(ApiModel):
    mission_day: int
    exercise: Optional[ExercisePlan] = None
    exercise_logged: bool
    attention_check_done: bool
    check_in_done: bool
    last_sleep: Optional[SleepSession] = None


@router.get("/today/plan")
def today_plan() -> TodayPlan:
    day = _mission_day()
    plan = db.query("exercise_plans", "day = ?", (day,), limit=1)
    since = iso(mission_day_start())
    last_sleep = db.query("sleep_sessions", order_by="start DESC", limit=1)
    return TodayPlan(
        mission_day=day,
        exercise=ExercisePlan.model_validate(plan[0]) if plan else None,
        exercise_logged=bool(plan) and db.count("exercise_logs", "plan_id = ?", (plan[0]["id"],)) > 0,
        attention_check_done=db.count("cognitive_tests", "ts >= ?", (since,)) > 0,
        check_in_done=db.count("checkins", "ts >= ? AND skipped = 0", (since,)) > 0,
        last_sleep=SleepSession.model_validate(last_sleep[0]) if last_sleep else None,
    )
