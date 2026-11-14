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
    from datetime import timedelta

    from server.core.status import mission_day_start
    from server.rules.r_data_01_stale import StaleDataRule

    # Noon of the previous mission day: continuous metrics are fresh AND a blood
    # pressure spot check exists for that day, so neither branch fires. (Anchored
    # to the mission clock so an unrelated manual reading near "now" can't leak
    # in; a mid-day time keeps us clear of the ~6 h-stale skin_temp near now.)
    now = mission_day_start() - timedelta(hours=12)
    assert StaleDataRule().evaluate(RuleContext(now=now)) is None


def test_bp_missing_is_reported(client):
    from datetime import timedelta

    from server.core.status import mission_day_start
    from server.rules.r_data_01_stale import StaleDataRule

    # A few hours into the current mission day: skin_temp is stale and today's
    # blood pressure has not been taken. (Before "now", so the manual bp reading
    # another test inserts at real-now is excluded.)
    now = mission_day_start() + timedelta(hours=5)
    draft = StaleDataRule().evaluate(RuleContext(now=now))
    assert draft is not None
    assert draft.level == "info"
    text = " ".join(draft.missing).lower()
    assert "blood pressure" in text and "missing" in text  # bp named as missing
    assert "stale" in text  # a stale continuous metric is still labelled stale
    steps = " ".join(s.text.lower() for s in draft.next_steps)
    assert "cuff" in steps and "manual blood pressure" in steps
    assert "low battery" in text  # cuff sensor status surfaced in plain words


def test_alert_separates_stale_and_missing(client):
    alerts = client.get("/api/alerts").json()
    a = next(a for a in alerts if a["ruleId"] == "R-DATA-01")
    assert a["level"] == "info"
    joined = " ".join(a["missing"]).lower()
    assert "stale" in joined
    assert "blood pressure" in joined and "missing" in joined


def test_engine_does_not_duplicate_open_alerts(client):
    before = len(client.get("/api/alerts").json())
    run_rules()
    assert len(client.get("/api/alerts").json()) == before
