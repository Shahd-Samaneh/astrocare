"""Cabin conditions as a *possible factor* on health alerts (R-FAT-01, R-SLP-01).

Adds one factor per cabin metric that crossed a sourced threshold, plus the cabin
data behind it in dataUsed. It never fires an alert by itself and never names a
cause: every factor says "possible link, not a confirmed cause".

  * CO₂: average over the last `co2_headache_avg_days` (7) above `co2_headache_avg_max`
    (2.5 mmHg; NASA OCHMO TB-004: headache risk below 1 % needs a 7-day average under 2.5).
  * cabin_temp / humidity: any reading in the alert's window outside the NASA-STD-3001
    range (`*_min` / `*_max`).
  * noise: none. thresholds.yaml has no sourced noise limit (only a team-decision SD
    multiplier), so no factor is added for it.

A threshold is only used when it has a number and a real source (config.has_real_source).
"""
from __future__ import annotations

import statistics
from datetime import datetime

from server.core.config import has_real_source

from .base import RuleContext

CO2_FACTOR = "Cabin CO2 was higher than usual (possible link, not a confirmed cause)"
TEMP_FACTOR = "Cabin temperature was outside its usual range (possible link, not a confirmed cause)"
HUMIDITY_FACTOR = "Cabin humidity was outside its usual range (possible link, not a confirmed cause)"
MAX_IDS = 10  # out-of-range reading ids listed per metric; the rest are summarised


def _sourced(ctx: RuleContext, *names: str) -> bool:
    t = ctx.thresholds
    return all(n in t and t[n].value is not None and has_real_source(t[n]) for n in names)


def _co2(ctx: RuleContext) -> tuple[list[str], list[str]]:
    if not _sourced(ctx, "co2_headache_avg_max", "co2_headache_avg_days"):
        return [], []
    days = float(ctx.threshold("co2_headache_avg_days"))
    readings = ctx.cabin("co2", hours=days * 24)
    if not readings:
        return [], []
    avg = statistics.fmean(r.value for r in readings)
    limit = float(ctx.threshold("co2_headache_avg_max"))
    if not avg > limit:
        return [], []
    unit = readings[-1].unit
    return [CO2_FACTOR], [
        f"Cabin CO₂ {days:g}-day average {avg:.2f} {unit} (> {limit:g} {unit}) from {len(readings)} readings "
        f"{readings[0].ts}–{readings[-1].ts}"
    ]


def _range(ctx: RuleContext, metric: str, factor: str, since: datetime) -> tuple[list[str], list[str]]:
    lo_key, hi_key = f"{metric}_min", f"{metric}_max"
    if not _sourced(ctx, lo_key, hi_key):
        return [], []
    lo, hi = float(ctx.threshold(lo_key)), float(ctx.threshold(hi_key))
    hours = max((ctx.now - since).total_seconds() / 3600, 0)
    out = [r for r in ctx.cabin(metric, hours=hours) if r.value < lo or r.value > hi]
    if not out:
        return [], []
    used = [r.id for r in out[:MAX_IDS]]
    if len(out) > MAX_IDS:
        used.append(f"…and {len(out) - MAX_IDS} more {metric} readings outside {lo:g}–{hi:g} {out[0].unit}")
    return [factor], used


def cabin_factors(ctx: RuleContext, since: datetime) -> tuple[list[str], list[str]]:
    """(possible_factors, data_used) for cabin conditions; `since` = start of the alert's window."""
    factors: list[str] = []
    used: list[str] = []
    for f, u in (_co2(ctx), _range(ctx, "cabin_temp", TEMP_FACTOR, since),
                 _range(ctx, "humidity", HUMIDITY_FACTOR, since)):
        factors += f
        used += u
    return factors, used
