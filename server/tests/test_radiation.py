"""Radiation estimate: mission day × MSL RAD cruise rate, against the NASA career limit.

GET /api/radiation/estimate, the Today radiation tile and the report's radiation section.
"""
from __future__ import annotations

from server.core.config import REFERENCES_DIR, Threshold, has_real_source, thresholds
from server.features.monitoring import router as mon


def test_thresholds_are_sourced_and_cite_reference_files():
    t = thresholds()
    limit, rate = t["radiation_career_limit_msv"], t["radiation_deep_space_rate_msv_per_day"]
    assert (limit.value, limit.unit) == (600, "mSv")
    assert (rate.value, rate.unit) == (1.8, "mSv/day")
    assert has_real_source(limit) and has_real_source(rate)
    assert "[V1 4030]" in limit.source and "references/nasa-ochmo-radiation.txt" in limit.source
    assert "MSL" in rate.source and "references/nasa-msl-rad-cruise.txt" in rate.source
    assert "simulated estimate, not a dosimeter reading" in rate.note
    for ref in ("nasa-ochmo-radiation", "nasa-msl-rad-cruise", "csa-radiation-monitoring"):
        head = (REFERENCES_DIR / f"{ref}.txt").read_text(encoding="utf-8").splitlines()[:3]
        assert head[0].startswith("title: ") and head[1].startswith("url: ") and head[2] == f"id: {ref}"


def test_limit_text_is_in_the_reference():
    ochmo = (REFERENCES_DIR / "nasa-ochmo-radiation.txt").read_text(encoding="utf-8")
    assert "shall be less \nthan 600 mSv" in ochmo or "shall be less than 600 mSv" in ochmo
    msl = (REFERENCES_DIR / "nasa-msl-rad-cruise.txt").read_text(encoding="utf-8")
    assert "1.8 mSv per day" in msl


def test_endpoint_estimate_for_the_current_mission_day(client):
    est = client.get("/api/radiation/estimate").json()
    day = client.get("/api/status").json()["missionDay"]
    assert est["available"] is True
    assert est["missionDay"] == day
    assert est["rateMsvPerDay"] == 1.8 and est["careerLimitMsv"] == 600
    assert est["cumulativeMsv"] == int(day * 1.8 + 0.5)
    assert est["pctOfLimit"] == int(day * 1.8 / 600 * 100 + 0.5)
    assert est["withinLimit"] is True
    assert est["source"] == "simulated"
    assert est["label"] == "Estimate · simulated · MSL RAD rate"
    assert est["note"] == "No dosimeter connected; this is an estimate from a NASA-measured deep-space rate."
    assert est["limitSourceLabel"] == "NASA-STD-3001 [V1 4030]"
    assert est["rateSourceLabel"] == "NASA/JPL Mars Science Laboratory (MSL) RAD"


def test_neutron_share_is_only_an_iss_comparison(client):
    est = client.get("/api/radiation/estimate").json()
    assert est["comparison"] == "For comparison: on the ISS, neutrons are about 30% of the dose (CSA, CANS)"
    assert "references/csa-radiation-monitoring.txt" in est["comparisonSource"]
    assert "neutron" not in est["label"].lower() and "neutron" not in est["note"].lower()


def test_seeded_demo_day_values():
    est = mon.radiation_estimate(142)
    assert (est.cumulative_msv, est.pct_of_limit, est.within_limit) == (256, 43, True)  # 255.6 mSv, 42.6 %


def test_at_or_above_the_limit_is_review_without_an_invented_fraction():
    assert mon._radiation(333)[0] == "stable"  # 599.4 mSv: still below 600
    status, text, label = mon._radiation(334)  # 601.2 mSv
    assert (status, label) == ("review", "at or above career limit")
    assert text == "601 mSv · 100% of career limit (estimate)"


def test_unsourced_threshold_gives_no_estimate(monkeypatch):
    t = dict(thresholds())
    t["radiation_deep_space_rate_msv_per_day"] = Threshold(value=1.8, unit="mSv/day", source="TODO", note="")
    monkeypatch.setattr(mon, "thresholds", lambda: t)
    assert mon.radiation_estimate(142).available is False
    assert mon._radiation(142) == ("no_data", "No connected measurements", None)


def test_report_radiation_section(client):
    rep = client.post("/api/reports", json={"sections": ["radiation"]}).json()
    body = rep["sections"][0]["body"]
    day = client.get("/api/status").json()["missionDay"]
    assert body.startswith("Estimate · simulated · MSL RAD rate:")
    assert f"{int(day * 1.8 + 0.5)} mSv after {day} mission days" in body
    assert "NASA-STD-3001 [V1 4030]" in body and "within limit" in body
    assert "No dosimeter connected" in body
    assert "For comparison: on the ISS, neutrons are about 30% of the dose (CSA, CANS)." in body
    assert "not available yet" not in body
