"""Assistant tests (owner: Marah)."""
from __future__ import annotations

import pytest

from server.features.assistant import store
from server.features.assistant.permissions import DEFAULT_PERMISSIONS, get_permissions


@pytest.fixture
def reset_permissions(client):
    store.save_permissions(DEFAULT_PERMISSIONS)
    yield
    store.save_permissions(DEFAULT_PERMISSIONS)


# ---- permissions -------------------------------------------------------------
def test_permissions_defaults(client, reset_permissions):
    r = client.get("/api/assistant/permissions")
    assert r.status_code == 200
    body = r.json()
    assert body["assistant"]["checkins"] is False
    assert body["report"]["checkins"] is False
    assert body["assistant"]["vitals"] is True


def test_permissions_partial_put_merges(client, reset_permissions):
    r = client.put("/api/assistant/permissions", json={"report": {"checkins": True}})
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["checkins"] is True
    assert body["assistant"]["checkins"] is False  # untouched
    # the Python helper Noura imports sees the same value
    assert get_permissions()["report"]["checkins"] is True


def test_permissions_ignores_unknown_keys(client, reset_permissions):
    r = client.put("/api/assistant/permissions", json={"assistant": {"notePrivate": True, "sleep": False}})
    assert r.status_code == 200
    perms = get_permissions()
    assert "notePrivate" not in perms["assistant"]
    assert perms["assistant"]["sleep"] is False
