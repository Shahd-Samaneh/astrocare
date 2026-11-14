"""Rule engine: discovers every `r_*.py` module in this package, runs its rules,
and stores new alerts.

    from server.rules.engine import run_rules
    new_alerts = run_rules()          # evaluates all rules "now"
"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import uuid

from server.core import db
from server.core.config import iso
from server.core.models import Alert

from .base import Rule, RuleContext

log = logging.getLogger("astrocare.rules")


def discover_rules() -> list[Rule]:
    """Instantiate every concrete Rule subclass found in rules/r_*.py."""
    import server.rules as pkg

    rules: list[Rule] = []
    for mod_info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if not mod_info.name.startswith("r_"):
            continue
        module = importlib.import_module(f"{pkg.__name__}.{mod_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Rule) and obj is not Rule and not inspect.isabstract(obj) and obj.__module__ == module.__name__:
                rules.append(obj())
    return rules


def _is_open_duplicate(rule_id: str, key: str) -> bool:
    return db.count("alerts", "rule_id = ? AND dedupe_key = ? AND status != 'closed'", (rule_id, key)) > 0


def run_rules(ctx: RuleContext | None = None) -> list[Alert]:
    """Evaluate all rules and store the alerts they produce. Returns the new alerts."""
    ctx = ctx or RuleContext()
    created: list[Alert] = []
    for rule in discover_rules():
        try:
            draft = rule.evaluate(ctx)
        except Exception:  # one broken rule must never stop the others
            log.exception("Rule %s failed", rule.id)
            continue
        if draft is None:
            continue
        key = draft.dedupe_key or draft.title
        if _is_open_duplicate(rule.id, key):
            continue
        alert = Alert(
            id=f"al-{uuid.uuid4().hex[:10]}", rule_id=rule.id, level=draft.level, ts=iso(ctx.now),
            title=draft.title, what_changed=draft.what_changed, data_used=draft.data_used,
            missing=draft.missing, possible_factors=draft.possible_factors, next_steps=draft.next_steps,
            status="new", sources=draft.sources or list(rule.sources),
        )
        db.insert("alerts", {**alert.model_dump(), "dedupe_key": key})
        created.append(alert)
    return created
