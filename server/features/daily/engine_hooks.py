# Owner: Shahd
"""Run the rule engine after every Daily POST, then keep our alerts current.

    from .engine_hooks import run_daily_engine
    run_daily_engine()

1. `run_rules()`: the engine's existing run function. It creates new alerts and
   skips a rule whose alert is still open.
2. `sync_daily_alerts()`: for our two rules only (R-SLP-01, R-FAT-01), update the
   open alert in place instead of leaving it stale (contract §3 "one open alert
   per rule, each run updates it"):
     * whatChanged / dataUsed / possibleFactors / nextSteps from a fresh evaluation
     * missing recomputed (a check-in today, done or skipped, removes "Today's check-in")
     * R-FAT-01 retest: a test with context 'retest' + relatedAlertId after the
       alert's time sets status 'recheck' and appends "Retest at HH:MM: …".
       Never auto-closes: closing is a human decision.
     * "{alertId}" in action routes is replaced with the real alert id.
This is a workaround until the engine updates open alerts itself
(docs/proposals/daily-contracts.md §3).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from server.core import db
from server.core.config import parse_ts
from server.core.status import mission_clock
from server.rules.base import RuleContext
from server.rules.engine import run_rules
from server.rules.r_fat_01_fatigue_pattern import ALERT_ID_TOKEN, FatiguePatternRule, fatigue_missing
from server.rules.r_slp_01_short_sleep import ShortSleepRule

from .attention_stats import DailyNextStep, baseline_from, load_tests, within

log = logging.getLogger("astrocare.daily")
RETEST_PREFIX = "Retest at "


def run_daily_engine(now: datetime | None = None) -> None:
    ctx = RuleContext(now=now)
    run_rules(ctx)
    sync_daily_alerts(ctx)


def open_alert(rule_id: str) -> dict[str, Any] | None:
    rows = db.query("alerts", "rule_id = ? AND status != 'closed'", (rule_id,), order_by="ts DESC", limit=1)
    return rows[0] if rows else None


def _dump_steps(steps: list, alert_id: str) -> list[dict[str, Any]]:
    out = []
    for s in steps:
        d = DailyNextStep.model_validate(s.model_dump() if hasattr(s, "model_dump") else s).model_dump()
        if d.get("action") and ALERT_ID_TOKEN in d["action"]["route"]:
            d["action"]["route"] = d["action"]["route"].replace(ALERT_ID_TOKEN, alert_id)
        out.append(d)
    return out


def _strip_retest_lines(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not line.startswith(RETEST_PREFIX)).strip()


def retest_lines(alert: dict[str, Any]) -> list[str]:
    """One line per retest linked to this alert and done after the alert was raised."""
    tests = load_tests()
    alert_ts = parse_ts(alert["ts"])
    retests = sorted(
        (t for t in tests
         if t.context == "retest" and t.related_alert_id == alert["id"] and parse_ts(t.ts) >= alert_ts),
        key=lambda t: t.ts,
    )
    lines = []
    for t in retests:
        base = baseline_from(tests, parse_ts(t.ts))
        w = within(t.median_ms, base)
        verdict = "no baseline yet" if w is None else ("within your usual range" if w else "outside your usual range")
        hhmm = mission_clock(parse_ts(t.ts))[0][-5:]  # mission time (MET) HH:MM
        lines.append(f"{RETEST_PREFIX}{hhmm}: median {t.median_ms:.0f} ms ({verdict})")
    return lines


def sync_daily_alerts(ctx: RuleContext | None = None) -> None:
    ctx = ctx or RuleContext()
    for rule in (ShortSleepRule(), FatiguePatternRule()):
        alert = open_alert(rule.id)
        if not alert:
            continue
        try:
            draft = rule.evaluate(ctx)
        except Exception:  # never break a POST because of a rule
            log.exception("Rule %s failed during sync", rule.id)
            continue

        fields: dict[str, Any] = {}
        if draft is not None:
            base_text = draft.what_changed
            fields.update(
                data_used=draft.data_used, missing=draft.missing, possible_factors=draft.possible_factors,
                sources=draft.sources or list(rule.sources),
                next_steps=_dump_steps(draft.next_steps, alert["id"]),
            )
        else:  # the condition no longer holds: keep the alert open, refresh only what we can
            base_text = _strip_retest_lines(alert["what_changed"] or "")
            fields["next_steps"] = _dump_steps(alert.get("next_steps") or [], alert["id"])

        if rule.id == FatiguePatternRule.id:
            fields["missing"] = fatigue_missing(ctx)
            lines = retest_lines(alert)
            if lines:
                fields["status"] = "recheck"
                base_text = "\n".join([base_text, *lines])

        fields["what_changed"] = base_text
        db.update("alerts", alert["id"], fields)
