# Proposal: Digital twin, shared changes (for Haya)

Owner: Shahd. All feature code is in `app/src/features/twin/` and `server/features/twin/`
(a read-only aggregator), with tests in `server/tests/test_twin.py` and
`app/src/features/twin/tests/`. The shared changes below are minimal and additive.
Nothing was renamed or removed.

## Shared files changed

1. **`server/main.py`**: imports `server.features.twin.router` and adds `twin_router` to the
   router tuple (2 lines). New endpoints: `GET /api/twin/state`, `GET /api/twin/timeline`.
2. **`app/src/routes.tsx`**: a lazy route `twin` (`React.lazy` + `Suspense` with the shared
   `LoadingState`), so three.js loads only on `/twin`.
3. **`app/src/shared/components/SideNav.tsx`**: one nav item under Monitor:
   `{ to: '/twin', label: 'Digital twin', icon: PersonStanding }` (lucide-react, already a
   dependency).
4. **`app/package.json` / `app/package-lock.json`**: dependencies `three@^0.170.0` and
   `@react-three/fiber@^8.17.10` (v8 = React 18), plus dev dependency `@types/three@^0.170.0`.
   No drei and no other packages.
5. **`scripts/check-offline.mjs`**: an exact-match allowlist `VENDOR_DOC_TEXT` with one URL from an
   r3f error message (`throw new Error("... See: https://docs.pmnd.rs/react-three-fiber/api/objects#using-3rd-party-objects-declaratively")`),
   which is never requested. It is documented in the file; any other URL still fails.

## Read-only use of other teams' code (not modified)

- Monitoring: `body_systems`, `latest_readings`, `cabin_latest`, `list_sensors`,
  `radiation_estimate`, `vision.vision_summary`, `bone.week_adherence`, `bone.bone_estimate`,
  `BodySystem`/`LatestReading` models.
- Daily: `sleep.sleep_summary`, `exercise.load_plan_items`, `sources.SOURCES`, and the
  `NasaBasis` component (via `features/daily/index.ts`).
- Rules: `RuleContext` is subclassed in `server/features/twin/history.py` (time-bounded reads)
  to replay R-FAT-01, R-SLP-01, R-HR-01, R-SPO2-01 and R-CAB-01 for past days. Rules never write,
  and the twin creates no alerts.

## Small requests (optional, not required for the demo)

- **NasaBasis label prop (Daily, Shahd/Nadia):** a `label?: string` prop would let the twin show
  "Why this view?" as specified. Today it shows "Why we track this".
- **Sensor history (core, Haya):** the `sensors` table only stores the current status. A
  connection log would let the timeline show sensors per day; today those days are "No data".
- **A "watch" status token:** the twin uses `--accent` for "watch". A dedicated token would
  keep it separate if the accent colour ever changes.
