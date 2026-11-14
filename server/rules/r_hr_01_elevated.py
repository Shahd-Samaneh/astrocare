"""R-HR-01 · Heart rate elevated above personal baseline.

Fires a *review* alert when the last `hr_consecutive_readings` good-quality
heart-rate readings are ALL above the personal baseline range
(mean + `hr_sd_multiplier` · SD). Low-quality readings are skipped. With no
baseline for heart rate, the rule does not fire.

It never names a cause: it lists *possible factors* from data we actually have
(short sleep, cabin CO₂/temperature) and leaves any clinical step to the CMO.

Source: docs/AstroCare_Full_Plan.md §9.

Pattern mirrors r_data_01_stale.py:
  1. set id / name / sources
  2. read what you need from `ctx` (never query the DB directly)
  3. return AlertDraft(...) when the rule fires, else None
"""
from __future__ import annotations

from server.core.models import NextStep

from .base import AlertDraft, Rule, RuleContext


class ElevatedHeartRateRule(Rule):
    id = "R-HR-01"
    name = "Heart rate above baseline"
    sources = [
        "docs/AstroCare_Full_Plan.md §9",
        "config/thresholds.yaml: hr_sd_multiplier, hr_consecutive_readings",
    ]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        base = ctx.profile.baseline.get("heart_rate") if ctx.profile else None
        if base is None:
            return None  # no personal baseline yet: cannot judge

        n = int(ctx.threshold("hr_consecutive_readings"))
        k = float(ctx.threshold("hr_sd_multiplier"))
        upper = base.mean + k * base.sd

        good = [r for r in ctx.readings("heart_rate") if r.quality == "good"]
        if len(good) < n:
            return None
        window = good[-n:]  # the most recent n good readings
        if not all(r.value > upper for r in window):
            return None

        values = ", ".join(f"{round(r.value)}" for r in window)
        unit = window[-1].unit
        what_changed = (
            f"Last {n} heart-rate readings were {values} {unit}, all above the personal "
            f"baseline range (above {upper:.0f} {unit} = mean {base.mean:.0f} + {k:g}·SD {base.sd:.0f})."
        )

        # Which readings, and the time window they cover.
        data_used = [r.id for r in window]
        data_used.append(f"Heart-rate window {window[0].ts}–{window[-1].ts}")

        # Possible factors (never a stated cause), drawn only from data we have.
        factors: list[str] = []
        last_sleep = ctx.sleep(1)
        short_h = float(ctx.threshold("sleep_short_hours"))
        if last_sleep and last_sleep[-1].duration_min / 60 < short_h:
            factors.append(f"Short sleep last night ({last_sleep[-1].duration_min / 60:.1f} h)")
        co2 = ctx.cabin("co2", hours=6)
        if co2:
            factors.append(f"Recent cabin CO₂ around {co2[-1].value:g} {co2[-1].unit}")
        cabin_temp = ctx.cabin("cabin_temp", hours=6)
        if cabin_temp:
            factors.append(f"Recent cabin temperature around {cabin_temp[-1].value:g} {cabin_temp[-1].unit}")
        factors.append("Recent physical activity or exertion")

        next_steps = [
            NextStep(text="Recheck heart rate at rest in about 10 minutes"),
            NextStep(text="Review cardiovascular status with the CMO", locked_for_cmo=True),
        ]

        return AlertDraft(
            level="review",
            title="Heart rate above baseline",
            what_changed=what_changed,
            data_used=data_used,
            possible_factors=factors,
            next_steps=next_steps,
            dedupe_key="hr-above-baseline",
        )
