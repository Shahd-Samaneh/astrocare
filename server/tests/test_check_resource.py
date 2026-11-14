"""Tests for check_resource against the real seeded inventory and profile.

The seeded profile (crew c2) is allergic to Penicillin; resources come from
data/simulated/resources.json via the seeded DB.
"""
from __future__ import annotations

from server.core import db
from server.core.config import utcnow
from server.core.models import NextStep, Profile, Resource
from server.rules.resources import check_resource


def _inventory():
    resources = [Resource.model_validate(r) for r in db.query("resources")]
    profile = Profile.model_validate(db.query("profiles", limit=1)[0])
    return resources, profile, utcnow()


def _check(resource_id, text="Take as directed"):
    resources, profile, now = _inventory()
    return check_resource(NextStep(text=text, resource_id=resource_id), profile, resources, now)


def test_amoxicillin_allergy_conflict_locked(client):
    s = _check("med-03")
    assert s.availability == "allergy_conflict"
    assert s.locked_for_cmo is True


def test_ibuprofen_out_of_stock_locked(client):
    s = _check("med-02")
    assert s.availability == "out_of_stock"
    assert s.locked_for_cmo is True


def test_melatonin_expired_locked(client):
    s = _check("med-06")
    assert s.availability == "expired"
    assert s.locked_for_cmo is True


def test_zolpidem_low_counts_as_available_locked(client):
    s = _check("med-07")
    assert s.availability == "available"  # status "low" is still available
    assert s.locked_for_cmo is True


def test_paracetamol_available_locked(client):
    s = _check("med-01")
    assert s.availability == "available"
    assert s.locked_for_cmo is True


def test_bp_cuff_available_not_locked(client):
    s = _check("eq-bp-cuff")
    assert s.availability == "available"
    assert s.locked_for_cmo is False  # equipment, not a medicine


def test_step_without_resource_id_unchanged(client):
    resources, profile, now = _inventory()
    step = NextStep(text="Rest and recheck")
    out = check_resource(step, profile, resources, now)
    assert out is step
    assert out.availability is None
    assert out.locked_for_cmo is False


def test_unknown_resource_id_out_of_stock(client):
    s = _check("does-not-exist")
    assert s.availability == "out_of_stock"


def test_does_not_mutate_input(client):
    resources, profile, now = _inventory()
    step = NextStep(text="Take", resource_id="med-01")
    check_resource(step, profile, resources, now)
    assert step.availability is None  # original untouched
    assert step.locked_for_cmo is False


def test_engine_fills_availability_on_stored_alert(client):
    alerts = client.get("/api/alerts").json()
    a = next(x for x in alerts if x["ruleId"] == "R-DATA-01")
    cuff = next((st for st in a["nextSteps"] if st.get("resourceId") == "eq-bp-cuff"), None)
    assert cuff is not None, "R-DATA-01 should link the bp cuff step to eq-bp-cuff"
    assert cuff["availability"] == "available"
    assert cuff["lockedForCMO"] is False
