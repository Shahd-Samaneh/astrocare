/** Bone & muscle: exercise adherence (the countermeasure) and an illustrative bone-density estimate.
 * No sensor measures bone or muscle in flight. Adherence comes from GET /exercise/plan (each item
 * with its latest log); the estimate from GET /bone/estimate (mission day ÷ average month × NASA's
 * 1–1.5 %/month from config/thresholds.yaml). No medication or supplement advice on this page.
 */
import { Button, Card, ErrorState, LoadingState, PageHeader } from '../../../shared/components';
import { useApi } from '../../../shared/api/client';
import type { BoneEstimate, ExerciseStatus } from '../../../shared/types/contracts';
import styles from './Bone.module.css';

/** The fields of GET /exercise/plan this page reads. */
interface PlanItem {
  id: string;
  day: number;
  type: string;
  log?: { status: ExerciseStatus; reason?: string | null; alternativeType?: string } | null;
}

const WINDOW_DAYS = 7;
const STATUS_LABELS: Record<ExerciseStatus, string> = { done: 'Done', partial: 'Partial', skipped: 'Skipped' };

function rowStatus(item: PlanItem | undefined, isToday: boolean): { label: string; detail?: string; cls: string } {
  if (!item) return { label: 'No session planned', cls: styles.none };
  const log = item.log;
  if (!log) return isToday ? { label: 'Not logged yet', cls: styles.none } : { label: 'Not logged', cls: styles.missed };
  const detail = log.status === 'partial' && log.alternativeType ? `instead: ${log.alternativeType}`
    : log.status === 'skipped' && log.reason ? `reason: ${log.reason}` : undefined;
  return { label: STATUS_LABELS[log.status], detail, cls: log.status === 'skipped' ? styles.missed : styles[log.status] };
}

function Adherence({ today, plan }: { today: number; plan: PlanItem[] }) {
  const days = Array.from({ length: WINDOW_DAYS }, (_, i) => today - WINDOW_DAYS + 1 + i);
  const inWindow = plan.filter((p) => p.day >= days[0] && p.day <= today);
  const count = (s: ExerciseStatus) => inWindow.filter((p) => p.log?.status === s).length;
  const notLogged = inWindow.filter((p) => !p.log && p.day < today).length;
  return (
    <Card title="Exercise adherence" subtitle={`Last ${WINDOW_DAYS} mission days (${days[0]}–${today}) · example plan (simulated)`}>
      <p className={styles.summary}>
        <strong>{inWindow.length} planned</strong>
        <span>{count('done')} done · {count('partial')} partial · {count('skipped')} skipped · {notLogged} not logged</span>
      </p>
      <ul className={styles.days}>
        {days.map((day) => {
          const item = plan.find((p) => p.day === day);
          const s = rowStatus(item, day === today);
          return (
            <li key={day}>
              <span className={styles.day}>Day {day}{day === today && ' · today'}</span>
              <span className={styles.session}>{item?.type ?? '—'}</span>
              <span className={`${styles.status} ${s.cls}`}>
                {s.label}{s.detail && <small> ({s.detail})</small>}
              </span>
            </li>
          );
        })}
      </ul>
      <p className={styles.muted}>Partial = an alternative session was done; it counts as exercise done.</p>
      <Button variant="secondary" to="/daily#exercise">Open exercise</Button>
    </Card>
  );
}

function Estimate({ est }: { est: BoneEstimate }) {
  return (
    <Card title="Bone density change (illustrative estimate)" subtitle={est.label}>
      <p className={styles.note} role="note">{est.note}</p>
      {est.available && est.lossPctPerMonthMin != null && est.lossPctPerMonthMax != null
        && est.estimatedLossPctMin != null && est.estimatedLossPctMax != null ? (
        <>
          <p className={styles.fact}>
            In microgravity, astronauts lose on average about {est.lossPctPerMonthMin}–{est.lossPctPerMonthMax}% of
            bone density per month (NASA).
          </p>
          <p className={styles.value}>
            <strong>≈ {est.estimatedLossPctMin}–{est.estimatedLossPctMax}%</strong>
            <span>Mission day {est.missionDay} ≈ {est.monthsInFlight} months in flight × {est.lossPctPerMonthMin}–{est.lossPctPerMonthMax}% per month</span>
          </p>
          <p className={styles.muted}>{est.sourceScope}</p>
          <p className={styles.sources}>Source: {est.source}</p>
        </>
      ) : (
        <p className={styles.muted}>No estimate: the monthly bone-loss range has no sourced value in thresholds.yaml.</p>
      )}
      <p className={styles.why}>{est.why}.</p>
    </Card>
  );
}

export default function Bone() {
  const estimate = useApi<BoneEstimate>('/bone/estimate', { refreshMs: 60_000 });
  const plan = useApi<PlanItem[]>('/exercise/plan', { refreshMs: 60_000 });
  const error = estimate.error ?? plan.error;
  const reload = () => { estimate.reload(); plan.reload(); };

  return (
    <>
      <PageHeader eyebrow="Space medicine" title="Bone & muscle" />
      {(estimate.loading && !estimate.data) || (plan.loading && !plan.data) ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : estimate.data && plan.data ? (
        <div className={styles.stack}>
          <Adherence today={estimate.data.missionDay} plan={plan.data} />
          <Estimate est={estimate.data} />
        </div>
      ) : null}
    </>
  );
}
