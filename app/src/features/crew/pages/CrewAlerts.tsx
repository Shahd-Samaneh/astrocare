// Owner: Shahd. Crew alerts (/crew): the CMO and Commander view of R-LOC-01 events.
// Open Watches and emergencies first, then the history. "Simulate event (demo)" is shown only
// when config/app.yaml has demo: true. Experimental. Not a medical device.
import { FlaskConical } from 'lucide-react';
import { useState } from 'react';
import { ApiError } from '../../../shared/api/client';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '../../../shared/components';
import { EXPERIMENTAL_LABEL, OUTCOME_LABEL, simulateLoc } from '../api.crew';
import { EmergencyCard, Signals, Timeline } from '../EmergencyCard';
import { useCrewFeed } from '../crewFeed';
import { timeText } from '../crewState';
import styles from '../Crew.module.css';

export default function CrewAlerts() {
  const feed = useCrewFeed();
  const { status } = useAppStatus();
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState<string>();
  const data = feed.data;

  const simulate = async () => {
    setDemoBusy(true);
    setDemoError(undefined);
    try {
      await simulateLoc();
    } catch (e) {
      setDemoError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDemoBusy(false);
      feed.reload();
    }
  };

  const eyebrow = `Support · CMO and Commander${status ? ` · Mission day ${status.missionDay}` : ''}`;

  return (
    <>
      <PageHeader
        eyebrow={eyebrow}
        title="Crew alerts"
        actions={
          data?.demo && (
            <Button
              variant="secondary"
              icon={<FlaskConical size={16} />}
              onClick={() => void simulate()}
              disabled={demoBusy}
            >
              Simulate event (demo)
            </Button>
          )
        }
      />
      <div className={styles.column}>
        <p className={styles.note} role="note">
          {EXPERIMENTAL_LABEL} Possible loss of consciousness is flagged from sensor signals plus no
          response to “Are you OK?”. It is never a diagnosis.
          {data?.demo && ' “Simulate event (demo)” injects simulated readings.'}
        </p>
        {demoError && (
          <p className={styles.error} role="alert">
            Demo: {demoError}
          </p>
        )}

        {!data && feed.loading ? (
          <LoadingState />
        ) : !data && feed.error ? (
          <ErrorState message={feed.error.message} onRetry={feed.reload} />
        ) : data && data.open.length === 0 ? (
          <Card title="Open events">
            <EmptyState
              title="No open watch or emergency"
              description={`If R-LOC-01 fires, the crew member gets “Are you OK?” for ${data.responseSeconds} s before the CMO and the Commander are alerted here.`}
            />
          </Card>
        ) : (
          data?.open.map((em) => <EmergencyCard key={em.id} em={em} />)
        )}

        {data && (
          <Card title="History" subtitle="Resolved events, newest first">
            {data.history.length === 0 ? (
              <p className={styles.note}>No past events.</p>
            ) : (
              <ul className={styles.history}>
                {data.history.map((em) => (
                  <li key={em.id} className={styles.historyItem}>
                    <details>
                      <summary>
                        <time dateTime={em.detectedTs}>{timeText(em.detectedTs)}</time>
                        <span>{em.crewName}</span>
                        <Badge variant={em.escalatedTs ? 'urgent' : 'neutral'}>
                          {em.escalatedTs ? 'Escalated' : 'Watch only'}
                        </Badge>
                        <span>{em.outcome ? OUTCOME_LABEL[em.outcome] : '—'}</span>
                      </summary>
                      <div className={styles.historyBody}>
                        {em.note && <p className={styles.note}>Note: {em.note}</p>}
                        <Signals em={em} />
                        <Timeline steps={em.timeline} />
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
