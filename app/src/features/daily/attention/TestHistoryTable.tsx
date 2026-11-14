// Owner: Shahd. Collapsible "All tests" table, newest first, 20 rows at a time.
// "Within range" is against the same-mode baseline as it was at that test's time
// (computed on the server); "—" while that baseline was still building.
import { ChevronDown } from 'lucide-react';
import { useId, useState } from 'react';
import { Button } from '../../../shared/components';
import { rangeStatusOf, type DailyCognitiveTest, type RangeStatus } from '../api.attention';
import styles from './Attention.module.css';

const PAGE = 20;

function when(ts: string) {
  const d = new Date(ts);
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString(
    [],
    {
      hour: '2-digit',
      minute: '2-digit',
    },
  )}`;
}

function WithinCell({ status }: { status: RangeStatus | null }) {
  switch (status) {
    case null:
      return (
        <span title="Baseline still building">
          —<span className="sr-only">baseline still building</span>
        </span>
      );
    case 'within':
      return (
        <span className={styles.ok}>
          ✓<span className="sr-only">within your usual range</span>
        </span>
      );
    case 'faster':
      return (
        <span className={styles.ok}>
          ✓ faster<span className="sr-only"> than usual</span>
        </span>
      );
    case 'slower':
      return <span>a little slower</span>;
    case 'flagged':
      return (
        <span className={styles.off}>
          ✗ slower<span className="sr-only"> than usual</span>
        </span>
      );
  }
}

export function TestHistoryTable({ tests }: { tests: DailyCognitiveTest[] }) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(PAGE);
  const contentId = useId();
  const rows = tests.slice(0, shown);

  return (
    <section className={styles.history} aria-label="All tests">
      <h2 className={styles.historyHeading}>
        <button
          type="button"
          className={styles.disclosure}
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((o) => !o)}
        >
          <span>All tests</span>
          <span className={styles.meta}>{tests.length} saved</span>
          <ChevronDown
            size={18}
            aria-hidden
            className={open ? styles.chevronOpen : styles.chevron}
          />
        </button>
      </h2>
      <div id={contentId} hidden={!open} className={styles.historyBody}>
        <div
          className={styles.tableWrap}
          tabIndex={0}
          aria-label="All tests table, scrolls sideways"
        >
          <table className={styles.table}>
            <caption className="sr-only">All attention tests, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Mission day</th>
                <th scope="col">Mode</th>
                <th scope="col">Context</th>
                <th scope="col">Median</th>
                <th scope="col">Lapses</th>
                <th scope="col">Sleepiness</th>
                <th scope="col">Input</th>
                <th scope="col">Vs usual range</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td>{when(t.ts)}</td>
                  <td>{t.missionDay ?? '—'}</td>
                  <td>{t.mode === 'extended' ? 'Extended' : 'Quick'}</td>
                  <td>{t.context === 'retest' ? 'Retest' : 'Routine'}</td>
                  <td className={styles.num}>{Math.round(t.medianMs)} ms</td>
                  <td className={styles.num}>{t.lapses}</td>
                  <td className={styles.num}>
                    {t.sleepinessKss != null ? `${t.sleepinessKss}/9` : '—'}
                  </td>
                  <td>{t.inputMethod ?? '—'}</td>
                  <td>
                    <WithinCell status={rangeStatusOf(t.rangeStatus, t.withinRange)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {shown < tests.length && (
          <div>
            <Button variant="secondary" onClick={() => setShown((n) => n + PAGE)}>
              Show more ({tests.length - shown} left)
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
