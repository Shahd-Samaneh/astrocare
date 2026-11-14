"""Reports: report items (owner: Noura)."""


def _add(client, **over):
    body = {"kind": "note", "title": "Test note", "text": "hello", "sourceFeature": "relax", **over}
    r = client.post("/api/reports/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_add_item_shows_in_pending(client):
    item = _add(client, kind="cmo_question", title="Medication question for CMO", sourceFeature="assistant")
    assert item["id"].startswith("item-")
    assert item["reportId"] is None
    pending = client.get("/api/reports/items?pending=true").json()
    assert item["id"] in [i["id"] for i in pending]


def test_alert_item_keeps_ref_id(client):
    item = _add(client, kind="alert", refId="al-123", title="R-FAT-01", sourceFeature="monitoring")
    assert item["refId"] == "al-123"


def test_delete_item(client):
    item = _add(client)
    assert client.delete(f"/api/reports/items/{item['id']}").status_code == 204
    pending = client.get("/api/reports/items?pending=true").json()
    assert item["id"] not in [i["id"] for i in pending]
    assert client.delete(f"/api/reports/items/{item['id']}").status_code == 404


def test_bad_kind_is_rejected(client):
    r = client.post("/api/reports/items", json={"kind": "medicine", "title": "x", "sourceFeature": "daily"})
    assert r.status_code == 422


def test_python_helper(client):
    from server.features.reports.service import add_report_item, list_report_items
    item = add_report_item("alert", "From Python", "direct call", "monitoring", ref_id="al-9")
    assert item["id"] in [i["id"] for i in list_report_items(pending_only=True)]

    

# ---- comms window ----------------------------------------------------------------
def test_comms_shape(client):
    c = client.get("/api/comms").json()
    for key in ("connected", "nextWindowTs", "windowDurationMin", "queuedCount"):
        assert key in c, key
    assert c["windowDurationMin"] == 45


def test_simulate_window_sends_queued(client):
    from server.core import db

    db.update("reports", "rep-142", {"status": "queued"})  # make sure at least one is queued
    before = client.get("/api/comms").json()["queuedCount"]
    assert before >= 1

    r = client.post("/api/comms/simulate-window").json()
    assert "rep-142" in r["sentReportIds"]
    assert db.get("reports", "rep-142")["status"] == "sent"

    after = client.get("/api/comms").json()
    assert after["queuedCount"] == 0
    assert after["connected"] is True and after["simulatedWindow"] is True
    assert client.get("/api/status").json()["outboxCount"] == 0

    

# ---- reports ---------------------------------------------------------------------
def test_report_includes_pending_items_then_sets_report_id(client):
    item = _add(client, kind="cmo_question", title="Medication question for CMO", sourceFeature="assistant")
    r = client.post("/api/reports", json={"sections": ["summary", "items"]})
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["status"] == "ready"
    items_body = next(s["body"] for s in rep["sections"] if s["id"] == "items")
    assert "Medication question for CMO" in items_body
    all_items = {i["id"]: i for i in client.get("/api/reports/items").json()}
    assert all_items[item["id"]]["reportId"] == rep["id"]
    pending = client.get("/api/reports/items?pending=true").json()
    assert item["id"] not in [i["id"] for i in pending]


def test_checkins_not_included_without_permission(client):
    rep = client.post("/api/reports", json={"sections": ["checkins"]}).json()
    body = rep["sections"][0]["body"]
    assert body == "Not included: permission required."
    doc = client.get(f"/api/reports/{rep['id']}/file?format=json").json()
    assert doc["checkinsIncluded"] is False
    assert "mood" not in str(doc["sections"])


def test_pdf_and_json_files_exist(client):
    rep = client.post("/api/reports", json={"sections": ["summary", "vitals", "sleep"]}).json()
    pdf = client.get(f"/api/reports/{rep['id']}/file?format=pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    doc = client.get(f"/api/reports/{rep['id']}/file?format=json").json()
    assert doc["simulated"] is True and "SIMULATED" in doc["notice"]
    assert doc["missionDay"] == 142
    assert len(doc["sources"]) >= 1


def test_unknown_section_is_rejected(client):
    assert client.post("/api/reports", json={"sections": ["medicine"]}).status_code == 422
    assert client.post("/api/reports", json={"sections": []}).status_code == 422


def test_queue_then_window_sends_report(client):
    rep = client.post("/api/reports", json={"sections": ["summary"]}).json()
    q = client.post(f"/api/reports/{rep['id']}/queue")
    assert q.status_code == 200 and q.json()["status"] == "queued"
    assert client.get("/api/comms").json()["queuedCount"] >= 1

    client.post("/api/comms/simulate-window")
    after = {r["id"]: r for r in client.get("/api/reports").json()}[rep["id"]]
    assert after["status"] == "sent"
    assert after["sentTs"] is not None
    assert client.get("/api/comms").json()["queuedCount"] == 0


def test_only_ready_reports_can_be_queued(client):
    sent = client.get("/api/reports?status=sent").json()
    assert sent, "expected at least one sent report"
    assert client.post(f"/api/reports/{sent[0]['id']}/queue").status_code == 409
    assert client.post("/api/reports/rep-nope/queue").status_code == 404