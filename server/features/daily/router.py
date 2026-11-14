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
