"""Digital twin API (owner: Shahd). Read-only.

    GET /api/twin/state                    -> TwinState (live status per body region)
    GET /api/twin/timeline?from=129&to=142 -> TwinTimeline (one entry per mission day)

Both default to the shared mission clock; `to` is capped at today (no future days).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .models import TwinState, TwinTimeline
from .service import twin_state, twin_timeline

router = APIRouter(tags=["twin"])

MAX_DAYS = 60


@router.get("/twin/state")
def get_twin_state() -> TwinState:
    return twin_state()


@router.get("/twin/timeline")
def get_twin_timeline(
    from_day: Optional[int] = Query(None, alias="from", ge=0, description="First mission day (default: today - 13)"),
    to_day: Optional[int] = Query(None, alias="to", ge=0, description="Last mission day (default and max: today)"),
) -> TwinTimeline:
    if from_day is not None and to_day is not None:
        if from_day > to_day:
            raise HTTPException(422, "`from` must be less than or equal to `to`")
        if to_day - from_day + 1 > MAX_DAYS:
            raise HTTPException(422, f"At most {MAX_DAYS} days per request")
    return twin_timeline(from_day, to_day)
