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
assistant_timeout_sec:
  value: 20
  unit: s
  source: "AstroCare_Full_Plan.md §11 (team decision: fallback if the local model is slower than 20 s)"
  note: "Ollama chat timeout; after it the assistant answers from the alert template."

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


---

## Noura: Reports, comms, relax

Local copies until merged:
- Python: `server/features/reports/router.py` (`ReportItem`, `ReportItemIn`)
- TS: `app/src/features/support/reports/types.ts` (coming with the reports screen)

### N1. `ReportItem` (contracts §1) → `contracts.ts` + `models.py`

```ts
type ReportItemKind = 'alert' | 'cmo_question' | 'note';

interface ReportItem {
  id: string;
  kind: ReportItemKind;
  refId?: string | null;      // alert.id when kind = 'alert'
  title: string;
  text: string;
  sourceFeature: 'monitoring' | 'daily' | 'assistant' | 'relax';
  createdTs: string;
  reportId?: string | null;   // set once the item is included in a report
}
```

**Live now:**
```
POST   /api/reports/items   { kind, refId?, title, text, sourceFeature } -> 201 ReportItem
GET    /api/reports/items?pending=true                                    -> ReportItem[]
DELETE /api/reports/items/{id}                                            -> 204 (404 if unknown)
```
Python: `from server.features.reports.service import add_report_item`
`add_report_item(kind, title, text, source_feature, ref_id=None) -> dict`

`sourceFeature` adds `'relax'` to the contract list (the Relax "Request support" button).

### N2. Tables (created by my own code, not `core/db.TABLES`)

`report_items` is created with `CREATE TABLE IF NOT EXISTS` in `server/features/reports/service.py`, through `core.db.connect()`. `comms_windows` will follow the same way.

### N3. `shared/api/client.ts`: `del` (same as Marah's A4)

Needed for `DELETE /api/reports/items/{id}`. Until then my `reports/api.ts` uses `fetch('/api/...')` directly.


### N4. `CommsStatus` (contracts §3)

```ts
interface CommsStatus {
  connected: boolean;          // scheduled window open now, or a simulated one
  simulatedWindow: boolean;
  nextWindowTs: string;        // from core/status.next_comm_window() (config/app.yaml), not duplicated
  windowDurationMin: number;
  queuedCount: number;
  signalDelaySec: number;
  lastWindowTs?: string | null;
}
```

**Live now:**
```
GET  /api/comms                   -> CommsStatus   (replaces the old shape with `outbox[]`)
POST /api/comms/simulate-window   -> { windowId, openedTs, sentReportIds[] }   // demo only: queued -> sent
```
Python: `from server.features.reports.service import get_comms_status` (same shape, snake_case). Haya can call it from `core/status` if useful.
Table: `comms_windows` (created in my `service.py`).