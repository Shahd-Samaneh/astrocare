"""Rule engine: discovery, the example stale-data rule, and de-duplication."""
from server.core.config import threshold
from server.rules.base import RuleContext
from server.rules.engine import discover_rules, run_rules


def test_example_rule_is_discovered():
    ids = [r.id for r in discover_rules()]
    assert "R-DATA-01" in ids


def test_thresholds_have_sources():
    from server.core.config import thresholds

    for name, t in thresholds().items():
        assert t.source, f"threshold {name} has no source"
    assert threshold("stale_minutes") == 120
    assert threshold("co2_max") == 3  # sourced before the demo (NASA OCHMO TB-004)


def test_stale_rule_fires_on_skin_temp(client):  # client fixture seeds the DB
    alerts = client.get("/api/alerts").json()
    stale = [a for a in alerts if a["ruleId"] == "R-DATA-01"]
    assert stale, "expected an alert from the stale-data rule"
    a = stale[0]
    assert a["level"] == "info"
    assert "Skin temperature" in a["title"]
    assert a["missing"] and a["nextSteps"]
    assert "lockedForCMO" in a["nextSteps"][0]


def test_rule_does_not_fire_without_stale_data(client):
    from server.rules.r_data_01_stale import StaleDataRule

    ctx = RuleContext()
    # Pretend "now" is 30 minutes after the last skin reading: nothing is stale.
    last = ctx.latest("skin_temp")
    from datetime import timedelta

    from server.core.config import parse_ts

    assert StaleDataRule().evaluate(RuleContext(now=parse_ts(last.ts) + timedelta(minutes=30))) is None


def test_engine_does_not_duplicate_open_alerts(client):
    before = len(client.get("/api/alerts").json())
    run_rules()
    assert len(client.get("/api/alerts").json()) == before
