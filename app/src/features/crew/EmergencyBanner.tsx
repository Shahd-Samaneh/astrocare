// Owner: Shahd. Persistent red banner on every page while an escalated R-LOC-01 emergency is
// not acknowledged by the CMO or the Commander. Not dismissible; links to /crew.
import { Siren } from 'lucide-react';
import { Button } from '../../shared/components';
import { timeText, unacknowledged } from './crewState';
import { useCrewFeed } from './crewFeed';
import styles from './Crew.module.css';

export function EmergencyBanner() {
  const items = unacknowledged(useCrewFeed().data);
  return (
    <div role="alert" aria-live="assertive">
      {items.map((em) => (
        <div key={em.id} className={styles.banner}>
          <Siren className={styles.bannerIcon} size={24} aria-hidden />
          <div className={styles.bannerText}>
            <strong className={styles.bannerTitle}>
              Emergency: possible loss of consciousness, {em.crewName}
            </strong>
            <span className={styles.bannerSub}>
              No response to “Are you OK?” · escalated {timeText(em.escalatedTs)} · not acknowledged
              yet
            </span>
          </div>
          <Button variant="warn" to="/crew">
            Open Crew alerts
          </Button>
        </div>
      ))}
    </div>
  );
}
