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

---

## Shahd, round 2: Attention check upgrades, R-CIRC-01, connected charts

### Decisions

| # | Decision | Why |
|---|---|---|
| S20 | New `GET /api/daily/thresholds` (in `thresholds.py`, mine) returns every `daily:` key with `value`, `unit`, `source` and `note`. Charts draw their lines from it. | No threshold numbers in frontend code. |
| S21 | Tests now carry `missionDay` (derived from `ts` with the mission clock). The sleep fallback in `summary.py` also returns `date`, `start`, `end` and `source` (Nadia's contract fields are a subset). | The 14-day chart and the history table group by mission day. |
| S22 | Sleep vs reaction time chart: bars use the **longest** session per night. The line uses the median of **routine quick** tests per mission day. "Both off" = sleep < `sleep_short_hours` **and** median ≥ baseline × (1 + `attention_slower_pct`/100). Missing days are gaps. The caption is "Shown together, not a proven cause." | Same definitions as R-FAT-01, so the chart and the alert agree. |
| S23 | R-CIRC-01 compares bedtimes on a clock that starts at **noon** (23:30 vs 00:30 = 1 h, not 23 h), using mission time. It needs ≥ 2 of the last 3 nights; nights without data go into `missing`. The main sleep of a night is its longest session. New key `daily.sleep_onset_shift_hours` = 2, "experimental value". | Avoids the midnight wrap. Naps don't count as bedtimes. |
| S24 | Seeded bedtimes are 22:42 / 00:28 / 00:36, a 1.9 h spread, so **R-CIRC-01 doesn't fire in the demo**. It's tested on synthetic nights. Proposal §4b has the one-line simulator change (+30 min on the two short nights). | Rule: don't edit the simulator. |
| S25 | Hours awake = test time − `end` of the last sleep session that **ended before** the test. It's computed on the server (`sleepContext` in the `POST /api/tests` response). "—" when unknown. The SIM badge shows when that session's `source` is `simulated`. | One definition, testable. |
| S26 | Practice trial default: on until the first test **saved on this device**, then off. The user's own choice is remembered in `localStorage` (`astrocare.daily.attention.practice`), every access in try/catch. A false start during practice is shown but not counted. | The seeded history shouldn't count as "this person has done a test here". |
| S27 | PVT counter: display only (`requestAnimationFrame`). The measured RT always comes from the controller's own `performance.now()` stamp, so it's identical with `prefers-reduced-motion` (static highlighted target, no counting). The frozen RT shows ~1 s. | Timing logic must not depend on the animation. |
| S28 | KSS (Karolinska Sleepiness Scale) 1–9 or `null` (skipped), stored in **`daily_test_meta`**. Anchor labels for 1/3/5/7/9 follow the published scale. "Test again" returns to the intro and clears the rating. | A rating belongs to one test. |
| S29 | `daily_test_meta(test_id, mode, sleepiness_kss, input_method, trial_offsets_ms)` was created once in 4c with all columns. No row = a quick test with no extra data (all simulated tests). | No schema migrations between steps. |
| S30 | Extended mode: random waits of 2–10 s until 3 minutes have passed since the first real trial (the practice trial doesn't count towards the 3 minutes). If time runs out during a wait, the test ends there. A false start is counted but doesn't "repeat" a trial. | Spec. |
| S31 | **Interval note:** in both modes the time between a response and the next stimulus is the ~1 s frozen-RT display **plus** the random wait (so 3–9 s quick, 3–11 s extended). | Honest description of what the code does. |
| S32 | PVT measures (server, `pvt_measures`) are computed for every test: mean RT, fastest/slowest 10 % mean (10 % = `round(n/10)`, at least 1 response), response speed = mean(1000/RT) in 1/s, lapses (≥ `pvt_lapse_ms`), false starts. They're shown for Extended only. | Standard PVT outcome set. With 5 trials, "10 %" is one response, so it's hidden for Quick. |
| S33 | Baselines are **per mode** (`GET /api/tests/baseline?mode=`). With fewer than 3 same-mode tests, `building: true`: the UI shows "Building your baseline (n/3)", `withinRange` is `null`, and % vs baseline is labelled "preliminary". The ±10 % range from contract §5 is still computed for the API. R-FAT-01 and the 14-day chart use **quick** routine tests only. | Never compare a 3-minute test with 5-trial tests. |
| S34 | Retest Before vs After: Before = median of the routine tests (same mode as the retest) in the 48 h before the alert's time; After = the retest median. The response carries the alert status **after** the engine ran (so `recheck`). | The number that triggered the alert. |
| S35 | Input method = the first real response: `pointerType` mouse → `mouse`, touch/pen → `touch`, Space → `keyboard`. "Usual" = most common known input among the baseline tests. No note when that is unknown (the seeded tests have none). | Fair comparison without guessing. |
| S36 | History table `withinRange` is computed per test against the same-mode baseline **as it was at that test's time**. Limitation: with a min–max range of only 3–7 tests the band is narrow, so some ordinary days show ✗ (e.g. `pvt-138`, 297 ms vs a 281–296 ms range). | Honest per-row verdict. The range method is a team choice ("experimental"). |
| S37 | A faster-than-usual result is also labelled "Outside your usual range" (same badge). | Wording stays neutral; outside ≠ bad. |
| S38 | "Add to report": the button probes `GET /api/reports/items?pending=true` and is **hidden on 404**. On `shahd/daily` today it's hidden, because Noura's API is on `main` but not yet on `feature/daily`. I checked the exact payload (`kind: 'note'`, `title`, one-line `text`, `sourceFeature: 'daily'`, `refId`) against `origin/main` in a temporary worktree: 201 Created. Only test numbers and KSS are sent, never check-in notes. | Spec (hide on 404). |
| S39 | `GET /api/tests` limit raised to 200 (the page loads 200: charts use the last 14 days, the table pages by 20). | History table. |

### Sources (for the report)
- **KSS:** Åkerstedt T, Gillberg M. *Subjective and objective sleepiness in the active individual.* International Journal of Neuroscience, 1990; 52(1–2): 29–37. Cited in docs and the report only; there's no URL in `app/src`.
- PVT outcome measures (mean RT, fastest/slowest 10 %, 1/RT, lapses ≥ 500 ms) follow common PVT reporting conventions. Our 3-minute Extended mode is **not** a validated PVT-B implementation, and the UI says "Experimental, not validated".

### Browser check (step 6)
- Ran with headless Edge, driven by a DevTools-protocol script (in the scratchpad, not committed).
- Your `npm run dev` was already holding port 8000 (auto-reloading API + Vite), so `npm run start` couldn't bind. I tested against that server with a fresh `npm run build`, and left your dev server running.
- Results:

| State | Result |
|---|---|
| Quick + practice | ✅ "Practice: not counted" shown first, PVT counter visible, result with KSS 7/9 line, hours slept/awake + SIM badge, dot plot, both charts, collapsed table and NASA panel |
| Retest (`?retest=<R-FAT-01 id>`) | ✅ Before 342 ms / After 279 ms / −63 ms (−18 %) / status RECHECK, "Back to the alert" |
| Reduced motion | ✅ no counter, static highlighted target, result saved |
| Extended (3 min) | ✅ ran the full 3 minutes: 22 responses, server measures shown (mean RT, fastest/slowest 10 %, response speed 3.76 1/s), "Building your baseline (0/3)" with no verdict, time-on-task chart. The first two values (5000 ms, 1356 ms) are artifacts: the script paused 20 s for a screenshot. |
| Timing check | An in-page responder firing 250–255 ms after the stimulus recorded 251–256 ms. |

- No console errors, page exceptions or non-localhost requests in any run.
- The test rows created during the check were removed with `npm run reseed`.
