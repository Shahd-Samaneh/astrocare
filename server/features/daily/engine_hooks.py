# Owner: Shahd
"""Run the rule engine after every Daily POST.

    from .engine_hooks import run_daily_engine
    run_daily_engine()

Calls the engine's existing `run_rules()`. Step 7 extends this with the in-place
update of our open alerts (the engine only skips duplicates today; see
docs/proposals/daily-contracts.md §3).
"""
from __future__ import annotations

from datetime import datetime

from server.rules.base import RuleContext
from server.rules.engine import run_rules


def run_daily_engine(now: datetime | None = None) -> None:
    run_rules(RuleContext(now=now))
