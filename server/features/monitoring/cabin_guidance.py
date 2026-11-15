"""What to do when a cabin value is unusual: the one place these steps are written.

Used by R-CAB-01 / R-CAB-02 / R-CAB-03 (alert next steps) and by GET /cabin/latest
(the "What to do" list on the Today cabin tiles), so the tile and the alert always say
the same thing.

Rules for this file:
  * operational steps only: never medication, never a diagnosis
  * no numbers here: limits live in config/thresholds.yaml with their sources
  * a cabin value is a *possible link, not a confirmed cause* for how the crew feels
  * `resource_id` must exist in data/simulated/resources.json; it is checked with
    rules.resources.check_resource (the engine does it for alerts, cabin_latest for tiles)
  * every step has a `source` id from SOURCES

Resources: the earplug step uses eq-earplugs and the portable CO₂ reading uses
eq-co2-monitor (both simulated items in resources.json). Never set a resource_id that is
not in resources.json: an unknown id shows as "out of stock".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from server.core.models import NextStep, NextStepAction

# Short id -> full citation shown in an alert's sources.
SOURCES: dict[str, str] = {
    "ochmo-tb-004": "NASA OCHMO Technical Brief TB-004 Carbon Dioxide (NASA-STD-3001 Vol. 2 [V2 6004])",
    "ochmo-tb-002": "NASA OCHMO-TB-002 Rev B Environmental Control and Life Support System (ECLSS)",
    "ochmo-tb-002-exercise": "NASA OCHMO-TB-002 Rev B Environmental Control and Life Support System (ECLSS): "
                             "exercise increases CO₂, perspiration and metabolic heat output [V2 7041]",
    "nasa-hrp-sleep-risk": "NASA HRP sleep risk: noise and temperature can inhibit sleep "
                           "(references/nasa-hrp-sleep-risk.txt)",
    "team-decision": "Team decision (operational step, no published source)",
}

CHECKIN = NextStepAction(label="Open check-in", route="/daily#checkin")


@dataclass(frozen=True)
class GuidanceStep:
    text: str
    source: str  # key of SOURCES
    resource_id: Optional[str] = None
    action: Optional[NextStepAction] = None

    def to_next_step(self) -> NextStep:
        return NextStep(text=self.text, resource_id=self.resource_id, action=self.action)


# Guidance key -> steps, in the order the crew should do them.
GUIDANCE: dict[str, tuple[GuidanceStep, ...]] = {
    "co2_high": (
        GuidanceStep("Confirm with a portable CO₂ reading", "ochmo-tb-004", resource_id="eq-co2-monitor"),
        GuidanceStep("Inform the crew member responsible for life support", "ochmo-tb-004"),
        GuidanceStep("Move to a better-ventilated module", "ochmo-tb-004"),
        GuidanceStep("Postpone strenuous exercise for now (exercise raises CO₂ output)",
                     "ochmo-tb-002-exercise"),
        GuidanceStep("Log any headache in today's check-in", "ochmo-tb-004", action=CHECKIN),
    ),
    "temperature_out": (
        GuidanceStep("Inform the crew member responsible for life support", "ochmo-tb-002"),
        GuidanceStep("Adjust clothing layers", "team-decision"),
        GuidanceStep("Drink water as set in the mission plan", "team-decision"),
        GuidanceStep("Watch your sleep and focus today", "nasa-hrp-sleep-risk"),
    ),
    "humidity_out": (
        GuidanceStep("Inform the crew member responsible for life support", "ochmo-tb-002"),
        GuidanceStep("Log any dry eyes or dry skin in today's check-in", "team-decision", action=CHECKIN),
    ),
    "noise_high": (
        GuidanceStep("Use earplugs", "nasa-hrp-sleep-risk", resource_id="eq-earplugs"),
        GuidanceStep("Sleep in a quieter area if possible", "nasa-hrp-sleep-risk"),
        GuidanceStep("Log any effect on your sleep in today's check-in", "nasa-hrp-sleep-risk", action=CHECKIN),
    ),
}

# (cabin metric, GET /cabin/latest status) -> guidance key. Missing pairs have no guidance
# (e.g. low noise or low CO₂ is not a concern).
_KEY_FOR_STATUS: dict[tuple[str, str], str] = {
    ("co2", "above_usual"): "co2_high",
    ("cabin_temp", "above_usual"): "temperature_out",
    ("cabin_temp", "below_usual"): "temperature_out",
    ("humidity", "above_usual"): "humidity_out",
    ("humidity", "below_usual"): "humidity_out",
    ("noise", "above_usual"): "noise_high",
}

# Which rule raises the alert for each guidance key (for linking an open alert from a tile).
RULE_FOR_KEY = {"co2_high": "R-CAB-01", "temperature_out": "R-CAB-02", "humidity_out": "R-CAB-02",
                "noise_high": "R-CAB-03"}


def guidance_key(metric: str, status: str) -> Optional[str]:
    return _KEY_FOR_STATUS.get((metric, status))


def steps(key: str) -> list[GuidanceStep]:
    return list(GUIDANCE[key])


def next_steps(key: str) -> list[NextStep]:
    """The guidance as alert NextSteps (resource availability is stamped by the engine)."""
    return [s.to_next_step() for s in GUIDANCE[key]]


def sources(*keys: str) -> list[str]:
    """Full citations used by the given guidance keys, in first-use order, no duplicates."""
    out: list[str] = []
    for key in keys:
        for s in GUIDANCE[key]:
            if SOURCES[s.source] not in out:
                out.append(SOURCES[s.source])
    return out
