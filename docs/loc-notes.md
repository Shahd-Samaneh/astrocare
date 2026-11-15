# Possible loss of consciousness (R-LOC-01): notes

Owner: Shahd. Feature: R-LOC-01 → "Are you OK?" → CMO and Commander (`/crew`).

**Experimental. Not a medical device.** The app never says "fainted" and never diagnoses.
The alert title is always "Possible loss of consciousness: check crew member now". No
treatment advice is generated: the only clinical next step ("CMO: medical assessment and any
treatment decision") is locked for CMO review.

## Science basis

- **No fall in microgravity.** On Earth, many loss-of-consciousness detectors look for a fall.
  In weightlessness the body floats, so there is no fall to detect. R-LOC-01 therefore uses
  body signals plus **no response** to a direct check ("Are you OK?"), not a fall sensor.
- **When the risk is highest.** NASA's Human Research Program lists cardiovascular
  adaptation to weightlessness as a risk ("Weightlessness alters blood circulation and how
  the heart and blood vessels function", `references/nasa-hrp-risks.txt`), and dizziness
  during gravitational changes under sensorimotor risks (same file). NASA's ongoing studies
  look at gravity transitions for Moon landings and crew discomfort during re-entry
  (`references/nasa-hrp-ongoing.txt`). So orthostatic intolerance (light-headedness or loss
  of consciousness when upright under gravity) matters mainly **when returning to gravity**:
  landing, and lunar or Mars surface operations. During transit it is less likely, which is
  one more reason the rule treats every signal as unconfirmed.
- **Gap in our references.** None of the NASA pages in `references/` uses the words
  "orthostatic intolerance". The statement above rests on the cardiovascular and
  gravity-transition text quoted there. Before this goes beyond a demo, the specific NASA
  HRP cardiovascular / orthostatic intolerance page should be added to `references/` (as a
  text file, like the others). No new URL is added in `app/src`.

## Decisions

### Rule (server/rules/r_loc_01_possible_loc.py)

- **2 of 4 signals in 60 s.** Each signal has a start time. The rule fires when at least
  `loc.min_signals` (2) of them start inside the last `loc.window_seconds` (60 s):
  1. **HR change**: a good-quality heart-rate reading more than `loc.hr_change_pct` (30 %)
     above or below the median of the good readings in the previous `loc.hr_median_seconds`
     (300 s, the "last 5 minutes"). The median needs at least `loc.min_stream_readings` (3)
     readings, otherwise this signal can't be judged.
  2. **Chest signal gap**: the chest strap (`s-chest`, the sensor for `heart_rate`) was
     streaming (≥ 3 good readings in the 5 min before its last reading) and then sent
     nothing for `loc.signal_gap_seconds` (20 s). The signal starts when the gap reaches 20 s.
  3. **No motion**: the wrist sensor showed movement (≥ `loc.motion_min_g`, 0.05 g), then
     only still samples for `loc.no_motion_seconds` (30 s), **while samples kept arriving**
     (a wrist sensor that stops sending is missing data, not stillness).
  4. **Low SpO₂**: a good-quality SpO₂ reading below the existing `spo2_min` (92 %).
- **"Streaming" requirement.** Seeded vitals are every 30 min and the live feed every 5 min.
  Without the ≥ 3 readings in 5 min rule, every normal 5-min pause would look like a
  "signal gap", and there would be no median to compare a heart-rate reading with.
  Normal data can't fire the rule (tested).
- **Low quality never counts.** HR, SpO₂ and motion use good-quality readings only; a chest
  gap needs a good-quality stream before it. So low-quality data alone never fires it (tested).
- **One open alert per crew member.** Dedupe key `loc-<astronautId>`. Also, signals at or
  before an earlier R-LOC-01 alert are ignored, so the same 60 s of data can't fire a second
  alert right after "I'm OK" closed the first.
- **Alert content.** `whatChanged` lists each signal with its time and values. `missing`
  lists the chest strap, wrist motion or SpO₂ when they have no data in the window.
  `possibleFactors` are all marked "not confirmed": sensor detached or moved, sleeping or
  resting quietly, loss of consciousness, other cause.
- **When it runs.** The rule runs with the engine (server start, after Daily POSTs, and the
  demo trigger). A real deployment needs it to run continuously on the live sensor stream;
  that is engine scheduling (Haya), listed in the proposal.

### Level: `urgent` plus an `emergency` flag (not a new level)

Adding `emergency` to `AlertLevel` would touch the shared contract and other teams' code:
`Badge` has a label per level (`Record<BadgeVariant, string>`), the Alerts page, Today and
the reports PDF all switch on levels. So the alert stays **`urgent`** in the shared `Alert`
contract, and the crew API marks it with **`emergency: true`** (plus `alertLevel: 'urgent'`)
on every `/api/crew/emergencies` item. The Watch, overlay, banner and escalation are driven
by that crew record. A real `emergency` level is a proposal for Haya.

### Watch, "Are you OK?" and escalation (server/features/crew/store.py)

- One `crew_emergencies` row per R-LOC-01 alert, created by the crew feature (not the engine):
  the next `GET /api/crew/emergencies` after the alert opens the **Watch**. The app polls it
  every 1 s while a Watch is open and every 3 s otherwise (local only), so the overlay
  appears on any page within about a second. The demo trigger opens it at once.
- The 30 s countdown (`loc.response_seconds`) starts when the Watch opens (the moment
  "Are you OK?" is shown), not at the alert's timestamp, so the crew member always gets the
  full 30 s. The server clock decides; the screen counts down from the server deadline.
- **"I'm OK" in time**: escalation cancelled, the event is resolved with outcome
  `responded`, the R-LOC-01 alert is closed, the Watch disappears. All logged.
- **No response by the deadline**: the next read escalates it. Status `emergency`, red
  banner on every page until the CMO or the Commander acknowledges, red count on the
  side-nav item. "Acknowledged" means at least one of the two has acknowledged; both buttons
  stay available and both are recorded.
- **Late "I'm OK"** (after escalation): it is recorded in the timeline, but the emergency
  stays open. Once the CMO and Commander have been alerted, a person closes it.
- **The overlay after escalation.** In this demo the crew member and the CMO share one
  screen, so the full-screen check closes when the event escalates, and the red banner and
  `/crew` take over. On separate devices the crew screen could keep the check open.
- **Resolve** needs an outcome (`responded`, `sensor_issue`, `medical_event`, `other`) and
  a note. It closes the alert. If someone closes the R-LOC-01 alert on the Alerts page
  instead, the event is resolved as `other` with a note saying so.
- **Timeline**: detected → check shown → responded | no response → escalated →
  (report queued, only when it really is) → acknowledged by CMO / Commander → resolved, each with a
  timestamp and an actor (`system`, `crew`, `cmo`, `commander`). Every step is also written
  to the action log as `crew_loc:<step>`.
- Escalation happens when the API is read. The app is always open on board, so this is
  within about a second of the deadline. A server-side timer would be needed if no screen is
  open (proposal).

### Earth report outbox

`POST /api/reports/items` exists, but its `sourceFeature` only accepts
`monitoring | daily | assistant | relax`, and the item list re-validates that field. Writing
an item with `sourceFeature: 'crew'` would break `GET /api/reports/items` for everyone, and
using another feature's name would be wrong. So the crew feature **checks the reports API
types**. As soon as Noura adds `'crew'` to both `ReportItemIn` and `ReportItem`, escalation adds
a `kind: 'note'` item (sent at the next comm window), with no other change. Tested both ways.

Until then, nothing is added. The card shows only "Earth report: will be queued when reporting
is available", with no timeline row. The technical reason is kept out of the UI: it goes to the
action log as `crew_loc:report_skipped: reports API does not accept sourceFeature 'crew' yet
(see docs/proposals/loc.md)`, and to this note.

### Times on the Crew alerts page

Every time on `/crew` is local time, as HH:MM:SS. That covers the card, the timeline, the
history, and the times inside the signal and missing-data texts. The crew API sends those
texts with ISO UTC times (e.g. `until 2026-11-15T04:18:40Z`). The page turns each one into
local HH:MM:SS (`localTimes` in `crewState.ts`). The alert's own `whatChanged` / `missing`,
shown on other teams' pages, keep times labelled "HH:MM:SS UTC", so they are never ambiguous
there.

### Wrist motion data

The shared `Metric` type has no motion metric, and adding one would change other teams'
`Record<Metric, …>` maps. Wrist motion samples are stored in the crew feature's own
`crew_motion` table (`sensorId: 's-wrist'`, value in g, quality, source). Nothing generates
them except the demo trigger, so in normal use the "no motion" signal can't fire and
`missing` says so. A real wrist motion stream (simulator or sensor) is a proposal.

### Reseed

`crew_emergencies` and `crew_motion` are emptied when the database is reseeded. The crew
feature keeps the last `seeded_at` it saw in `meta`, and wipes its rows when that changes.
Any event whose R-LOC-01 alert no longer exists is also dropped. This avoids editing
`server/core/db.py`. `npm run reseed` leaves no Watch or emergency open (tested).

### Demo trigger

`POST /api/crew/demo/loc` (only with `demo: true` in `config/app.yaml`, otherwise 404) adds
simulated readings for "now":
- **Heart rate:** about 72 bpm every 10 s for 6 min, then 41 and 40 bpm.
- **Chest strap:** silent for the last 25 s.
- **Wrist:** moving until 40 s ago, then still.

That gives 3 of the 4 signals. It runs the engine, opens the Watch, and returns the alert
id. Every injected row has `source: 'simulated'` and an id starting `demo-loc-`. If an
event is already open, or was just handled less than a minute ago, it returns 409. The
"Simulate event (demo)" button on `/crew` is shown only when `demo: true`.

### Thresholds

All values are under `loc:` in `config/thresholds.yaml`, each with `source` and `note`. None
has a published source, so every note says "experimental value":

| key | value |
| --- | --- |
| `window_seconds` | 60 s |
| `min_signals` | 2 |
| `hr_change_pct` | 30 % |
| `hr_median_seconds` | 300 s |
| `min_stream_readings` | 3 |
| `signal_gap_seconds` | 20 s |
| `no_motion_seconds` | 30 s |
| `motion_min_g` | 0.05 g |
| `response_seconds` | 30 s |

## Files

- **Server:**
  - `server/rules/r_loc_01_possible_loc.py`
  - `server/features/crew/`: `store.py`, `router.py`, `demo.py`, `thresholds.py`
  - `server/tests/test_crew_loc.py`
- **App:**
  - `app/src/features/crew/`: `api.crew.ts`, `crewState.ts`, `crewFeed.ts`, `AreYouOkOverlay.tsx`, `EmergencyBanner.tsx`, `EmergencyCard.tsx`, `pages/CrewAlerts.tsx`, `Crew.module.css`
  - `crew.test.mjs`, run with `node --experimental-strip-types --test "app/src/features/crew/*.test.mjs"`. It is not part of `npm run test`.
- **Shared files changed:** listed in `docs/proposals/loc.md` for Haya.
