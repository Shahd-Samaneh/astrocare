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