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
        reply = self.reply(user) if callable(self.reply) else self.reply  # callable: reply from the prompt
        for tok in re.findall(r"\S+\s*|\s+", reply):
            yield tok
        yield llm.ChatResult(text=reply.strip(), eval_count=40, eval_duration_ns=2_000_000_000,
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
    fake_chat.reply = lambda user: (
        f"Sleep loss is common in spaceflight [{_num(user, 'Sleep risk')}]. "
        f"Your sleep was short [{_num(user, 'Your data: sleep')}].\nMISSING: none")
    before = len(store.log_rows(10_000))
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert set(body) >= {"answer", "sources", "missing", "refused", "mode", "latencyMs"}
    # the reference is cited first, so it becomes [1]; the sleep data becomes [2]
    assert body["answer"] == "Sleep loss is common in spaceflight [1]. Your sleep was short [2]."
    assert [s["id"] for s in body["sources"]] == ["nasa-hrp-sleep-risk", "user-data:sleep"]
    assert body["sources"][0]["url"] == "https://www.nasa.gov/example"
    assert body["missing"] == []
    rows = store.log_rows(10_000)
    assert len(rows) == before + 1 and rows[0]["mode"] == "llm" and rows[0]["eval_count"] == 40


def test_parse_answer_drops_invalid_citations():
    p = build_prompt("q", {"alerts": []}, [REF_HIT], arabic=False)
    parsed = parse_answer("A [9]. B [2].\n**MISSING:** x; none", p)
    assert parsed.answer == "A. B [1]."
    assert parsed.missing == ["x"]


def _num(user: str, title_start: str) -> int:
    """The [n] number the prompt gave to the source whose title starts with `title_start`."""
    return int(re.search(rf"^\[(\d+)\] {re.escape(title_start)}", user, re.M).group(1))


def test_arabic_question_asks_for_arabic_answer(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "ليش طلعلي التنبيه؟"})
    _, user = fake_chat.calls[0]
    assert "LANGUAGE: Arabic\nQUESTION: ليش طلعلي التنبيه؟" in user


# ---- prompt layout (prompt cache) -----------------------------------------------------
def test_system_prompt_identical_on_every_call(client, fake_chat, mock_ctx):
    for q in ["Why did I get the alert?", "ليش طلعلي التنبيه؟", "How does radiation affect astronauts?"]:
        client.post("/api/assistant/ask", json={"question": q})
    systems = {s for s, _ in fake_chat.calls}
    assert len(systems) == 1
    assert "{" not in next(iter(systems))  # no leftover placeholders


def test_prompt_order_data_then_passages_then_question(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"})
    _, user = fake_chat.calls[0]
    i_data, i_alert = user.index("Your data: vital signs"), user.index("Alert R-FAT-01")
    i_refs, i_q = user.index("REFERENCE PASSAGES"), user.index("QUESTION:")
    assert i_data < i_alert < i_refs < i_q
    assert user.rstrip().endswith("QUESTION: Why did I get the alert?")


def test_user_data_prefix_stable_between_questions(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"})
    client.post("/api/assistant/ask", json={"question": "How does radiation affect astronauts?"})
    (_, a), (_, b) = fake_chat.calls
    assert a.split("REFERENCE PASSAGES")[0] == b.split("REFERENCE PASSAGES")[0]


# ---- "my data" questions cover sleep and attention, with citations ------------------
def test_data_summary_adds_missing_sleep_and_attention(client, fake_chat, mock_ctx):
    fake_chat.reply = lambda user: f"Heart rate is 74 bpm [{_num(user, 'Your data: vital signs')}].\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"}).json()
    ids = [s["id"] for s in body["sources"]]
    assert ids == ["user-data:vitals", "user-data:sleep", "user-data:attention"]
    assert "Sleep, last 7 days: 5 nights" in body["answer"] and "[2]" in body["answer"]
    assert "Attention tests, last 7 days: 2 tests" in body["answer"] and "[3]" in body["answer"]
    assert "latest median reaction time 338 ms" in body["answer"]


def test_data_summary_not_duplicated_when_model_covers_it(client, fake_chat, mock_ctx):
    fake_chat.reply = lambda user: (f"You slept 5 h 20 m on average [{_num(user, 'Your data: sleep')}] and your "
                                    f"attention was slower [{_num(user, 'Your data: attention')}].\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"}).json()
    assert "Sleep, last 7 days" not in body["answer"] and len(body["sources"]) == 2


def test_title_heading_counts_as_citation(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Your data: sleep (7 days)\nYou slept about 5 h 20 m on the last nights.\n\n"
                       "**Your data: attention tests (7 days)**\nThe latest test was slower.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"}).json()
    assert [s["id"] for s in body["sources"]] == ["user-data:sleep", "user-data:attention"]
    assert "Sleep, last 7 days" not in body["answer"]  # covered: nothing appended
    assert "Your data: sleep (7 days) [1]" in body["answer"]


def test_sentences_naming_a_source_get_cited(client, fake_chat, mock_ctx):
    fake_chat.reply = ("The alert Short sleep and slower attention was raised for you. "
                       "Your sleep data shows short nights. Your attention tests were slower. "
                       "Sleep loss is a known spaceflight risk.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"}).json()
    ids = [s["id"] for s in body["sources"]]
    assert ids[0] == "alert:al-mock-fat01" and "user-data:sleep" in ids and "user-data:attention" in ids
    assert "was raised for you [1]." in body["answer"]
    # a sentence naming no source stays uncited (no invented citation)
    assert "Sleep loss is a known spaceflight risk." in body["answer"]


def test_not_shared_data_is_labelled(client, fake_chat, mock_ctx):
    set_permissions({"assistant": {"sleep": False}})
    client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"})
    _, user = fake_chat.calls[0]
    assert re.search(r"\] Your data: sleep \(7 days\)\nNot shared with the assistant", user)


# ---- ingest + retrieval -------------------------------------------------------------
def test_ingest_is_idempotent(client, tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("title: Doc A\nurl: https://example.org/a\nid: doc-a\n\n" + "word " * 1200, encoding="utf-8")
    calls: list[int] = []
    monkeypatch.setattr(ingest, "embed", lambda texts, timeout=60.0: calls.append(len(texts)) or [[1.0, 0.0]] * len(texts))
    first = ingest.ingest(tmp_path)
    assert first["chunks"] == 5 and first["embedded"] == 5  # 300-word chunks, 40 overlap
    second = ingest.ingest(tmp_path)
    assert second["embedded"] == 0 and second["chunks"] == 5
    meta = store.source_meta()
    assert meta["doc-a"] == ("Doc A", "https://example.org/a")
    with db.connect() as conn:  # leave no fake vectors for other tests
        conn.execute("DELETE FROM assistant_chunks WHERE source_id = 'doc-a'")


def test_ingest_rebuild_replaces_everything(client, tmp_path, monkeypatch):
    (tmp_path / "b.txt").write_text("title: Doc B\nurl: u\nid: doc-b\n\n" + "word " * 400, encoding="utf-8")
    monkeypatch.setattr(ingest, "embed", lambda texts, timeout=60.0: [[0.0, 1.0]] * len(texts))
    ingest.ingest(tmp_path)
    stats = ingest.ingest(tmp_path, rebuild=True)
    assert stats["embedded"] == stats["chunks"] == 2  # everything re-embedded, nothing skipped
    assert {c["source_id"] for c in store.all_chunks()} == {"doc-b"}  # old rows gone
    with db.connect() as conn:
        conn.execute("DELETE FROM assistant_chunks WHERE source_id = 'doc-b'")


def test_ingest_rebuild_keeps_old_index_if_embedding_fails(client, tmp_path, monkeypatch):
    (tmp_path / "c.txt").write_text("title: C\nurl: u\nid: doc-c\n\n" + "word " * 100, encoding="utf-8")
    monkeypatch.setattr(ingest, "embed", lambda texts, timeout=60.0: [[1.0, 0.0]] * len(texts))
    ingest.ingest(tmp_path)

    def boom(texts, timeout=60.0):
        raise llm.OllamaError("off")
    monkeypatch.setattr(ingest, "embed", boom)
    with pytest.raises(llm.OllamaError):
        ingest.ingest(tmp_path, rebuild=True)
    assert {c["source_id"] for c in store.all_chunks()} == {"doc-c"}
    with db.connect() as conn:
        conn.execute("DELETE FROM assistant_chunks WHERE source_id = 'doc-c'")


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


# ---- fixed facts ------------------------------------------------------------------------
# mock data: 5 nights (430, 415, 320, 320, 320 min), 2 tests (281 ms, then 338 ms with 1 lapse),
# heart rate / SpO2 / resp rate up to date, skin temperature stale, blood pressure missing.
def test_fixed_facts_are_computed_in_code_and_shown_in_prompt(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"})
    _, user = fake_chat.calls[0]
    assert ("FIXED FACT: Sleep, last 7 days: 5 nights recorded; average 6 h 01 m; shortest 5 h 20 m; "
            "last night 5 h 20 m; 3 night(s) under 6 h.") in user
    assert ("FIXED FACT: Attention tests, last 7 days: 2 tests; latest median reaction time 338 ms "
            "(first test in the window: 281 ms); lapses in the latest test: 1; lapses over 7 days: 1.") in user
    assert "FIXED FACT: Vital signs: up to date: heart rate, SpO₂, respiration rate; stale: skin temperature" in user
    assert "missing today: blood pressure." in user


@pytest.mark.parametrize("wrong, fact_start", [
    ("Your attention tests show no lapses.", "Attention tests, last 7 days: 2 tests"),
    ("Your latest median reaction time was 300 ms.", "Attention tests, last 7 days: 2 tests"),
    ("Your sleep data is stale.", "Sleep, last 7 days: 5 nights"),
    ("You slept an average of 7 hours and 30 minutes.", "Sleep, last 7 days: 5 nights"),
    ("You had 1 night under 6 h this week.", "Sleep, last 7 days: 5 nights"),
    ("Your heart rate data is stale.", "Vital signs: up to date: heart rate"),
    ("Your skin temperature is up to date.", "Vital signs: up to date: heart rate"),
])
def test_contradicting_sentence_is_replaced_by_the_fact(client, fake_chat, mock_ctx, wrong, fact_start):
    fake_chat.reply = f"Here is your summary. {wrong} Keep resting.\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"}).json()
    assert wrong not in body["answer"]
    assert fact_start in body["answer"]
    assert "Here is your summary." in body["answer"] and "Keep resting." in body["answer"]
    fact_ids = {s["id"] for s in body["sources"]}
    assert fact_ids & {"user-data:sleep", "user-data:attention", "user-data:vitals"}  # fact line is cited


@pytest.mark.parametrize("right", [
    "Your latest median reaction time was 338 ms, up from 281 ms.",
    "Your latest test had 1 lapse.",
    "You slept 5 h 20 m last night, and 3 nights were under 6 h.",
    "Your skin temperature reading is stale.",
    "Your blood pressure is missing today.",
    "NASA notes that astronauts often get less than 6 hours of sleep and have no lapses only when rested.",
])
def test_correct_or_reference_sentences_are_kept(client, fake_chat, mock_ctx, right):
    fake_chat.reply = f"{right}\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"}).json()
    assert right.rstrip(".") in body["answer"]


def test_same_fact_is_written_only_once(client, fake_chat, mock_ctx):
    fake_chat.reply = "Your attention tests show no lapses. Your latest test also had zero lapses.\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "How is my attention?"}).json()
    assert body["answer"].count("Attention tests, last 7 days") == 1


def test_arabic_fact_replacement(client, fake_chat, mock_ctx):
    fake_chat.reply = "نومك بيانات قديمة.\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "شو بتبيّن بياناتي آخر 7 أيام؟"}).json()
    assert "النوم، آخر 7 أيام: 5 ليالي مسجّلة" in body["answer"]


# ---- cache priming ----------------------------------------------------------------------
def test_prime_sends_the_exact_prefix_of_a_real_prompt(client, fake_chat, mock_ctx, monkeypatch):
    sent: dict = {}

    class Resp:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        sent.setdefault(url.rsplit("/", 1)[-1], json)
        return Resp()
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setattr(llm, "embed", lambda texts, timeout=60.0: [[1.0]] * len(texts))
    assert service.prime_cache() is True
    primed = sent["chat"]
    assert primed["options"]["num_predict"] == 1 and primed["keep_alive"] == "60m"
    client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"})
    system, user = fake_chat.calls[0]
    assert primed["messages"][0]["content"] == system
    assert user.startswith(primed["messages"][1]["content"])


def test_prime_never_raises_when_ollama_is_off(monkeypatch, mock_ctx):
    monkeypatch.setattr(llm, "ollama_cfg", lambda: {"url": "http://127.0.0.1:9", "chat_model": "x", "embed_model": "y"})
    assert service.prime_cache() is False


def test_first_token_timeout_is_30s():
    from server.features.assistant.settings import setting
    assert setting("assistant_first_token_timeout_sec") == 30


def test_echoed_fixed_fact_gets_its_citation_and_loses_the_label(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Sleep loss is a spaceflight risk.\n\nFIXED FACT: Sleep, last 7 days: 5 nights recorded; "
                       "average 6 h 01 m; shortest 5 h 20 m; last night 5 h 20 m; 3 night(s) under 6 h.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "How can sleep loss affect me?"}).json()
    assert "FIXED FACT" not in body["answer"]
    assert "3 night(s) under 6 h [1]." in body["answer"]
    assert [s["id"] for s in body["sources"]] == ["user-data:sleep"]


def test_you_have_slept_counts_as_citing_sleep(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Your data shows that you have slept 5 nights, with an average of 6 h 01 m. "
                       "Your latest median reaction time was 338 ms.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"}).json()
    assert body["answer"].count("Sleep, last 7 days") == 0  # covered by the model's own cited sentence
    assert {"user-data:sleep", "user-data:attention"} <= {s["id"] for s in body["sources"]}
