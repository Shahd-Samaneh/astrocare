# AstroCare: Daily pair contract (Shahd + Nadia)

This file adds to `README.md`, `CONTRIBUTING.md` and the team's Full Plan. If something conflicts, **CONTRIBUTING.md wins**.
**Rule:** what's written here is agreed. Nobody changes it alone: talk to the other person first.

## 0) Who owns what
| Path | Owner |
|---|---|
| `server/features/daily/router.py` (aggregator only: it includes the sub-routers) | Shahd |
| `server/features/daily/attention.py`, `checkins.py`, `summary.py`, `sources.py` | Shahd |
| `server/features/daily/sleep.py`, `exercise.py`, `today.py` | Nadia |
| `server/rules/r_slp_01_short_sleep.py`, `server/rules/r_fat_01_fatigue_pattern.py` | Shahd |
| `server/rules/r_ex_01_missed_exercise.py` | Nadia |
| `app/src/features/daily/attention/`, `checkin/`, `common/` (`NasaBasis`), `api.attention.ts`, `pages/AttentionCheck.tsx` | Shahd |
| `app/src/features/daily/sleep/`, `exercise/`, `today-cards/`, `api.log.ts`, `pages/DailyLog.tsx`, `index.ts` | Nadia (Shahd only adds her own export lines to `index.ts`) |
| `data/.../exercise_plan.json` (wherever the scaffold keeps it) | Nadia |
| Keys under `daily:` in `config/thresholds.yaml` | Shahd adds them and tells Haya |
| `server/core/`, `app/src/shared/`, `contracts.ts` + `models.py`, the simulator, `resources.json` | **Not ours.** We propose changes in `docs/proposals/daily-contracts.md`; we don't edit. |

Shahd works on `shahd/daily`, Nadia on `nadia/daily`, both created from `feature/daily`. Each merges into `feature/daily` by pull request, reviewed by the other. Merge `origin/feature/daily` into your own branch at least every 45 minutes so you get the other's merged work.

## 1) Contract changes we ask Haya for (small, optional fields)
- `CognitiveTest.context?: 'routine' | 'retest'` and `CognitiveTest.relatedAlertId?: string`
- `Alert.nextSteps[].action?: { label: string; route: string }`: lets Alert detail turn a next step into a button that opens our page
- Until Haya merges these: keep the extra fields in our own Pydantic and TS types, and store test context in a table prefixed `daily_` (e.g. `daily_test_context(test_id, context, related_alert_id)`).

## 2) API
### Shahd
```
GET  /api/tests?n=10            -> CognitiveTest[] (newest first, includes context)
GET  /api/tests/baseline        -> { medianMs, n, rangeLowMs, rangeHighMs }   # from the 7 routine tests before the last 48 h
POST /api/tests  { trialsMs[], falseStarts, context?, relatedAlertId? }
                                -> { test: CognitiveTest, pctVsBaseline, withinRange }
                                   # the server computes medianMs and lapses (pvt_lapse_ms), then runs the rule engine
GET  /api/checkins?n=7[&includePrivate=true] -> CheckIn[]   # notePrivate only with includePrivate=true
POST /api/checkins { mood, stress, notePrivate?, skipped }   -> CheckIn   # then runs the rule engine
GET  /api/daily/summary?days=7  -> DailySummary   # used by the assistant (Marah) and reports (Noura). Never contains notePrivate.
GET  /api/daily/sources         -> NasaSource[] { id, org, title, url, why }
```
### Nadia
```
GET   /api/sleep?days=7          -> SleepSession[]
GET   /api/sleep/summary?days=7  -> { nights: [{ date, missionDay, hours, awakenings, selfQuality }], personalAvgHours, lastNight }
POST  /api/sleep { start, end, awakenings, selfQuality }  -> SleepSession (source 'manual'), then runs the rule engine
PATCH /api/sleep/{id}/rating { selfQuality }
GET   /api/exercise/plan?day=    -> plan items, each with equipment + equipmentStatus resolved
GET   /api/exercise/alternatives?planId=&reason= -> { alternatives: [...ranked], message? }
POST  /api/exercise/log { planId, status, reason?, alternativeId? } -> ExerciseLog, then runs the rule engine
GET   /api/today/plan            -> { missionDay, items: [{ kind: 'checkin'|'attention'|'exercise'|'sleep_rating', title, status: 'todo'|'done'|'skipped', route }], fatigueFlag }
```
### Python service functions (for other pairs and for summary.py)
- Nadia: `sleep_summary(days:int) -> dict`, `exercise_summary(days:int) -> dict`
- Shahd: `attention_summary(n:int) -> dict`, `checkins_summary(n:int) -> dict` (no private notes)

`DailySummary = { sleep: sleep_summary, attention: attention_summary, exercise: exercise_summary, checkins: checkins_summary, activeDailyAlerts: Alert[] }`

## 3) Rules
| ID | Owner | Logic | Level |
|---|---|---|---|
| R-SLP-01 | Shahd | Sleep < `sleep_short_hours` on ≥ `sleep_short_nights` of the last 3 nights | info |
| **R-FAT-01** | Shahd | R-SLP-01 condition **and** the median of routine tests in the last 48 h is slower than the baseline by ≥ `attention_slower_pct` | **review** |
| R-EX-01 | Nadia | Exercise skipped, or not logged, on 2 consecutive days | info |

**R-FAT-01 content:**
- Title: "Possible fatigue pattern: short sleep and slower reaction time".
- `whatChanged`: the actual numbers (hours per night, ms vs baseline, %).
- `dataUsed`: the sleep and test ids.
- `missing`: "Today's check-in" (if none today), "Sleep self-rating for last night" (if empty).
- `possibleFactors`: always phrased as unconfirmed.
- `nextSteps` with actions:
  - Do today's check-in → `/daily#checkin`
  - Retest after rest → `/attention?retest=<alertId>`
  - Switch to a lighter exercise → `/daily#exercise`
- `sources`: `nasa-hrp-sleep-risk`, `nasa-hrp-bmed-risk`, `nasa-pvt-iss`.

**Behaviour:**
- **One open alert per rule.** Each run updates the existing alert instead of creating a new one.
- **Recheck:** a test with `context: 'retest'` and `relatedAlertId` after the alert's time sets `status = 'recheck'` and adds "Retest at HH:MM: median X ms (within / outside your usual range)" to `whatChanged`. It never auto-closes; closing is a human decision.
- **Check-in:** a check-in done today removes "Today's check-in" from `missing`.

Every POST in our endpoints triggers the rule engine, using the engine's existing run function.

## 4) NASA basis (`sources.py`, Shahd; the URLs live on the backend only, so the frontend stays free of URLs)
| id | Title | Used by |
|---|---|---|
| `nasa-hrp-sleep-risk` | NASA HRP: Risk of performance decrements and adverse health outcomes from sleep loss, circadian desynchronization and work overload | Sleep, R-SLP-01, R-FAT-01 |
| `nasa-hrp-bmed-risk` | NASA HRP evidence report: Risk of adverse cognitive or behavioral conditions and psychiatric disorders (NTRS 20250001454) | Check-in, attention, R-FAT-01 |
| `nasa-pvt-iss` | NASA TechPort 23201: Psychomotor Vigilance Test (PVT) on ISS | Attention check |
| `nasa-hrp-hazards` | NASA HRP: 5 Hazards of Human Spaceflight (isolation and confinement; gravity fields) | Check-in, exercise |
| `nasa-hrp-risks` | NASA HRP: Risks of Human Spaceflight (fitness and musculoskeletal risks) | Exercise, R-EX-01 |
| `nasa-bone-risk` | NASA: Risk of spaceflight-induced bone changes | Exercise |
| `nasa-hrp-ongoing` | NASA HRP: Ongoing research in space | Sleep (wrist-worn sleep/activity monitoring) |

Each page shows a small **"Why we track this"** panel: one or two sentences in our own words, plus the source titles.
- Never imply NASA endorses the app.
- Send this id list to Marah so the assistant's `references/` uses the same ids.

## 5) Demo behaviour (must work with `npm run reseed`)
- Seeded state:
  - Nights 141 and 142 are under 6 h.
  - The last two routine tests are about 20% slower.
  - There is no check-in today.

  This gives R-FAT-01 open at `review`, with "Today's check-in" missing.
- Live during the demo:
  1. Retest from the alert's next step: the alert goes to `recheck` with the result.
  2. Check-in: the missing list empties.
  3. Exercise "Couldn't do it", reason "fatigue": a lighter alternative is suggested, chosen and logged.

## 6) Checkpoints
| When | Ready |
|---|---|
| +30 min | **Shahd:** router split pushed, proposal file written, thresholds keys added. **Nadia:** exercise plan JSON, page skeleton on mocks |
| Test merge | All our endpoints return real data. The attention test works end to end. The sleep chart works. |
| Full merge (00:00) | The full R-FAT-01 loop (retest → recheck, check-in → missing cleared). The exercise flow with equipment check. Today cards handed to Haya. |
