"""R-SPO2-01 · Low blood-oxygen (SpO₂) episode.

A "low episode" is a run of the most recent SpO₂ readings that are all below
`spo2_min`, with at least 2 readings spanning at least `spo2_low_minutes` from
the first low reading to the latest. If the latest reading is back at or above
`spo2_min`, the rule does not fire.

Quality decides the level, not the value:
  - every reading in the episode is good quality  -> "urgent" (a real event);
  - any reading is low quality                    -> "info" (recheck the sensor).

It never names a cause or gives any treatment/oxygen advice: it lists *possible
factors* from what we have and leaves clinical action to the CMO.

Source: config/thresholds.yaml (spo2_min experimental, spo2_low_minutes team
decision).

Pattern mirrors r_data_01_stale.py / r_hr_01_elevated.py.
"""
from __future__ import annotations

from server.core.config import parse_ts
from server.core.models import NextStep

from .base import AlertDraft, Rule, RuleContext


class LowSpo2Rule(Rule):
    id = "R-SPO2-01"
    name = "SpO₂ low episode"
    sources = ["config/thresholds.yaml: spo2_min (experimental), spo2_low_minutes (team decision)"]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        spo2_min = float(ctx.threshold("spo2_min"))
        low_minutes = float(ctx.threshold("spo2_low_minutes"))

        readings = ctx.readings("spo2")  # oldest first
        if not readings:
            return None
        if readings[-1].value >= spo2_min:
            return None  # latest reading has recovered: no episode

        # Trailing run of consecutive readings below the threshold.
        episode = []
        for r in reversed(readings):
            if r.value < spo2_min:
                episode.append(r)
            else:
                break
        episode.reverse()  # oldest first
        if len(episode) < 2:
            return None

        start, end = parse_ts(episode[0].ts), parse_ts(episode[-1].ts)
        if (end - start).total_seconds() / 60 < low_minutes:
            return None

        all_good = all(r.quality == "good" for r in episode)
        unit = episode[-1].unit
        values = ", ".join(f"{round(r.value)}{unit}" for r in episode)
        times = ", ".join(r.ts for r in episode)

        what_changed = (
            f"SpO₂ readings {values} (at {times}), all below {spo2_min:.0f}{unit}, "
            f"over {(end - start).total_seconds() / 60:.0f} min."
        )
        data_used = [r.id for r in episode]
        data_used.append(f"SpO₂ window {episode[0].ts}–{episode[-1].ts}")
        data_used.append("Quality: " + ", ".join(r.quality for r in episode))

        # What context we lack for the same window.
        missing = []
        hr_in_window = [r for r in ctx.readings("heart_rate") if start <= parse_ts(r.ts) <= end]
        if not hr_in_window:
            missing.append("No heart-rate reading during this SpO₂ window.")

        possible_factors = [
            "Sensor fit or movement (finger/wrist oximeter)",
            "Cold hands or low peripheral perfusion",
            "Recent physical activity or exertion",
        ]

        if all_good:
            return AlertDraft(
                level="urgent",
                title="SpO₂ low",
                what_changed=what_changed,
                data_used=data_used,
                missing=missing,
                possible_factors=possible_factors,
                next_steps=[
                    NextStep(text="Recheck the oximeter fit and repeat the reading at rest"),
                    NextStep(text="Notify the CMO now", locked_for_cmo=True),
                ],
                dedupe_key="spo2-low-urgent",
            )

        return AlertDraft(
            level="info",
            title="SpO₂ low reading — recheck sensor",
            what_changed=what_changed,
            data_used=data_used,
            missing=missing,
            possible_factors=possible_factors,
            next_steps=[
                NextStep(text="Reposition or clean the sensor and repeat the reading"),
            ],
            dedupe_key="spo2-low-info",
        )
