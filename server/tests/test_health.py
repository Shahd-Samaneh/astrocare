"""Smoke tests: core endpoints and every feature stub answers."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_status_shape(client):
    s = client.get("/api/status").json()
    assert s["simulated"] is True
    assert s["missionDay"] == 142
    assert s["met"].startswith("142:")
    assert s["crewInitials"] == "C2"
    assert s["outboxCount"] == 2
    assert s["localMode"] is True


def test_unknown_api_route_is_404(client):
    assert client.get("/api/does-not-exist").status_code == 404


def test_all_stub_endpoints_respond(client):
    for path in [
        "/api/profile", "/api/readings", "/api/readings/latest", "/api/cabin", "/api/sensors",
        "/api/alerts", "/api/resources", "/api/sleep", "/api/tests", "/api/checkins",
        "/api/exercise/plan", "/api/today/plan", "/api/assistant/info", "/api/reports",
        "/api/comms", "/api/relax/scenes", "/api/relax/sessions",
    ]:
        assert client.get(path).status_code == 200, path


def test_latest_marks_stale_and_missing(client):
    q = {x["metric"]: x["quality"] for x in client.get("/api/readings/latest").json()}
    assert q["skin_temp"] == "stale"
    assert q["bp_sys"] == "missing"
    assert q["heart_rate"] in ("good", "low")


def test_manual_reading_and_ack(client):
    r = client.post("/api/readings/manual", json={"metric": "bp_sys", "value": 118})
    assert r.status_code == 201
    assert r.json()["source"] == "manual"

    alert = client.get("/api/alerts").json()[0]
    acked = client.post(f"/api/alerts/{alert['id']}/ack").json()
    assert acked["status"] == "ack"


def test_posts_accept_camel_case(client):
    assert client.post("/api/checkins", json={"mood": 4, "stress": 2}).status_code == 201
    assert client.post("/api/tests", json={"trialsMs": [280, 300, 290, 610, 270]}).json()["test"]["lapses"] == 1
    assert client.post("/api/relax/sessions", json={
        "sceneId": "ocean-shore", "audioMode": "nature", "durationMin": 10, "stressBefore": 4,
    }).status_code == 201
    assert client.post("/api/reports", json={"sections": ["summary"], "itemIds": []}).json()["status"] == "ready"


def test_assistant_refuses_medication_questions(client, monkeypatch):
    from server.features.assistant import llm
    monkeypatch.setattr(llm, "ollama_cfg", lambda: {"url": "http://127.0.0.1:9", "chat_model": "x", "embed_model": "y"})
    assert client.post("/api/assistant/ask", json={"question": "What dose of ibuprofen?"}).json()["refused"] is True
    assert client.post("/api/assistant/ask", json={"question": "Can I take 200 mg?"}).json()["refused"] is True
    ok = client.post("/api/assistant/ask", json={"question": "How does microgravity affect sleep?"}).json()
    assert ok["refused"] is False
    assert ok["mode"] == "fallback"  # Ollama pointed at a dead port in tests
