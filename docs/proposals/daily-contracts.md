# Proposals from the Daily pair (Shahd + Nadia) → Haya

We don't edit `server/core/`, `app/src/shared/`, the contracts or the simulator ourselves.
Everything below is a request. Until it is merged, we work around it inside `server/features/daily/` and `app/src/features/daily/`. The workaround is noted under each item.

---

## 1. `CognitiveTest.context` and `CognitiveTest.relatedAlertId`

**Why:**
1. R-FAT-01 must compare only *routine* tests with the baseline. A retest done right after rest must not be mixed into that comparison.
2. A retest has to point at the alert it answers, so the alert can move to `recheck`.
3. Both fields are optional, so existing rows and clients keep working.

`app/src/shared/types/contracts.ts`
```diff
+export type TestContext = 'routine' | 'retest';
+
 export interface CognitiveTest {
   id: string;
   ts: string;
   trialsMs: number[];
   medianMs: number;
   lapses: number;
   falseStarts: number;
+  context?: TestContext; // default 'routine'
+  relatedAlertId?: string | null;
 }
```

`server/core/models.py`
```diff
+TestContext = Literal["routine", "retest"]
+
 class CognitiveTest(ApiModel):
     id: str
     ts: str
     trials_ms: list[float]
     median_ms: float
     lapses: int
     false_starts: int
+    context: TestContext = "routine"
+    related_alert_id: Optional[str] = None
```

`server/core/db.py` (`TABLES["cognitive_tests"]`)
```diff
     "cognitive_tests": {
         "id": "TEXT PRIMARY KEY", "ts": "TEXT", "trials_ms": "JSON", "median_ms": "REAL",
         "lapses": "INTEGER", "false_starts": "INTEGER",
+        "context": "TEXT", "related_alert_id": "TEXT",
     },
```

**Workaround now:**
- `DailyCognitiveTest(CognitiveTest)` in `server/features/daily/attention_stats.py`, plus the TS type `DailyCognitiveTest` in `app/src/features/daily/api.attention.ts`.
- A table `daily_test_context(test_id, context, related_alert_id)`, created by our code with `CREATE TABLE IF NOT EXISTS`. A test without a row there is `routine`.
- After the merge, we drop the table and read the columns directly.

---

## 2. `Alert.nextSteps[].action`

**Why:**
1. Alert detail can show a next step as a button that opens the right page (`/attention?retest=<id>`, `/daily#checkin`).
2. That closes the demo loop: alert → retest → `recheck`, without Alert detail hard-coding Daily routes.
3. The field is optional. Steps without it render as today.

`app/src/shared/types/contracts.ts`
```diff
+export interface NextStepAction {
+  label: string;
+  route: string; // in-app route, e.g. "/attention?retest=al-123"
+}
+
 export interface NextStep {
   text: string;
   resourceId?: string | null;
   availability?: Availability | null;
   lockedForCMO: boolean;
+  action?: NextStepAction | null;
 }
```

`server/core/models.py`
```diff
+class NextStepAction(ApiModel):
+    label: str
+    route: str
+
+
 class NextStep(ApiModel):
     text: str
     resource_id: Optional[str] = None
     availability: Optional[Availability] = None
     locked_for_cmo: bool = Field(default=False, alias="lockedForCMO")
+    action: Optional[NextStepAction] = None
```

**Workaround now:** `DailyNextStep(NextStep)` with `action` in `server/features/daily/attention_stats.py`. Our engine hook writes the steps, including `action`, into the alert's `next_steps` JSON column, so the data is already in the DB.
→ But `/api/alerts` returns rows through the shared `Alert` model, and Pydantic drops the unknown `action` key there. So until this field is merged, **Alert detail won't see `action`**. Our routes (`/attention?retest=<alertId>`, `/daily#checkin`) work when opened directly, and the step text names them.

---

## 3. Engine: update the open alert instead of skipping it

**Why:**
1. The contract says "one open alert per rule; each run updates it". Today `run_rules()` only *skips* duplicates, so `whatChanged` and `missing` never refresh (for example, after a check-in).
2. Without this, the alert would keep showing "Today's check-in" as missing after the crew member did it.
3. The change is small and also fixes stale content for every other rule.

`server/rules/engine.py`
```diff
-def _is_open_duplicate(rule_id: str, key: str) -> bool:
-    return db.count("alerts", "rule_id = ? AND dedupe_key = ? AND status != 'closed'", (rule_id, key)) > 0
+def _open_duplicate(rule_id: str, key: str) -> dict | None:
+    rows = db.query("alerts", "rule_id = ? AND dedupe_key = ? AND status != 'closed'", (rule_id, key), limit=1)
+    return rows[0] if rows else None
@@
         key = draft.dedupe_key or draft.title
-        if _is_open_duplicate(rule.id, key):
-            continue
+        existing = _open_duplicate(rule.id, key)
+        if existing:
+            db.update("alerts", existing["id"], {
+                "what_changed": draft.what_changed, "data_used": draft.data_used,
+                "missing": draft.missing, "possible_factors": draft.possible_factors,
+                "next_steps": [s.model_dump(by_alias=False) for s in draft.next_steps],
+            })
+            continue
```

**Workaround now:** `run_daily_engine()` in `server/features/daily/engine_hooks.py` calls the existing `run_rules()`. It then re-evaluates *only our two rules* (R-SLP-01, R-FAT-01) and updates their open alert in place. It also applies the retest → `recheck` step. Every POST in our endpoints calls it. Other pairs' rules are unaffected.

---

## 4. Simulator

Checked after `npm run reseed` (step 11 in Shahd's task):

| Expectation | Result |
|---|---|
| Nights 141 and 142 are under 6 h | ✅ ~5 h each (`sleep-141`, `sleep-142`) |
| Last two routine tests ≈ 20 % slower than baseline | ✅ `pvt-141` and `pvt-142` ≈ 342 ms vs a baseline of ≈ 285 ms |
| **No check-in today** | ❌ `ci-142` is created at 07:00 on day 142, and the seed time is 142:07:31, so a check-in already exists today |
| R-FAT-01 open at `review` with "Today's check-in" missing | ❌ follows from the row above: the alert opens, but "Today's check-in" is not in `missing` |

**Exact change needed** in `server/core/simulator.py`, check-ins loop: stop at yesterday, as the blood-pressure loop already does.
```diff
     # ---- check-ins -------------------------------------------------------------
-    for d in range(first_day, today + 1):
+    for d in range(first_day, today):  # no check-in today: the demo shows it as missing
         skipped = d == first_day + 6
```
Nothing else depends on `ci-142` (we searched for `ci-142` and `checkins` in `server/`).
Also update the docstring at the top of the file: "* no check-in today (R-FAT-01 lists it as missing)".

---

## 5. Small note: `test_health.py`

`POST /api/tests` now returns the contract shape `{ test, pctVsBaseline, withinRange }`. So the one assertion in `server/tests/test_health.py::test_posts_accept_camel_case` that read `.json()["lapses"]` now reads `.json()["test"]["lapses"]`. That's a one-line change, made by Shahd in her branch, and called out here so the reviewer sees it.
