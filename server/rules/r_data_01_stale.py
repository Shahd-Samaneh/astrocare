"""EXAMPLE RULE: copy this file to create a new one.

R-DATA-01 · Stale or missing data
Two data-quality checks, both *info*:
  - a continuous metric (heart rate, SpO₂, skin temp, respiration) with no
    reading for more than `stale_minutes` (config/thresholds.yaml) = *stale*;
  - blood pressure (a twice-a-day spot check) with no reading since the current
    mission day began = *missing*.
It never interprets the value medically: it only says which data is stale and
which is missing, and how to fix it.

Pattern:
  1. set id / name / sources
  2. read what you need from `ctx` (never query the DB directly)
  3. return AlertDraft(...) when the rule fires, else None
"""
from __future__ import annotations

from server.core.config import parse_ts
from server.core.models import NextStep
from server.core.status import mission_day_start

from .base import AlertDraft, Rule, RuleContext

# Metrics that are expected to stream continuously.
CONTINUOUS_METRICS = ("heart_rate", "spo2", "skin_temp", "resp_rate")
# Blood pressure is a spot check (twice a day): it is "missing" rather than
# "stale" when nothing has been recorded since the mission day began.
BP_METRICS = ("bp_sys", "bp_dia")
LABELS = {"heart_rate": "Heart rate", "spo2": "SpO₂", "skin_temp": "Skin temperature", "resp_rate": "Respiration rate"}


def _fmt_age(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h} h {m:02d} m" if h else f"{m} m"


class StaleDataRule(Rule):
    id = "R-DATA-01"
    name = "Stale or missing data"
    sources = ["config/thresholds.yaml: stale_minutes (team decision, data quality)"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        limit = float(ctx.threshold("stale_minutes"))

        # -- stale continuous metrics --------------------------------------
        stale: list[tuple[str, float, str | None]] = []  # (metric, age_min, reading id)
        for metric in CONTINUOUS_METRICS:
            last = ctx.latest(metric)
            age = (ctx.now - parse_ts(last.ts)).total_seconds() / 60 if last else float("inf")
            if age > limit:
                stale.append((metric, age, last.id if last else None))

        # -- blood pressure missing since the mission day began ------------
        day_start = mission_day_start(ctx.now)
        bp_missing = not any(
            (r := ctx.latest(m)) is not None and parse_ts(r.ts) >= day_start for m in BP_METRICS
        )

        if not stale and not bp_missing:
            return None

        missing, factors, steps = [], [], []

        # Stale lines first (keeps a continuous metric as next_steps[0]).
        for metric, age, _ in stale:
            sensor = ctx.sensor_for(metric)
            where = f" (sensor '{sensor.name}' is {sensor.status.replace('_', ' ')})" if sensor else ""
            when = "no reading at all" if age == float("inf") else f"no reading for {_fmt_age(age)}"
            missing.append(f"{LABELS[metric]}: stale — {when}{where}")
            if sensor and sensor.status != "connected":
                factors.append(f"{sensor.name} {sensor.status.replace('_', ' ')}")
                steps.append(NextStep(text=f"Check that the {sensor.name.lower()} is attached and paired"))
            steps.append(NextStep(text=f"Enter a manual {LABELS[metric].lower()} reading"))

        # Blood-pressure missing line.
        if bp_missing:
            bp_sensor = ctx.sensor_for("bp_sys")
            where = f" (sensor '{bp_sensor.name}' is {bp_sensor.status.replace('_', ' ')})" if bp_sensor else ""
            missing.append(f"Blood pressure: missing — no reading since the mission day began{where}")
            if bp_sensor and bp_sensor.status != "connected":
                factors.append(f"{bp_sensor.name} {bp_sensor.status.replace('_', ' ')}")
            factors.append("Spot check not taken yet today")
            cuff = bp_sensor.name.lower() if bp_sensor else "blood pressure cuff"
            cuff_state = f" (it is {bp_sensor.status.replace('_', ' ')})" if bp_sensor and bp_sensor.status != "connected" else ""
            steps.append(NextStep(text=f"Check the {cuff}{cuff_state}"))
            steps.append(NextStep(text="Enter a manual blood pressure reading"))

        factors += ["Sensor removed for exercise or hygiene", "Battery depleted"]

        # Title names what triggered the alert and labels each as stale or
        # missing. With only stale metrics, keep the original "... : no recent
        # data" wording.
        stale_names = ", ".join(LABELS[m] for m, _, _ in stale)
        if bp_missing:
            segments = ([f"{stale_names} stale"] if stale else []) + ["Blood pressure missing"]
            title = " · ".join(segments)
        else:
            title = f"{stale_names}: no recent data"

        changes = []
        if stale:
            changes.append(f"No new {', '.join(LABELS[m] for m, _, _ in stale).lower()} reading for more than {int(limit)} minutes.")
        if bp_missing:
            changes.append("No blood pressure reading since the current mission day began.")

        return AlertDraft(
            level="info",
            title=title,
            what_changed=" ".join(changes),
            data_used=[rid for _, _, rid in stale if rid],
            missing=missing,
            possible_factors=list(dict.fromkeys(factors)),
            # Dedupe on the stale-metric set only (as the original rule did): the
            # same ongoing data-quality situation must not re-alert, and the key
            # stays stable even after a manual bp reading clears the "missing" flag.
            next_steps=steps,
            dedupe_key=",".join(sorted(m for m, _, _ in stale)),
        )
