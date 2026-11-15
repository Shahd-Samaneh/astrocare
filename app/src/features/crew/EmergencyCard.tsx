// Owner: Shahd. One R-LOC-01 event for the CMO and Commander: calm Watch while the crew member
// has time to answer, red emergency once escalated. Signals, missing data, countdown status,
// Acknowledge (CMO / Commander), Resolve with an outcome, and the timeline.
import { CheckCheck, CircleCheck, Siren, Eye } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { ApiError } from '../../shared/api/client';
import { Badge, Button, Card } from '../../shared/components';
import {
  OUTCOME_LABEL,
  ROLE_LABEL,
  acknowledge,
  resolveEmergency,
  type CrewEmergency,
  type CrewRole,
  type Outcome,
  type TimelineStep,
} from './api.crew';
import { useCrewFeed } from './crewFeed';
import { localTimes, timeText } from './crewState';
import styles from './Crew.module.css';

const OUTCOMES = Object.keys(OUTCOME_LABEL) as Outcome[];

function stepClass(s: TimelineStep) {
  if (s.step === 'no_response' || s.step === 'escalated')
    return `${styles.step} ${styles.stepDanger}`;
  if (s.step === 'detected' || s.step === 'check_shown') return `${styles.step} ${styles.stepWarn}`;
  return styles.step;
}

export function Timeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol className={styles.timeline} aria-label="Timeline">
      {steps.map((s, i) => (
        <li key={`${s.step}-${i}`} className={stepClass(s)}>
          <time className={styles.stepTime} dateTime={s.ts}>
            {timeText(s.ts)}
          </time>
          {localTimes(s.text)}
        </li>
      ))}
    </ol>
  );
}

export function Signals({ em }: { em: CrewEmergency }) {
  return (
    <>
      <div>
        <p className={styles.sectionLabel}>Signals (unconfirmed)</p>
        <ul className={styles.list}>
          {em.signals.length ? (
            em.signals.map((s) => (
              <li key={s.kind}>
                <strong>{s.label}</strong> at {timeText(s.ts)}: {localTimes(s.detail)}
              </li>
            ))
          ) : (
            <li>See the alert for the signals.</li>
          )}
        </ul>
      </div>
      {em.missing.length > 0 && (
        <div>
          <p className={styles.sectionLabel}>Missing data</p>
          <ul className={styles.list}>
            {em.missing.map((m) => (
              <li key={m}>{localTimes(m)}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function statusText(em: CrewEmergency, left: number) {
  if (em.status === 'watch')
    return left > 0 ? `Waiting for a response: ${left} s left` : 'No response: escalating…';
  if (em.respondedTs)
    return `Escalated ${timeText(em.escalatedTs)} · crew member answered ${timeText(em.respondedTs)}`;
  return `No response · escalated ${timeText(em.escalatedTs)}`;
}

export function EmergencyCard({ em }: { em: CrewEmergency }) {
  const feed = useCrewFeed();
  const left = feed.left(em.deadlineTs);
  const [resolving, setResolving] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>();
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(undefined);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
      feed.reload();
    }
  };

  const ack = (role: CrewRole) => void run(() => acknowledge(em.id, role));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!outcome) return setError('Choose an outcome.');
    if (!note.trim()) return setError('Add a short note.');
    if (await run(() => resolveEmergency(em.id, outcome, note.trim()))) setResolving(false);
  };

  const isWatch = em.status === 'watch';
  const title = isWatch ? (
    <>Watch: possible loss of consciousness, {em.crewName}</>
  ) : (
    <>Emergency: possible loss of consciousness, {em.crewName}</>
  );

  return (
    <Card
      className={isWatch ? styles.watch : styles.emergency}
      title={
        <span className={styles.row}>
          {isWatch ? <Eye size={18} aria-hidden /> : <Siren size={18} aria-hidden />}
          {title}
        </span>
      }
      subtitle={`R-LOC-01 · detected ${timeText(em.detectedTs)}`}
      actions={
        isWatch ? (
          <Badge variant="review">Watch</Badge>
        ) : em.acknowledged ? (
          <Badge variant="urgent">Acknowledged</Badge>
        ) : (
          <Badge variant="urgent">Not acknowledged</Badge>
        )
      }
    >
      {isWatch && (
        <p className={styles.lead} aria-live="polite">
          Possible loss of consciousness detected for {em.crewName}. Waiting for their response (
          <span className={styles.countInline}>{left} s</span>)…
        </p>
      )}

      <dl className={styles.facts}>
        <div className={styles.fact}>
          <dt>Crew member</dt>
          <dd>{em.crewName}</dd>
        </div>
        <div className={styles.fact}>
          <dt>Detected</dt>
          <dd>{timeText(em.detectedTs)}</dd>
        </div>
        <div className={styles.fact}>
          <dt>Countdown</dt>
          <dd>{statusText(em, left)}</dd>
        </div>
        <div className={styles.fact}>
          <dt>Acknowledged</dt>
          <dd>
            CMO {em.ackCmoTs ? timeText(em.ackCmoTs) : '—'} · Commander{' '}
            {em.ackCommanderTs ? timeText(em.ackCommanderTs) : '—'}
          </dd>
        </div>
      </dl>

      <Signals em={em} />

      {em.reportNote && <p className={styles.note}>Earth report: {em.reportNote}</p>}

      <div className={styles.row}>
        {(['cmo', 'commander'] as CrewRole[]).map((role) => {
          const done = role === 'cmo' ? em.ackCmoTs : em.ackCommanderTs;
          return (
            <Button
              key={role}
              variant={isWatch ? 'secondary' : 'warn'}
              icon={<CheckCheck size={16} />}
              onClick={() => ack(role)}
              disabled={busy || !!done}
              aria-label={
                done
                  ? `Acknowledged by the ${ROLE_LABEL[role]}`
                  : `Acknowledge as ${ROLE_LABEL[role]}`
              }
            >
              {done ? `Acknowledged (${ROLE_LABEL[role]})` : `Acknowledge (${ROLE_LABEL[role]})`}
            </Button>
          );
        })}
        {!resolving && (
          <Button
            variant="secondary"
            icon={<CircleCheck size={16} />}
            onClick={() => setResolving(true)}
            disabled={busy}
          >
            Resolve
          </Button>
        )}
        <Button variant="ghost" to={`/alerts/${encodeURIComponent(em.alertId)}`}>
          Open the alert
        </Button>
      </div>

      {resolving && (
        <form onSubmit={submit} className={styles.column} aria-label="Resolve this event">
          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>Outcome</legend>
            {OUTCOMES.map((o) => (
              <label key={o} className={styles.radio}>
                <input
                  type="radio"
                  name={`outcome-${em.id}`}
                  value={o}
                  checked={outcome === o}
                  onChange={() => setOutcome(o)}
                />
                {OUTCOME_LABEL[o]}
              </label>
            ))}
          </fieldset>
          <label className={styles.label} htmlFor={`note-${em.id}`}>
            Note (required)
          </label>
          <textarea
            id={`note-${em.id}`}
            className={styles.textarea}
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What was found, e.g. “Chest strap had come loose.”"
          />
          <div className={styles.row}>
            <Button type="submit" disabled={busy}>
              Resolve event
            </Button>
            <Button variant="ghost" onClick={() => setResolving(false)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div>
        <p className={styles.sectionLabel}>Timeline</p>
        <Timeline steps={em.timeline} />
      </div>
    </Card>
  );
}
