"""R-CAB-02 · Cabin temperature or humidity outside the usual range.

Looks at the latest fresh reading (not older than `stale_minutes`; older data is
R-DATA-01's job) of cabin temperature and of cabin humidity, the same value the
Today tile shows:

  * outside the [V2 6013] comfort zone (`cabin_temp_min/max`, `humidity_min/max`) -> info
  * outside the wider [V2 6012] crew-health limit (`*_health_min/max`)            -> review

Both metrics go into one alert (one open alert per rule); the level is the higher of
the two. A limit is only used when thresholds.yaml gives it a number and a real source.
Escalation note: while an info alert is open, the engine's dedupe keeps it open rather
than adding a second (review) alert; the tile still shows the current value and steps.

It never names a cause. Next steps come from server/features/monitoring/cabin_guidance.py
("temperature_out" / "humidity_out", the same lists the Today tiles show).

Source: NASA-STD-3001 Vol. 2 Rev D [V2 6013] / [V2 6012], via NASA OCHMO-TB-002 Rev B (ECLSS).
"""
from __future__ import annotations

from server.core.config import has_real_source
from server.core.models import NextStep, NextStepAction
from server.features.monitoring import cabin_guidance

from .base import AlertDraft, Rule, RuleContext

# metric -> (label, comfort min/max keys, health min/max keys, guidance key)
_METRICS = {
    "cabin_temp": ("temperature", ("cabin_temp_min", "cabin_temp_max"),
                   ("cabin_temp_health_min", "cabin_temp_health_max"), "temperature_out"),
    "humidity": ("humidity", ("humidity_min", "humidity_max"),
                 ("humidity_health_min", "humidity_health_max"), "humidity_out"),
}
FACTOR = "possible link, not a confirmed cause"


def _limits(ctx: RuleContext, keys: tuple[str, str]) -> tuple[float, float] | None:
    t = ctx.thresholds
    if not all(k in t and t[k].value is not None and has_real_source(t[k]) for k in keys):
        return None
    return float(t[keys[0]].value), float(t[keys[1]].value)


class CabinTempHumidityRule(Rule):
    id = "R-CAB-02"
    name = "Cabin temperature or humidity outside the usual range"
    sources = [
        "NASA-STD-3001 Vol. 2 Rev D [V2 6013] Crew Performance Environmental Zone, via NASA OCHMO-TB-002 Rev B (ECLSS)",
        "NASA-STD-3001 Vol. 2 Rev D [V2 6012] Crew Health Environmental Limits, via NASA OCHMO-TB-002 Rev B (ECLSS)",
        "config/thresholds.yaml: cabin_temp_min/max, humidity_min/max, cabin_temp_health_min/max, "
        "humidity_health_min/max, stale_minutes",
    ]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        fresh_hours = float(ctx.threshold("stale_minutes")) / 60
        changes: list[str] = []
        data_used: list[str] = []
        missing: list[str] = []
        keys: list[str] = []
        levels: list[str] = []

        for metric, (label, comfort_keys, health_keys, gkey) in _METRICS.items():
            comfort = _limits(ctx, comfort_keys)
            if comfort is None:
                continue  # no sourced comfort zone: cannot judge (same as the tile)
            readings = ctx.cabin(metric, hours=fresh_hours)
            if not readings:
                missing.append(f"Recent cabin {label} reading")
                continue
            latest = readings[-1]
            lo, hi = comfort
            if lo <= latest.value <= hi:
                continue
            health = _limits(ctx, health_keys)
            u = "%" if latest.unit == "%" else f" {latest.unit}"
            change = f"Cabin {label} is {latest.value:g}{u}, outside the comfort zone {lo:g}–{hi:g}{u} [V2 6013]"
            if health and not (health[0] <= latest.value <= health[1]):
                change += f" and outside the crew-health limit {health[0]:g}–{health[1]:g}{u} [V2 6012]"
                levels.append("review")
            else:
                levels.append("info")
            changes.append(change + ".")
            data_used.append(latest.id)
            keys.append(gkey)

        if not keys:
            return None

        factors = []
        if "temperature_out" in keys:
            factors += [f"Cabin thermal control or air circulation settings ({FACTOR})",
                        f"Crew activity or equipment heat in the module ({FACTOR})"]
        if "humidity_out" in keys:
            factors += [f"Humidity control performance ({FACTOR})",
                        f"Crew activity or exercise in the module ({FACTOR})"]

        steps: list[NextStep] = []
        for key in keys:  # shared steps (e.g. "inform life support") are listed once
            steps += [s for s in cabin_guidance.next_steps(key) if s.text not in {x.text for x in steps}]
        steps.append(NextStep(text="Add this alert to the report",
                              action=NextStepAction(label="Open reports", route="/reports")))

        return AlertDraft(
            level="review" if "review" in levels else "info",
            title="Cabin temperature or humidity outside the usual range",
            what_changed=" ".join(changes),
            data_used=data_used,
            missing=missing,
            possible_factors=factors,
            next_steps=steps,
            sources=[*self.sources, *cabin_guidance.sources(*keys)],
            dedupe_key="cab-temp-humidity",
        )
