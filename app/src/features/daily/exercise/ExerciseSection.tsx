// Exercise section of the Daily log: today's example plan, Done / "Couldn't do it" flow, week counts.
import { useState } from 'react';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, SectionHeader } from '../../../shared/components';
import type { ExerciseReason } from '../../../shared/types/contracts';
import { NasaBasisLocal } from '../sleep/NasaBasisLocal';
import { errorText, logApi, useDailyQuery } from '../api.log';
import type { ExerciseItem } from '../types.log';
import { AlternativesPanel } from './AlternativesPanel';
import { EquipmentStatusBadge, IntensityBadge } from './badges';
import styles from './ExerciseSection.module.css';

const REASONS: { value: ExerciseReason; label: string }[] = [
  { value: 'pain', label: 'Pain' },
  { value: 'fatigue', label: 'Fatigue' },
  { value: 'equipment', label: 'Equipment' },
  { value: 'time', label: 'Not enough time' },
];

function logSummary(item: ExerciseItem): string | null {
  const log = item.log;
  if (!log) return null;
  if (log.status === 'done') return 'Logged today: done.';
  const why = log.reason ? ` Reason: ${log.reason}.` : '';
  if (log.status === 'partial') return `Logged today: did ${log.alternativeType ?? 'an alternative'} instead.${why}`;
  return `Logged today: skipped.${why}`;
}

export function ExerciseSection({ missionDay, onChanged }: { missionDay: number | undefined; onChanged: () => void }) {
  const plan = useDailyQuery<ExerciseItem[]>('exercise-plan', () => logApi.exercisePlan());
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ExerciseReason>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();

  const items = plan.data ?? [];
  const today = missionDay === undefined ? undefined : items.find((i) => i.day === missionDay);
  const week = items.filter((i) => missionDay !== undefined && i.day <= missionDay && i.log);
  const count = (s: string) => week.filter((i) => i.log?.status === s).length;

  function afterLog(message: string) {
    setNotice(message);
    setOpen(false);
    setReason(undefined);
    plan.reload();
    onChanged();
  }

  async function markDone() {
    if (!today) return;
    setBusy(true);
    setError(undefined);
    try {
      await logApi.logExercise({ planId: today.id, status: 'done' });
      afterLog('Logged as done. Nice work.');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  let body;
  if ((plan.loading && !plan.data) || missionDay === undefined) body = <LoadingState label="Loading exercise…" />;
  else if (plan.error && !plan.data) body = <ErrorState message={plan.error.message} onRetry={plan.reload} />;
  else if (!today) {
    body = <EmptyState title="No session planned today" description="There is nothing scheduled for this mission day. Mobility and stretching is always an option." />;
  } else {
    const summary = logSummary(today);
    body = (
      <Card
        title="Today's session"
        subtitle={`Mission day ${today.day}`}
        actions={<Badge variant="neutral">Example plan</Badge>}
      >
        <div className={styles.session}>
          <strong className={styles.sessionType}>{today.type}</strong>
          <div className={styles.row}>
            <span className={styles.meta}>{today.durationMin} min</span>
            <IntensityBadge intensity={today.intensity} />
            {today.equipment ? (
              <span className={styles.equipment}>
                {today.equipment.name} <EquipmentStatusBadge status={today.equipment.status} />
              </span>
            ) : (
              <span className={styles.meta}>No equipment</span>
            )}
          </div>
          {!today.available && (
            <p className={styles.warn}>This equipment is not available right now. Use "Couldn't do it" to see alternatives.</p>
          )}
          {summary && <p className={styles.logged}>{summary}</p>}
        </div>

        <div className={styles.actions}>
          <Button disabled={busy} onClick={markDone}>Done</Button>
          <Button variant="secondary" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            Couldn't do it
          </Button>
        </div>
        {error && <p className={styles.err} role="alert">{error}</p>}

        {open && (
          <div className={styles.panel}>
            <div role="group" aria-labelledby="why-label">
              <p id="why-label" className={styles.altsIntro}>What got in the way?</p>
              <div className={styles.chips}>
                {REASONS.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    className={styles.chip}
                    aria-pressed={reason === r.value}
                    onClick={() => setReason(r.value)}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              {reason === 'pain' && (
                <p className={styles.hint}>If pain is new, severe or getting worse, tell the flight surgeon. This app can't diagnose it.</p>
              )}
            </div>
            {reason && <AlternativesPanel key={reason} plan={today} reason={reason} onLogged={afterLog} />}
          </div>
        )}
      </Card>
    );
  }

  return (
    <section id="exercise" aria-label="Exercise" className={styles.anchor}>
      <SectionHeader title="Exercise" description="Today's session from the example plan, and what to do when you can't do it." />
      <div className={styles.stack}>
        {body}
        {notice && <p className={styles.notice} role="status">{notice}</p>}
        {plan.data && (
          <p className={styles.week} aria-label="This week">
            This week: <strong>{count('done')}</strong> done, <strong>{count('partial')}</strong> done with an alternative,{' '}
            <strong>{count('skipped')}</strong> skipped.
          </p>
        )}
        <NasaBasisLocal
          sourceIds={['nasa-hrp-risks', 'nasa-bone-risk', 'nasa-hrp-hazards']}
          why="Without gravity, muscles and bones are loaded much less, so regular exercise is part of staying fit in space. Long isolation also makes routines harder to keep. The durations here are an example plan, not a prescription."
        />
      </div>
    </section>
  );
}
