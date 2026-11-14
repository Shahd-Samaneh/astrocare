"""Sleep API (owner: Nadia). Contract: docs/daily-contract.md §2.

    GET   /api/sleep?days=7            -> SleepSession[] (oldest first)
    GET   /api/sleep/summary?days=7    -> nights + personalAvgHours + lastNight
    POST  /api/sleep                   -> SleepSession (source 'manual'), then runs the rule engine
    PATCH /api/sleep/{id}/rating       -> SleepSession, then runs the rule engine

Other modules call `sleep_summary(days)`.

Additions to the contract (all optional, nothing was removed or renamed), so the UI
never has to hard-code a threshold or look a night up by date:
    nights[].id, nights[].short, summary.shortThresholdHours, lastNight.id
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from server.core import db
from server.core.config import iso, parse_ts, threshold
from server.core.models import ApiModel, SleepSession
from server.core.status import mission_clock
from .engine_hooks import run_daily_engine

router = APIRouter(tags=["daily"])

MAX_SLEEP_HOURS = 16  # validation limit for manual entries (contract: 0-16 h)
BASELINE_DAYS = 3  # "personal average" = mean of the first 3 mission days in the data


# ---- helpers ---------------------------------------------------------------
def _hours(row: dict[str, Any]) -> float:
    return round(row["duration_min"] / 60, 2)


def _mission_day_of(ts: str) -> int:
    """Mission day on which a timestamp falls (the night belongs to the day it ends on)."""
    return mission_clock(parse_ts(ts))[1]


def personal_avg_hours(rows: list[dict[str, Any]]) -> Optional[float]:
    """Mean hours of the first 3 mission days present in `rows`, or of all nights if fewer."""
    if not rows:
        return None
    by_day: "OrderedDict[int, list[float]]" = OrderedDict()
    for r in sorted(rows, key=lambda r: r["start"]):
        by_day.setdefault(_mission_day_of(r["end"]), []).append(_hours(r))
    first_days = sorted(by_day)[:BASELINE_DAYS]
    values = [h for d in first_days for h in by_day[d]]
    return round(sum(values) / len(values), 2)


def _night(row: dict[str, Any], short_below: Optional[float]) -> dict[str, Any]:
    hours = _hours(row)
    return {
        "id": row["id"],
        "date": parse_ts(row["end"]).date().isoformat(),
        "missionDay": _mission_day_of(row["end"]),
        "hours": hours,
        "awakenings": row["awakenings"],
        "selfQuality": row.get("self_quality"),
        "short": short_below is not None and hours < float(short_below),
    }


def sleep_summary(days: int = 7) -> dict[str, Any]:
    """Last `days` nights, oldest first, plus the personal average and last night."""
    latest = db.query("sleep_sessions", order_by="start DESC", limit=max(1, days))
    short_below = threshold("sleep_short_hours")
    nights = [_night(r, short_below) for r in reversed(latest)]
    return {
        "nights": nights,
        "personalAvgHours": personal_avg_hours(db.query("sleep_sessions", order_by="start")),
        "shortThresholdHours": short_below,
        "lastNight": nights[-1] if nights else None,
    }


def _validate_rating(value: Optional[int]) -> None:
    if value is not None and not (1 <= value <= 5):
        raise HTTPException(422, "Sleep rating must be between 1 and 5.")


# ---- endpoints ---------------------------------------------------------------
@router.get("/sleep")
def list_sleep(days: int = Query(7, gt=0, le=60)) -> list[SleepSession]:
    rows = db.query("sleep_sessions", order_by="start DESC", limit=days)
    return [SleepSession.model_validate(r) for r in reversed(rows)]


@router.get("/sleep/summary")
def get_sleep_summary(days: int = Query(7, gt=0, le=60)) -> dict:
    return sleep_summary(days)


class SleepIn(ApiModel):
    start: str
    end: str
    awakenings: int = 0
    self_quality: Optional[int] = None


@router.post("/sleep", status_code=201)
def add_sleep(body: SleepIn) -> SleepSession:
    try:
        start, end = parse_ts(body.start), parse_ts(body.end)
    except ValueError:
        raise HTTPException(422, "Start and end must be valid date-times.")
    if end <= start:
        raise HTTPException(422, "Wake-up time must be after the time you went to sleep.")
    if end - start > timedelta(hours=MAX_SLEEP_HOURS):
        raise HTTPException(422, f"A sleep session can be at most {MAX_SLEEP_HOURS} hours.")
    if body.awakenings < 0:
        raise HTTPException(422, "Awakenings can't be negative.")
    _validate_rating(body.self_quality)

    session = SleepSession(
        id=db.new_id("sleep"), start=iso(start), end=iso(end),
        duration_min=int(round((end - start).total_seconds() / 60)),
        awakenings=body.awakenings, self_quality=body.self_quality, source="manual",
    )
    db.insert("sleep_sessions", session.model_dump())
    db.log_action("crew", "log_sleep", session.id)
    run_daily_engine()
    return session


class RatingIn(ApiModel):
    self_quality: int


@router.patch("/sleep/{sleep_id}/rating")
def rate_sleep(sleep_id: str, body: RatingIn) -> SleepSession:
    if not db.get("sleep_sessions", sleep_id):
        raise HTTPException(404, "Sleep session not found.")
    _validate_rating(body.self_quality)
    db.update("sleep_sessions", sleep_id, {"self_quality": body.self_quality})
    db.log_action("crew", "rate_sleep", sleep_id)
    run_daily_engine()
    return SleepSession.model_validate(db.get("sleep_sessions", sleep_id))
