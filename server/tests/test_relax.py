"""Relax: scenes and sessions (owner: Noura)."""


def test_scenes_have_media_fields(client):
    scenes = client.get("/api/relax/scenes").json()
    assert len(scenes) >= 1
    s = scenes[0]
    for key in ("id", "name", "description", "audio", "image", "audioFiles"):
        assert key in s, key
    # no remote URLs: media is either null or served locally
    for sc in scenes:
        for url in (sc["image"], sc["audioFiles"]["nature"], sc["audioFiles"]["music"]):
            assert url is None or url.startswith("/api/relax/media/")


def test_session_without_stress_after_is_saved(client):
    r = client.post("/api/relax/sessions", json={
        "sceneId": "forest-stream", "audioMode": "nature", "durationMin": 5, "stressBefore": 7,
    })
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["stressAfter"] is None
    ids = [x["id"] for x in client.get("/api/relax/sessions").json()]
    assert s["id"] in ids


def test_finish_session_adds_stress_after(client):
    s = client.post("/api/relax/sessions", json={
        "sceneId": "ocean-shore", "audioMode": "none", "durationMin": 3, "stressBefore": 8,
    }).json()
    r = client.patch(f"/api/relax/sessions/{s['id']}", json={"stressAfter": 4})
    assert r.status_code == 200
    assert r.json()["stressAfter"] == 4
    assert r.json()["stressBefore"] == 8


def test_stress_scale_is_1_to_10(client):
    base = {"sceneId": "night-sky", "audioMode": "none", "durationMin": 5}
    assert client.post("/api/relax/sessions", json={**base, "stressBefore": 10}).status_code == 201
    assert client.post("/api/relax/sessions", json={**base, "stressBefore": 11}).status_code == 422
    assert client.post("/api/relax/sessions", json={**base, "stressBefore": 0}).status_code == 422


def test_bad_duration_and_unknown_session(client):
    body = {"sceneId": "night-sky", "audioMode": "none", "durationMin": 7, "stressBefore": 5}
    assert client.post("/api/relax/sessions", json=body).status_code == 422
    assert client.patch("/api/relax/sessions/relax-nope", json={"stressAfter": 3}).status_code == 404


def test_media_route_blocks_path_traversal(client):
    assert client.get("/api/relax/media/../config/app.yaml").status_code == 404
    assert client.get("/api/relax/media/scenes/does-not-exist.jpg").status_code == 404