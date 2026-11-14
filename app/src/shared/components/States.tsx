// Loading / empty / error placeholders.
//   if (loading) return <LoadingState />;
//   if (error) return <ErrorState message={error.message} onRetry={reload} />;
//   if (!items.length) return <EmptyState title="No sessions yet" />;
import type { ReactNode } from 'react';
import { CircleAlert, Inbox, LoaderCircle } from 'lucide-react';
import { Button } from './Button';
import styles from './States.module.css';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className={styles.state} role="status" aria-live="polite">
      <LoaderCircle className={styles.spin} size={22} aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className={styles.state}>
      <Inbox size={22} aria-hidden />
      <strong className={styles.title}>{title}</strong>
      {description && <p className={styles.desc}>{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className={`${styles.state} ${styles.error}`} role="alert">
      <CircleAlert size={22} aria-hidden />
      <strong className={styles.title}>Something went wrong</strong>
      {message && <p className={styles.desc}>{message}</p>}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
