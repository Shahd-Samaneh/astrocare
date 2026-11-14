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
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
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
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
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
    client.post("/api/assistant/ask", json={"question": "ليش نومي قليل؟"})
    _, user = fake_chat.calls[0]
    assert "LANGUAGE: Arabic\nQUESTION: ليش نومي قليل؟" in user
    assert "RULE: Do not add medical claims that aren't in the context above." in user


def test_english_prompt_has_no_arabic_rule(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
    _, user = fake_chat.calls[0]
    assert "RULE:" not in user


# ---- prompt layout (prompt cache) -----------------------------------------------------
def test_system_prompt_identical_on_every_call(client, fake_chat, mock_ctx):
    for q in ["Is my sleep a problem?", "ليش نومي قليل؟", "How does radiation affect astronauts?"]:
        client.post("/api/assistant/ask", json={"question": q})
    systems = {s for s, _ in fake_chat.calls}
    assert len(systems) == 1
    assert "{" not in next(iter(systems))  # no leftover placeholders


def test_prompt_order_data_then_passages_then_question(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
    _, user = fake_chat.calls[0]
    i_data, i_alert = user.index("Your data: vital signs"), user.index("Alert R-FAT-01")
    i_refs, i_q = user.index("REFERENCE PASSAGES"), user.index("QUESTION:")
    assert i_data < i_alert < i_refs < i_q
    assert user.rstrip().endswith("QUESTION: Is my sleep a problem?")


def test_user_data_prefix_stable_between_questions(client, fake_chat, mock_ctx):
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
    client.post("/api/assistant/ask", json={"question": "How does radiation affect astronauts?"})
    (_, a), (_, b) = fake_chat.calls
    assert a.split("REFERENCE PASSAGES")[0] == b.split("REFERENCE PASSAGES")[0]


# ---- deterministic answers: alert and "my data" questions never reach the model --------
@pytest.mark.parametrize("q, route", [
    ("Why did I get the alert?", "alert"),
    ("What does this alert mean?", "alert"),
    ("Explain R-FAT-01", "alert"),
    ("ليش طلعلي التنبيه؟", "alert"),
    ("شو يعني هالتنبيه؟", "alert"),
    ("What does my data from the last 7 days show?", "data"),
    ("Summarize my data", "data"),
    ("شو بتبيّن بياناتي آخر 7 أيام؟", "data"),
    ("بياناتي", "data"),
    ("How do alerts work?", None),
    ("How was my mood this week?", None),
    ("How can sleep loss affect my performance on the mission?", None),
    ("ليش نومي قليل؟", None),
])
def test_question_routing_en_ar(q, route):
    from server.features.assistant.direct import is_alert_question, is_data_question
    got = "alert" if is_alert_question(q) else "data" if is_data_question(q) else None
    assert got == route, q


def _no_model(monkeypatch):
    monkeypatch.setattr(service.llm, "chat_stream", _must_not_call)
    monkeypatch.setattr(service, "retrieve", _must_not_call)


def test_alert_question_is_answered_from_the_alert_without_model(client, monkeypatch, mock_ctx):
    _no_model(monkeypatch)
    body = client.post("/api/assistant/ask", json={"question": "Why did I get the alert?"}).json()
    assert body["mode"] == "alert" and body["alertRuleId"] == "R-FAT-01" and body["note"] is None
    a = body["answer"]
    assert "**Alert R-FAT-01: Short sleep and slower attention**" in a
    assert "Sleep averaged 5 h 20 m" in a and "Several short nights in a row" in a
    assert "Protect an 8-hour sleep opportunity" in a and "Melatonin" not in a
    # the alert is cited once at the end of each list, not on every bullet
    assert "- Several short nights in a row\n" in a and "- Cabin noise during the sleep period [1]" in a
    assert body["missing"] == ["Blood pressure: no reading since the start of mission day 142"]
    assert body["sources"][0]["id"] == "alert:al-mock-fat01"


def test_arabic_alert_question_uses_arabic_labels(client, monkeypatch, mock_ctx):
    _no_model(monkeypatch)
    body = client.post("/api/assistant/ask", json={"question": "ليش طلعلي التنبيه؟"}).json()
    assert body["mode"] == "alert" and body["alertRuleId"] == "R-FAT-01"
    assert "**التنبيه R-FAT-01:" in body["answer"] and "شو تغيّر" in body["answer"]
    assert "عوامل محتملة" in body["answer"]


def test_rule_id_in_question_picks_that_alert():
    from server.features.assistant.direct import pick_alert_for
    alerts = [{"id": "a", "ruleId": "R-FAT-01", "level": "review", "ts": "2026-11-14", "status": "new"},
              {"id": "b", "ruleId": "R-HR-02", "level": "urgent", "ts": "2026-11-13", "status": "new"}]
    assert pick_alert_for("Why did I get the alert?", alerts)["id"] == "b"   # highest level
    assert pick_alert_for("What is r-fat-01?", alerts)["id"] == "a"          # named rule
    assert pick_alert_for("Why the alert?", []) is None


def test_data_question_is_answered_from_fixed_facts_without_model(client, monkeypatch, mock_ctx):
    _no_model(monkeypatch)
    body = client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"}).json()
    assert body["mode"] == "data" and body["refused"] is False
    a = body["answer"]
    assert [s["id"] for s in body["sources"]] == ["user-data:vitals", "user-data:sleep",
                                                    "user-data:attention", "user-data:exercise"]
    assert "- Vital signs: up to date: heart rate, SpO₂, respiration rate" in a and a.count("[1]") == 1
    assert "- Sleep, last 7 days: 5 nights recorded; average 6 h 01 m" in a and "3 night(s) under 6 h [2]" in a
    assert "latest median reaction time 338 ms" in a and "[3]" in a
    assert "- Exercise today: planned Resistive exercise (ARED) (60 min); not logged yet [4]" in a
    assert "- Check-ins: not shared with the assistant (permission off)." in a  # permission off: no data
    assert body["missing"] == ["Blood pressure: no reading today"]


def test_arabic_data_question_is_answered_in_arabic(client, monkeypatch, mock_ctx):
    _no_model(monkeypatch)
    body = client.post("/api/assistant/ask", json={"question": "شو بتبيّن بياناتي آخر 7 أيام؟"}).json()
    assert body["mode"] == "data"
    assert "النوم، آخر 7 أيام: 5 ليالي مسجّلة" in body["answer"]
    assert "تسجيلات الحالة: مش مشاركة مع المساعد" in body["answer"]
    assert body["missing"] == ["ضغط الدم: ما في قراءة اليوم"]


def test_data_answer_respects_permissions(client, monkeypatch, mock_ctx):
    _no_model(monkeypatch)
    set_permissions({"assistant": {"sleep": False, "checkins": True}})
    body = client.post("/api/assistant/ask", json={"question": "Summarize my data"}).json()
    a = body["answer"]
    assert "- Sleep: not shared with the assistant (permission off)." in a and "5 nights" not in a
    assert "user-data:sleep" not in [s["id"] for s in body["sources"]]
    assert "Check-ins, last 7 days: 1 check-in(s), 0 skipped; latest mood 3/5, stress 4/5" in a
    assert "PRIVATE-NOTE" not in a


def test_title_heading_counts_as_citation(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Your data: sleep (7 days)\nYou slept about 5 h 20 m on the last nights.\n\n"
                       "**Your data: attention tests (7 days)**\nThe latest test was slower.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "How are my sleep and attention?"}).json()
    assert [s["id"] for s in body["sources"]] == ["user-data:sleep", "user-data:attention"]
    assert "Your data: sleep (7 days) [1]" in body["answer"]


def test_sentences_naming_a_source_get_cited(client, fake_chat, mock_ctx):
    fake_chat.reply = ("The alert Short sleep and slower attention was raised for you. "
                       "Your sleep data shows short nights. Your attention tests were slower. "
                       "Sleep loss is a known spaceflight risk.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    ids = [s["id"] for s in body["sources"]]
    assert ids[0] == "alert:al-mock-fat01" and "user-data:sleep" in ids and "user-data:attention" in ids
    assert "was raised for you [1]." in body["answer"]
    # a sentence naming no source stays uncited (no invented citation)
    assert "Sleep loss is a known spaceflight risk." in body["answer"]


def test_not_shared_data_is_labelled(client, fake_chat, mock_ctx):
    set_permissions({"assistant": {"sleep": False}})
    client.post("/api/assistant/ask", json={"question": "How am I sleeping?"})
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
    evs = _events(client, "Is my sleep a problem?")
    assert evs[-1]["answer"]["mode"] == "fallback" and "R-FAT-01" in evs[-1]["answer"]["answer"]


def test_stall_after_first_token_keeps_partial_answer(client, fake_chat, mock_ctx):
    fake_chat.reply = "Your sleep was short over the last three nights [1]"
    fake_chat.complete = False
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert body["mode"] == "llm" and body["answer"].startswith("Your sleep was short")
    assert "incomplete" in body["note"] and body["missing"] == []  # a notice, not missing data


def test_cut_off_missing_line_is_not_reported(client, fake_chat, mock_ctx):
    fake_chat.reply = "Sleep loss can slow attention [1].\nMISSING: How can sleep loss be"  # hit the token cap
    fake_chat.complete = False
    body = client.post("/api/assistant/ask", json={"question": "How can sleep loss affect me?"}).json()
    assert body["missing"] == [] and "incomplete" in body["note"]


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
    client.post("/api/assistant/ask", json={"question": "How am I sleeping?"})
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
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
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
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
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
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
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
    body = client.post("/api/assistant/ask", json={"question": "How am I sleeping?"}).json()
    assert "user-data:sleep" in {s["id"] for s in body["sources"]}
    assert "6 h 01 m [1]." in body["answer"]


# ---- template fallback fixes ---------------------------------------------------------
def test_fallback_says_too_slow_vs_not_available(client, monkeypatch, mock_ctx):
    monkeypatch.setattr(service, "retrieve", lambda q, k=None: [REF_HIT])

    def slow(*_a, **_k):
        raise llm.FirstTokenTimeout("no first token")
        yield  # pragma: no cover
    monkeypatch.setattr(service.llm, "chat_stream", slow)
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert body["mode"] == "fallback" and "taking too long" in body["note"]
    # the notice is a note under the badge: never in the answer text or the missing line
    assert "taking too long" not in body["answer"]
    assert body["missing"] == ["Blood pressure: no reading since the start of mission day 142"]

    def off(*_a, **_k):
        raise llm.OllamaError("connection refused")
        yield  # pragma: no cover
    monkeypatch.setattr(service.llm, "chat_stream", off)
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert "not available" in body["note"] and not any("template" in m.lower() for m in body["missing"])


def test_fallback_picks_highest_level_open_alert():
    from server.features.assistant.fallback import pick_alert
    alerts = [
        {"id": "a1", "level": "info", "ts": "2026-11-14T10:00:00Z", "status": "new"},
        {"id": "a2", "level": "review", "ts": "2026-11-13T10:00:00Z", "status": "new"},       # R-FAT-01 style
        {"id": "a3", "level": "urgent", "ts": "2026-11-12T10:00:00Z", "status": "closed"},    # closed: skipped
        {"id": "a4", "level": "review", "ts": "2026-11-12T09:00:00Z", "status": "ack"},
    ]
    assert pick_alert(alerts)["id"] == "a2"


def test_fallback_has_no_duplicate_missing_items_or_sources(client):
    from server.features.assistant.fallback import build_fallback
    alert = {"id": "x", "ruleId": "R-T", "title": "T", "whatChanged": "w", "dataUsed": ["r1", "r2", "r3"],
             "missing": ["BP: no reading", "bp: no reading.", "SpO2 stale"], "possibleFactors": ["f", "f"],
             "nextSteps": [], "sources": ["note A", "note A"], "level": "review", "status": "new"}
    answer, sources, missing = build_fallback(alert, arabic=False)
    assert missing == ["BP: no reading", "SpO2 stale"]              # deduped, once; no template notice
    assert "BP: no reading" not in answer                            # not repeated in the text
    assert answer.count("[1]") == 2                                  # what changed + end of the factor list
    assert "- f [1]" in answer and answer.count("- f") == 1
    assert [s.title for s in sources] == ["Alert R-T: T", "note A"]  # each source once


def test_arabic_plurals():
    from server.features.assistant.arabic import ar_n
    from server.features.assistant.fallback import build_fallback
    assert [ar_n(n, "night") for n in (1, 2, 3, 10, 11)] == ["ليلة واحدة", "ليلتين", "3 ليالي", "10 ليالي", "11 ليلة"]
    alert = {"id": "x", "ruleId": "R", "title": "T", "whatChanged": "w", "dataUsed": ["a", "b"], "missing": [],
             "possibleFactors": [], "nextSteps": [], "sources": []}
    assert "قراءتين" in build_fallback(alert, arabic=True)[0]


# ---- cause wording ---------------------------------------------------------------------
@pytest.mark.parametrize("wrong, banned", [
    ("Your alert was caused by the disconnected patch.", "caused by"),
    ("Your sleep is short because of cabin noise.", "because of"),
    ("Your attention was slower due to short sleep.", "due to"),
    ("The cause of your alert is the disconnected sensor.", "cause of"),
    ("These are mentioned in the reference passage as possible causes for the alert.", "possible causes"),
])
def test_cause_wording_about_user_data_is_softened(client, fake_chat, mock_ctx, wrong, banned):
    fake_chat.reply = f"{wrong}\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert banned not in body["answer"].lower()
    assert "a possible link, not a confirmed cause" in body["answer"]


def test_arabic_cause_wording_is_softened(client, fake_chat, mock_ctx):
    fake_chat.reply = "نومك قليل بسبب الضجة.\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "ليش نومي قليل؟"}).json()
    assert "بسبب" not in body["answer"] and "ارتباط محتمل، مش سبب مؤكد" in body["answer"]


def test_reference_cause_sentence_and_correct_wording_are_kept():
    from server.features.assistant.wording import soften_causes
    ref = "Space radiation causes DNA damage in cells."
    assert soften_causes(ref, set(), arabic=False) == ref  # not about the user's data
    ok = "Your short sleep is a possible factor (a possible link, not a confirmed cause)."
    assert soften_causes(ok, set(), arabic=False) == ok     # already right: unchanged, no double tag


# ---- weak citations ----------------------------------------------------------------------
def _sources_with_vectors():
    from server.features.assistant.prompt import PromptSource
    return [
        PromptSource("user-data:sleep", "Your data: sleep (7 days)", None, "{}"),
        PromptSource("nasa-hrp-sleep-risk", "Sleep risk", None, "...", vectors=[[1.0, 0.0, 0.0]]),
        PromptSource("csa-bio-monitor", "Bio-Monitor", None, "...", vectors=[[0.0, 1.0, 0.0]]),
    ]


def test_supported_citation_is_kept_and_unsupported_is_dropped():
    from server.features.assistant.citecheck import check_citations
    text = ("Sleep loss leads to errors on tasks [2]. "
            "Patch disconnection is a common factor for alerts in general [3]. "
            "You slept 5 h last night [1].")
    vecs = {"Sleep loss": [0.95, 0.05, 0.0], "Patch": [0.1, 0.1, 0.99]}  # 1: like the sleep passage; 2: like neither

    def fake_embed(texts):
        return [next(v for k, v in vecs.items() if k in t) for t in texts]
    out, report = check_citations(text, _sources_with_vectors(), fake_embed, 0.775, arabic=False)
    assert "Sleep loss leads to errors on tasks [2]." in out                      # supported: kept
    assert "[3]" not in out and "in general (general information)." in out       # dropped + marked general
    assert "You slept 5 h last night [1]." in out                                  # user data: never checked
    assert [r["kept"] for r in report] == [True, False]


def test_user_data_sentence_losing_reference_citation_is_not_marked_general():
    from server.features.assistant.citecheck import check_citations
    out, _ = check_citations("Your sleep was short last week [3].", _sources_with_vectors(),
                             lambda texts: [[0.0, 0.0, 1.0]] * len(texts), 0.775, arabic=False)
    assert "[3]" not in out and "general information" not in out


def test_citation_check_never_fails_the_answer():
    from server.features.assistant.citecheck import check_citations

    def boom(texts):
        raise llm.OllamaError("off")
    text = "Sleep loss leads to errors [2]."
    assert check_citations(text, _sources_with_vectors(), boom, 0.775, arabic=False)[0] == text


def test_citation_check_runs_in_the_ask_flow(client, fake_chat, mock_ctx, monkeypatch):
    hit = Hit(id="nasa-hrp-sleep-risk:0", source_id="nasa-hrp-sleep-risk", title="Sleep risk (NASA HRP)",
              url=None, text="Astronauts commonly experience sleep deprivation.", score=0.8, embedding=[1.0, 0.0])
    monkeypatch.setattr(service, "retrieve", lambda q, k=None: [hit])
    monkeypatch.setattr(service, "_embed_for_check", lambda texts: [[0.0, 1.0]] * len(texts))  # unsupported
    fake_chat.reply = lambda user: f"Bone loss is 2% per month [{_num(user, 'Sleep risk')}].\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "How much bone do astronauts lose?"}).json()
    assert body["answer"] == "Bone loss is 2% per month (general information)."
    assert body["sources"] == []


# ---- token caps ------------------------------------------------------------------------
def test_arabic_questions_get_150_tokens_others_200(client, mock_ctx, monkeypatch):
    seen = []

    def capture(system, user, **kw):
        seen.append(kw.get("max_tokens"))
        yield llm.ChatResult(text="ok [1].\nMISSING: none")
    monkeypatch.setattr(service.llm, "chat_stream", capture)
    monkeypatch.setattr(service, "retrieve", lambda q, k=None: [REF_HIT])
    client.post("/api/assistant/ask", json={"question": "What does my data from the last 7 days show?"})  # no model
    client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"})
    client.post("/api/assistant/ask", json={"question": "ليش نومي قليل؟"})
    assert seen == [200, 150]


def test_dropped_citation_takes_its_joining_word_with_it():
    from server.features.assistant.citecheck import check_citations
    sources = _sources_with_vectors()
    out, _ = check_citations("These factors are in the passages [3] and [1].", sources,
                             lambda texts: [[0.0, 0.0, 1.0]] * len(texts), 0.775, arabic=False)
    assert out == "These factors are in the passages [1]."


def test_echoed_raw_data_line_is_removed(client, fake_chat, mock_ctx):
    fake_chat.reply = ('Your sleep was short [2].\n\nDATA: {"nights":5,"durationsMin":[430,415]}\nMISSING: none')
    body = client.post("/api/assistant/ask", json={"question": "How is my sleep?"}).json()
    assert "DATA:" not in body["answer"] and "durationsMin" not in body["answer"]


def test_false_missing_area_is_dropped(client, fake_chat, mock_ctx):
    fake_chat.reply = lambda user: (
        f"You slept 6 h 01 m on average [{_num(user, 'Your data: sleep')}].\n"
        "MISSING: your vital signs data for the last 7 days; blood pressure reading today")
    body = client.post("/api/assistant/ask", json={"question": "How am I sleeping?"}).json()
    assert body["missing"] == ["blood pressure reading today"]  # the false "vital signs missing" is gone


# ---- empty answer ------------------------------------------------------------------------
@pytest.mark.parametrize("reply", ["MISSING: temperature on Mars", "[1].\n\nPossible link:\nMISSING: none"])
def test_empty_answer_says_not_found(client, fake_chat, mock_ctx, reply):
    fake_chat.reply = reply
    body = client.post("/api/assistant/ask", json={"question": "What is the temperature on Mars?"}).json()
    assert body["mode"] == "llm"
    assert body["answer"] == "This isn't in the on-board references or your data."
    assert body["missing"] == ["the temperature on Mars"] and body["sources"] == []


def test_empty_arabic_answer_says_not_found_in_arabic(client, fake_chat, mock_ctx):
    fake_chat.reply = "MISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "شو درجة الحرارة على المريخ؟"}).json()
    assert body["answer"] == "هاي المعلومة مش موجودة بالمراجع اللي على المركبة ولا ببياناتك."
    assert body["missing"] == ["درجة الحرارة على المريخ"]


# ---- "possible possible" ---------------------------------------------------------------
@pytest.mark.parametrize("wrong", [
    "These are mentioned as possible causes for your alert.",
    "The possible cause of your alert is cabin noise.",
    "Your alert has possible underlying causes.",
    "Your short nights are possible possible factors.",
])
def test_cause_wording_never_doubles_possible(wrong):
    from server.features.assistant.wording import soften_causes
    out = soften_causes(wrong, set(), arabic=False)
    assert "possible possible" not in out.lower() and "a a " not in out.lower()
    assert "cause of" not in out and "causes for" not in out


def test_arabic_cause_wording_never_doubles():
    from server.features.assistant.wording import soften_causes
    out = soften_causes("الأسباب المحتملة لتنبيهك هي الضجة.", set(), arabic=True)
    assert "المحتملة المحتملة" not in out and "العوامل المحتملة لتنبيهك" in out


# ---- citations ---------------------------------------------------------------------------
def test_repeated_list_citations_are_cited_once_at_the_end():
    from server.features.assistant.prompt import merge_list_citations, split_citations
    text = "Possible factors:\n- Short nights [1, 2]\n- Noise [1, 2].\n- Schedule [1, 2]\n\nRest [3]."
    assert split_citations(merge_list_citations(text)) == (
        "Possible factors:\n- Short nights\n- Noise.\n- Schedule [1][2]\n\nRest [3].")
    # different citations per bullet stay where they are
    assert merge_list_citations("- A [1]\n- B [2]") == "- A [1]\n- B [2]"


def test_answer_citations_are_rendered_one_per_bracket(client, fake_chat, mock_ctx):
    fake_chat.reply = lambda user: (
        f"- Short sleep [{_num(user, 'Your data: sleep')}, {_num(user, 'Sleep risk')}]\n"
        f"- Fatigue risk [{_num(user, 'Your data: sleep')}, {_num(user, 'Sleep risk')}]\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert "- Short sleep\n- Fatigue risk [1][2]" in body["answer"]
    assert ", " not in re.sub(r"[^\[\],\d ]", "", body["answer"])  # no "[1, 2]" left


# ---- missing line: only real missing data -----------------------------------------------
def test_missing_line_drops_notices_and_next_steps(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Your sleep was short [2].\nMISSING: Protect an 8-hour sleep opportunity tonight; "
                       "template answer; next steps from the alert; blood pressure reading today")
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert body["missing"] == ["blood pressure reading today"]


# ---- "the astronaut" -> "you" ----------------------------------------------------------------
def test_the_astronaut_becomes_you(client, fake_chat, mock_ctx):
    fake_chat.reply = ("The astronaut's sleep was short [2]. The astronaut is tired, and the astronaut has "
                       "3 short nights.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    a = body["answer"]
    assert "astronaut" not in a.lower()
    assert a.startswith("Your sleep was short") and "You are tired, and you have 3 short nights" in a


def test_system_prompt_says_address_the_user_as_you():
    from server.features.assistant.prompt import SYSTEM_PROMPT
    assert 'Never write "the astronaut"' in SYSTEM_PROMPT


# ---- sleep self-contradiction ------------------------------------------------------------
@pytest.mark.parametrize("wrong", [
    "Your sleep data shows no irregularities.",
    "There were no irregularities.",
    "You had no short nights this week.",
    "Your sleep was regular.",
])
def test_no_irregularities_is_replaced_when_nights_were_short(client, fake_chat, mock_ctx, wrong):
    fake_chat.reply = f"{wrong} Keep resting.\nMISSING: none"  # mock: 3 nights under 6 h
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert wrong.rstrip(".") not in body["answer"]
    assert "3 night(s) under 6 h" in body["answer"] and "Keep resting." in body["answer"]


def test_general_no_sleep_problems_sentence_is_kept(client, fake_chat, mock_ctx):
    fake_chat.reply = "Most astronauts report no sleep problems in the first week.\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert "Most astronauts report no sleep problems" in body["answer"]


def test_no_recent_data_is_not_read_as_fresh(client, fake_chat, mock_ctx):
    fake_chat.reply = "Your skin temperature has no recent data.\nMISSING: none"  # mock: skin temp is stale
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert "Your skin temperature has no recent data" in body["answer"]
    assert "Vital signs: up to date" not in body["answer"]


def test_sentence_quoting_alert_factors_cites_the_alert(client, fake_chat, mock_ctx):
    fake_chat.reply = ("The possible factors listed include several short nights in a row and a shifted work "
                       "schedule.\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert [s["id"] for s in body["sources"]] == ["alert:al-mock-fat01"]
    assert body["answer"].endswith("schedule [1].")


# ---- invented label lines ----------------------------------------------------------------
def test_label_only_lines_are_removed(client, fake_chat, mock_ctx):
    fake_chat.reply = ("Sleep loss can lead to fatigue [1].\n\nPossible link:\n\n**NOT A CONFIRMED CAUSE:**\n\n"
                       "الخلاصة:\n\nNext steps:\n- Rest well tonight\nMISSING: none")
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    a = body["answer"]
    assert "Possible link:" not in a and "NOT A CONFIRMED CAUSE" not in a and "الخلاصة" not in a
    assert "Next steps:\n- Rest well tonight" in a  # a label that heads a list stays
    assert "Sleep loss can lead to fatigue" in a


def test_label_with_text_after_it_is_kept(client, fake_chat, mock_ctx):
    fake_chat.reply = "Possible link: short sleep and slower attention.\nMISSING: none"
    body = client.post("/api/assistant/ask", json={"question": "Is my sleep a problem?"}).json()
    assert body["answer"].startswith("Possible link: short sleep and slower attention")


def test_hard_stop_is_120s():
    from server.features.assistant.settings import setting
    assert setting("assistant_max_answer_sec") == 120
