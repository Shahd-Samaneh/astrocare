"""R-CIRC-01 · Irregular sleep schedule (owner: Shahd, Daily pair).

Bedtimes (sleep start, mission time) across the last 3 nights that differ by more
than `daily.sleep_onset_shift_hours` produce an *info* alert. It describes the
schedule only; it never names a cause.

Pattern (same as r_data_01_stale.py):
  1. set id / name / sources
  2. read what you need from `ctx`
  3. return AlertDraft(...) when the rule fires, else None

Bedtimes are compared on a clock that starts at noon, so 23:30 and 00:30 are 1 h
apart (not 23 h). Nights are named after the mission day the crew member woke up
(same as R-SLP-01). When one night has several sessions (e.g. a nap), the longest
one is that night's main sleep.
"""
from __future__ import annotations

from server.core.config import parse_ts
from server.core.models import SleepSession
from server.core.status import mission_clock
from server.features.daily.attention_stats import DailyNextStep, NextStepAction
from server.features.daily.thresholds import daily_threshold

from .base import AlertDraft, Rule, RuleContext
from .r_slp_01_short_sleep import night_day

NIGHTS_CHECKED = 3
SESSIONS_LOOKBACK = 10


def bedtime_hhmm(s: SleepSession) -> str:
    """Sleep start as mission time HH:MM."""
    return mission_clock(parse_ts(s.start))[0][-5:]


def minutes_from_noon(s: SleepSession) -> int:
    hh, mm = (int(x) for x in bedtime_hhmm(s).split(":"))
    return (hh * 60 + mm - 12 * 60) % (24 * 60)


def main_sleep_by_night(ctx: RuleContext, nights: list[int]) -> dict[int, SleepSession]:
    out: dict[int, SleepSession] = {}
    for s in ctx.sleep(SESSIONS_LOOKBACK):
        d = night_day(s)
        if d in nights and (d not in out or s.duration_min > out[d].duration_min):
            out[d] = s
    return out


class IrregularScheduleRule(Rule):
    id = "R-CIRC-01"
    name = "Irregular sleep schedule"
    sources = ["nasa-hrp-sleep-risk"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        limit_h = float(daily_threshold("sleep_onset_shift_hours"))
        today = mission_clock(ctx.now)[1]
        nights = list(range(today - NIGHTS_CHECKED + 1, today + 1))
        by_night = main_sleep_by_night(ctx, nights)
        present = [d for d in nights if d in by_night]
        if len(present) < 2:
            return None  # nothing to compare
        onsets = [minutes_from_noon(by_night[d]) for d in present]
        spread_h = (max(onsets) - min(onsets)) / 60
        if spread_h <= limit_h:
            return None

        bedtimes = ", ".join(f"{bedtime_hhmm(by_night[d])} (night {d})" for d in present)
        return AlertDraft(
            level="info",
            title="Irregular sleep schedule: bedtimes shifted over the last nights",
            what_changed=(
                f"Bedtimes over the last {NIGHTS_CHECKED} nights: {bedtimes}. They differ by "
                f"{spread_h:.1f} h (this alert starts above {limit_h:g} h; mission time)."
            ),
            data_used=[by_night[d].id for d in present],
            missing=[f"No sleep data for night {d}" for d in nights if d not in by_night],
            possible_factors=[
                "Schedule shifts (not confirmed)",
                "A heavy workload or late tasks (not confirmed)",
                "Lighting in the sleep station or cabin (not confirmed)",
            ],
            next_steps=[
                DailyNextStep(text="Review tonight's sleep window",
                              action=NextStepAction(label="Open sleep log", route="/daily#sleep")),
            ],
            dedupe_key="irregular-schedule",
        )
