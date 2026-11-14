# Owner: Shahd
"""Daily check-in endpoints.

GET  /api/checkins?n=7[&includePrivate=true]   newest first. notePrivate only with includePrivate=true
POST /api/checkins { mood, stress, notePrivate?, skipped }  then runs the rule engine

`skipped: true` is a valid check-in: it counts as "done today (skipped)".
The private note never leaves this endpoint unless explicitly asked for; it is
never part of a summary, the assistant context or a report.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, parse_ts, utcnow
from server.core.models import ApiModel, CheckIn
from server.core.status import mission_day_start

from .engine_hooks import run_daily_engine

router = APIRouter()

NOTE_MAX = 2000


class CheckInIn(ApiModel):
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    stress: Optional[int] = Field(default=None, ge=1, le=5)
    note_private: Optional[str] = Field(default=None, max_length=NOTE_MAX)
    skipped: bool = False
    ts: Optional[str] = None  # tests and backfill only; the UI never sends it


def _public(c: CheckIn, include_private: bool = False) -> dict:
    """JSON (camelCase). Without include_private the key `notePrivate` is absent, not null."""
    return c.model_dump(by_alias=True, exclude=None if include_private else {"note_private"})


def _load(n: int | None = None) -> list[CheckIn]:
    return [CheckIn.model_validate(r) for r in db.query("checkins", order_by="ts DESC", limit=n)]


@router.get("/checkins")
def list_checkins(
    n: int = Query(7, gt=0, le=100),
    include_private: bool = Query(False, alias="includePrivate"),
) -> list[dict]:
    return [_public(c, include_private) for c in _load(n)]


@router.post("/checkins", status_code=201)
def add_checkin(body: CheckInIn) -> CheckIn:
    if not body.skipped and (body.mood is None or body.stress is None):
        raise HTTPException(status_code=422, detail="mood and stress are required unless skipped is true")
    note = (body.note_private or "").strip() or None
    c = CheckIn(
        id=db.new_id("ci"), ts=iso(parse_ts(body.ts)) if body.ts else iso(utcnow()),
        mood=None if body.skipped else body.mood, stress=None if body.skipped else body.stress,
        note_private=None if body.skipped else note, skipped=body.skipped,
    )
    db.insert("checkins", c.model_dump())
    db.log_action("crew", "checkin_skipped" if c.skipped else "checkin", c.id)
    run_daily_engine()
    return c  # the author sees their own note in the response


def checkin_today(now: datetime | None = None) -> CheckIn | None:
    """Latest check-in (done or skipped) since the start of the current mission day."""
    now = now or utcnow()
    since = mission_day_start(now)
    for c in _load(20):
        ts = parse_ts(c.ts)
        if since <= ts <= now:
            return c
    return None


def checkins_summary(n: int = 7) -> dict:
    """Service function for summary.py, the assistant and reports. Never contains notePrivate."""
    items = _load(n)
    done = [c for c in items if not c.skipped]
    today = checkin_today()

    def avg(vals: list[int]) -> float | None:
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "todayStatus": "todo" if today is None else ("skipped" if today.skipped else "done"),
        "latest": _public(items[0]) if items else None,
        "count": len(items),
        "skippedCount": len(items) - len(done),
        "avgMood": avg([c.mood for c in done if c.mood is not None]),
        "avgStress": avg([c.stress for c in done if c.stress is not None]),
        "items": [_public(c) for c in items],
    }
