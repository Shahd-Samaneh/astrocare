// Small uppercase status chip for data quality or alert level.
//   <Badge variant="stale" />            -> "STALE"
//   <Badge variant="review">Review</Badge>
import type { ReactNode } from 'react';
import type { AlertLevel, Quality } from '../types/contracts';
import styles from './Badge.module.css';

export type BadgeVariant = Quality | AlertLevel | 'neutral' | 'pink';

const DEFAULT_LABEL: Record<BadgeVariant, string> = {
  good: 'Good',
  low: 'Low quality',
  stale: 'Stale',
  missing: 'Missing',
  info: 'Info',
  review: 'Review',
  urgent: 'Urgent',
  neutral: '',
  pink: '',
};

export interface BadgeProps {
  variant: BadgeVariant;
  children?: ReactNode;
  title?: string;
}

export function Badge({ variant, children, title }: BadgeProps) {
  return (
    <span className={`${styles.badge} ${styles[variant]}`} title={title}>
      {children ?? DEFAULT_LABEL[variant]}
    </span>
  );
}

/** Alias: same component, named for status use. */
export const StatusChip = Badge;
