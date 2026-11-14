"""Resource availability for alert next-steps.

check_resource stamps a NextStep with the availability of the resource it
references, and locks any medicine step for the CMO. The engine runs it on every
step before storing an alert, so rules never call it themselves.

Source: Full Plan §9 — availability is one of available / out_of_stock /
expired / allergy_conflict, and any step involving a medicine is always
lockedForCMO = true.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from server.core.models import NextStep, Profile, Resource


def _expired_by_date(expiry: Optional[str], now: datetime) -> bool:
    """True when `expiry` (ISO date) is strictly before now's date."""
    if not expiry:
        return False
    try:
        return date.fromisoformat(expiry[:10]) < now.date()
    except ValueError:
        return False


def check_resource(step: NextStep, profile: Optional[Profile], resources: list[Resource], now: datetime) -> NextStep:
    """Return a copy of `step` with `availability` set (and medicines CMO-locked).

    Safety-first order: allergy conflict, then expired, then out of stock, else
    available ("low" stock still counts as available). The input is never mutated.
    """
    if step.resource_id is None:
        return step  # nothing to check

    resource = next((r for r in resources if r.id == step.resource_id), None)
    if resource is None:
        return step.model_copy(update={"availability": "out_of_stock"})

    allergies = {a.lower() for a in (profile.allergies if profile else [])}
    contraindicated = {a.lower() for a in resource.contraindicated_allergies}
    if allergies & contraindicated:
        availability = "allergy_conflict"
    elif resource.status == "expired" or _expired_by_date(resource.expiry, now):
        availability = "expired"
    elif resource.status == "out_of_stock" or resource.qty <= 0:
        availability = "out_of_stock"
    else:
        availability = "available"

    locked = step.locked_for_cmo or resource.kind == "medicine"
    return step.model_copy(update={"availability": availability, "locked_for_cmo": locked})
