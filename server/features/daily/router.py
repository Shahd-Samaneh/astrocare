"""Daily API aggregator (owner: Shahd). Only includes the sub-routers.

Shahd: attention.py · checkins.py · summary.py · sources.py · thresholds.py
Nadia: sleep.py · exercise.py · today.py

Mounted under /api by server/main.py, so every path below is /api/<path>.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import attention, checkins, exercise, sleep, sources, summary, thresholds, today

router = APIRouter(tags=["daily"])

for _sub in (sleep, attention, checkins, exercise, today, summary, sources, thresholds):
    router.include_router(_sub.router)


# ---- service functions for other features -------------------------------------------------
# Before the split, the endpoint functions lived in this module, and the assistant
# (server/features/assistant/context.py) still imports them from here. These plain wrappers
# keep those names working with explicit, safe defaults: calling an endpoint function directly
# would leave its Query(...) defaults in place. Check-ins never include private notes here.
def list_sleep(nights: int = 7) -> list:
    return sleep.list_sleep(days=nights)


def list_tests(n: int = 10) -> list:
    return attention.list_tests(n=n)


def list_checkins(n: int = 7) -> list[dict]:
    return checkins.list_checkins(n=n, include_private=False)


def exercise_plan(day: int | None = None) -> list[dict]:
    return exercise.exercise_plan(day=day)


def today_plan() -> dict:
    return today.today_plan()
