"""Assistant tests (owner: Marah). Ollama is always mocked or pointed at a dead port."""
from __future__ import annotations

import json
import re
import socket
import threading

import pytest

from server.core import db
from server.features.assistant import ingest, llm, service, store
from server.features.assistant.context import build_context
from server.features.assistant.permissions import DEFAULT_PERMISSIONS, get_permissions, set_permissions
from server.features.assistant.prompt import build_prompt, parse_answer
from server.features.assistant.retrieval import Hit, top_k
from server.features.assistant.safety import check_question

REF_HIT = Hit(id="nasa-hrp-sleep-risk:0", source_id="nasa-hrp-sleep-risk", title="Sleep risk (NASA HRP)",
              url="https://www.nasa.gov/example", text="Astronauts commonly experience sleep deprivation.", score=0.8)


@pytest.fixture
def reset_permissions(client):
    store.save_permissions(DEFAULT_PERMISSIONS)
    yield
    store.save_permissions(DEFAULT_PERMISSIONS)


@pytest.fixture
def mock_ctx(monkeypatch, reset_permissions):
    """Use mock_context.json for every source (it has a notePrivate and a CMO-locked step)."""
    monkeypatch.setenv("ASTROCARE_ASSISTANT_MOCK", "1")


class FakeChat:
    """Stands in for llm.chat_stream: records every prompt and streams `reply` word by word."""

    def __init__(self, reply: str = "Answer [1].\nMISSING: none"):
        self.reply = reply
        self.complete = True
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str, **_kw):
        self.calls.append((system, user))
        for tok in re.findall(r"\S+\s*|\s+", self.reply):
            yield tok
        yield llm.ChatResult(text=self.reply.strip(), eval_count=40, eval_duration_ns=2_000_000_000,
                             first_token_ms=1500, model="fake", complete=self.complete)


@pytest.fixture
def fake_chat(monkeypatch):
    fc = FakeChat()
    monkeypatch.setattr(service.llm, "chat_stream", fc)
    monkeypatch.setattr(service, "retrieve", lambda q, k=None: [REF_HIT])
    return fc


def _must_not_call(*_a, **_k):
    raise AssertionError("the model must not be called")


# ---- 1. medication question -> refused, model never called -------------------------
@pytest.mark.parametrize("q", [
    "What dose of melatonin should I take?",
    "Can I take ibuprofen for my headache?",   # name read from the resources table
    "How many mg is safe?",
    "شو الدوا المناسب للصداع؟",
    "كم حبة لازم آخد؟",
    "Can I take Tylenol?",                     # static brand-name list
    "Is Panadol ok for a headache?",
    "What about sleeping pills?",
    "بقدر آخد بنادول؟",
    "هل البنادول آمن؟",
])
def test_medication_refused_without_model(client, monkeypatch, q):
    monkeypatch.setattr(service.llm, "chat_stream", _must_not_call)
    monkeypatch.setattr(service.llm, "embed", _must_not_call)
    monkeypatch.setattr(service, "retrieve", _must_not_call)
    r = client.post("/api/assistant/ask", json={"question": q})
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is True
    assert body["refusalReason"] == "medication"
    assert "CMO" in body["answer"]


def test_ordinary_questions_pass_the_filter(client):
    for q in ["Why did I get the alert?", "What steps should I take next?", "How long does it take to adapt?",
              "ليش طلعلي التنبيه؟", "اخذت قسط من الراحة",
              # radiation dose is a reference question, not medication
              "What is the career radiation dose limit?", "شو حد جرعة الإشعاع؟"]:
        assert check_question(q) is None, q


def test_model_output_with_a_dose_is_replaced_by_refusal(client, fake_chat, mock_ctx):
    fake_chat.reply = "You could take 200 mg [1].\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "How can I sleep better?"}).json()
    assert body["refused"] is True and "200 mg" not in body["answer"]


# ---- 2. no answer in the references -> missing + "not there" -------------------------
def test_no_answer_reports_missing(client, fake_chat, mock_ctx):
    fake_chat.reply = ("This information is not in the available data or references.\n"
                       "MISSING: boiling point of titanium")
    body = client.post("/api/assistant/ask", json={"question": "What is the boiling point of titanium?"}).json()
    assert body["mode"] == "llm" and body["refused"] is False
    assert body["missing"] == ["boiling point of titanium"]
    assert "not in the available data" in body["answer"]
    assert "MISSING" not in body["answer"]
    system, _ = fake_chat.calls[0]
    assert "say clearly that this information is not in the available data" in system


# ---- 3. Ollama off -> template fallback from the alert --------------------------------
def test_ollama_off_gives_fallback_from_alert(client, monkeypatch, mock_ctx):
    # a real failure: nothing listens on port 9
    monkeypatch.setattr(llm, "ollama_cfg", lambda: {"url": "http://127.0.0.1:9", "chat_model": "x", "embed_model": "y"})
    store.ensure_tables()
    with db.connect() as conn:  # make retrieval actually try to embed the question
        conn.execute("INSERT OR REPLACE INTO assistant_chunks VALUES ('t:0','t','T',NULL,0,'text','h','m','[1,0]')")
    body = client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"}).json()
    assert body["mode"] == "fallback" and body["refused"] is False
    a = body["answer"]
    assert "R-FAT-01" in a
    assert "Sleep averaged 5 h 20 m" in a              # whatChanged
    assert "Several short nights in a row" in a        # possibleFactors
    assert "Protect an 8-hour sleep opportunity" in a  # nextSteps
    assert "Melatonin" not in a                        # CMO-locked step is not shown
    assert "Blood pressure: no reading" in " ".join(body["missing"])
    assert any(s["id"] == "alert:al-mock-fat01" for s in body["sources"])
    with db.connect() as conn:
        conn.execute("DELETE FROM assistant_chunks WHERE id = 't:0'")


# ---- 4. notePrivate never reaches the model -----------------------------------------
def test_note_private_never_in_prompt(client, fake_chat, mock_ctx):
    set_permissions({"assistant": {"checkins": True}})
    client.post("/api/assistant/ask", json={"question": "How was my mood this week?"})
    system, user = fake_chat.calls[0]
    assert "PRIVATE-NOTE-MUST-NEVER-REACH-THE-MODEL" not in system + user
    assert "notePrivate" not in user and "note_private" not in user
    assert '"stress":4' in user  # the check-in itself is there


def test_cmo_locked_step_never_in_prompt(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"})
    _, user = fake_chat.calls[0]
    assert "Melatonin" not in user and "locked" in user


# ---- 5. permissions: checkins=false -> no check-ins in the context ------------------
def test_checkins_off_not_in_context(client, fake_chat, mock_ctx):
    assert get_permissions()["assistant"]["checkins"] is False
    ctx = build_context()
    assert "checkins7d" not in ctx
    assert any("check-ins" in x for x in ctx["notShared"])
    client.post("/api/assistant/ask", json={"question": "How was my stress?"})
    _, user = fake_chat.calls[0]
    assert '"stress":4' not in user and "checkins7d" not in user


def test_sleep_off_not_in_context(client, mock_ctx):
    set_permissions({"assistant": {"sleep": False}})
    ctx = build_context()
    assert "sleep7d" not in ctx and "sleep" in ctx["notShared"]


# ---- permissions endpoint -----------------------------------------------------------
def test_permissions_defaults(client, reset_permissions):
    body = client.get("/api/assistant/permissions").json()
    assert body["assistant"]["checkins"] is False
    assert body["report"]["checkins"] is False
    assert body["assistant"]["vitals"] is True


def test_permissions_partial_put_merges(client, reset_permissions):
    body = client.put("/api/assistant/permissions", json={"report": {"checkins": True}}).json()
    assert body["report"]["checkins"] is True
    assert body["assistant"]["checkins"] is False  # untouched
    assert get_permissions()["report"]["checkins"] is True  # the helper Noura imports


def test_permissions_ignores_unknown_keys(client, reset_permissions):
    assert client.put("/api/assistant/permissions", json={"assistant": {"notePrivate": True, "sleep": False}}).status_code == 200
    perms = get_permissions()
    assert "notePrivate" not in perms["assistant"] and perms["assistant"]["sleep"] is False


# ---- answer shape, log, citations -----------------------------------------------------
def test_llm_answer_shape_and_log(client, fake_chat, mock_ctx):
    fake_chat.reply = "Sleep loss is common in spaceflight [3]. Your sleep was short [1].\nMISSING: none"
    before = len(store.log_rows(10_000))
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert set(body) >= {"answer", "sources", "missing", "refused", "mode", "latencyMs"}
    # [3] (the reference) is cited first, so it becomes [1]; the user data becomes [2]
    assert body["answer"] == "Sleep loss is common in spaceflight [1]. Your sleep was short [2]."
    assert [s["id"] for s in body["sources"]] == ["nasa-hrp-sleep-risk", "user-data"]
    assert body["sources"][0]["url"] == "https://www.nasa.gov/example"
    assert body["missing"] == []
    rows = store.log_rows(10_000)
    assert len(rows) == before + 1 and rows[0]["mode"] == "llm" and rows[0]["eval_count"] == 40


def test_parse_answer_drops_invalid_citations():
    p = build_prompt("q", {"alerts": []}, [REF_HIT], arabic=False)
    parsed = parse_answer("A [9]. B [2].\n**MISSING:** x; none", p)
    assert parsed.answer == "A. B [1]."
    assert parsed.missing == ["x"]


def test_arabic_question_asks_for_arabic_answer(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "ليش طلعلي التنبيه؟"})
    system, _ = fake_chat.calls[0]
    assert "Write the answer in Arabic" in system


# ---- ingest + retrieval -------------------------------------------------------------
def test_ingest_is_idempotent(client, tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("title: Doc A\nurl: https://example.org/a\nid: doc-a\n\n" + "word " * 1200, encoding="utf-8")
    calls: list[int] = []
    monkeypatch.setattr(ingest, "embed", lambda texts, timeout=60.0: calls.append(len(texts)) or [[1.0, 0.0]] * len(texts))
    first = ingest.ingest(tmp_path)
    assert first["chunks"] == 3 and first["embedded"] == 3  # 500-word chunks, 50 overlap
    second = ingest.ingest(tmp_path)
    assert second["embedded"] == 0 and second["chunks"] == 3
    meta = store.source_meta()
    assert meta["doc-a"] == ("Doc A", "https://example.org/a")
    with db.connect() as conn:  # leave no fake vectors for other tests
        conn.execute("DELETE FROM assistant_chunks WHERE source_id = 'doc-a'")


def test_parse_reference_header(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("title: T\nurl: U\nid: the-id\n\nBody text here.", encoding="utf-8")
    doc = ingest.parse_reference(f)
    assert (doc.source_id, doc.title, doc.url, doc.body) == ("the-id", "T", "U", "Body text here.")


def test_top_k_cosine():
    chunks = [{"id": str(i), "source_id": str(i), "title": "", "url": None, "text": "", "embedding": v}
              for i, v in enumerate([[1, 0], [0, 1], [0.7, 0.7]])]
    assert [h.id for h in top_k([1, 0.1], chunks, 2)] == ["0", "2"]


def test_info_reports_measured_values(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
    body = client.get("/api/assistant/info").json()
    assert body["tokensPerSec"] == 20.0  # 40 tokens / 2 s from the fake model
    assert body["avgFirstTokenMs"] == 1500.0
    assert body["answersLogged"] >= 1


# ---- streaming ------------------------------------------------------------------------
def _events(client, question: str) -> list[dict]:
    r = client.post("/api/assistant/ask/stream", json={"question": question})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def test_stream_sends_tokens_then_final(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Your sleep was shorter than your baseline over the last three nights, which is a "
                       "possible link, not a confirmed cause [1]. NASA lists sleep loss as a risk [3].\n"
                       "MISSING: none")
    evs = _events(client, "Is my sleep a problem?")
    tokens = [e["text"] for e in evs if e["type"] == "token"]
    assert len(tokens) > 3 and evs[-1]["type"] == "final"
    streamed = "".join(tokens)
    assert streamed and "MISSING" not in streamed
    final = evs[-1]["answer"]
    assert final["mode"] == "llm" and final["answer"].startswith(streamed.strip()[:40])
    assert evs[-1]["stats"]["firstTokenMs"] == 1500
    assert store.log_rows(1)[0]["first_token_ms"] == 1500


def test_stream_refusal_is_a_single_final_event(client, monkeypatch):
    monkeypatch.setattr(service.llm, "chat_stream", _must_not_call)
    evs = _events(client, "Can I take Tylenol?")
    assert [e["type"] for e in evs] == ["final"] and evs[0]["answer"]["refused"] is True


def test_dose_in_stream_is_never_shown(client, fake_chat, mock_ctx):
    fake_chat.reply = "To sleep better you could take 200 mg of something before bed, and rest well tonight."
    evs = _events(client, "How can I sleep better?")
    shown = "".join(e["text"] for e in evs if e["type"] == "token")
    assert "mg" not in shown and "200" not in shown
    assert evs[-1]["answer"]["refused"] is True and "200 mg" not in evs[-1]["answer"]["answer"]


def test_medicine_name_in_stream_is_never_shown(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Short sleep is common in space and many crews report it during long missions. "
                       "Some people use Tylenol for headaches after short nights.")
    evs = _events(client, "Why am I tired?")
    shown = "".join(e["text"] for e in evs if e["type"] == "token")
    assert "Tylenol" not in shown
    assert "reset" in [e["type"] for e in evs] and evs[-1]["answer"]["refused"] is True


def test_no_first_token_in_time_falls_back(client, monkeypatch, mock_ctx):
    def slow(*_a, **_k):
        raise llm.FirstTokenTimeout("no first token within 20 s")
        yield  # pragma: no cover  (makes this a generator)
    monkeypatch.setattr(service.llm, "chat_stream", slow)
    monkeypatch.setattr(service, "retrieve", lambda q, k=None: [REF_HIT])
    evs = _events(client, "Why did I get the alert?")
    assert evs[-1]["answer"]["mode"] == "fallback" and "R-FAT-01" in evs[-1]["answer"]["answer"]


def test_stall_after_first_token_keeps_partial_answer(client, fake_chat, mock_ctx):
    fake_chat.reply = "Your sleep was short over the last three nights [1]"
    fake_chat.complete = False
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert body["mode"] == "llm" and body["answer"].startswith("Your sleep was short")
    assert any("incomplete" in m for m in body["missing"])


def test_cut_off_missing_line_is_not_reported(client, fake_chat, mock_ctx):
    fake_chat.reply = "Sleep loss can slow attention [1].\nMISSING: How can sleep loss be"  # hit the token cap
    fake_chat.complete = False
    body = client.post("/api/assistant/ask", json={"question": "How can sleep loss affect me?"}).json()
    assert len(body["missing"]) == 1 and "incomplete" in body["missing"][0]


def test_real_first_token_timeout_against_a_silent_server(monkeypatch):
    """chat_stream itself: a local server that accepts the request but never answers."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    conns = []
    threading.Thread(target=lambda: conns.append(srv.accept()), daemon=True).start()
    monkeypatch.setattr(llm, "ollama_cfg", lambda: {"url": f"http://127.0.0.1:{port}", "chat_model": "x", "embed_model": "y"})
    with pytest.raises(llm.FirstTokenTimeout):
        list(llm.chat_stream("s", "u", model="x", first_token_timeout=0.5))
    srv.close()


def test_chat_model_is_configurable(monkeypatch):
    from server.features.assistant.settings import chat_model
    assert chat_model() == "llama3.2:3b"
    monkeypatch.setenv("ASTROCARE_CHAT_MODEL", "llama3.2:1b")
    assert chat_model() == "llama3.2:1b"
