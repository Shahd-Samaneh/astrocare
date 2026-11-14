# Owner: Shahd
"""Daily check-in endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, utcnow
from server.core.models import CheckIn

router = APIRouter()


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
