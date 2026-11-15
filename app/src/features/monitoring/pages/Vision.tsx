/** Vision check: a near-vision card and an Amsler grid self-check, per eye (no sensor for SANS).
 * Results are compared with the first (baseline) check by GET /vision/summary; the page shows
 * that comparison as given. A self-check to notice changes: it never diagnoses.
 */
import { useState } from 'react';
import { Button, Card, ErrorState, LoadingState, PageHeader, SimulatedBadge } from '../../../shared/components';
import { api, useApi } from '../../../shared/api/client';
import type { VisionCheck, VisionCheckIn, VisionSummary } from '../../../shared/types/contracts';
import { formatTime } from '../../../shared/utils/format';
import styles from './Vision.module.css';

type SideEye = 'left' | 'right';
const EYES: { id: SideEye; label: string }[] = [
  { id: 'left', label: 'Left eye' },
  { id: 'right', label: 'Right eye' },
];

/** Near-vision card: line 1 is the largest. Sizes are CSS px (not a calibrated chart): use the
 * same screen, distance and lighting each time so results can be compared. 10 lines = the
 * backend's NEAR_VISION_LINES. */
const NEAR_VISION_LINES: { px: number; text: string }[] = [
  { px: 34, text: 'The ship turns' },
  { px: 28, text: 'Stars over the bay' },
  { px: 24, text: 'A calm night in orbit' },
  { px: 20, text: 'The crew checks the water tank' },
  { px: 17, text: 'Morning light falls across the deck' },
  { px: 15, text: 'Pack the kit and close the hatch slowly' },
  { px: 13, text: 'Read the list twice before the evening call home' },
  { px: 12, text: 'A small note was left beside the window of the lab' },
  { px: 11, text: 'Each panel was cleaned and checked after the long shift' },
  { px: 10, text: 'The last line of text is the smallest one on this card today' },
];

const GRID_CELLS = 20;
const GRID_PX = 240;

function AmslerGrid() {
  const step = GRID_PX / GRID_CELLS;
  const lines = Array.from({ length: GRID_CELLS + 1 }, (_, i) => i * step);
  return (
    <svg
      className={styles.grid}
      viewBox={`0 0 ${GRID_PX} ${GRID_PX}`}
      width={GRID_PX}
      height={GRID_PX}
      role="img"
      aria-label={`Amsler grid: ${GRID_CELLS} by ${GRID_CELLS} squares with a dot in the centre`}
    >
      <rect x="0" y="0" width={GRID_PX} height={GRID_PX} className={styles.gridBg} />
      {lines.map((p) => (
        <g key={p}>
          <line x1={p} y1={0} x2={p} y2={GRID_PX} className={styles.gridLine} />
          <line x1={0} y1={p} x2={GRID_PX} y2={p} className={styles.gridLine} />
        </g>
      ))}
      <circle cx={GRID_PX / 2} cy={GRID_PX / 2} r={4} className={styles.gridDot} />
    </svg>
  );
}

function eyeName(eye: VisionCheck['eye']): string {
  return eye === 'both' ? 'Both eyes' : eye === 'left' ? 'Left eye' : 'Right eye';
}

export default function Vision() {
  const summary = useApi<VisionSummary>('/vision/summary');
  const history = useApi<VisionCheck[]>('/vision/checks?n=10');
  const [lines, setLines] = useState<Partial<Record<SideEye, number>>>({});
  const [grid, setGrid] = useState<Partial<Record<SideEye, boolean>>>({});
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  const [saved, setSaved] = useState(false);
  const [reportState, setReportState] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');

  const complete = EYES.every(({ id }) => lines[id] !== undefined && grid[id] !== undefined);
  const s = summary.data;

  const save = async () => {
    if (!complete) return;
    setSaving(true);
    setSaveError(undefined);
    const body: VisionCheckIn[] = EYES.map(({ id }) => ({
      eye: id,
      nearVisionSmallestLine: lines[id] as number,
      amslerChanged: grid[id] as boolean,
      notes: notes.trim() || null,
    }));
    try {
      await api.post<VisionCheck[]>('/vision/checks', body);
      setSaved(true);
      setReportState('idle');
      setLines({});
      setGrid({});
      setNotes('');
      summary.reload();
      history.reload();
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const addToReport = async () => {
    if (!s) return;
    setReportState('sending');
    try {
      await api.post('/reports/items', {
        kind: 'note',
        title: 'Vision self-check: change since baseline',
        text: `${s.changes.join('. ')}. Baseline: mission day ${s.baselineMissionDay}; latest: mission day ${s.lastMissionDay}. ${s.disclaimer}`,
        sourceFeature: 'monitoring',
      });
      setReportState('done');
    } catch {
      setReportState('error');
    }
  };

  const question = s
    ? `My vision self-check changed since baseline (${s.changes.join('; ')}). What does NASA say about vision changes in spaceflight, and what should I tell the CMO?`
    : '';

  return (
    <>
      <PageHeader eyebrow="Space medicine" title="Vision check" />
      <p className={styles.disclaimer} role="note">
        {s?.disclaimer ?? 'A self-check to notice changes. It does not diagnose. Changes go to the CMO for proper eye exams.'}
      </p>

      <div className={styles.layout}>
        <Card title="Latest result" subtitle={s?.lastMissionDay != null ? `Last check · mission day ${s.lastMissionDay}` : undefined}>
          {summary.loading && !s ? (
            <LoadingState />
          ) : summary.error ? (
            <ErrorState message={summary.error.message} onRetry={summary.reload} />
          ) : s ? (
            <div role="status" aria-live="polite">
              {saved && <p className={styles.saved}>Check saved.</p>}
              {s.lastMissionDay == null ? (
                <p className={styles.result}>No self-check yet. <span className={styles.muted}>Your first check becomes the baseline.</span></p>
              ) : s.changed ? (
                <>
                  <ul className={styles.changes}>
                    {s.changes.map((c) => <li key={c}>{c}</li>)}
                  </ul>
                  <p className={styles.muted}>Compared with the baseline check on mission day {s.baselineMissionDay}.</p>
                  <div className={styles.actions}>
                    <Button onClick={addToReport} disabled={reportState === 'sending' || reportState === 'done'}>
                      {reportState === 'done' ? 'Added to report' : 'Add to report for the CMO'}
                    </Button>
                    <Button variant="secondary" to={`/assistant?q=${encodeURIComponent(question)}`}>Ask the assistant</Button>
                  </div>
                  {reportState === 'error' && <p className={styles.error} role="alert">Could not add to the report. Try again.</p>}
                </>
              ) : (
                <p className={styles.result}>
                  <strong>Same as baseline</strong>
                  <span className={styles.muted}> · baseline on mission day {s.baselineMissionDay}</span>
                </p>
              )}
              {s.due && s.lastMissionDay != null && (
                <p className={styles.due}>Self-check due: no check in the last {s.dueDays} days.</p>
              )}
            </div>
          ) : null}
        </Card>

        <Card title="Step 1 · Near-vision card" subtitle="Smallest line you can read comfortably">
          <ul className={styles.instructions}>
            <li>Hold the screen at arm's length. Cover one eye and test each eye on its own.</li>
            <li>Use the same distance, screen and lighting each time, so checks can be compared.</li>
            <li>Pick the smallest line you can read comfortably, without straining.</li>
          </ul>
          <ol className={styles.card} aria-label="Near-vision card, line 1 is the largest">
            {NEAR_VISION_LINES.map((l, i) => (
              <li key={l.px} style={{ fontSize: `${l.px}px` }}>
                <span className={styles.lineNum} aria-hidden>{i + 1}</span>
                {l.text}
              </li>
            ))}
          </ol>
          {EYES.map(({ id, label }) => (
            <fieldset key={id} className={styles.fieldset}>
              <legend>{label}: smallest line read comfortably</legend>
              <div className={styles.options}>
                {NEAR_VISION_LINES.map((_, i) => (
                  <label key={i} className={`${styles.option} ${lines[id] === i + 1 ? styles.selected : ''}`}>
                    <input
                      type="radio"
                      name={`line-${id}`}
                      value={i + 1}
                      checked={lines[id] === i + 1}
                      onChange={() => setLines((v) => ({ ...v, [id]: i + 1 }))}
                      aria-label={`${label}, line ${i + 1}`}
                    />
                    <span aria-hidden>{i + 1}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </Card>

        <Card title="Step 2 · Amsler grid" subtitle="Cover one eye and look at the centre dot">
          <ul className={styles.instructions}>
            <li>Same distance and lighting as step 1. Keep looking at the centre dot.</li>
            <li>Test each eye on its own.</li>
          </ul>
          <AmslerGrid />
          {EYES.map(({ id, label }) => (
            <fieldset key={id} className={styles.fieldset}>
              <legend>{label}: Do any lines look wavy, blurred or missing?</legend>
              <div className={styles.options}>
                {([['Yes', true], ['No', false]] as const).map(([text, value]) => (
                  <label key={text} className={`${styles.option} ${styles.wide} ${grid[id] === value ? styles.selected : ''}`}>
                    <input
                      type="radio"
                      name={`grid-${id}`}
                      checked={grid[id] === value}
                      onChange={() => setGrid((v) => ({ ...v, [id]: value }))}
                    />
                    <span>{text}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <label className={styles.notesLabel} htmlFor="vision-notes">Notes (optional)</label>
          <textarea
            id="vision-notes"
            className={styles.notes}
            value={notes}
            maxLength={1000}
            rows={2}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className={styles.actions}>
            <Button onClick={save} disabled={!complete || saving}>{saving ? 'Saving…' : 'Save check'}</Button>
            {!complete && <span className={styles.muted}>Answer both steps for each eye to save.</span>}
          </div>
          {saveError && <p className={styles.error} role="alert">Could not save: {saveError}</p>}
        </Card>

        <Card title="Recent checks">
          {history.error ? (
            <ErrorState message={history.error.message} onRetry={history.reload} />
          ) : history.data && history.data.length ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr><th scope="col">When</th><th scope="col">Eye</th><th scope="col">Smallest line</th><th scope="col">Grid</th></tr>
                </thead>
                <tbody>
                  {history.data.map((c) => (
                    <tr key={c.id}>
                      <td>{new Date(c.ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} {formatTime(c.ts)}{' '}
                        {c.source === 'simulated' && <SimulatedBadge source="simulated" />}</td>
                      <td>{eyeName(c.eye)}</td>
                      <td>{c.nearVisionSmallestLine}</td>
                      <td>{c.amslerChanged ? 'Changes reported' : 'No change'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className={styles.muted}>{history.loading ? 'Loading…' : 'No checks yet.'}</p>
          )}
        </Card>

        <Card title="Why we track this">
          <p className={styles.why}>{s?.why}</p>
          {s && <p className={styles.muted}>Source: NASA Human Research Program, “{s.sourceTitle}” (references/{s.sourceRef}.txt)</p>}
        </Card>
      </div>
    </>
  );
}
