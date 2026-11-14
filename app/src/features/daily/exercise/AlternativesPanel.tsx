// Ranked alternatives for one reason. Choosing one logs the session as `partial`.
// An empty list shows the server's message and offers "Reschedule to tomorrow" (logs `skipped`).
import { useState } from 'react';
import { Button, ErrorState, LoadingState } from '../../../shared/components';
import type { ExerciseReason } from '../../../shared/types/contracts';
import { errorText, logApi, useDailyQuery } from '../api.log';
import type { AlternativesResult, ExerciseItem } from '../types.log';
import { EquipmentStatusBadge, IntensityBadge } from './badges';
import styles from './ExerciseSection.module.css';

export interface AlternativesPanelProps {
  plan: ExerciseItem;
  reason: ExerciseReason;
  onLogged: (message: string) => void;
}

export function AlternativesPanel({ plan, reason, onLogged }: AlternativesPanelProps) {
  const { data, error, loading, reload } = useDailyQuery<AlternativesResult>(`alts-${plan.id}-${reason}`, () =>
    logApi.alternatives(plan.id, reason),
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string>();

  async function run(body: Parameters<typeof logApi.logExercise>[0], message: string) {
    setBusy(true);
    setActionError(undefined);
    try {
      await logApi.logExercise(body);
      onLogged(message);
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <LoadingState label="Finding alternatives…" />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className={styles.alts} aria-live="polite">
      {data.alternatives.length === 0 ? (
        <div className={styles.emptyAlts}>
          <p>{data.message ?? 'No alternative available. Try rescheduling.'}</p>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => run({ planId: plan.id, status: 'skipped', reason }, 'Rescheduled to tomorrow. Logged as skipped today.')}
          >
            Reschedule to tomorrow
          </Button>
        </div>
      ) : (
        <>
          <p className={styles.altsIntro}>Suggested alternatives, best match first:</p>
          <ul className={styles.altList}>
            {data.alternatives.map((a) => (
              <li key={a.id} className={styles.alt}>
                <div className={styles.altMain}>
                  <strong>{a.type}</strong>
                  <span className={styles.meta}>{a.durationMin} min</span>
                  <IntensityBadge intensity={a.intensity} />
                  {a.equipment && <EquipmentStatusBadge status={a.equipment.status} />}
                </div>
                <ul className={styles.why} aria-label="Why this is suggested">
                  {a.why.map((w) => (
                    <li key={w} className={styles.whyChip}>{w}</li>
                  ))}
                </ul>
                <Button
                  disabled={busy}
                  aria-label={`Choose ${a.type}`}
                  onClick={() => run({ planId: plan.id, status: 'partial', reason, alternativeId: a.id }, `Logged as partial: ${a.type}.`)}
                >
                  Choose this
                </Button>
              </li>
            ))}
          </ul>
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => run({ planId: plan.id, status: 'skipped', reason }, 'Logged as skipped.')}
          >
            Skip this session instead
          </Button>
        </>
      )}
      {actionError && <p className={styles.err} role="alert">{actionError}</p>}
    </div>
  );
}
