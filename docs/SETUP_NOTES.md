# Setup notes

The team set up the scaffold on 2026-11-11 on Windows 11 (Node 24.21, npm 11, Python 3.14.7).

## Summary

- **Status: scaffold complete; every verification check passed.**
- Frontend: React 18.3 + TS 5.7 + Vite 6, react-router-dom 6, Recharts 2, lucide-react, local @fontsource fonts. Twelve shared components, AppShell, and 12 routed placeholder pages, each making a live API call.
- Backend: FastAPI + Pydantic v2 + SQLite (`sqlite3`). There are 14 contract tables, a simulator with the demo scenario, a rule engine with one example rule, and working stubs for every endpoint in the brief.
- Tests: 21 pytest tests and `tsc --noEmit` pass. `npm run build` passes. `npm run check:offline` finds 0 remote URLs.
- Ollama: installed on this machine (not on PATH). `nomic-embed-text` and `llama3.2:3b` were pulled (see below).
- The scaffold started without a git repository. We decided to create it together at the hackathon (see CONTRIBUTING.md).

## Verification results

| # | Check | Result |
|---|---|---|
| 1 | `npm run test` (pytest + `tsc --noEmit`) | ✅ 21 passed, typecheck clean |
| 2 | `npm run build` | ✅ `app/dist` built (JS ≈ 658 kB, 193 kB gzip) |
| 3 | `npm run start` + curl | ✅ `/api/health` → `{"ok":true}`; `/api/status` → `simulated: true`, missionDay 142, MET `142:07:31`, outbox 2; `/api/alerts` → 1 alert `R-DATA-01` "Skin temperature: no recent data"; `/vitals` serves the SPA; unknown `/api/*` → 404. Server stopped afterwards. |
| 4 | URL scan of `app/src`, `app/index.html`, `app/dist` | ✅ no remote URLs in our code. The built bundle keeps only W3C XML namespace identifiers (see decision D9). |
| 5 | SideNav 12 items / routes / status bar | ✅ 12 `NavLink`s ↔ 12 routes in `routes.tsx` (+ `/alerts/:id` + 404). Active state comes from `NavLink`; the status bar reads `/api/status`. Everything compiles. Not checked in a browser. |
| 6 | No `.git` folder | ✅ none created |

## Decisions

- **D1 Hand-written Vite project, not `npm create vite`.** The current template uses React 19, and the brief asks for React 18. `app/package.json` pins `react@^18.3.1`, `react-router-dom@^6`, `recharts@^2`, `vite@^6`, `typescript@~5.7`. The file layout is the same as the template's.
- **D2 Python versions.** `requirements.txt` pins major versions (`fastapi<1`, `pydantic>=2.7,<3`, `numpy>=2,<3`, `pandas>=2.2,<4`, `reportlab>=4,<5`, `httpx<1`, `pytest>=8,<10`, ...). On Python 3.14 pip installed pandas 3.1 and pytest 9.2. We widened pandas to `<4` because pandas 2.x has no wheels for newer Pythons.
- **D3 Cross-platform runner.** `scripts/py.mjs` runs the root `.venv`'s Python on any OS, so the root npm scripts (`dev`, `start`, `test`, `reseed`) work on Windows, macOS and Linux. `npm run setup` runs `scripts/setup.mjs`. `setup.sh` and `setup.ps1` are standalone copies of the same steps.
- **D4 snake_case ↔ camelCase.** Pydantic models use snake_case (the same as the DB columns) with a camelCase alias generator, so the JSON matches `contracts.ts` exactly. Request bodies accept either spelling. `NextStep.lockedForCMO` has an explicit alias.
- **D5 Small additions to the contract.** Untyped items in the brief were given shapes:
  - `ExercisePlan.day` = mission day (int); `alternatives` = `ExerciseAlternative {id, type, durationMin, equipmentId?, note?}`
  - `Report.sections` = `ReportSection {id, title, body}`
  - `Resource.status` = `available|low|out_of_stock|expired`
  - `Profile.baseline` keys = metrics + `pvt_median_ms` + `sleep_hours`
  - helper (not stored) `LatestReading` for `GET /api/readings/latest`
  - `alerts.dedupe_key` is an internal DB column only.
- **D6 Mission clock.** `config/app.yaml` sets `met_at_seed: "142:07:31"`. The seed time is stored in the DB, and MET runs from there, so the clock stays consistent across restarts. All simulated data is relative to the seed time. The contract's `met` is `DDD:HH:MM`. The status bar shows `DDD:HH:MM:SS` so it visibly ticks every second. Mission day = the DDD part.
- **D7 Simulated data on reseed.** Simulated data is generated once (first start). For a fresh demo scenario run `npm run reseed`, or set `simulator.reseed_on_start: true` in `config/app.yaml` on demo day. As real time passes, the stale reading gets older and mission day eventually ticks to 143.
- **D8 Stale vs missing.** `R-DATA-01` covers only continuous metrics (HR, SpO₂, skin temp, resp rate). Blood pressure is a twice-daily spot check. `/api/readings/latest` marks it `missing` when there is no reading since the start of the mission day. A future "BP missing today" rule should follow the example rule.
- **D9 Offline URL check.** Our code (`app/src`, `index.html`) contains no remote URLs, and ESLint now fails on any non-localhost URL literal. The built vendor bundle contained:
  - two React error-message doc links. A small Vite plugin (`app/vite.config.ts`) turns them into plain text.
  - W3C XML namespace identifiers (`http://www.w3.org/2000/svg`, `.../1999/xhtml`, `.../1999/xlink`, `.../1998/Math/MathML`, `.../XML/1998/namespace`). React and Recharts need these strings to create SVG elements, and they are never fetched. Removing them would break every icon and chart, so they stay, on an explicit allowlist in `scripts/check-offline.mjs`.
- **D10 Favicon.** Dropped the SVG favicon file, because a standalone SVG needs an `xmlns="http://…"` attribute. `index.html` uses `<link rel="icon" href="data:,">` so the browser doesn't request one. The logo is an inline React SVG.
- **D11 Extra files** beyond the brief's tree:
  - `server/core/status.py` (mission clock + AppStatus, avoids circular imports)
  - `app/src/shared/api/AppStatusContext.tsx` (one shared `/api/status` poll)
  - `app/src/shared/utils/format.ts`
  - `shared/components/PlaceholderPage.tsx` + `Logo.tsx`
  - `features/*/owners.ts` (reads `OWNERS.md` via Vite `?raw`)
  - `data/simulated/exercise_plan.json`, `relax_scenes.json`
  - `scripts/py.mjs`, `setup.mjs`, `check-offline.mjs`, `dev_api.py`
  - `server/tests/conftest.py`, `app/.prettierrc.json`
- **D12 Storage numbers.** The SideNav storage numbers ("3.4 of 64 GB") are constants in `AppShell.tsx` until the backend exposes real disk usage.
- **D13 Badge counts.** The Reports badge counts reports that are not yet `sent`. The Alerts badge counts `status=new`.
- **D14 Ollama on Windows.** Ollama was installed at `%LOCALAPPDATA%\Programs\Ollama` but isn't on PATH. The setup scripts now look in that folder too. `/api/assistant/info` reported `reachable: true`.
- **D15 Thresholds.** `spo2_min: 92` (note "verify source"), `sleep_short_hours` with `source: TODO`, and `co2_max: null`. All three still need a NASA reference before the demo.

- **D16 `npm run dev` crash on Windows (fixed 2026-11-12).** Symptom: any backend reload killed Vite, and `concurrently -k` then stopped everything with exit code 1. There were two causes:
  1. *Too much was watched.* `--reload-dir server` included `server/.venv`, so changes inside site-packages triggered reloads. **The virtualenv now lives at the project root (`.venv`).** `py.mjs`, all three setup scripts, `.vscode/settings.json` and the README point there. After pulling this change, run `npm run setup` once, then delete your old `server/.venv`.
  2. *How uvicorn reloads on Windows.* To restart its worker, uvicorn calls `os.kill(pid, CTRL_C_EVENT)`. Windows can't send Ctrl+C to a single process, so every process on the console gets it, including Vite, npm and concurrently. Moving the venv only made reloads rarer; every reload still killed Vite.

  Fix: the API now starts through `scripts/dev_api.py` (`npm run dev:api`), which runs uvicorn with:
  - watch dirs `server/` + `config/`, `--reload-include=*.py` and `--reload-include=*.yaml`
  - excludes `.venv/*`, `__pycache__/*`, `data/*`, `server/tests/*` (one level deeper too), `test_*.py`
  - on Windows only, the reloader terminates the worker (as uvicorn already does on macOS/Linux) instead of sending a console Ctrl+C. The app's lifespan has no shutdown work, so nothing is lost.

  Notes for anyone editing the flags:
  - `--reload-dir` accepts only directories (`server/main.py` would be silently dropped). That's why we watch `server/` and exclude the tests.
  - On Windows, Click (uvicorn's CLI) glob-expands arguments, so `server/tests/*` would turn into a list of files. The script disables that expansion.
  - Directory-style `--reload-exclude` values never match in uvicorn 0.54, so the excludes are glob patterns.

  `concurrently` no longer uses `-k`, and it has `--restart-tries 3 --restart-after 2000`, so if the API process dies, Vite keeps running and the API is restarted.

  Verified with `npm run dev`:
  - two edits to `server/core/status.py` and two to `config/app.yaml` each reloaded the worker
  - edits to `server/tests/test_health.py` and to a file in `.venv` caused no reload
  - a syntax error in `server/main.py` broke only the API until it was fixed, and then it came back
  - Vite answered HTTP 200 throughout and never exited or restarted
  - `npm run test` still passes (21 tests + typecheck)

  Not tested: pressing Ctrl+C in a real terminal to stop everything. It uses uvicorn's normal path, which this change doesn't touch.

## Skipped or failed

- Nothing was skipped. No prerequisites were missing.
- One fix during setup: blood pressure first showed as `good`, because the check used a 24-hour look-back. It now uses the mission-day start, and a test covers it.
- Browser check not done (optional). Components compile and the routes exist, but nobody has looked at the UI in a browser yet.
- npm warned that esbuild's `postinstall` script was not run (npm's install-scripts policy). The build works anyway, because the platform binary `@esbuild/win32-x64` was installed. If `vite build` ever fails on a teammate's machine with an esbuild error, run `npm install-scripts approve esbuild` (or `npm rebuild esbuild`) inside `app/`.

## Ollama

Installed and running here. Models pulled: `nomic-embed-text`, `llama3.2:3b`.
On a teammate's machine without it: install from https://ollama.com/download, then

```bash
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

## Next steps for the team

1. **Haya:** follow CONTRIBUTING.md §1 (git init, first commit, GitHub repo, `develop` + three feature branches, branch protection).
2. **Everyone:** clone, run `npm run setup`, then `npm run dev`. Open http://localhost:5173 and check that your pages load and show live JSON.
3. **Monitoring (Haya + Wala):** write `core/adapter.py::load_dataset` once the dataset is in `data/raw/`. Build Today/Vitals/Alert detail from the placeholders. Add rules (sleep short, attention slower, BP missing today, HR outside baseline) by copying `r_data_01_stale.py`.
4. **Daily (Shahd + Nadia):** Daily log (sleep, exercise "couldn't do it" flow, check-in) and the 5-trial attention test (`POST /api/tests` already computes median and lapses).
5. **Support (Marah + Noura):** assistant retrieval over `references/` with Ollama (keep the medication refusal), ReportLab PDF export, comm-window outbox, relax scenes + media in `media/`.
6. **Before the demo:**
   - every threshold has a real source (`co2_max`, `spo2_min`, `sleep_short_hours`)
   - `npm run check:offline` passes
   - `npm run reseed`
   - `npm run build && npm run start`
