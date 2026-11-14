"""R-CAB-01 · Cabin CO₂ above the 1-hour limit.

Averages cabin CO₂ over the last `co2_avg_window_minutes` and fires a *review*
alert when that average is above `co2_max`. With no CO₂ readings in the window
the rule does not fire (missing data is R-DATA-01's job).

The average is computed exactly as the co2 status in GET /api/cabin/latest
(same window boundary, same `statistics.fmean`, same comparison), so the Today
cabin card and this alert agree whenever readings exist in the window. The logic
is replicated here rather than imported from the router.

It never names a cause: it lists *possible factors* and gives operational steps
only (no medicine or treatment advice).

Source: NASA-STD-3001 Vol. 2 [V2 6004] / NASA OCHMO Technical Brief TB-004.

Pattern mirrors r_data_01_stale.py.
"""
from __future__ import annotations

import statistics

from server.core.models import NextStep

from .base import AlertDraft, Rule, RuleContext


class CabinCo2Rule(Rule):
    id = "R-CAB-01"
    name = "Cabin CO₂ above limit"
    sources = [
        "NASA-STD-3001 Vol. 2 [V2 6004] / NASA OCHMO Technical Brief TB-004 Carbon Dioxide",
        "config/thresholds.yaml: co2_max, co2_avg_window_minutes",
    ]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        co2_max = ctx.threshold("co2_max")
        if co2_max is None:
            return None  # no sourced limit: cannot judge (same as the card)

        window = float(ctx.threshold("co2_avg_window_minutes"))
        # Same window boundary as the card: ts >= now - window minutes.
        readings = ctx.cabin("co2", hours=window / 60)
        if not readings:
            return None  # nothing in the window: R-DATA-01 covers missing data

        avg = statistics.fmean(r.value for r in readings)
        if not avg > co2_max:
            return None

        unit = readings[-1].unit
        what_changed = (
            f"Cabin CO₂ averaged {avg:.1f} {unit} over the last {int(window)} min, "
            f"above the {co2_max:g} {unit} limit."
        )
        data_used = [r.id for r in readings]
        data_used.append(f"CO₂ window {readings[0].ts}–{readings[-1].ts}")

        return AlertDraft(
            level="review",
            title="Cabin CO₂ above limit",
            what_changed=what_changed,
            data_used=data_used,
            possible_factors=[
                "Crew activity or exercise in the module",
                "Reduced air circulation",
                "CO₂ removal system performance",
            ],
            next_steps=[
                NextStep(text="Check air circulation and fans near the crew area; follow the vehicle's CO₂ procedure"),
                NextStep(text="Recheck the CO₂ average after the next window"),
                NextStep(text="If crew report symptoms such as headache, inform the CMO", locked_for_cmo=True),
            ],
            dedupe_key="cab-co2-high",
        )
