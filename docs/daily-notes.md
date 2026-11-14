# Daily notes (Shahd + Nadia)

Working log for the Daily pair. The agreed contract is in [daily-contract.md](daily-contract.md). Requests to Haya are in [proposals/daily-contracts.md](proposals/daily-contracts.md).

## Shahd: decisions

| # | Decision | Why |
|---|---|---|
| S1 | Created `feature/daily` from `main` and pushed it. `shahd/daily` was already on the same commit. | The branch didn't exist on GitHub, and `develop` doesn't exist yet either. |
| S2 | `gh` isn't installed, so **no PR was opened or merged automatically**. A direct merge into `feature/daily` was also blocked (correctly: PRs only). | The PR links are under "For Shahd" below. |
| S3 | `config/thresholds.yaml` → `daily:` gets its own `value/source/note` header. Nested keys are read by `server/features/daily/thresholds.py::daily_threshold()`, which uses the core `_load_yaml` and falls back to the top-level key. | The core loader is flat, and `test_thresholds_have_sources` checks every top-level entry. Proposal §6 makes nesting first-class. |
| S4 | Only `pvt_lapse_ms` has a source ("Psychomotor Vigilance Test convention"). Every other daily key is `note: "experimental value"`. No citation was invented. | Medical honesty rule. |
| S5 | Lapse = RT **≥** `pvt_lapse_ms` (the old stub used `>`). | Contract §5 says "lapses (≥ pvt_lapse_ms)". |
| S6 | The baseline maths live in one place, `server/features/daily/attention_stats.py`, used by the API, the summary and both rules. It also holds the contract extensions (`DailyCognitiveTest`, `DailyNextStep`, `DailyAlert`) and the `daily_test_context` table. | Prevents two baselines drifting apart. Extensions stay out of core (contract §1). |
| S7 | Baseline = median of the 7 newest **routine** tests older than 48 h. Range = min/max of those (or median ± 10 % when there are fewer than 3). Retests are never in the baseline or in the "last 48 h" median. | Contract §3 and §5. A retest after rest would otherwise mask the pattern. |
| S8 | The engine only *skips* duplicates, so `engine_hooks.py::run_daily_engine()` runs `run_rules()` and then updates the open R-SLP-01 / R-FAT-01 alert in place: whatChanged, missing, nextSteps with the real alert id in `/attention?retest=<id>`, and retest → `recheck`. Every Daily POST calls it. | Contract §3 ("one open alert, each run updates it"). Proposal §3 moves this into the engine. |
| S9 | Retest line: `Retest at HH:MM: median X ms (within/outside your usual range)`. HH:MM is **mission time (MET)**, the same clock as the status bar. Alerts never auto-close. | Consistent with the rest of the app. Closing is a human decision. |
| S10 | The "No response within 5 s" trial records 5000 ms (a lapse). This is a UI constant, not a clinical threshold. | Keeps the test from hanging if the crew member walks away. |
| S11 | Space is handled on `window` only. The response area uses `pointerdown` (not `click`), so one key press or tap never counts twice. The stimulus time is re-taken in the animation frame that paints it. | Timing fairness. |
| S12 | `POST /api/tests` returns `{ test, pctVsBaseline, withinRange, baseline }`. `baseline` is an extra field, so the UI doesn't need a second request. `server/tests/test_health.py` got a one-line change (`["test"]["lapses"]`). | Contract shape, plus the existing smoke test. |
| S13 | `GET /api/tests` and `GET /api/checkins` are now **newest first** with default `n` 10 and 7. Before, they were oldest-first with n=14. | Contract §2. Nobody else called them (checked with grep). |
| S14 | Default `GET /api/checkins` **omits** the `notePrivate` key (not `null`). A skipped check-in stores no mood, stress or note. Mood and stress are required unless `skipped`. | Privacy by construction. |
| S15 | `GET /api/daily/summary` uses Nadia's `sleep_summary` / `exercise_summary` if they exist in `sleep.py` / `exercise.py`, else stubs marked `"stub": true`. `activeDailyAlerts` is returned through `DailyAlert`, so `nextSteps[].action` **is** visible there, while `/api/alerts` still drops it (proposal §2). | Marah and Noura can build on it now. |
| S16 | The NASA URLs live only in `server/features/daily/sources.py`. The frontend shows titles and our own "why" sentence, never links. `NasaBasis` adds "Public NASA material, summarised in our own words. Not an endorsement." | Offline rule. Never imply endorsement. |
| S17 | The page header is eyebrow `Daily · Mission day N · <date>` with the title "Attention check". | Matches the other pages' PageHeader pattern. |
| S18 | `CheckInPanel` takes `id` (default `checkin`) and `hideBasis`. "Add another check-in" reopens the form after "Done today ✓". | Nadia embeds it at `#checkin`. |
| S19 | Daily tests use their own fresh DB per test (`server/tests/_daily_helpers.py`), and restore the shared DB path afterwards. They **remove today's seeded check-in** to emulate proposal §4. An `xfail` test marks the pending simulator change. | Keeps the session `client` fixture untouched, and makes the gap visible. |

## Simulator check (step 11, after `npm run reseed`)

| Check | Result |
|---|---|
| Nights 141–142 under 6 h | ✅ 4.9 h and 5.1 h |
| Last 2 routine tests ≈ 20 % slower | ✅ 342 ms vs baseline 285 ms (+20 %) |
| No check-in today | ❌ `ci-142` exists (07:00 on day 142; seed time is 142:07:31) |
| R-FAT-01 open at `review` with "Today's check-in" missing | ⚠️ open at `review`, but `missing` is empty because of the row above |

The exact one-line fix for `server/core/simulator.py` is in proposals §4. **Send it to Haya.**

## Verification (step 13)

- `npm run test`: 44 passed, 1 xfailed (the simulator item above), typecheck clean.
- `npm run lint`: clean.
- `npm run build` then `npm run check:offline`: 0 remote URLs.
- Live check on `npm run start` (after `npm run reseed`):
  - `/api/alerts` showed R-FAT-01 at `review`
  - a POST retest then moved it to `recheck` with "Retest at 07:31: median 295 ms (within your usual range)"
  - a POST check-in returned 201
  - `/attention?retest=…` serves the SPA
  - reseeded afterwards
- Not checked: the UI in a real browser (clicking through the test by hand).

---

## Shahd: done / not done / for Nadia / for Haya / for Marah

### Done
- Contract saved (`docs/daily-contract.md`) and proposals written (`docs/proposals/daily-contracts.md` §1–6).
- Router split:
  - `router.py` only aggregates
  - Nadia's `sleep.py`, `exercise.py`, `today.py` keep the old stub behaviour (`# Owner: Nadia`)
- `daily:` thresholds with sources and notes.
- `GET /api/daily/sources`, with 7 sources.
- Attention API:
  - `GET /api/tests`, `GET /api/tests/baseline`, `POST /api/tests` (context, retest, engine run)
  - service function `attention_summary(n)`
- Check-in API:
  - `GET /api/checkins` (`includePrivate` opt-in), `POST /api/checkins` (skip counts, engine run)
  - service function `checkins_summary(n)`
- Rules R-SLP-01 (info) and R-FAT-01 (review), plus the in-place sync: dedupe, retest → recheck, check-in clears missing, action routes.
- `GET /api/daily/summary` (never contains private notes).
- Attention check page:
  - intro, 5-trial runner (click / tap / Space, Esc, false starts repeat), result, last-10 chart over the baseline band
  - last night's sleep, retest mode with a link back to the alert, NasaBasis
- `CheckInPanel`, exported from `app/src/features/daily/index.ts`.
- Tests: `test_daily_attention.py`, `test_daily_rules.py`.

### Not done
- **No PRs opened** (`gh` isn't installed), so the "split router" PR is **not merged**. Open both PRs by hand (links below).
- "Today's check-in" doesn't show as missing in the real seeded demo until Haya applies proposal §4.
- Alert detail can't render next-step buttons until Haya merges proposal §2 (`action`) and §3 (engine update).
- Not tested by hand in a browser.

### For Nadia
- `server/features/daily/sleep.py`, `exercise.py` and `today.py` are yours. They are unchanged stubs with `# Owner: Nadia`.
- Add `sleep_summary(days)` to `sleep.py` and `exercise_summary(days)` to `exercise.py`. `summary.py` picks them up automatically and stops using its stubs.
- Embed the check-in:
  ```tsx
  import { CheckInPanel } from '../index';
  <CheckInPanel />   // renders <section id="checkin">
  ```
- `index.ts` is yours. I added only the lines under `// Shahd`.
- R-FAT-01's next steps link to `/daily#checkin` and `/daily#exercise`. Please give the exercise card `id="exercise"`, and the sleep card `id="sleep"` (R-SLP-01 links to `/daily#sleep`).
- Your POSTs should call the engine too. Use `from .engine_hooks import run_daily_engine` so our alerts refresh.
- Today plan: a **skipped** check-in counts as done (`today.py` still uses `skipped = 0`).

### For Haya
- Please review `docs/proposals/daily-contracts.md`:
  - §1 `CognitiveTest.context` / `relatedAlertId`
  - §2 `NextStep.action`
  - §3 engine updates the open alert, and replaces `{alertId}` in action routes
  - **§4 simulator: no check-in today (one line)**
  - §5 `test_health.py` one-line change
  - §6 nested thresholds
- New threshold keys under `daily:`:
  - `sleep_short_hours`, `sleep_short_nights`, `attention_slower_pct`, `attention_baseline_n`, `pvt_lapse_ms`, `exercise_missed_days`
  - three of them duplicate existing top-level keys (see §6)
- New rule files in `server/rules/`: `r_slp_01_short_sleep.py` and `r_fat_01_fatigue_pattern.py`.

### For Marah (assistant `references/` ids)
Use these exact ids so alert `sources`, `GET /api/daily/sources` and the assistant agree:
```
nasa-hrp-sleep-risk
nasa-hrp-bmed-risk
nasa-pvt-iss
nasa-hrp-hazards
nasa-hrp-risks
nasa-bone-risk
nasa-hrp-ongoing
```
- `GET /api/daily/summary?days=7` is ready for the assistant context. It never contains `notePrivate`.

### For Shahd (manual steps)
- Open PR `shahd/daily` → `feature/daily`: https://github.com/Shahd-Samaneh/astrocare/compare/feature/daily...shahd/daily?expand=1
- Ask Nadia to review it, then merge.
