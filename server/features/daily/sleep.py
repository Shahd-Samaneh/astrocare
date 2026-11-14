# Owner: Nadia
"""Sleep endpoints (stub moved from router.py, behaviour unchanged)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import Field

from server.core import db
from server.core.models import SleepSession, Source

router = APIRouter()


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
