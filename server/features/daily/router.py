"""Daily API: sleep, attention tests, check-ins, exercise (owners: Shahd + Nadia).

Working stubs that read/write the DB. Extend freely inside this folder.
"""
from __future__ import annotations

import statistics
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, threshold, utcnow
from server.core.status import mission_clock, mission_day_start
from server.core.models import (
    ApiModel, CheckIn, CognitiveTest, ExerciseLog, ExercisePlan, Source, SleepSession,
)

router = APIRouter(tags=["daily"])


def _mission_day() -> int:
    return mission_clock()[1]


# ---- sleep -----------------------------------------------------------------
class SleepIn(SleepSession):
    id: str = Field(default_factory=lambda: db.new_id("sleep"))
    source: Source = "manual"


@router.get("/sleep")
def list_sleep(nights: int = Query(7, gt=0, le=60)) -> list[SleepSession]:
    rows = db.query("sleep_sessions", order_by="start DESC", limit=nights)
    return [SleepSession.model_validate(r) for r in reversed(rows)]


@router.post("/sleep", status_code=201)
def add_sleep(body: SleepIn) -> SleepSession:
    s = SleepSession.model_validate(body.model_dump())
    db.insert("sleep_sessions", s.model_dump())
    db.log_action("crew", "log_sleep", s.id)
    return s


# ---- attention tests ----------------------------------------------------------
class TestIn(ApiModel):
    trials_ms: list[float] = Field(min_length=1)
    false_starts: int = 0
    ts: Optional[str] = None


@router.get("/tests")
def list_tests(n: int = Query(14, gt=0, le=100)) -> list[CognitiveTest]:
    rows = db.query("cognitive_tests", order_by="ts DESC", limit=n)
    return [CognitiveTest.model_validate(r) for r in reversed(rows)]


@router.post("/tests", status_code=201)
def add_test(body: TestIn) -> CognitiveTest:
    lapse_ms = float(threshold("pvt_lapse_ms"))
    t = CognitiveTest(
        id=db.new_id("pvt"), ts=body.ts or iso(utcnow()), trials_ms=body.trials_ms,
        median_ms=float(statistics.median(body.trials_ms)),
        lapses=sum(1 for x in body.trials_ms if x > lapse_ms), false_starts=body.false_starts,
    )
    db.insert("cognitive_tests", t.model_dump())
    db.log_action("crew", "attention_test", t.id)
    return t


# ---- check-ins -------------------------------------------------------------------
class CheckInIn(CheckIn):
    id: str = Field(default_factory=lambda: db.new_id("ci"))
    ts: str = Field(default_factory=lambda: iso(utcnow()))


@router.get("/checkins")
def list_checkins(n: int = Query(14, gt=0, le=100)) -> list[CheckIn]:
    rows = db.query("checkins", order_by="ts DESC", limit=n)
    return [CheckIn.model_validate(r) for r in reversed(rows)]


@router.post("/checkins", status_code=201)
def add_checkin(body: CheckInIn) -> CheckIn:
    c = CheckIn.model_validate(body.model_dump())
    db.insert("checkins", c.model_dump())
    db.log_action("crew", "checkin", c.id)
    return c


# ---- exercise -------------------------------------------------------------------
@router.get("/exercise/plan")
def exercise_plan() -> list[ExercisePlan]:
    return [ExercisePlan.model_validate(r) for r in db.query("exercise_plans", order_by="day")]


class ExerciseLogIn(ExerciseLog):
    id: str = Field(default_factory=lambda: db.new_id("exl"))
    ts: str = Field(default_factory=lambda: iso(utcnow()))


@router.post("/exercise/log", status_code=201)
def log_exercise(body: ExerciseLogIn) -> ExerciseLog:
    entry = ExerciseLog.model_validate(body.model_dump())
    db.insert("exercise_logs", entry.model_dump())
    db.log_action("crew", f"exercise_{entry.status}", entry.id)
    return entry


# ---- today ------------------------------------------------------------------------
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
