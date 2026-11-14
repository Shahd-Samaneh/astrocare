# Support pair: contract proposals for Haya

Shared file for Marah and Noura. Each person appends her own section; don't overwrite the other's.
Until Haya merges a change, the owner keeps a local copy of the types inside her own folder.

---

## Marah: Assistant + permissions

Local copies until merged:
- TS: `app/src/features/support/assistant/types.ts`
- Python: `server/features/assistant/models.py`

### A1. `AssistantAnswer` (contracts §4) → `contracts.ts` + `models.py`

```ts
interface AssistantSource { id: string; title: string; url?: string }

interface AssistantAnswer {
  answer: string;
  sources: AssistantSource[];
  missing: string[];
  refused: boolean;
  refusalReason?: 'medication' | 'diagnosis';
  // llm: local model · fallback: template (model off / too slow)
  // alert / data: built in code from the open alert / the fixed facts, without the model
  mode: 'llm' | 'fallback' | 'alert' | 'data';
  latencyMs: number;
  note?: string;        // small notice under the badge (template / too slow / cut off); never in `missing`
  alertRuleId?: string; // mode 'alert': the rule explained (badge "From alert R-FAT-01")
}
```
`missing` holds only real missing data (no template notice, no next steps).
`POST /api/assistant/ask { question }` now returns this type. It replaces the stub's `AskOut` (`model` and `Source.path` are dropped).

### A2. `AssistantPermissions` (contracts §5)

```ts
interface AssistantPermissions {
  assistant: { vitals: boolean; sleep: boolean; tests: boolean; exercise: boolean; checkins: boolean };
  report: { checkins: boolean };
}
```
Defaults: everything `true` except `assistant.checkins = false` and `report.checkins = false`.
`GET /api/assistant/permissions` and `PUT /api/assistant/permissions` (partial body allowed and merged).
Python: `from server.features.assistant.permissions import get_permissions` → a dict in this snake_case shape (the keys are already single words).

### A3. `AssistantInfo` (P1)

```ts
interface AssistantInfo {
  ollamaUrl: string; reachable: boolean; chatModel: string; embedModel: string;
  modelsAvailable: string[];
  modelSizeBytes?: number;     // from Ollama /api/tags
  ramBytes?: number;           // from Ollama /api/ps (size of the loaded model)
  avgLatencyMs?: number;       // measured, from assistant_log
  avgFirstTokenMs?: number;    // measured, time to the first streamed token
  tokensPerSec?: number;       // measured, eval_count / eval_duration
  answersLogged: number;
  chunksIndexed: number;
}
```

### A4. `shared/api/client.ts`: add `put`

`api` only has `get` and `post`. Proposal: `put: <T>(path, body) => request<T>('PUT', path, body)` (and `del` for Noura's `DELETE /api/reports/items/{id}`).
Until then my `assistant/api.ts` uses `fetch('/api/...')` directly (relative path, same origin).

### A5. `config/thresholds.yaml`: new keys (engineering values, not clinical)

```yaml
assistant_first_token_timeout_sec:
  value: 30
  unit: s
  source: "Team decision (demo latency), not clinical; replaces the 20 s in AstroCare_Full_Plan.md §11"
  note: "Time from the question to the first streamed token; with no token by then the assistant answers from the alert template. Also the longest allowed gap between two tokens. Raised from 20 s: on the demo laptop a streamed answer can start at ~22 s, and that is better than a template at 20 s."

assistant_max_answer_sec:
  value: 120
  unit: s
  source: "Team decision (latency), not clinical"
  note: "Hard stop for a streamed answer; the part written so far is kept and marked incomplete. Raised from 90 s: at ~3 tokens/s a full summary took ~100 s on the demo laptop."

assistant_top_k:
  value: 3
  unit: chunks
  source: "Team decision (retrieval latency), not clinical"
  note: "Reference passages given to the model per question (was 4)."

assistant_chunk_words:
  value: 300
  unit: words
  source: "Team decision (retrieval latency), not clinical; replaces the ~500 words in AstroCare_Full_Plan.md §11"
  note: "Chunk size for references/ ingestion. After a change, rebuild: python -m server.features.assistant.ingest --rebuild"

assistant_chunk_overlap_words:
  value: 40
  unit: words
  source: "Team decision (retrieval), not clinical"
  note: "Overlap between consecutive chunks."

assistant_max_answer_tokens:
  value: 200
  unit: tokens
  source: "Team decision (latency), not clinical"
  note: "Upper bound on the local model's answer length (keeps the reply inside the timeout)."

assistant_max_arabic_tokens:
  value: 150
  unit: tokens
  source: "Team decision (latency), not clinical"
  note: "Answer length cap for Arabic questions sent to the model (replaces assistant_max_summary_tokens: 'my data' summaries are now built in code from the fixed facts, without the model)."

assistant_citation_min_similarity:
  value: 0.775
  unit: cosine
  source: "Calibrated on benchmark answers (2026-11-14): 10 supported sentence/passage pairs scored 0.783–0.929, 9 unsupported pairs 0.607–0.767; value = midpoint"
  note: "nomic-embed-text cosine between an answer sentence and its cited reference passage; below it the citation is dropped (user data and alert citations are never dropped). Small margin: re-calibrate if the references or the embed model change."

assistant_num_ctx:
  value: 4096
  unit: tokens
  source: "Team decision: fits system prompt + user data + 3 passages of ~300 words"
  note: "Ollama context window for the chat model."

assistant_slow_reply_ms:
  value: 10000
  unit: ms
  source: "Team decision (UX), not clinical"
  note: "Before the first word, the UI shows 'Thinking on this device…'; after this it shows 'The local model is reading your data and the references…'."
```
Until merged, `server/features/assistant/settings.py` reads these keys from `thresholds.yaml` and falls back to the same values.

**Plan note (AstroCare_Full_Plan.md §11, "المساعد"):** the references are now split into passages of **~300 words
with a 40-word overlap**, and the model gets the **top 3** (not ~500 words / top 4). Reason: on the demo laptop,
reading a ~2,400-token prompt took most of the 20 s first-token budget. Measured result: see the benchmark in the
PR description. The same plan line says "fallback if slower than 20 s": that is now **30 s to the first token**
(see `assistant_first_token_timeout_sec`). Please update the plan line when you merge this.

**Also (no new keys):** every Ollama call sends `keep_alive: "60m"`. At server startup (router `on_startup`, so
`main.py` is unchanged; skipped under pytest or with `ASTROCARE_NO_WARMUP=1`) and when the Assistant page opens
(`POST /api/assistant/warmup`), a background thread loads the embed model and **primes the prompt cache**: it sends
the exact fixed system prompt + the current user-data block and asks for one token, so the first real question
only reads its passages and the question. The system prompt is identical on every call, with the answer language
on a `LANGUAGE:` line just before the question.

**Fixed facts (no new keys):** for sleep, attention, vital signs and exercise, the exact values (nights recorded,
average/shortest/last night, nights under `sleep_short_hours`, latest attention median, lapses, which readings are
up to date / stale / missing, exercise logged) are computed in code (`assistant/facts.py`) and shown to the model as
`FIXED FACT:` lines it must not change. A sentence about the user's own data that contradicts one of them (e.g. "no
lapses" when lapses > 0, or "stale" for fresh data) is replaced by the fact line, with its citation.
`sleep_short_hours` is read from `config/thresholds.yaml`, where its `source` is still `TODO`.

### A6. Tables (created by my own code, not `core/db.TABLES`)

`assistant_chunks`, `assistant_log`, `assistant_permissions` are created with `CREATE TABLE IF NOT EXISTS` in `server/features/assistant/store.py`, through `core.db.connect()`. If Haya prefers, they can move into `TABLES`; the column names stay the same.

### A7. Shared components (move to `shared/components` later)

- `SourceList`: numbered sources under an answer (title + `[n]`).
- `ModeBadge`: "Local model" / "Template" badge.

Both live in `app/src/features/support/assistant/components/` for now.

### A8. `server/tests/test_health.py`: update the assistant test (Haya's file)

`test_assistant_refuses_medication_questions` asserts the stub's behaviour: `ok["sources"] == []` for
"How does microgravity affect sleep?". With the real assistant that answer has sources (references, or the
alert in fallback mode), and the test also calls the real Ollama on the machine, so it is slow and machine-dependent.
Proposed change (the two refusal asserts stay as they are):

```python
def test_assistant_refuses_medication_questions(client, monkeypatch):
    from server.features.assistant import llm
    monkeypatch.setattr(llm, "ollama_cfg", lambda: {"url": "http://127.0.0.1:9", "chat_model": "x", "embed_model": "y"})
    assert client.post("/api/assistant/ask", json={"question": "What dose of ibuprofen?"}).json()["refused"] is True
    assert client.post("/api/assistant/ask", json={"question": "Can I take 200 mg?"}).json()["refused"] is True
    ok = client.post("/api/assistant/ask", json={"question": "How does microgravity affect sleep?"}).json()
    assert ok["refused"] is False
    assert ok["mode"] == "fallback"  # Ollama pointed at a dead port in tests
```

### A9. Streaming answers: `POST /api/assistant/ask/stream`

Same body and flow as `/ask`, but the response is NDJSON (`application/x-ndjson`), one event per line:

```ts
type AssistantStreamEvent =
  | { type: 'token'; text: string }   // a piece of the answer, safe to show
  | { type: 'reset' }                 // drop the tokens shown so far (the final answer replaces them)
  | { type: 'final'; answer: AssistantAnswer; stats: { model: string | null; firstTokenMs: number | null;
                                                        evalCount: number | null; evalDurationNs: number | null } };
```
`final` is always the last event. A refused question is only a `final`. Tokens are held back by a few
characters so the output safety check sees a whole medicine name or dose before anything is shown.
`/ask` stays as it is (it runs the same flow and returns only the final answer).

### A10. Chat model setting

`ASTROCARE_CHAT_MODEL` (env var) overrides `config/app.yaml` → `ollama.chat_model` (default `llama3.2:3b`).
If the team picks `llama3.2:1b` for the demo, the change is one line in `app.yaml` (Haya), and
`setup` scripts should also `ollama pull` that model.

### A11. Answer post-processing (no contract change)

Every model answer goes through, in order: cite echoed facts and named sources → replace sentences that contradict a
fixed fact → **soften cause wording** about the user's data ("caused by", "because of", "due to", "cause(s)", "سبب",
"بسبب" → "possible factor" / "possibly linked to", plus "(a possible link, not a confirmed cause)") → **weak-citation
check** (`assistant_citation_min_similarity`; an uncited general sentence gets "(general information)") → renumber
citations. The template fallback says whether the model was **too slow** or **not available**, explains the
**highest-level open alert** (urgent > review > info, newest first), lists missing data once, cites [1] once, lists each
source once, and uses correct Arabic plurals.

### A12. `AssistantAnswer.nextSteps` + "Add to report" notes

```ts
interface AnswerStep { text: string; link?: string | null; lockedForCMO: boolean }
interface AssistantAnswer { /* ...A1... */ nextSteps?: AnswerStep[] }  // mode 'alert' and the alert template
```
Same order and wording as the "Next steps" list in the answer text; a CMO-locked step is `"(needs CMO review)"`
with no link. Every answer now has **Add to report**, which sends Noura's `POST /api/reports/items`
`{ kind: 'note', title: <question>, text: <answer without the sources list and its [n] markers>, sourceFeature: 'assistant' }`
(medication refusals keep the CMO button instead). Answers built in code (alert, my data, template) list only the
sources their text cites, renumbered 1..n, like model answers already did. Alert answers end with
`Background: [2][3]` (AR `خلفية: [2][3]`), citing each `alert.sources` id that is a `references/<id>.txt` file
(title and url from its header); ids with no such file are ignored.

### A13. `NextStep.link` (contracts.ts `NextStep` + `core/models.py`), for Haya and the Daily pair

The assistant can show a next step as a button that navigates in the app (`/daily#checkin`,
`/attention?retest=<alertId>`), but `NextStep` today is only `{ text, resourceId?, availability?, lockedForCMO }`,
so every step is plain text. Proposal:

```ts
interface NextStep { text: string; resourceId?: string | null; availability?: Availability | null;
                     lockedForCMO: boolean; link?: string | null }  // in-app path, starts with "/"
```
Once it is merged, the assistant change is one line: `step_link()` in `server/features/assistant/fallback.py`
returns `step.get("link")`. Only same-app paths are used (a host, a scheme or `//` is dropped), and a
CMO-locked step never gets a button.

### A14. Deep link `/assistant?q=<text>` (for Haya: "Ask the assistant" on Alert detail and Today)

Opening `/assistant?q=<url-encoded question>` asks that question once, on arrival. `?q` is then removed from the
URL (replace), so Back or a reload does not ask it again. If another answer is still being written, the question
is put in the input box instead. Suggested buttons:

```tsx
// Alert detail: explains exactly this alert (the backend picks the alert by its rule id)
<Button variant="secondary" to={`/assistant?q=${encodeURIComponent(`Why did I get ${alert.ruleId}?`)}`}>
  Ask the assistant
</Button>
// Today
<Button variant="secondary" to={`/assistant?q=${encodeURIComponent('What does my data from the last 7 days show?')}`}>
  Ask the assistant
</Button>
```
The conversation is kept when the user leaves the Assistant page and comes back (and across a reload of the
same tab: `sessionStorage`), and **Clear chat** empties it.
