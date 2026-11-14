# Daily health: Attention check, sleep and fatigue signals (Shahd)

*All data shown in AstroCare is simulated. Sources are public NASA/CSA pages and published literature; listing them does not mean any agency endorses the app. Nothing in this feature decides fitness for duty.*

## What it does

**Attention check.** A short reaction-time test in the style of the Psychomotor Vigilance Test (PVT), which NASA has used on the ISS to follow alertness (NASA TechPort 23201). A light appears after a random wait; the crew member responds with a click, tap or the Space key. When the light appears, a millisecond counter starts at 0 and stops at the response, as on the classic PVT display. With reduced motion turned on, a static highlighted target replaces the counting animation, and the timing works the same way.

- **Quick mode (default):** 5 trials, about 1 minute. The result is the median reaction time, with lapses (responses ≥ 500 ms, the usual PVT convention) and false starts (responses before the light).
- **Extended mode (3 minutes):** responses continue until 3 minutes have passed. The server adds standard PVT outcome measures: mean reaction time, the mean of the fastest and slowest 10 % of responses, and response speed (mean of 1/RT, in 1/s). A small chart shows reaction time over the 3 minutes, so a slowdown within the test (a time-on-task effect) becomes visible. **Labelled "Experimental, not validated".**
- **Optional practice trial**, marked "Practice: not counted".
- **Sleepiness self-rating before the test:** the 9-point Karolinska Sleepiness Scale (KSS; Åkerstedt & Gillberg, 1990), optional. The result shows the self-rating next to the measured speed, with the note "Self-rating and measured speed can disagree. Both are useful."
- **Personal baseline, never other people.** A result is compared only with the same person's earlier routine tests *of the same mode*, taken more than 48 hours before. With fewer than 3 such tests the app says "Building your baseline (n/3)" and gives no within/outside verdict.
- **Context from the sleep log:** "slept 5.1 h · awake for 9 h", marked SIM when the sleep data is simulated.
- **Input method fairness:** the first response's input (mouse, touch or keyboard) is stored. If it differs from the baseline tests, the app warns that the comparison may be less reliable.
- **History:** the last 10 tests over the usual range, and a full table (mode, context, median, lapses, sleepiness, input, within range).
- **"Add to report":** sends one line with median, lapses, % vs baseline and sleepiness to the report outbox. Private check-in notes are never included.

**Sleep and reaction time chart (14 days).** Sleep hours per night as bars, with a dashed line at the short-sleep threshold, and the daily median reaction time as a line over the personal baseline band. Days with both short sleep and a slower reaction time are highlighted. Days without data are gaps. Caption on the chart: **"Shown together, not a proven cause."**

**Rules.** Each alert lists what changed, the data used, what is missing, *possible* factors (always "not confirmed"), and next steps. None of them names a cause or suggests medication.

| Rule | Fires when | Level |
|---|---|---|
| R-SLP-01 | Sleep under 6 h on 2 of the last 3 nights | info |
| **R-FAT-01** | R-SLP-01 **and** the routine quick-test median in the last 48 h is ≥ 15 % slower than the personal baseline | review |
| R-CIRC-01 | Bedtimes over the last 3 nights differ by more than 2 h | info |

A **retest** linked to R-FAT-01 moves the alert to "recheck". The result screen then shows **Before vs After**: the median that triggered the alert, the retest median, the difference in ms and %, and the alert's new status. The alert never closes automatically; closing it is a human decision.

## Why (NASA basis)

| Feature | Source |
|---|---|
| Sleep log, R-SLP-01, R-CIRC-01, R-FAT-01 | NASA HRP: Risk of performance decrements and adverse health outcomes from sleep loss, circadian desynchronization and work overload |
| Attention check, R-FAT-01 | NASA TechPort 23201: Psychomotor Vigilance Test (PVT) on ISS · NASA HRP evidence report on cognitive and behavioural conditions (NTRS 20250001454) |
| Sleep monitoring | NASA HRP: Ongoing research (wrist-worn sleep/activity monitoring) |
| Sleepiness self-rating | Åkerstedt T, Gillberg M. *Subjective and objective sleepiness in the active individual.* Int J Neurosci 1990; 52(1–2): 29–37 |

## Limits (stated honestly)

- **Thresholds are team choices.** The 6 h short-sleep cut-off, 2 short nights, +15 % slowdown, 7-test baseline and 2 h bedtime shift are all marked "experimental value" in `config/thresholds.yaml`. Only the 500 ms lapse definition is a standard PVT convention.
- **The Extended mode is not a validated PVT.** It's 3 minutes long with 2–10 s waits (plus about 1 s of on-screen feedback between trials), on an ordinary screen and input device. Its numbers are only compared with the same person's other Extended tests.
- **The usual range is a team choice.** It is the baseline median ± the larger of 10 % and the spread of the baseline tests. A result faster than the range is shown as "Faster than usual", never as a problem; only a result ≥ 15 % slower than the baseline is flagged ("Slower than usual").
- **Browser timing:** a scripted check measured within a few ms of a known 250 ms response, but display refresh and input hardware add delays that vary by device. That is one reason input method is recorded.
- **R-CIRC-01 doesn't fire on the current simulated data** (bedtime spread 1.9 h). It is verified with synthetic data, and a simulator change is proposed.
- **All demo data is simulated.**
