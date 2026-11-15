# Proposal: shared-file changes for R-LOC-01 / Crew alerts

For review by Haya. Owner of the feature: Shahd. Details and reasons: `docs/loc-notes.md`.

Every change below is additive. No existing behaviour of another team changes. With no open
LOC event, the app looks exactly as before, apart from the new "Crew alerts" nav item.

## Changed shared files

| File | Change |
| --- | --- |
| `server/main.py` | Imports `server.features.crew.router` and adds `crew_router` to the router tuple (all routes under `/api/crew`). |
| `app/src/routes.tsx` | Adds the import of `CrewAlerts` and the route `{ path: 'crew', element: <CrewAlerts /> }`. |
| `app/src/shared/components/SideNav.tsx` | Adds the "Crew alerts" item (`/crew`, `Siren` icon) at the top of **Support**, with `badge: 'crew'`. Adds optional props `crewEmergencyCount` (red count) and `crewWatch` (yellow dot). The defaults are 0 and false, so other callers are unaffected. |
| `app/src/shared/components/SideNav.module.css` | Adds `.badgeDanger` (red count) and `.dotWarn` (yellow dot, also placed in the collapsed rail). |
| `app/src/shared/layout/AppShell.tsx` | Calls `useCrewFeedSource()` once (polls `GET /api/crew/emergencies`: 1 s while a Watch is open, 3 s otherwise) and wraps the shell in `CrewFeedContext.Provider`. It passes the crew props to `SideNav`, renders `<EmergencyBanner />` under the offline status bar, and renders `<AreYouOkOverlay />` once. Most of the diff is re-indentation from the wrap; `git diff -w` shows +14 lines. |
| `config/app.yaml` | New top-level key `demo: true`. It shows "Simulate event (demo)", and the demo endpoint refuses when it is false. |
| `config/thresholds.yaml` | New `loc:` group, with the same shape as `daily:`. The core loader sees it as one group entry with `value: null`. |

## Not changed (on purpose)

- **`shared/types/contracts.ts` / `server/core/models.py`:** the crew types are feature-owned (`server/features/crew/router.py`, `app/src/features/crew/api.crew.ts`), like `api.attention.ts`.
- **`AlertLevel`:** no new `emergency` level. The alert is `urgent`, and the crew record carries `emergency: true`.
- **Simulator:** the demo trigger injects its own readings, and normal data has no motion stream.
- **`server/core/db.py`:** the crew tables are cleared on reseed by the crew feature itself, which watches `seeded_at`.
- **`server/rules/engine.py`:** the Watch is opened lazily by the crew feature, not by an engine hook.

## Requests for later

1. **Reports (Noura): accept `sourceFeature: 'crew'`.** Add `"crew"` to the `Literal` in `ReportItemIn` and `ReportItem` (`server/features/reports/router.py`). Escalation then adds a `kind: 'note'` item to the Earth outbox automatically. Today the card shows "will be queued when reporting is available", and the reason goes to the action log only, because writing `'crew'` now would break `GET /api/reports/items`.
2. **Contract: a real `emergency` alert level** (optional). Add it to `AlertLevel` (both files), `Badge` labels/styles, and wherever levels are switched on. Until then, `urgent` + `emergency: true` is used.
3. **Engine: continuous evaluation.** Run R-LOC-01 on every new vital reading, or on a short timer, rather than only on start / POSTs / demo.
4. **Server-side escalation timer.** Escalation now happens on the next read of `/api/crew/emergencies`. That is fine while a screen is open, but a timer would cover the case where no screen is open.
5. **Wrist motion metric.** Today motion lives in the crew feature's `crew_motion` table. If the team wants motion in `readings`, add a `motion` metric to `Metric` (both files) and to the simulator.
6. **References.** Add the NASA HRP cardiovascular / orthostatic intolerance page to `references/` as a text file. The current references support the "returning to gravity" point only indirectly (`docs/loc-notes.md`).
