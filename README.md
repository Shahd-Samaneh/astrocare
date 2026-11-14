# AstroCare

Offline-first health monitoring and decision support for astronauts in deep space.
It runs entirely on the device (browser UI + local API + local LLM), with no Earth link required. Built by **PinkSpectrum**.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Node.js | ≥ 20 | https://nodejs.org |
| Python | ≥ 3.11 | https://www.python.org/downloads/ |
| Ollama | optional | Needed only for the Assistant: https://ollama.com/download |

## Setup (one command)

```bash
npm run setup          # any OS (needs Node + Python)
# or
bash scripts/setup.sh                                    # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
```

This installs the root + frontend packages, creates `.venv` (project root), installs the Python packages, and (if Ollama is installed) pulls `llama3.2:3b` and `nomic-embed-text`.

## Run

| Command | What it does |
|---|---|
| `npm run dev` | Vite on http://localhost:5173 (hot reload) + FastAPI on :8000 (auto-reload of `server/` minus tests, and `config/`). Use this while coding. A backend crash or reload never stops Vite. |
| `npm run build` | Builds the frontend into `app/dist`. |
| `npm run start` | **Demo mode.** One process on http://localhost:8000 serves the UI and `/api`, fully offline. Run `build` first. |
| `npm run test` | `pytest` + `tsc --noEmit`. |
| `npm run lint` | ESLint (also blocks remote URLs in code). |
| `npm run check:offline` | Scans `app/src`, `app/index.html` and `app/dist` for remote URLs. |
| `npm run reseed` | Wipes `data/astrocare.db` and regenerates the simulated demo data. |

API docs while the server runs: http://localhost:8000/docs

## Folder map

```
app/                      React + TypeScript + Vite
  src/shared/             design tokens, contracts.ts, api client, shared components, AppShell   (via Haya)
  src/features/monitoring Today, Vitals, Alerts, Resources, Profile, Radiation, Bone            (Haya + Wala)
  src/features/daily      Daily log, Attention check                                             (Shahd + Nadia)
  src/features/support    Assistant, Reports, Relax                                              (Marah + Noura)
server/                   FastAPI
  core/                   db, models (contract), config, simulator, seed, adapter, status        (via Haya)
  rules/                  rule engine + rules (r_*.py are auto-discovered)
  features/<name>/router  monitoring · daily · assistant · reports · relax
  tests/
config/                   app.yaml (mission, crew, comms) · thresholds.yaml (every value has a source)
data/                     astrocare.db (generated, not committed) · raw/ (hackathon dataset) · simulated/
references/               NASA texts for the assistant
media/                    relaxation scenes and audio
docs/                     ARCHITECTURE.md · SETUP_NOTES.md
scripts/                  setup scripts, python runner, dev API launcher, offline check
.venv/                    Python virtualenv (created by setup, not committed)
```

## Who owns what

| Pair | Frontend | Backend |
|---|---|---|
| Haya + Wala | `app/src/features/monitoring` | `server/features/monitoring`, `server/rules` |
| Shahd + Nadia | `app/src/features/daily` | `server/features/daily` |
| Marah + Noura | `app/src/features/support` | `server/features/assistant`, `reports`, `relax` |

Changes to `app/src/shared/`, `server/core/` or the data contract go through **Haya**. See [CONTRIBUTING.md](CONTRIBUTING.md).

## The offline rule

The running app must make **zero requests to the internet**:
no CDNs, no Google Fonts, no remote images, no external APIs. Fonts (`@fontsource/*`) and icons (`lucide-react`) are npm packages bundled at build time. The only network calls go to `localhost` (our API on :8000 and Ollama on :11434). ESLint fails on remote URLs in code, and `npm run check:offline` checks the build.

## Data contract

`app/src/shared/types/contracts.ts` ⇄ `server/core/models.py`. Change both files together, via Haya. JSON is camelCase, Python is snake_case (Pydantic aliases handle the mapping). All demo data has `source: "simulated"` and the UI shows a **SIMULATED DATA** chip.

## How to add a rule

1. Copy `server/rules/r_data_01_stale.py` to `server/rules/r_<area>_<nn>_<name>.py` (e.g. `r_sleep_01_short.py`).
2. Set `id`, `name`, `sources`. Read the data through `ctx` (`ctx.readings("heart_rate", hours=24)`, `ctx.sleep(7)`, `ctx.tests()`, `ctx.profile`, `ctx.resources`, `ctx.threshold("sleep_short_hours")`, ...).
3. Return an `AlertDraft(...)` when it fires, else `None`. Use plain words: "possible link", never "diagnosis".
4. Any number you use goes in `config/thresholds.yaml` **with a source**.
5. Add a test in `server/tests/test_rules.py`. The engine finds the file automatically, runs it on startup, and won't duplicate an open alert.
