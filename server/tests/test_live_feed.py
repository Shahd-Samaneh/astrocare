"""Demo live feed (server/core/live_feed.py). Own throwaway DB; the feed task itself never runs in tests."""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_db():
    old = os.environ.get("ASTROCARE_DB_PATH")
    os.environ["ASTROCARE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="astrocare-feed-")) / "feed.db")
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("ASTROCARE_DB_PATH", None)
        else:
            os.environ["ASTROCARE_DB_PATH"] = old


def _latest(c) -> dict[str, str]:
    return {x["metric"]: x["quality"] for x in c.get("/api/readings/latest").json()}


def test_feed_is_on_in_app_yaml_but_off_under_pytest():
    from server.core import live_feed
    assert live_feed.settings()["enabled"] is True
    assert live_feed.feed_enabled() is False


def test_tick_adds_good_in_band_readings_for_three_metrics_only(fresh_db):
    from server.core import db, live_feed
    from server.core.config import utcnow
    from server.core.seed import seed

    t0 = utcnow()
    seed(t0, force=True)
    base = db.query("profiles", limit=1)[0]["baseline"]
    def vitals(rows):  # cabin rows have no quality
        return [r for r in rows if "quality" in r]

    assert vitals(live_feed.tick(t0 + timedelta(minutes=1))) == []  # seed readings are fresh: nothing due yet
    rows = vitals(live_feed.tick(t0 + timedelta(minutes=5)))
    rows += vitals(live_feed.tick(t0 + timedelta(minutes=10)))
    assert sorted({r["metric"] for r in rows}) == ["heart_rate", "resp_rate", "spo2"]
    assert len(rows) == 6
    for r in rows:
        b = base[r["metric"]]
        assert abs(r["value"] - b["mean"]) <= 0.5 * b["sd"] + 1e-9, r
        assert r["quality"] == "good" and r["source"] == "simulated" and r["id"].startswith("live-")
    assert db.count("readings", "id LIKE 'live-%' AND metric IN ('skin_temp', 'bp_sys', 'bp_dia')") == 0
    assert db.get_meta(live_feed.HEARTBEAT_KEY)


def test_three_hours_of_feed_keeps_vitals_fresh_and_leaves_the_demo_story_alone(fresh_db):
    from server.core import db, live_feed
    from server.core.config import utcnow
    from server.core.seed import seed
    from server.features.daily.engine_hooks import run_daily_engine
    from server.main import app
    from server.rules.engine import run_rules

    now = utcnow()
    seeded = now - timedelta(hours=3)
    seed(seeded, force=True)
    run_rules()
    c = TestClient(app)  # no lifespan: the DB is exactly what we set up
    q = _latest(c)
    assert (q["heart_rate"], q["spo2"], q["resp_rate"]) == ("stale",) * 3  # without the feed

    t = seeded
    while t <= now:  # what the server does every 5 minutes for 3 h
        live_feed.tick(t)
        t += timedelta(minutes=5)

    q = _latest(c)
    assert (q["heart_rate"], q["spo2"], q["resp_rate"]) == ("good",) * 3
    assert q["skin_temp"] == "stale" and q["bp_sys"] == "missing" and q["bp_dia"] == "missing"

    run_rules()
    run_daily_engine()
    alerts = [a for a in c.get("/api/alerts").json() if a["status"] != "closed"]
    rules = {a["ruleId"] for a in alerts}
    assert "R-HR-01" not in rules and "R-SPO2-01" not in rules and "R-CAB-01" not in rules
    cabin = c.get("/api/cabin/latest").json()
    assert all(not e["stale"] and e["status"] == "usual" for e in cabin), cabin
    fat = [a for a in alerts if a["ruleId"] == "R-FAT-01"]
    assert len(fat) == 1 and fat[0]["level"] == "review" and fat[0]["missing"] == ["Today's check-in"]
    assert c.get("/api/status").json()["missionDay"] == 142
    assert db.count("readings", "id LIKE 'live-%'") == 3 * 36


def test_cabin_feed_every_15_min_stays_near_seed_and_inside_limits(fresh_db):
    from server.core import db, live_feed
    from server.core.config import threshold, utcnow
    from server.core.seed import seed

    t0 = utcnow()
    seed(t0, force=True)
    anchor = {m: db.query("cabin_readings", "metric = ?", (m,), order_by="ts DESC", limit=1)[0]["value"]
              for m in live_feed.CABIN_LIVE_METRICS}
    t = t0
    for _ in range(4 * 24):  # one day of ticks, every 15 min
        t += timedelta(minutes=15)
        live_feed.tick(t)
    live = db.query("cabin_readings", "id LIKE 'live-%'")
    assert len(live) == 4 * 24 * 4  # one per metric per tick
    for r in live:
        v, m = r["value"], r["metric"]
        assert r["source"] == "simulated"
        if m == "co2":
            assert v < threshold("co2_max")
        elif m in ("cabin_temp", "humidity"):
            assert threshold(f"{m}_min") < v < threshold(f"{m}_max")
        assert abs(v - anchor[m]) <= 3.0, r  # close to the latest seeded value (jitter = 0.25 x seeded SD)
    # not due again within 15 min
    assert [r for r in live_feed.tick(t + timedelta(minutes=10)) if "quality" not in r] == []


def test_cabin_feed_keeps_co2_under_limit_even_from_a_high_seed(fresh_db):
    from server.core import db, live_feed
    from server.core.config import iso, threshold, utcnow
    from server.core.seed import seed

    t0 = utcnow()
    seed(t0, force=True)
    db.insert("cabin_readings", {"id": "c-co2-high", "metric": "co2", "value": 4.5, "unit": "mmHg",
                                 "ts": iso(t0), "source": "simulated"})  # latest seeded value above the limit
    t = t0
    for _ in range(8):
        t += timedelta(minutes=15)
        rows = [r for r in live_feed.tick(t) if r["metric"] == "co2"]
        assert rows and rows[0]["value"] <= threshold("co2_max") - 0.1 + 1e-9
