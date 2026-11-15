"""R-CAB-03 · Cabin noise unusual vs your 7-day cabin average (team decision).

There is no sourced NASA noise limit in config/thresholds.yaml or references/, so this
rule does not use one. It compares the latest fresh noise reading (not older than
`stale_minutes`) with the cabin's own recent history, exactly like the Today noise tile:
above mean + `noise_sd_multiplier` · SD of the last `noise_baseline_days` of readings.
Both values are labelled "Team decision" in thresholds.yaml. Level is always *info*.

Only high noise fires (low noise needs no action). Needs at least 2 readings and SD > 0.
It never names a cause. Next steps come from server/features/monitoring/cabin_guidance.py
("noise_high", the same list the Today noise tile shows).
"""
from __future__ import annotations

import statistics

from server.core.models import NextStep, NextStepAction
from server.features.monitoring import cabin_guidance

from .base import AlertDraft, Rule, RuleContext

FACTOR = "possible link, not a confirmed cause"


class CabinNoiseRule(Rule):
    id = "R-CAB-03"
    name = "Cabin noise above your 7-day cabin average"
    sources = [
        "Team decision: no NASA noise limit in config/thresholds.yaml or references/; "
        "compared with the cabin's own recent noise (mean + k·SD)",
        "config/thresholds.yaml: noise_sd_multiplier, noise_baseline_days, stale_minutes",
        *cabin_guidance.sources("noise_high"),
    ]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        days = float(ctx.threshold("noise_baseline_days"))
        k = float(ctx.threshold("noise_sd_multiplier"))
        history = ctx.cabin("noise", hours=days * 24)
        if len(history) < 2:
            return None  # no baseline yet
        if not ctx.cabin("noise", hours=float(ctx.threshold("stale_minutes")) / 60):
            return None  # latest reading is stale: R-DATA-01's job
        latest = history[-1]
        mean, sd = statistics.fmean(r.value for r in history), statistics.stdev(r.value for r in history)
        if sd == 0 or not latest.value > mean + k * sd:
            return None

        return AlertDraft(
            level="info",
            title="Cabin noise above your usual level",
            what_changed=(
                f"Cabin noise is {latest.value:g} {latest.unit}, above your {int(days)}-day cabin average "
                f"of {mean:.1f} {latest.unit} by more than {k:g} SD ({sd:.1f} {latest.unit}). "
                "This is a comparison with recent cabin history (team decision), not a NASA limit."
            ),
            data_used=[latest.id, f"Noise baseline: {len(history)} readings over {int(days)} days"],
            missing=["A sourced NASA noise limit (none configured)"],
            possible_factors=[
                f"Equipment or fans running in the module ({FACTOR})",
                f"Crew activity or exercise nearby ({FACTOR})",
            ],
            next_steps=[
                *cabin_guidance.next_steps("noise_high"),
                NextStep(text="Add this alert to the report",
                         action=NextStepAction(label="Open reports", route="/reports")),
            ],
            dedupe_key="cab-noise-high",
        )
