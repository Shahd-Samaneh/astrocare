"""Tests for GET /api/cabin/latest (cabin status for the Today screen).

These seed controlled cabin_readings directly through the db layer, then restore
the originally seeded rows so the shared session database is left untouched.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

from server.core import db
from server.core.config import iso, utcnow
from server.core.models import CABIN_METRICS
from server.core.simulator import UNITS

CABIN_UNITS = {"co2": "mmHg", "cabin_temp": "°C", "noise": "dBA", "humidity": "%"}


def _delete(metric: str) -> None:
    from server.core.db import connect

    with connect() as conn:
        conn.execute("DELETE FROM cabin_readings WHERE metric = ?", (metric,))


def _reading(metric: str, value: float, ts) -> dict:
    return {
        "id": db.new_id("cr-test"), "metric": metric, "value": value,
        "unit": UNITS[metric], "ts": iso(ts), "source": "simulated",
    }


@contextmanager
def _isolated_metric(metric: str):
    """Replace all rows for a cabin metric for the duration of the test."""
    saved = db.query("cabin_readings", "metric = ?", (metric,))
    _delete(metric)
    try:
        yield
    finally:
        _delete(metric)
        if saved:
            db.insert_many("cabin_readings", saved)


def _entry(client, metric: str) -> dict:
    data = {e["metric"]: e for e in client.get("/api/cabin/latest").json()}
    return data[metric]


def test_shape_one_entry_per_metric(client):
    entries = client.get("/api/cabin/latest").json()
    assert {e["metric"] for e in entries} == set(CABIN_METRICS)
    allowed = {"usual", "above_usual", "below_usual", "missing"}
    for e in entries:
        assert e["status"] in allowed
        assert set(e) >= {"metric", "value", "unit", "ts", "status"}
        if e["status"] != "missing":
            assert e["unit"] == CABIN_UNITS[e["metric"]]


def test_missing_when_no_readings(client):
    with _isolated_metric("humidity"):
        e = _entry(client, "humidity")
        assert e["status"] == "missing"
        assert e["value"] is None
        assert e["ts"] is None
        assert e["unit"] == "%"  # still reports the metric's unit


def test_cabin_temp_uses_fixed_range(client):
    now = utcnow()
    with _isolated_metric("cabin_temp"):
        db.insert("cabin_readings", _reading("cabin_temp", 22.0, now))
        assert _entry(client, "cabin_temp")["status"] == "usual"

        db.insert("cabin_readings", _reading("cabin_temp", 30.0, now + timedelta(minutes=1)))
        hot = _entry(client, "cabin_temp")
        assert hot["status"] == "above_usual"
        assert hot["value"] == 30.0  # returns the latest value, not the range

        db.insert("cabin_readings", _reading("cabin_temp", 15.0, now + timedelta(minutes=2)))
        assert _entry(client, "cabin_temp")["status"] == "below_usual"


def test_humidity_range(client):
    now = utcnow()
    with _isolated_metric("humidity"):
        db.insert("cabin_readings", _reading("humidity", 45.0, now))
        assert _entry(client, "humidity")["status"] == "usual"
        db.insert("cabin_readings", _reading("humidity", 70.0, now + timedelta(minutes=1)))
        assert _entry(client, "humidity")["status"] == "above_usual"
        db.insert("cabin_readings", _reading("humidity", 20.0, now + timedelta(minutes=2)))
        assert _entry(client, "humidity")["status"] == "below_usual"


def test_co2_uses_one_hour_average(client):
    now = utcnow()
    with _isolated_metric("co2"):
        # Last-hour average clearly below co2_max (3 mmHg) -> usual.
        for i in range(6):
            db.insert("cabin_readings", _reading("co2", 2.0, now - timedelta(minutes=50 - i)))
        assert _entry(client, "co2")["status"] == "usual"

    with _isolated_metric("co2"):
        # Last-hour average clearly above co2_max -> above_usual.
        for i in range(6):
            db.insert("cabin_readings", _reading("co2", 5.0, now - timedelta(minutes=50 - i)))
        latest = _reading("co2", 5.0, now)
        db.insert("cabin_readings", latest)
        hot = _entry(client, "co2")
        assert hot["status"] == "above_usual"
        assert hot["ts"] == latest["ts"]  # latest reading is what the screen shows


def test_co2_above_limit_only_on_hour_average_not_last_spike(client):
    now = utcnow()
    with _isolated_metric("co2"):
        # Many low readings over the hour, one brief spike last: the hour mean
        # stays under the limit, so status is usual despite the high latest value.
        for i in range(30):
            db.insert("cabin_readings", _reading("co2", 1.0, now - timedelta(minutes=59 - i)))
        db.insert("cabin_readings", _reading("co2", 9.0, now))
        assert _entry(client, "co2")["status"] == "usual"


def test_noise_uses_baseline_mean_and_sd(client):
    now = utcnow()
    with _isolated_metric("noise"):
        # Tight baseline around 50 dBA over the last few days.
        for i in range(12):
            db.insert("cabin_readings", _reading("noise", 50.0 + (i % 3), now - timedelta(hours=i + 1)))
        db.insert("cabin_readings", _reading("noise", 51.0, now))
        assert _entry(client, "noise")["status"] == "usual"

        db.insert("cabin_readings", _reading("noise", 85.0, now + timedelta(minutes=1)))
        assert _entry(client, "noise")["status"] == "above_usual"

        db.insert("cabin_readings", _reading("noise", 10.0, now + timedelta(minutes=2)))
        assert _entry(client, "noise")["status"] == "below_usual"


def test_stale_uses_the_vitals_rule(client):
    from server.core.config import threshold

    now = utcnow()
    stale_min = float(threshold("stale_minutes"))
    with _isolated_metric("humidity"):
        db.insert("cabin_readings", _reading("humidity", 45.0, now - timedelta(minutes=stale_min - 1)))
        e = _entry(client, "humidity")
        assert e["stale"] is False and e["ageMinutes"] in (int(stale_min) - 1, int(stale_min))
        _delete("humidity")
        db.insert("cabin_readings", _reading("humidity", 45.0, now - timedelta(minutes=stale_min + 5)))
        e = _entry(client, "humidity")
        assert e["stale"] is True and e["status"] == "usual"  # stale is separate from the range status


def test_limits_only_where_thresholds_yaml_has_a_real_source(client):
    from server.core.config import threshold, threshold_entry

    data = {e["metric"]: e for e in client.get("/api/cabin/latest").json()}
    co2 = data["co2"]["limit"]
    assert co2["min"] is None and co2["max"] == threshold("co2_max")
    assert co2["windowMinutes"] == threshold("co2_avg_window_minutes")
    assert co2["source"] == threshold_entry("co2_max").source and co2["sourceLabel"] == "NASA-STD-3001 [V2 6004]"
    assert co2["name"] is None and co2["healthMin"] is None
    for m in ("cabin_temp", "humidity"):
        lim = data[m]["limit"]
        assert (lim["min"], lim["max"]) == (threshold(f"{m}_min"), threshold(f"{m}_max"))
        assert lim["sourceLabel"] == "NASA-STD-3001 [V2 6013]" and lim["windowMinutes"] is None
        assert lim["name"] == "Comfort zone"
        assert (lim["healthMin"], lim["healthMax"]) == (threshold(f"{m}_health_min"), threshold(f"{m}_health_max"))
        assert lim["healthSourceLabel"] == "NASA-STD-3001 [V2 6012]"
    assert data["noise"]["limit"] is None  # team-decision SD multiplier, no sourced number


def test_no_limit_when_a_bound_has_no_real_source(client, monkeypatch):
    from server.core import config
    from server.features.monitoring import router

    patched = dict(config.thresholds())
    patched["humidity_max"] = config.Threshold(value=60, unit="%", source="TODO", note="")
    monkeypatch.setattr(router, "thresholds", lambda: patched)
    data = {e["metric"]: e for e in client.get("/api/cabin/latest").json()}
    assert data["humidity"]["limit"] is None
    assert data["cabin_temp"]["limit"] is not None


def test_6012_and_6013_entries_trace_to_tb002_rev_b():
    from server.core.config import thresholds

    t = thresholds()
    for key in ("cabin_temp_min", "cabin_temp_max", "humidity_min", "humidity_max"):
        assert "[V2 6013]" in t[key].source and "OCHMO-TB-002 Rev B" in t[key].source and "p. 4 and p. 8" in t[key].source
        assert "crew-health limit is [V2 6012] 18–27 °C, 25–75 %" in t[key].note
    health = {"cabin_temp_health_min": 18, "cabin_temp_health_max": 27, "humidity_health_min": 25, "humidity_health_max": 75}
    for key, value in health.items():
        assert t[key].value == value and "[V2 6012]" in t[key].source and "OCHMO-TB-002 Rev B" in t[key].source


def test_health_limits_are_not_used_by_any_rule():
    from pathlib import Path

    rules = Path(__file__).resolve().parents[1] / "rules"
    for py in rules.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "_health_min" not in text and "_health_max" not in text, py.name


def test_health_limit_hidden_when_it_has_no_real_source(client, monkeypatch):
    from server.core import config
    from server.features.monitoring import router

    patched = dict(config.thresholds())
    patched["humidity_health_max"] = config.Threshold(value=75, unit="%", source="TODO", note="")
    monkeypatch.setattr(router, "thresholds", lambda: patched)
    data = {e["metric"]: e for e in client.get("/api/cabin/latest").json()}
    assert data["humidity"]["limit"]["name"] == "Comfort zone"  # the 6013 range still shows
    assert data["humidity"]["limit"]["healthMin"] is None and data["humidity"]["limit"]["healthSourceLabel"] is None
    assert data["cabin_temp"]["limit"]["healthMax"] == 27
