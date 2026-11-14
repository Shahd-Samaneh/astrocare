# Contributing to AstroCare (hackathon workflow)

## 1. Git setup (do this once, at the hackathon)

The repo is git-ready (`.gitignore` is in place) but **not** initialised yet. One person (Haya) runs:

```bash
git init -b main
git add .
git commit -m "Initial AstroCare scaffold"
# Create an empty repo on GitHub (no README/.gitignore), then:
git remote add origin https://github.com/<org-or-user>/astrocare.git
git push -u origin main

git checkout -b develop && git push -u origin develop
git checkout -b feature/monitoring && git push -u origin feature/monitoring
git checkout develop && git checkout -b feature/daily && git push -u origin feature/daily
git checkout develop && git checkout -b feature/support && git push -u origin feature/support
```

On GitHub: add all teammates as collaborators, and protect `main` and `develop` (pull request required, 1 approval).

Everyone else:

```bash
git clone https://github.com/<org-or-user>/astrocare.git && cd astrocare
npm run setup
git checkout feature/<your-pair>
```

## 2. Branches

```
main                 demo only: always runs with `npm run build && npm run start`
  └── develop        integration
        ├── feature/monitoring   Haya + Wala
        ├── feature/daily        Shahd + Nadia
        └── feature/support      Marah + Noura
```

Pull `develop` into your feature branch often (`git pull origin develop`), at least every few hours.

## 3. Pull requests

- Every PR goes into `develop` and is **reviewed by someone from another pair**.
- Before opening it: `npm run test`, `npm run lint` and `npm run build` pass.
- Keep PRs small. Say in the description what changed and how to check it.
- `develop` → `main` happens only after the merges below, once the demo runs.

## 4. Merge schedule (Saturday)

| Time | What |
|---|---|
| **16:00** | **Test merge.** Every pair merges its branch into `develop`; fix conflicts and broken tests together. |
| **20:00** | **Full merge.** Final features into `develop`, then `develop` → `main`. After this, bug fixes only. |

## 5. Ownership

- **Each pair edits only its own `features/<name>` folders**, on both the frontend (`app/src/features/<name>`) and the backend (`server/features/<name>`).
- **Changes to `app/src/shared/`, `server/core/` or the contracts (`contracts.ts` + `models.py`) go through Haya.** Ask in the team chat; Haya makes or approves the change, so everyone builds against the same contract.
- Monitoring also owns `server/rules/`. Other pairs can propose rules through a PR.
- Need a new endpoint? Add it to your own router. Need a new field in the contract? Ask Haya.

## 6. Thresholds

**Every threshold needs a source.** Numbers live only in `config/thresholds.yaml` (`value`, `unit`, `source`, `note`), never in code. If there is no source yet, set `source: "TODO"` and leave a note; it must be fixed before the demo (e.g. `co2_max` is still `null`).

## 7. House rules

- Offline: no remote URLs, CDNs, Google Fonts or external APIs (lint blocks them; `npm run check:offline` checks the build).
- Use the design tokens (`app/src/shared/styles/tokens.css`) and the shared components; no raw colours.
- Accessibility: 44 px minimum click targets, visible keyboard focus, proper ARIA labels.
- Medical wording: "possible link, not a confirmed cause". The assistant never gives medication or dose advice.
