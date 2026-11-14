# Owner: Shahd
"""Attention (reaction-time) test endpoints.

GET  /api/tests?n=10        newest first, with context
GET  /api/tests/baseline    median of the routine tests before the last 48 h
POST /api/tests             server scores the trials, stores, runs the rule engine

Experimental. Does not decide fitness for duty.
"""
from __future__ import annotations

import statistics
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from server.core import db
from server.core.config import iso, parse_ts, utcnow
from server.core.models import ApiModel

from .attention_stats import (
    AttentionBaseline, DailyCognitiveTest, TestContext, baseline_from, load_tests, pct_vs,
    recent_routine, score_trials, set_test_context, within,
)
from .engine_hooks import run_daily_engine

router = APIRouter()


class TestIn(ApiModel):
    trials_ms: list[float] = Field(min_length=1, max_length=20)
    false_starts: int = Field(default=0, ge=0)
    context: TestContext = "routine"
    related_alert_id: Optional[str] = None
    ts: Optional[str] = None  # tests and backfill only; the UI never sends it


class TestResult(ApiModel):
    test: DailyCognitiveTest
    pct_vs_baseline: Optional[float] = None
    within_range: Optional[bool] = None
    baseline: AttentionBaseline


@router.get("/tests")
def list_tests(n: int = Query(10, gt=0, le=100)) -> list[DailyCognitiveTest]:
    return load_tests(limit=n)


@router.get("/tests/baseline")
def get_baseline() -> AttentionBaseline:
    return baseline_from(load_tests(), utcnow())


@router.post("/tests", status_code=201)
def add_test(body: TestIn) -> TestResult:
    try:
        valid, median, lapses = score_trials(body.trials_ms)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if body.context == "retest" and body.related_alert_id and not db.get("alerts", body.related_alert_id):
        raise HTTPException(status_code=404, detail=f"Unknown alert {body.related_alert_id}")

    ts = iso(parse_ts(body.ts)) if body.ts else iso(utcnow())
    test = DailyCognitiveTest(
        id=db.new_id("pvt"), ts=ts, trials_ms=valid, median_ms=median, lapses=lapses,
        false_starts=body.false_starts, context=body.context,
        related_alert_id=body.related_alert_id if body.context == "retest" else None,
    )
    # Baseline before inserting: the new test never counts towards its own baseline.
    base = baseline_from(load_tests(), parse_ts(ts))
    db.insert("cognitive_tests", test.model_dump())  # extra fields are ignored by db.insert
    set_test_context(test.id, test.context, test.related_alert_id)
    db.log_action("crew", "attention_test" if test.context == "routine" else "attention_retest", test.id)
    run_daily_engine()
    return TestResult(test=test, pct_vs_baseline=pct_vs(median, base), within_range=within(median, base), baseline=base)


def attention_summary(n: int = 10) -> dict:
    """Service function for summary.py, the assistant and reports. JSON-ready (camelCase)."""
    now = utcnow()
    all_tests = load_tests()
    base = baseline_from(all_tests, now)
    recent = recent_routine(all_tests, now)
    latest = all_tests[0] if all_tests else None
    recent_median = float(statistics.median(t.median_ms for t in recent)) if recent else None
    return {
        "baseline": base.model_dump(by_alias=True),
        "latest": latest.model_dump(by_alias=True) if latest else None,
        "latestPctVsBaseline": pct_vs(latest.median_ms, base) if latest else None,
        "latestWithinRange": within(latest.median_ms, base) if latest else None,
        "recentRoutineMedianMs": recent_median,
        "recentRoutinePctVsBaseline": pct_vs(recent_median, base) if recent_median else None,
        "tests": [t.model_dump(by_alias=True) for t in all_tests[:n]],
        "note": "Experimental. Does not decide fitness for duty.",
    }
