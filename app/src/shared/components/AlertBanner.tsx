// Prominent banner for one alert.
//   <AlertBanner alert={alert} actionLabel="Review" actionTo={`/alerts/${alert.id}`} />
import { TriangleAlert } from 'lucide-react';
import type { Alert } from '../types/contracts';
import { Badge } from './Badge';
import { Button } from './Button';
import styles from './AlertBanner.module.css';

export interface AlertBannerProps {
  alert: Alert;
  actionLabel?: string;
  /** Route to open (renders a link) … */
  actionTo?: string;
  /** … or a click handler. */
  onAction?: () => void;
}

export function AlertBanner({ alert, actionLabel = 'Review', actionTo, onAction }: AlertBannerProps) {
  const n = alert.missing.length;
  return (
    <section className={styles.banner} role="region" aria-label={`Alert: ${alert.title}`}>
      <TriangleAlert className={styles.icon} size={24} aria-hidden />
      <div className={styles.body}>
        <div className={styles.titleRow}>
          <Badge variant={alert.level} />
          <strong className={styles.title}>{alert.title}</strong>
        </div>
        <p className={styles.sub}>
          Possible link, not a confirmed cause. {n} piece{n === 1 ? '' : 's'} of information{' '}
          {n === 1 ? 'is' : 'are'} missing.
        </p>
      </div>
      {actionTo ? (
        <Button variant="warn" to={actionTo}>
          {actionLabel}
        </Button>
      ) : (
        onAction && (
          <Button variant="warn" onClick={onAction}>
            {actionLabel}
          </Button>
        )
      )}
    </section>
  );
}
