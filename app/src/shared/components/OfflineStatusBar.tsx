// Top header with mission + comms status. Reads AppStatus from AppStatusProvider (GET /api/status, 30 s).
//   <OfflineStatusBar />
// If the local backend is unreachable it shows "Local service offline" instead of crashing.
import { SatelliteDish, ServerOff, Wifi, WifiOff } from 'lucide-react';
import { useAppStatus } from '../api/AppStatusContext';
import { formatDuration, formatMet, relativeTime, useNow } from '../utils/format';
import styles from './OfflineStatusBar.module.css';

export function OfflineStatusBar() {
  const { status, error, receivedAt } = useAppStatus();
  const now = useNow(1000);

  if (!status) {
    return (
      <header className={styles.bar}>
        {error ? (
          <span className={`${styles.pill} ${styles.offline}`} role="status">
            <ServerOff size={14} aria-hidden /> Local service offline
          </span>
        ) : (
          <span className={styles.muted} role="status">
            Connecting to local service…
          </span>
        )}
      </header>
    );
  }

  const toWindow = (new Date(status.nextCommWindowTs).getTime() - now) / 1000;
  const met = formatMet(status.met, (now - receivedAt) / 1000);

  return (
    <header className={styles.bar}>
      <span className={styles.mission}>
        <SatelliteDish size={16} aria-hidden className={styles.signal} />
        <strong>{status.missionName}</strong>
        <span className={styles.muted}>· deep-space transit</span>
      </span>

      {status.localMode ? (
        <span className={`${styles.pill} ${styles.local}`}>
          <WifiOff size={14} aria-hidden /> Local mode · no Earth link
        </span>
      ) : (
        <span className={`${styles.pill} ${styles.link}`}>
          <Wifi size={14} aria-hidden /> Earth link available
        </span>
      )}

      <span className={styles.item}>
        Next comm window ≈{' '}
        <strong className="mono" aria-live="off">
          {toWindow > 0 ? formatDuration(toWindow) : 'open now'}
        </strong>
      </span>
      <span className={styles.item}>
        Signal delay <strong className="mono">{formatDuration(status.signalDelaySec)}</strong>
      </span>
      <span className={styles.item}>
        Last sync <strong>{relativeTime(status.lastSyncTs, now)}</strong>
      </span>
      <span className={styles.item}>
        Outbox{' '}
        <strong>
          {status.outboxCount} report{status.outboxCount === 1 ? '' : 's'}
        </strong>
      </span>

      {error && (
        <span className={`${styles.pill} ${styles.offline}`} role="status">
          <ServerOff size={14} aria-hidden /> Local service offline
        </span>
      )}

      <span className={styles.spacer} />

      {status.simulated && (
        <span className={styles.simulated} title="Values come from the simulator, not real sensors">
          SIMULATED DATA
        </span>
      )}

      <span className={`${styles.met} mono`} aria-label={`Mission elapsed time ${met}`}>
        MET {met}
      </span>

      <span className={styles.avatar} role="img" aria-label={status.crewName} title={status.crewName}>
        {status.crewInitials}
      </span>
    </header>
  );
}
