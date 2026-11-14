// Today page card: last night's sleep vs the personal average, a 7-night sparkline, link to /daily#sleep.
// Self-contained: fetches /api/sleep/summary itself and handles loading and error.
import { Button, Card, EmptyState, ErrorState, LoadingState } from '../../../shared/components';
import { logApi, useDailyQuery } from '../api.log';
import styles from './TodayCards.module.css';

const SPARK_MAX_HOURS = 10;

export function SleepSummaryCard() {
  const { data, error, loading, reload } = useDailyQuery('sleep-summary-card', () => logApi.sleepSummary(7));
  const last = data?.lastNight;
  const avg = data?.personalAvgHours;
  const diff = last && avg != null ? Math.round((last.hours - avg) * 10) / 10 : null;

  let body;
  if (loading && !data) body = <LoadingState label="Loading sleep…" />;
  else if (error && !data) body = <ErrorState message={error.message} onRetry={reload} />;
  else if (!data || !last) body = <EmptyState title="No sleep logged yet" />;
  else {
    const compare =
      diff === null ? '' : diff === 0 ? 'the same as your average' : `${Math.abs(diff)} h ${diff < 0 ? 'below' : 'above'} your average of ${avg} h`;
    body = (
      <>
        <p className={styles.big}>{last.hours} h</p>
        <p className={styles.muted}>last night{compare && `, ${compare}`}</p>
        <div
          className={styles.spark}
          role="img"
          aria-label={`Sleep over the last ${data.nights.length} nights, in hours: ${data.nights.map((n) => n.hours).join(', ')}`}
        >
          {data.nights.map((n) => (
            <span
              key={n.id}
              className={n.short ? `${styles.bar} ${styles.barShort}` : styles.bar}
              style={{ height: `${Math.min(100, (n.hours / SPARK_MAX_HOURS) * 100)}%` }}
            />
          ))}
        </div>
      </>
    );
  }

  return (
    <Card title="Sleep" subtitle="Last 7 nights">
      {body}
      <div>
        <Button variant="secondary" to="/daily#sleep">Open sleep log</Button>
      </div>
    </Card>
  );
}
