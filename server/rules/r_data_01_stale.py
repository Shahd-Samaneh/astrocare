"""EXAMPLE RULE: copy this file to create a new one.

R-DATA-01 · Stale data
A continuous metric with no reading for more than `stale_minutes`
(config/thresholds.yaml) produces an *info* alert. It never interprets the
missing value medically: it only says the data is missing and how to fix it.

Pattern:
  1. set id / name / sources
  2. read what you need from `ctx` (never query the DB directly)
  3. return AlertDraft(...) when the rule fires, else None
"""
from __future__ import annotations

from server.core.config import parse_ts
from server.core.models import NextStep

from .base import AlertDraft, Rule, RuleContext

# Metrics that are expected to stream continuously. Blood pressure is a spot
# check (twice a day) and gets its own "missing today" rule later.
CONTINUOUS_METRICS = ("heart_rate", "spo2", "skin_temp", "resp_rate")
LABELS = {"heart_rate": "Heart rate", "spo2": "SpO₂", "skin_temp": "Skin temperature", "resp_rate": "Respiration rate"}


def _fmt_age(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h} h {m:02d} m" if h else f"{m} m"


class StaleDataRule(Rule):
    id = "R-DATA-01"
    name = "Stale continuous metric"
    sources = ["config/thresholds.yaml: stale_minutes (team decision, data quality)"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        limit = float(ctx.threshold("stale_minutes"))
        stale: list[tuple[str, float, str | None]] = []  # (metric, age_min, reading id)
        for metric in CONTINUOUS_METRICS:
            last = ctx.latest(metric)
            age = (ctx.now - parse_ts(last.ts)).total_seconds() / 60 if last else float("inf")
            if age > limit:
                stale.append((metric, age, last.id if last else None))
        if not stale:
            return None

        names = ", ".join(LABELS[m] for m, _, _ in stale)
        missing, factors, steps = [], [], []
        for metric, age, _ in stale:
            sensor = ctx.sensor_for(metric)
            where = f" (sensor '{sensor.name}' is {sensor.status.replace('_', ' ')})" if sensor else ""
            when = "no reading at all" if age == float("inf") else f"no reading for {_fmt_age(age)}"
            missing.append(f"{LABELS[metric]}: {when}{where}")
            if sensor and sensor.status != "connected":
                factors.append(f"{sensor.name} {sensor.status.replace('_', ' ')}")
                steps.append(NextStep(text=f"Check that the {sensor.name.lower()} is attached and paired"))
            steps.append(NextStep(text=f"Enter a manual {LABELS[metric].lower()} reading"))
        factors += ["Sensor removed for exercise or hygiene", "Battery depleted"]

        return AlertDraft(
            level="info",
            title=f"{names}: no recent data",
            what_changed=f"No new {names.lower()} reading for more than {int(limit)} minutes.",
            data_used=[rid for _, _, rid in stale if rid],
            missing=missing,
            possible_factors=list(dict.fromkeys(factors)),
            next_steps=steps,
            dedupe_key=",".join(sorted(m for m, _, _ in stale)),
        )
