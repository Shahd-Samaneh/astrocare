# Owner: Shahd
"""Attention-test maths and the Daily extensions to the shared contract.

Used by attention.py, summary.py and the rules R-SLP-01 / R-FAT-01, so the baseline
is computed in exactly one place.

Contract extensions (see docs/proposals/daily-contracts.md §1-2), kept here until
Haya merges them into core/models.py + contracts.ts:
  * DailyCognitiveTest = CognitiveTest + context + related_alert_id
  * DailyNextStep      = NextStep + action {label, route}
  * DailyAlert         = Alert whose next_steps are DailyNextStep
Test context is stored in our own table `daily_test_context`. A test without a row
there is a 'routine' test (all simulated tests are routine). Mode, sleepiness (KSS),
input method and per-trial timing live in `daily_test_meta`; no row = a quick test.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from typing import Any, Iterable, Literal, Optional

from server.core import db
from server.core.config import parse_ts
from pydantic import Field

from server.core.models import Alert, ApiModel, CognitiveTest, NextStep
from server.core.status import mission_clock

from .thresholds import daily_threshold

TestContext = Literal["routine", "retest"]
TestMode = Literal["quick", "extended"]
InputMethod = Literal["mouse", "touch", "keyboard"]
RECENT_HOURS = 48  # "the last 48 h" in the contract (window, not a clinical threshold)
FEW_TESTS_PCT = 10  # range = median ± 10 % when the baseline has fewer than 3 tests (contract §5)


# ---- contract extensions ----------------------------------------------------
class DailyCognitiveTest(CognitiveTest):
    context: TestContext = "routine"
    related_alert_id: Optional[str] = None
    mission_day: Optional[int] = None  # derived from ts (mission clock), never stored
    # from daily_test_meta (absent row = a quick test with no extra data, e.g. simulated)
    mode: TestMode = "quick"
    sleepiness_kss: Optional[int] = Field(default=None, ge=1, le=9)  # Karolinska Sleepiness Scale
    input_method: Optional[InputMethod] = None
    trial_offsets_ms: Optional[list[float]] = None  # response time since test start, per trial


class NextStepAction(ApiModel):
    label: str
    route: str


class DailyNextStep(NextStep):
    action: Optional[NextStepAction] = None


class DailyAlert(Alert):
    next_steps: list[DailyNextStep] = []


# ---- daily_test_context table -----------------------------------------------
_DDL = (
    'CREATE TABLE IF NOT EXISTS "daily_test_context" '
    '("test_id" TEXT PRIMARY KEY, "context" TEXT NOT NULL, "related_alert_id" TEXT)'
)


def ensure_context_table() -> None:
    with db.connect() as conn:
        conn.execute(_DDL)


def set_test_context(test_id: str, context: TestContext, related_alert_id: str | None) -> None:
    ensure_context_table()
    with db.connect() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO "daily_test_context" (test_id, context, related_alert_id) VALUES (?, ?, ?)',
            (test_id, context, related_alert_id),
        )


def context_map() -> dict[str, tuple[str, str | None]]:
    ensure_context_table()
    with db.connect() as conn:
        rows = conn.execute('SELECT test_id, context, related_alert_id FROM "daily_test_context"').fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


# ---- daily_test_meta table (mode, sleepiness, input method, trial timing) -------
_META_DDL = (
    'CREATE TABLE IF NOT EXISTS "daily_test_meta" ('
    """"test_id" TEXT PRIMARY KEY, "mode" TEXT NOT NULL DEFAULT 'quick', "sleepiness_kss" INTEGER, """
    '"input_method" TEXT, "trial_offsets_ms" TEXT)'
)
META_FIELDS = ("mode", "sleepiness_kss", "input_method", "trial_offsets_ms")


def ensure_meta_table() -> None:
    with db.connect() as conn:
        conn.execute(_META_DDL)


def set_test_meta(test_id: str, *, mode: str = "quick", sleepiness_kss: int | None = None,
                  input_method: str | None = None, trial_offsets_ms: list[float] | None = None) -> None:
    ensure_meta_table()
    with db.connect() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO "daily_test_meta" (test_id, mode, sleepiness_kss, input_method, trial_offsets_ms) '
            "VALUES (?, ?, ?, ?, ?)",
            (test_id, mode, sleepiness_kss, input_method,
             json.dumps(trial_offsets_ms) if trial_offsets_ms is not None else None),
        )


def meta_map() -> dict[str, dict[str, Any]]:
    ensure_meta_table()
    with db.connect() as conn:
        rows = conn.execute(f'SELECT test_id, {", ".join(META_FIELDS)} FROM "daily_test_meta"').fetchall()
    out = {}
    for r in rows:
        d = dict(zip(META_FIELDS, r[1:]))
        d["trial_offsets_ms"] = json.loads(d["trial_offsets_ms"]) if d["trial_offsets_ms"] else None
        out[r[0]] = {k: v for k, v in d.items() if v is not None}
    return out


def with_context(tests: Iterable[CognitiveTest | dict[str, Any]]) -> list[DailyCognitiveTest]:
    """Attach context / relatedAlertId / meta / missionDay to plain tests (or DB rows)."""
    ctx = context_map()
    meta = meta_map()
    out = []
    for t in tests:
        data = t.model_dump() if isinstance(t, CognitiveTest) else dict(t)
        context, related = ctx.get(data["id"], ("routine", None))
        out.append(DailyCognitiveTest.model_validate({
            **data, "context": context, "related_alert_id": related,
            "mission_day": mission_clock(parse_ts(data["ts"]))[1],
            **meta.get(data["id"], {}),
        }))
    return out


def load_tests(limit: int | None = None) -> list[DailyCognitiveTest]:
    """All tests (or the newest `limit`) with context, newest first."""
    return with_context(db.query("cognitive_tests", order_by="ts DESC", limit=limit))


# ---- scoring -------------------------------------------------------------------
def score_trials(trials_ms: list[float]) -> tuple[list[float], float, int]:
    """(valid trials, median, lapses).

    The client repeats a trial after a false start, so every received value is a
    real response; we only drop non-positive values. Lapse = RT ≥ pvt_lapse_ms.
    """
    valid = [float(x) for x in trials_ms if x and x > 0]
    if not valid:
        raise ValueError("at least one valid trial is required")
    lapse_ms = float(daily_threshold("pvt_lapse_ms"))
    return valid, float(statistics.median(valid)), sum(1 for x in valid if x >= lapse_ms)


# ---- baseline ---------------------------------------------------------------------
class AttentionBaseline(ApiModel):
    median_ms: Optional[float] = None
    n: int = 0
    range_low_ms: Optional[float] = None
    range_high_ms: Optional[float] = None
    test_ids: list[str] = []


def _routine(tests: Iterable[DailyCognitiveTest]) -> list[DailyCognitiveTest]:
    return [t for t in tests if t.context == "routine"]


def baseline_from(tests: list[DailyCognitiveTest], now: datetime) -> AttentionBaseline:
    """Median of the `attention_baseline_n` newest routine tests older than 48 h."""
    n_max = int(daily_threshold("attention_baseline_n"))
    cutoff = now - timedelta(hours=RECENT_HOURS)
    older = sorted((t for t in _routine(tests) if parse_ts(t.ts) < cutoff), key=lambda t: t.ts, reverse=True)[:n_max]
    if not older:
        return AttentionBaseline()
    medians = [t.median_ms for t in older]
    med = float(statistics.median(medians))
    if len(older) >= 3:
        low, high = float(min(medians)), float(max(medians))
    else:
        low, high = med * (1 - FEW_TESTS_PCT / 100), med * (1 + FEW_TESTS_PCT / 100)
    return AttentionBaseline(median_ms=med, n=len(older), range_low_ms=low, range_high_ms=high,
                             test_ids=[t.id for t in older])


def recent_routine(tests: list[DailyCognitiveTest], now: datetime) -> list[DailyCognitiveTest]:
    """Routine tests in the last 48 h (up to `now`), oldest first."""
    cutoff = now - timedelta(hours=RECENT_HOURS)
    return sorted((t for t in _routine(tests) if cutoff <= parse_ts(t.ts) <= now), key=lambda t: t.ts)


def pct_vs(value: float, base: AttentionBaseline) -> float | None:
    if not base.median_ms:
        return None
    return round((value / base.median_ms - 1) * 100, 1)


def within(value: float, base: AttentionBaseline) -> bool | None:
    if base.range_low_ms is None or base.range_high_ms is None:
        return None
    return base.range_low_ms <= value <= base.range_high_ms
