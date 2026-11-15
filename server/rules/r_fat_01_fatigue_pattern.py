"""R-FAT-01 · Possible fatigue pattern: short sleep + slower reaction time
(owner: Shahd, Daily pair). This is the alert the demo is built on.

Fires when:
  * the R-SLP-01 condition holds (short sleep on enough of the last 3 nights), and
  * the median of the *routine* attention tests in the last 48 h is slower than
    the personal baseline by ≥ `daily.attention_slower_pct`.
Baseline = median of the `daily.attention_baseline_n` routine tests before the
last 48 h (server/features/daily/attention_stats.py, shared with GET /api/tests/baseline).

Level: review. Never names a cause: every factor is "possible, not confirmed".
Cabin CO₂ / temperature / humidity that crossed a sourced threshold in the alert's window is
added as a possible factor (rules/cabin_factors.py).

The engine creates the alert. The in-place update, the retest → recheck step and
the alert id inside the retest route are applied by
server/features/daily/engine_hooks.py (see docs/proposals/daily-contracts.md §3).
"""
from __future__ import annotations

import statistics

from datetime import timedelta

from server.core.config import parse_ts
from server.core.status import mission_day_start
from server.features.daily.attention_stats import (
    DailyNextStep, NextStepAction, baseline_from, pct_vs, recent_routine, with_context,
)
from server.features.daily.thresholds import daily_threshold

from .base import AlertDraft, Rule, RuleContext
from .cabin_factors import cabin_factors
from .r_slp_01_short_sleep import fmt_nights, short_sleep

ALERT_ID_TOKEN = "{alertId}"  # replaced with the real alert id by engine_hooks.py
MISSING_CHECKIN = "Today's check-in"
MISSING_SLEEP_RATING = "Sleep self-rating for last night"
TESTS_LOOKBACK = 60  # enough history for the baseline window


def checkin_done_today(ctx: RuleContext) -> bool:
    """A check-in (done *or* skipped) since the start of the current mission day."""
    since = mission_day_start(ctx.now)
    return any(since <= parse_ts(c.ts) <= ctx.now for c in ctx.checkins(10))


def fatigue_missing(ctx: RuleContext) -> list[str]:
    missing = []
    if not checkin_done_today(ctx):
        missing.append(MISSING_CHECKIN)
    last = ctx.sleep(1)
    if last and last[-1].self_quality is None:
        missing.append(MISSING_SLEEP_RATING)
    return missing


class FatiguePatternRule(Rule):
    id = "R-FAT-01"
    name = "Possible fatigue pattern: short sleep and slower reaction time"
    sources = ["nasa-hrp-sleep-risk", "nasa-hrp-bmed-risk", "nasa-pvt-iss"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        sleep = short_sleep(ctx)
        if not sleep.fires:
            return None

        tests = with_context(ctx.tests(TESTS_LOOKBACK))
        base = baseline_from(tests, ctx.now)
        recent = recent_routine(tests, ctx.now)
        if not base.median_ms or not recent:
            return None
        recent_median = float(statistics.median(t.median_ms for t in recent))
        pct = pct_vs(recent_median, base)
        slower_pct = float(daily_threshold("attention_slower_pct"))
        if pct is None or pct < slower_pct:
            return None

        n_short, n_nights, n_tests = len(sleep.short), len(sleep.nights), len(recent)
        what = (
            f"Sleep: under {sleep.limit_h:g} h on {n_short} of the last {n_nights} nights "
            f"({fmt_nights(sleep.nights)}). "
            f"Reaction time: median {recent_median:.0f} ms over {n_tests} routine "
            f"test{'s' if n_tests != 1 else ''} in the last 48 h vs your baseline {base.median_ms:.0f} ms "
            f"(+{pct:.0f} %; this alert starts at +{slower_pct:g} %; baseline from {base.n} earlier tests)."
        )
        # Window = the nights and tests this alert looks at.
        since = min([parse_ts(s.start) for s in sleep.nights] + [ctx.now - timedelta(hours=48)])
        cab_factors, cab_used = cabin_factors(ctx, since)
        return AlertDraft(
            level="review",
            title="Possible fatigue pattern: short sleep and slower reaction time",
            what_changed=what,
            data_used=[s.id for s in sleep.short] + [t.id for t in recent] + cab_used,
            missing=fatigue_missing(ctx),
            possible_factors=[
                "Accumulated short sleep may be slowing reaction time (possible link, not confirmed)",
                "Schedule shifts or a heavy workload (not confirmed)",
                "Stress or low mood (not confirmed; today's check-in would help)",
                "Distraction or a disturbed setting during the test (not confirmed)",
                *cab_factors,
            ],
            next_steps=[
                DailyNextStep(text="Do today's check-in (mood and stress)",
                              action=NextStepAction(label="Open check-in", route="/daily#checkin")),
                DailyNextStep(text="Retest attention after a rest break",
                              action=NextStepAction(label="Retest now", route=f"/attention?retest={ALERT_ID_TOKEN}")),
                DailyNextStep(text="Switch today's exercise to a lighter alternative from the plan",
                              action=NextStepAction(label="Open exercise", route="/daily#exercise")),
            ],
            dedupe_key="fatigue-pattern",
        )
