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
  mode: 'llm' | 'fallback';
  latencyMs: number;
}
```
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
  value: 20
  unit: s
  source: "AstroCare_Full_Plan.md §11 (team decision: fallback if the local model is slower than 20 s)"
  note: "Time from the question to the first streamed token; with no token by then the assistant answers from the alert template. Also the longest allowed gap between two tokens."

assistant_max_answer_sec:
  value: 90
  unit: s
  source: "Team decision (latency), not clinical"
  note: "Hard stop for a streamed answer; the part written so far is kept and marked incomplete."

assistant_top_k:
  value: 4
  unit: chunks
  source: "Team decision (retrieval), not clinical"
  note: "Reference chunks given to the model per question."

assistant_chunk_words:
  value: 500
  unit: words
  source: "AstroCare_Full_Plan.md §11 (team decision)"
  note: "Chunk size for references/ ingestion."

assistant_chunk_overlap_words:
  value: 50
  unit: words
  source: "Team decision (retrieval), not clinical"
  note: "Overlap between consecutive chunks."

assistant_max_answer_tokens:
  value: 200
  unit: tokens
  source: "Team decision (latency), not clinical"
  note: "Upper bound on the local model's answer length (keeps the reply inside the timeout)."

assistant_num_ctx:
  value: 4096
  unit: tokens
  source: "Team decision: fits system prompt + user data + 4 chunks of ~500 words"
  note: "Ollama context window for the chat model."

assistant_slow_reply_ms:
  value: 8000
  unit: ms
  source: "Team decision (UX), not clinical"
  note: "The UI shows a 'still thinking' message after this."
```
Until merged, `server/features/assistant/settings.py` reads these keys from `thresholds.yaml` and falls back to the same values.

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
