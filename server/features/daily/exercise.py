# Owner: Nadia
"""Exercise endpoints (stub moved from router.py, behaviour unchanged)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from server.core import db
from server.core.config import iso, utcnow
from server.core.models import ExerciseLog, ExercisePlan

router = APIRouter()


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
