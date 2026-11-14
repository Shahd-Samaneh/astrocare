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
from server.core.status import mission_clock

from .attention_stats import (
    AttentionBaseline, DailyCognitiveTest, InputMethod, RangeStatus, TestContext, TestMode, baseline_from, load_tests, pct_vs, pvt_measures,
    range_status, recent_routine, score_trials, set_test_context, set_test_meta, within,
)
from .engine_hooks import run_daily_engine

router = APIRouter()


MAX_TRIALS = 120  # an extended 3-minute test has ~20-40 responses


class TestIn(ApiModel):
    trials_ms: list[float] = Field(min_length=1, max_length=MAX_TRIALS)
    false_starts: int = Field(default=0, ge=0)
    context: TestContext = "routine"
    related_alert_id: Optional[str] = None
    mode: TestMode = "quick"  # 'extended' = 3 minutes, experimental, not validated
    sleepiness_kss: Optional[int] = Field(default=None, ge=1, le=9)  # KSS 1–9, optional
    trial_offsets_ms: Optional[list[float]] = Field(default=None, max_length=MAX_TRIALS)
    input_method: Optional[InputMethod] = None  # from the first response
    ts: Optional[str] = None  # tests and backfill only; the UI never sends it


class SleepContext(ApiModel):
    """From the sleep log: the last sleep session that ended before the test."""
    sleep_id: Optional[str] = None
    slept_hours: Optional[float] = None
    hours_awake: Optional[float] = None  # test time − end of that session
    source: Optional[str] = None


def sleep_context_at(ts: str) -> SleepContext:
    rows = db.query("sleep_sessions", '"end" <= ?', (ts,), order_by='"end" DESC', limit=1)
    if not rows:
        return SleepContext()
    r = rows[0]
    awake = (parse_ts(ts) - parse_ts(r["end"])).total_seconds() / 3600
    return SleepContext(sleep_id=r["id"], slept_hours=round(r["duration_min"] / 60, 1),
                        hours_awake=round(awake, 1), source=r["source"])


class RetestComparison(ApiModel):
    """Before vs after for a retest: the routine median that triggered the alert vs this retest."""
    alert_id: str
    rule_id: str
    alert_status: str  # after the engine ran (a retest sets 'recheck')
    before_median_ms: Optional[float] = None  # routine tests of the same mode, 48 h before the alert
    before_test_ids: list[str] = []
    after_median_ms: float
    diff_ms: Optional[float] = None  # after − before (negative = faster)
    diff_pct: Optional[float] = None


def retest_comparison(alert_id: str, test: DailyCognitiveTest) -> RetestComparison | None:
    alert = db.get("alerts", alert_id)
    if not alert:
        return None
    tests = [t for t in load_tests() if t.id != test.id]
    before = recent_routine(tests, parse_ts(alert["ts"]), mode=test.mode)
    before_med = float(statistics.median(t.median_ms for t in before)) if before else None
    diff = round(test.median_ms - before_med, 1) if before_med else None
    return RetestComparison(
        alert_id=alert_id, rule_id=alert["rule_id"], alert_status=alert["status"],
        before_median_ms=before_med, before_test_ids=[t.id for t in before], after_median_ms=test.median_ms,
        diff_ms=diff, diff_pct=round(diff / before_med * 100, 1) if before_med else None,
    )


class TestResult(ApiModel):
    test: DailyCognitiveTest
    pct_vs_baseline: Optional[float] = None
    within_range: Optional[bool] = None
    range_status: Optional[RangeStatus] = None  # within | faster | slower | flagged
    baseline: AttentionBaseline
    sleep_context: SleepContext = SleepContext()
    retest: Optional[RetestComparison] = None  # only for context 'retest' with relatedAlertId
    # True when this test's input differs from the most common input among the baseline tests
    input_differs: bool = False


@router.get("/tests")
def list_tests(n: int = Query(10, gt=0, le=200)) -> list[DailyCognitiveTest]:
    """Newest first. Each test carries withinRange vs the same-mode baseline at its own time
    (null while that baseline was still building)."""
    all_tests = load_tests()
    out = all_tests[:n]
    for t in out:
        base = baseline_from(all_tests, parse_ts(t.ts), mode=t.mode)
        t.within_range = None if base.building else within(t.median_ms, base)
        t.range_status = range_status(t.median_ms, base)
    return out


@router.get("/tests/baseline")
def get_baseline(mode: TestMode = Query("quick")) -> AttentionBaseline:
    return baseline_from(load_tests(), utcnow(), mode=mode)


@router.post("/tests", status_code=201)
def add_test(body: TestIn) -> TestResult:
    try:
        valid, median, lapses = score_trials(body.trials_ms)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if body.trial_offsets_ms is not None and len(body.trial_offsets_ms) != len(body.trials_ms):
        raise HTTPException(status_code=422, detail="trialOffsetsMs must have one value per trial")
    if body.context == "retest" and body.related_alert_id and not db.get("alerts", body.related_alert_id):
        raise HTTPException(status_code=404, detail=f"Unknown alert {body.related_alert_id}")

    ts = iso(parse_ts(body.ts)) if body.ts else iso(utcnow())
    test = DailyCognitiveTest(
        id=db.new_id("pvt"), ts=ts, trials_ms=valid, median_ms=median, lapses=lapses,
        false_starts=body.false_starts, context=body.context,
        related_alert_id=body.related_alert_id if body.context == "retest" else None,
        mission_day=mission_clock(parse_ts(ts))[1], sleepiness_kss=body.sleepiness_kss,
        mode=body.mode, input_method=body.input_method, trial_offsets_ms=body.trial_offsets_ms if valid == [float(x) for x in body.trials_ms] else None,
    )
    test.measures = pvt_measures(test.trials_ms, test.false_starts)
    # Baseline before inserting: the new test never counts towards its own baseline.
    base = baseline_from(load_tests(), parse_ts(ts), mode=test.mode)
    db.insert("cognitive_tests", test.model_dump())  # extra fields are ignored by db.insert
    set_test_context(test.id, test.context, test.related_alert_id)
    set_test_meta(test.id, mode=test.mode, sleepiness_kss=test.sleepiness_kss,
                  input_method=test.input_method, trial_offsets_ms=test.trial_offsets_ms)
    db.log_action("crew", "attention_test" if test.context == "routine" else "attention_retest", test.id)
    run_daily_engine()
    # While the same-mode baseline is still building (< 3 tests), no within/outside verdict.
    comparison = (retest_comparison(test.related_alert_id, test)
                  if test.context == "retest" and test.related_alert_id else None)
    return TestResult(test=test, pct_vs_baseline=pct_vs(median, base),
                      within_range=None if base.building else within(median, base),
                      range_status=range_status(median, base),
                      baseline=base, sleep_context=sleep_context_at(ts), retest=comparison,
                      input_differs=bool(test.input_method and base.usual_input_method
                                         and test.input_method != base.usual_input_method))


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
