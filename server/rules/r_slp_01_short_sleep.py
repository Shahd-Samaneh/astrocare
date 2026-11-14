"""R-SLP-01 · Short sleep on several recent nights (owner: Shahd, Daily pair).

Sleep shorter than `daily.sleep_short_hours` on at least `daily.sleep_short_nights`
of the last 3 nights produces an *info* alert. It only describes the sleep data;
it never names a cause.

Pattern (same as r_data_01_stale.py):
  1. set id / name / sources
  2. read what you need from `ctx`
  3. return AlertDraft(...) when the rule fires, else None

`short_sleep(ctx)` is reused by R-FAT-01.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from server.core.config import parse_ts
from server.core.models import SleepSession
from server.core.status import mission_clock
from server.features.daily.attention_stats import DailyNextStep, NextStepAction
from server.features.daily.thresholds import daily_threshold

from .base import AlertDraft, Rule, RuleContext

NIGHTS_CHECKED = 3  # "of the last 3 nights" (contract §3)


@dataclass
class ShortSleep:
    fires: bool
    nights: list[SleepSession] = field(default_factory=list)  # the last 3, oldest first
    short: list[SleepSession] = field(default_factory=list)
    limit_h: float = 0.0
    needed: int = 0


def night_day(s: SleepSession) -> int:
    """Mission day of the night, named after the day the crew member woke up."""
    return mission_clock(parse_ts(s.end))[1]


def hours(s: SleepSession) -> float:
    return s.duration_min / 60


def fmt_nights(nights: list[SleepSession]) -> str:
    return ", ".join(f"{hours(s):.1f} h (night {night_day(s)})" for s in nights)


def short_sleep(ctx: RuleContext) -> ShortSleep:
    limit_h = float(daily_threshold("sleep_short_hours"))
    needed = int(daily_threshold("sleep_short_nights"))
    nights = ctx.sleep(NIGHTS_CHECKED)
    short = [s for s in nights if hours(s) < limit_h]
    return ShortSleep(fires=len(short) >= needed, nights=nights, short=short, limit_h=limit_h, needed=needed)


class ShortSleepRule(Rule):
    id = "R-SLP-01"
    name = "Short sleep on several recent nights"
    sources = ["nasa-hrp-sleep-risk", "nasa-hrp-ongoing"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        res = short_sleep(ctx)
        if not res.fires:
            return None
        n, total = len(res.short), len(res.nights)
        missing = []
        if res.nights and res.nights[-1].self_quality is None:
            missing.append("Sleep self-rating for last night")
        return AlertDraft(
            level="info",
            title=f"Short sleep on {n} of the last {total} nights",
            what_changed=(
                f"Under {res.limit_h:g} h on {n} of the last {total} nights. "
                f"Last {total} nights: {fmt_nights(res.nights)}."
            ),
            data_used=[s.id for s in res.nights],
            missing=missing,
            possible_factors=[
                "Schedule shifts or a heavy workload (not confirmed)",
                "Noise, light or temperature in the sleep station (not confirmed)",
                "Stress or worry (not confirmed)",
            ],
            next_steps=[
                DailyNextStep(text="Rate last night's sleep in the Daily log",
                              action=NextStepAction(label="Open sleep log", route="/daily#sleep")),
                DailyNextStep(text="Plan a protected sleep window tonight if the schedule allows"),
            ],
            dedupe_key="short-sleep",
        )
