// Today page card: today's checklist (check-in, attention test, exercise, sleep rating).
// Self-contained: fetches /api/today/plan itself and handles loading and error.
import { Circle, CircleCheck, CircleMinus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, Card, ErrorState, LoadingState } from '../../../shared/components';
import { logApi, useDailyQuery } from '../api.log';
import type { TodayItem } from '../types.log';
import styles from './TodayCards.module.css';

const STATUS_TEXT: Record<TodayItem['status'], string> = { todo: 'To do', done: 'Done', skipped: 'Skipped' };

function StatusIcon({ status }: { status: TodayItem['status'] }) {
  if (status === 'done') return <CircleCheck size={22} className={styles.done} aria-hidden />;
  if (status === 'skipped') return <CircleMinus size={22} className={styles.skipped} aria-hidden />;
  return <Circle size={22} className={styles.todo} aria-hidden />;
}

export function TodayPlanCard() {
  const { data, error, loading, reload } = useDailyQuery('today-plan-card', () => logApi.todayPlan());
  return (
    <Card
      title="Today's plan"
      subtitle={data ? `Mission day ${data.missionDay}` : undefined}
      actions={data?.fatigueFlag ? <Badge variant="review">Fatigue pattern</Badge> : undefined}
    >
      {loading && !data ? (
        <LoadingState label="Loading today's plan…" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : (
        <ul className={styles.list}>
          {data?.items.map((item) => (
            <li key={item.kind}>
              <Link to={item.route} className={styles.item}>
                <StatusIcon status={item.status} />
                <span className={styles.title}>{item.title}</span>
                <span className="sr-only">{STATUS_TEXT[item.status]}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
