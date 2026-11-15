"""Bone & muscle: Today tile rule, GET /api/bone/estimate (illustrative), sourced thresholds."""
from __future__ import annotations

import re

from server.core import db
from server.core.config import REFERENCES_DIR, has_real_source, thresholds
from server.features.monitoring import bone


def _tile(client) -> dict:
    return next(s for s in client.get("/api/body-systems").json() if s["id"] == "bone_muscle")


# ---- thresholds come from the NASA reference ---------------------------------------
def test_bone_loss_thresholds_are_sourced_from_the_nasa_reference():
    t = thresholds()
    lo, hi = t["bone_loss_pct_per_month_min"], t["bone_loss_pct_per_month_max"]
    assert (lo.value, hi.value) == (1, 1.5)
    for entry in (lo, hi):
        assert has_real_source(entry)
        assert "references/nasa-bone-risk.txt" in entry.source
    ref = (REFERENCES_DIR / "nasa-bone-risk.txt").read_text(encoding="utf-8")
    assert "lose between 1% and 1.5% of their density each month" in ref


# ---- Today tile -------------------------------------------------------------------------
def test_tile_is_stable_with_counts_and_reason(client):
    tile = _tile(client)
    assert tile["status"] == "stable"  # seed: 2 planned past days (140, 141), 1 done + 1 partial
    assert tile["text"] == "1 done, 1 partial this week"
    assert tile["reason"] == "Exercise is the main countermeasure for bone and muscle loss"
    assert tile["alertId"] is None


def test_open_rex01_alert_forces_review(client):
    db.insert("alerts", {
        "id": "al-ex-test", "rule_id": "R-EX-01", "level": "info", "ts": "2026-11-14T00:00:00Z",
        "title": "Exercise test", "what_changed": "test", "data_used": [], "missing": [],
        "possible_factors": [], "next_steps": [], "status": "new", "sources": [],
    })
    try:
        tile = _tile(client)
        assert tile["status"] == "review"
        assert tile["alertId"] == "al-ex-test"
    finally:
        with db.connect() as conn:
            conn.execute("DELETE FROM alerts WHERE id = ?", ("al-ex-test",))


def _counts(monkeypatch, statuses: dict[int, str | None]) -> dict[str, int]:
    plans = [{"id": f"p{d}", "day": d} for d in statuses]
    monkeypatch.setattr(bone, "load_plan_items", lambda: plans)
    monkeypatch.setattr(bone, "latest_log", lambda pid: {"status": s} if (s := statuses[int(pid[1:])]) else None)
    return bone.week_adherence(today=150)


def test_most_planned_days_rule(monkeypatch):
    # window = days 144..149; today (150) and earlier days are ignored
    c = _counts(monkeypatch, {143: "skipped", 144: "done", 145: "partial", 146: "skipped", 147: None, 150: None})
    assert c == {"planned": 4, "done": 1, "partial": 1, "skipped": 1, "not_logged": 1}
    assert not bone.most_days_exercised(c)  # 2 of 4 is not "most"
    c = _counts(monkeypatch, {144: "done", 145: "partial", 146: "skipped"})
    assert bone.most_days_exercised(c)  # 2 of 3
    assert not bone.most_days_exercised({"planned": 0, "done": 0, "partial": 0, "skipped": 0, "not_logged": 0})


# ---- illustrative estimate -----------------------------------------------------------------
def test_estimate_for_mission_day_142():
    est = bone.bone_estimate(142)
    assert est.available is True
    assert est.months_in_flight == 4.7  # 142 / (365.25 / 12)
    assert (est.loss_pct_per_month_min, est.loss_pct_per_month_max) == (1, 1.5)
    assert (est.estimated_loss_pct_min, est.estimated_loss_pct_max) == (4.7, 7.0)
    assert "references/nasa-bone-risk.txt" in est.source
    assert "not a measurement" in est.note and "DEXA" in est.note


def test_endpoint_matches_current_mission_day(client):
    est = client.get("/api/bone/estimate").json()
    day = client.get("/api/status").json()["missionDay"]
    assert est["available"] is True and est["missionDay"] == day
    assert est["label"] == "Illustrative, not a measurement"


def test_estimate_unavailable_without_sourced_values(monkeypatch):
    t = dict(thresholds())
    t.pop("bone_loss_pct_per_month_max")
    monkeypatch.setattr(bone, "thresholds", lambda: t)
    est = bone.bone_estimate(142)
    assert est.available is False and est.estimated_loss_pct_min is None


def test_no_medication_or_supplement_advice():
    text = " ".join(str(v) for v in bone.bone_estimate(142).model_dump().values())
    assert not re.search(r"medic|supplement|bisphosph|calcium|vitamin|drug", text, re.I)
