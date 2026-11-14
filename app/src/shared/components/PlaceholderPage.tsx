// Scaffold page used by every feature until it is built. Shows owners, the planned
// content, and a live call to one stub endpoint (proves the wiring works).
//   <PlaceholderPage title="Vitals" owners={OWNERS} endpoint="/readings?metric=heart_rate"
//                    plan={['Metric tabs', 'Trend over baseline band']} />
import type { ReactNode } from 'react';
import { useApi } from '../api/client';
import { Badge } from './Badge';
import { Card } from './Card';
import { PageHeader } from './PageHeader';
import { ErrorState, LoadingState } from './States';
import styles from './PlaceholderPage.module.css';

export interface PlaceholderPageProps {
  title: string;
  owners: string;
  plan: string[];
  /** Path under /api, e.g. "/sleep". */
  endpoint: string;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  note?: ReactNode;
  /** Living examples of shared components, shown above the plan. */
  children?: ReactNode;
}

/** Keep the JSON short: long arrays are cut to their first items. */
function preview(value: unknown, max = 4): unknown {
  if (Array.isArray(value)) {
    const head = value.slice(0, max).map((v) => preview(v, max));
    return value.length > max ? [...head, `… ${value.length - max} more`] : head;
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, preview(v, max)]));
  }
  return value;
}

export function PlaceholderPage({ title, owners, plan, endpoint, eyebrow, actions, note, children }: PlaceholderPageProps) {
  const { data, error, loading, reload } = useApi<unknown>(endpoint);
  return (
    <>
      <PageHeader eyebrow={eyebrow ?? 'Placeholder · scaffold'} title={title} actions={actions} />
      {children}
      <Card
        title="What this page will contain"
        subtitle={
          <>
            Owners: <strong className={styles.owners}>{owners}</strong>
          </>
        }
        actions={<Badge variant="neutral">Scaffold</Badge>}
      >
        {note && <p className={styles.note}>{note}</p>}
        <ul className={styles.plan}>
          {plan.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </Card>
      <Card title="Live API" subtitle={<code className={styles.endpoint}>GET /api{endpoint}</code>}>
        {loading && !data ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : (
          <pre className={styles.pre} tabIndex={0} aria-label={`Response of GET /api${endpoint}`}>
            {JSON.stringify(preview(data), null, 2)}
          </pre>
        )}
      </Card>
    </>
  );
}
