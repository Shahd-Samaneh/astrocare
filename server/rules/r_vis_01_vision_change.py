"""R-VIS-01 · Vision self-check changed since baseline (info).

There is no sensor for vision & fluid shift (SANS). The crew does a near-vision card and an
Amsler grid self-check (server/features/monitoring/vision.py). This rule fires when the latest
check differs from the baseline check:
  * the smallest readable line moved `vision_line_drop_min` lines (or more) towards larger text, or
  * wavy, blurred or missing lines were reported on the Amsler grid.
No change, or no checks at all: no alert (an overdue check is shown on the Today tile instead).

It never names a cause or a diagnosis: it lists possible factors and gives two steps only,
repeat the check tomorrow and add it to the report for the CMO (who arranges proper eye exams).
The comparison is the same function as GET /vision/summary, so the page and the alert agree.
"""
from __future__ import annotations

from server.core.models import NextStep, NextStepAction
from server.features.monitoring.vision import DISCLAIMER, vision_summary

from .base import AlertDraft, Rule, RuleContext


class VisionChangeRule(Rule):
    id = "R-VIS-01"
    name = "Vision self-check changed since baseline"
    sources = [
        "nasa-hrp-risks",
        "config/thresholds.yaml: vision_line_drop_min (trial value, team decision)",
    ]

    def evaluate(self, ctx: RuleContext) -> AlertDraft | None:
        s = vision_summary(ctx.now)
        if not s.changed:
            return None

        used = {e.latest.id: e.latest for e in s.eyes if e.latest} | {e.baseline.id: e.baseline for e in s.eyes if e.baseline}
        data_used = sorted(used)
        missing = [f"Self-check of the {e.eye} eye" for e in s.eyes if e.latest is None]
        missing.append("A proper eye exam (only the CMO can arrange it; this self-check does not diagnose)")

        return AlertDraft(
            level="info",
            title="Vision self-check: change reported",
            what_changed=(
                f"{'. '.join(s.changes)}. Compared with the baseline check on mission day "
                f"{s.baseline_mission_day}; latest check on mission day {s.last_mission_day}. {DISCLAIMER}"
            ),
            data_used=data_used,
            missing=missing,
            possible_factors=[
                "A different distance or lighting than at the baseline check",
                "Tired or dry eyes at the time of the check",
                "Eye changes that can happen in spaceflight (only a proper eye exam can tell)",
            ],
            next_steps=[
                NextStep(text="Repeat the check tomorrow",
                         action=NextStepAction(label="Open vision check", route="/vision")),
                NextStep(text="Add to report for the CMO",
                         action=NextStepAction(label="Open reports", route="/reports")),
            ],
            dedupe_key="vision-change",  # one open alert at a time; closing it is a human decision
        )
