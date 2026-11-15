"""A reseed (`seed(force=True)`, i.e. `npm run reseed`) must reset the rehearsal state.

Uses its own throwaway DB so the shared session DB is untouched.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_db():
    old = os.environ.get("ASTROCARE_DB_PATH")
    os.environ["ASTROCARE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="astrocare-reseed-")) / "reseed.db")
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("ASTROCARE_DB_PATH", None)
        else:
            os.environ["ASTROCARE_DB_PATH"] = old


def _count(table: str) -> int:
    from server.core import db
    with db.connect() as conn:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def test_reseed_resets_rehearsal_state_but_keeps_reference_index(fresh_db):
    from server.core.seed import seed
    from server.features.assistant import store
    from server.features.assistant.permissions import DEFAULT_PERMISSIONS
    from server.main import app

    seed(force=True)
    with TestClient(app) as c:
        # --- a rehearsal --------------------------------------------------------
        c.post("/api/reports/items", json={"kind": "note", "title": "rehearsal", "text": "x", "sourceFeature": "assistant"})
        rep = c.post("/api/reports", json={"sections": ["summary"], "itemIds": []}).json()
        c.post(f"/api/reports/{rep['id']}/queue")
        c.post("/api/comms/simulate-window")
        c.post("/api/reports", json={"sections": ["summary"], "itemIds": []})  # a second one, left in the outbox
        c.post(f"/api/reports/{c.get('/api/reports').json()[0]['id']}/queue")
        c.put("/api/assistant/permissions", json={"assistant": {"checkins": True}, "report": {"checkins": True}})
        c.post("/api/relax/sessions", json={"sceneId": "ocean-shore", "audioMode": "none", "durationMin": 3, "stressBefore": 7})
        store.log_answer("rehearsal question", 1200, "fallback", False)
        with store.db.connect() as conn:  # one indexed reference passage
            conn.execute(
                "INSERT INTO assistant_chunks (id, source_id, title, url, chunk_index, text, content_hash, embed_model,"
                " embedding) VALUES ('ref-0', 'ref', 'Ref', NULL, 0, 'text', 'h', 'm', '[0.1]')"
            )
        assert _count("report_items") >= 1 and _count("comms_windows") == 1 and _count("assistant_log") == 1
        assert c.get("/api/comms").json()["simulatedWindow"] is True

    # --- reseed ---------------------------------------------------------------
    seed(force=True)

    with TestClient(app) as c:
        assert c.get("/api/reports/items?pending=true").json() == []
        assert {r["id"] for r in c.get("/api/reports").json()} == {"rep-135", "rep-141", "rep-142"}
        assert c.get("/api/status").json()["outboxCount"] == 0
        comms = c.get("/api/comms").json()
        assert comms["simulatedWindow"] is False and comms["lastWindowTs"] is None and comms["queuedCount"] == 0
        assert c.get("/api/assistant/permissions").json() == DEFAULT_PERMISSIONS
        assert {s["id"] for s in c.get("/api/relax/sessions").json()} == {"relax-136", "relax-139", "relax-141"}
        assert _count("assistant_log") == 0
        assert _count("assistant_chunks") == 1  # the reference index survives: no re-ingest needed


def _demo_state_module():
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "scripts" / "demo_state.py"
    spec = importlib.util.spec_from_file_location("demo_state", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_state_is_green_right_after_a_reseed_and_flags_a_rehearsal_leftover(fresh_db):
    from server.core.seed import seed
    from server.features.assistant.permissions import set_permissions
    from server.rules.engine import run_rules

    seed(force=True)
    run_rules()  # what `npm run reseed` does
    ds = _demo_state_module()
    from server.core import live_feed
    results = ds.run_state_checks(log=lambda _line: None)
    assert [name for name, ok, _ in results if not ok] == ["Live feed running"]  # no server in tests
    assert len(results) == 10  # incl. "Cabin readings fresh"

    live_feed.tick()  # what the running server does every minute
    results = ds.run_state_checks(log=lambda _line: None)
    assert [(name, ok) for name, ok, _ in results if not ok] == [], results

    set_permissions({"report": {"checkins": True}})
    bad = [name for name, ok, _ in ds.run_state_checks(log=lambda _line: None) if not ok]
    assert bad == ["Assistant permissions at defaults"]
