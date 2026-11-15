# Digital twin: decision notes

Owner: Shahd. Branch: `marah/digital-twin`. Page: `/twin` (side nav: Monitor → Digital twin).
Visual summary only, not a medical device. All data is simulated.

## What was built

| Stage | Status | Notes |
|---|---|---|
| 1. Backend aggregator | Done | `GET /api/twin/state`, `GET /api/twin/timeline`; 18 tests in `server/tests/test_twin.py` |
| 2. 3D astronaut | Done | Built from primitives in code; no assets loaded |
| 3. Timeline scrubber | Done | Slider, Play (0.8 s/day), Today |
| 4. Accessibility, fallback, polish | Done | List view, WebGL fallback, reduced motion, on-demand rendering, NasaBasis |
| 5. Tests and verification | Done | `npm run reseed` **not run** (see the end) |

## Data: where each region comes from

The aggregator (`server/features/twin/service.py`) is read-only. It calls the existing service
functions; it never changes another team's code and never writes to the DB.

| Region | Source | Status rule |
|---|---|---|
| brain | `body_systems()` sleep + cognition tiles, `sleep_summary(3)`, open alerts | review if R-FAT-01 open; watch if R-SLP-01 (or R-CIRC-01) open; watch if a sleep/cognition tile is in review without an alert; nodata if both tiles have no data |
| eyes | `vision.vision_summary()` | review on a reported change (or R-VIS-01 open); watch when the self-check is due; nodata with no check |
| heart | `latest_readings()` heart_rate + cardiovascular tile + R-HR-01 | nodata ("No recent data") when the latest HR is stale/missing; then no pulse |
| lungs | `latest_readings()` spo2/resp_rate + `cabin_latest()` co2 | R-SPO2-01 urgent → urgent, info → watch; R-CAB-01 or CO₂ above limit → review |
| bones | `bone.week_adherence()` + `bone.bone_estimate()` + R-EX-01 | same as the Bone & muscle tile; the bone-loss value is labelled "Illustrative" |
| radiation | `radiation_estimate()` | ok within the sourced limit, review at/above; labelled **Estimate · simulated** everywhere |
| temperature | `body_systems()` thermoregulation tile (stale/disconnected handling) | the tile's status; R-DATA-01 is linked but never changes the status |
| sensors | `GET /sensors` (`list_sensors()`), cabin monitor excluded | watch if any sensor is disconnected or on low battery |

Decisions:
- **Sensors (correction applied).** Only the real sensors from `/sensors`: Chest strap (torso), Skin
  temperature patch (upper arm), Wrist oximeter (left wrist), Blood pressure cuff (medical kit). The
  3D anchor comes from the sensor's `location`. The BP cuff is not on the body, so it is listed in the
  panel with no marker. No dosimeter and no actigraphy sensor are drawn or listed. The habitat
  "Cabin environment monitor" is left out because it is not a body sensor.
- **Radiation (correction applied).** The badge on the chest is a neutral "estimate" marker with a
  dashed edge. It is never green and never looks "connected"; it turns warn/danger only if the
  estimate reaches the limit. Every radiation value carries the quality `estimate` and the label
  "Estimate · simulated", including the timeline days.
- **Heart (correction applied).** Heart rate only. "Rhythm" is shown as **No data** (no ECG sensor).
- **Alert → status mapping** is an explicit table (`RULE_STATUS`), because the alert levels don't
  match the tiles. For example, R-EX-01 and R-VIS-01 are `info` alerts, but the tiles show them as
  review. Rules not in the table use their level (urgent → urgent, review → review, info → watch).
- **R-DATA-01** is linked on the temperature and sensors cards but never changes a status. It
  explains missing data; it is not a health signal (same rule as the Today tiles).
- **Sensors disconnected = watch, not review.** It is a data gap, not a health finding.
- **LOC/crew emergency feature:** not present in the code base, so it was skipped as instructed.
- **Brain route** goes to `/daily` (Daily log), where sleep lives. R-FAT-01's own steps link to the
  attention retest.
- **Source titles** come from `daily/sources.py` or the first `title:` line of `references/<id>.txt`.
  Text-only sources ("Team decision", yaml keys) are not listed as NASA sources.
- **Privacy:** check-ins are never read, so `note_private` cannot appear. There is a test for it.

## Timeline (history)

`GET /api/twin/timeline?from=129&to=142` returns one entry per mission day. By default it covers
today − 13 → today; `to` is capped at today, and a request may span at most 60 days.

- **Today's entry is the live state** (same as `/twin/state`), so "Today (live)" is consistent.
- **Past days** use only data stored by the end of that day:
  - Brain, heart and lungs replay the existing rules (R-FAT-01, R-SLP-01, R-HR-01, R-SPO2-01,
    R-CAB-01) on a `BoundedContext`. This is a `RuleContext` subclass in
    `server/features/twin/history.py` that only reads rows with `ts <= end of day`. The rules
    themselves are unchanged.
  - Heart and lungs show **day medians** of good-quality readings. The heart pulse in history uses
    that day's median HR.
  - Bones use exercise logs written by the end of that day. The bone-loss estimate is shown for
    that mission day, labelled "Illustrative".
  - Temperature uses the latest skin reading at the end of that day, with the same stale rule.
  - **Sensors have no history:** only the current status is stored, so past days are `nodata`.
    Nothing is inferred from `last_seen`.
  - History shows which rule *conditions held* that day (rule ids, no alert links), because history
    creates no alerts.
- No values are interpolated. A day with no stored data shows "No data". This is tested with a
  day before the seeded data.

**Demo moment, honest version.** Press Play: the brain is OK on days 129–140. It is **Watch (blue)
on day 141**: only one short night by then, but the attention test is already 19 % slower.
It turns **Review (yellow) on day 142**, when the second short night completes the R-FAT-01
condition. The prompt expected yellow on both 141 and 142. The data only supports the full
fatigue pattern on 142, so day 141 is not faked. The radiation estimate rises 232 → 256 mSv.

## 3D view

- Built from primitives only: a sphere helmet with a click-through clear shell and a dark visor
  segment, a capsule torso, a box backpack, capsule arms and legs, sphere gloves and box boots,
  a torus neck ring and a chest-strap band. A generic suit of our own design.
- No drei, no models, textures or HDR files. Orbit controls come from
  `three/examples/jsm/controls/OrbitControls.js`. Sensor numbers are drawn on a 2D canvas texture
  in code.
- Colours are read at runtime from CSS variables (`env.ts → readTheme`):
  ok `--ok`, watch `--accent`, review `--warn`, urgent `--danger`, nodata `--text-faint`
  (faint, semi-transparent, with a dashed ring). Background `--bg-app`, rim light `--accent`,
  suit `--text-2`/`--text-muted`, stars `--text`.
- Region placement: brain inside the helmet, eyes on the visor, heart and lungs on the chest.
  Bones are a spine inside the torso plus highlights along the front of each leg. The radiation
  estimate badge is on the chest. The temperature patch is on the astronaut's right upper arm (the
  data only says "Upper arm"). Sensor markers: 1 chest strap, 2 wrist oximeter (left wrist),
  3 skin patch (upper arm).
- The heart pulses at the latest bpm ("lub-dub" shape). With no recent reading it does not pulse,
  and the card says "No recent data".
- Interaction: drag to rotate, wheel/pinch to zoom (distance 1.1–6, no pan), and Reset view.
  Hovering shows a tooltip. Clicking selects a region and the camera eases to it.
  Keyboard (3D view focused): arrows rotate, `+`/`-` zoom, Home resets. Every region can also be
  selected from the panel list (buttons).
- **Bug found and fixed while testing:** three.js picks `Line` objects within a wide threshold, so
  the radiation badge's dashed ring stole clicks meant for the brain. Dashed rings and the helmet
  are now not pickable.

## Accessibility, fallback, reduced motion

- **List view** toggle (`aria-pressed`): the same regions as a table with a caption.
- **WebGL missing** → list view automatically, with a note. A runtime error or a real context loss
  in the 3D view also falls back to the list (error boundary).
  - **Bug found and fixed:** switching to the list view unmounts the canvas, and three.js then
    releases the WebGL context on purpose. That used to trigger the "stopped working" note and hide
    the toggle. Context loss now only counts while the canvas is still mounted.
- **`prefers-reduced-motion`**: no float, no pulse (the card shows "Heart rate N bpm (animation
  off)"), no camera easing (the camera jumps), and no orbit damping.
- 44 px targets (shared Button, region buttons, the close button, the slider), visible focus rings,
  ARIA labels, and a screen-reader summary of all regions for the 3D view.
- **"Why this view?":** uses the existing `NasaBasis` (ids: nasa-hrp-hazards, nasa-hrp-risks,
  nasa-bone-risk, nasa-hrp-sleep-risk) with our own sentence. NasaBasis only has the labels
  "Why we track this" and "Why this test?", so the line reads **"Why we track this"**. I did not
  change Daily's component; a `label` prop is suggested in `docs/proposals/twin.md`.

## Performance (correction: pause when hidden, test with Ollama)

- `dpr={[1, 2]}`, low-poly geometry (about 12–24 segments), no MSAA, animation through refs in
  `useFrame` (no React state per frame).
- Rendering is **on demand**:
  - The idle float and pulse request about 30 fps, only while the tab is visible, the canvas is in
    view (IntersectionObserver) and motion is allowed.
  - Otherwise a frame is drawn only after a control change, a camera move or new data.
  - **Hidden tab → `frameloop="never"`**: 0 draw calls were measured while hidden.
- The page is lazy-loaded (`React.lazy`). three.js is only in the `TwinPage` chunk, and the main
  bundle is unchanged, so on the Assistant page the twin costs nothing.
- **Measured with Ollama running** (`llama3.2:3b`, 80 tokens, 3 runs each). Edge headless used
  **software WebGL (SwiftShader), so this is the worst case:** the GPU work runs on the same CPU
  as the model.

  | Condition | tok/s |
  |---|---|
  | No browser | 12.1–13.9 |
  | Twin visible, first version (continuous 60 fps, MSAA) | 5.1 |
  | Twin visible, after the change (on-demand 30 fps, no MSAA) | 8.6 |
  | Twin tab hidden | 11.1–11.8 |

  On a machine with a GPU the visible cost should be smaller; I could not measure that here.
  If the visible cost matters for the demo, the next step is to stop the idle float after
  ~30 s without interaction (the pulse could keep running).

## Offline

- Only `three@0.170.0` and `@react-three/fiber@8.17.10` (+ `@types/three` as a dev dependency) were
  added. `npm audit fix --force` was not run.
- `npm run check:offline` passes. One exact string was allowlisted:
  `https://docs.pmnd.rs/react-three-fiber/api/objects#using-3rd-party-objects-declaratively`.
  It is part of an r3f `throw new Error(...)` message (text only, never requested).
- Browser test: every non-localhost request was blocked and recorded; there were none.

## Verification run (dev server, Edge headless with software WebGL)

- The page loads; no remote requests; no console errors.
- Rotate (drag), zoom (wheel), Reset view and keyboard rotate work.
- Clicking the brain eases the camera in; the card shows R-FAT-01 and R-SLP-01 with links to the
  alerts.
- The heart tooltip shows the bpm; the heart pulses (60–66 bpm in the runs).
- Play: day 129 → 141 every 0.8 s, then "Today (live)". Brain Watch on 141, Review today;
  radiation rises.
- List view works and switching back to 3D works.
- Reduced motion: the scene is static between frames, and clicking the heart shows
  "animation off".
- Commands: `npm run test` (430 passed + typecheck), `npm run lint` (clean),
  `node --experimental-strip-types --test "app/src/features/twin/tests/*.test.mjs"` (7 passed),
  `npm run build`, `npm run check:offline` (0 remote URLs).

## Not done / follow-ups

- **`npm run reseed` was not run**, because your dev server was running. Stop it, run
  `npm run reseed`, then restart `npm run dev`.
- The NasaBasis label is "Why we track this" instead of "Why this view?" (it needs a prop on
  Daily's component).
- No LOC/crew emergency feature exists, so nothing feeds `urgent` into heart/brain from it yet.
  An urgent R-SPO2-01 does drive lungs to urgent.
