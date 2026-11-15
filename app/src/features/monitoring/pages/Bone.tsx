import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useApi } from '../../../shared/api/client';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import { Card } from '../../../shared/components';
import type { ExerciseItem } from '../../daily/types.log';
import styles from './Bone.module.css';

interface BoneEstimate {
  minimum: number;
  maximum: number;
  unit: string;
  source: string;
  reference: string;
}

export default function Bone() {
  const { status } = useAppStatus();
  const { data: plan, error, loading } = useApi<ExerciseItem[]>('/exercise/plan');
  const { data: estimate, error: estimateError, loading: estimateLoading } = useApi<BoneEstimate>('/bone-risk-estimate');
  const day = status?.missionDay;
  const week = (plan ?? []).filter((item) => day !== undefined && item.day <= day && item.day > day - 7);
  const done = week.filter((item) => item.log?.status === 'done').length;
  const partial = week.filter((item) => item.log?.status === 'partial').length;
  const skipped = week.filter((item) => item.log?.status === 'skipped').length;
  const unlogged = week.filter((item) => !item.log).length;
  const months = day === undefined ? undefined : day / 30;
  const lower = estimate && months !== undefined ? estimate.minimum * months : undefined;
  const upper = estimate && months !== undefined ? estimate.maximum * months : undefined;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link to="/" className={styles.back}><ArrowLeft size={16} aria-hidden /> Today</Link>
          <p className={styles.eyebrow}>SPACE MEDICINE · MISSION DAY {day ?? '—'}</p>
          <h1>Bone &amp; muscle</h1>
          <p className={styles.description}>Exercise adherence and NASA’s reported bone-density change in microgravity.</p>
        </div>
        <Link to="/daily#exercise" className={styles.action}>Open exercise <ArrowRight size={16} aria-hidden /></Link>
      </header>

      <Card title="Exercise adherence" subtitle="Last 7 mission days · from the exercise plan and its latest logs">
        {error && <p role="alert" className={styles.error}>Could not load exercise log: {error.message}</p>}
        {loading && !plan ? <p className={styles.muted}>Loading exercise log…</p> : week.length === 0 ? (
          <p className={styles.muted}>No planned exercise sessions in this period.</p>
        ) : (
          <dl className={styles.counts}>
            <div><dt>Planned</dt><dd>{week.length}</dd></div>
            <div><dt>Done</dt><dd>{done}</dd></div>
            <div><dt>Partial</dt><dd>{partial}</dd></div>
            <div><dt>Skipped</dt><dd>{skipped}</dd></div>
            <div><dt>Not logged</dt><dd>{unlogged}</dd></div>
          </dl>
        )}
      </Card>

      <Card
        title="Illustrative bone-density estimate"
        subtitle={estimate
          ? `Without exercise, astronauts can lose about ${estimate.minimum}–${estimate.maximum}% bone density per month (NASA)`
          : 'NASA-reported monthly bone-density change; rate unavailable until sourced thresholds load.'}
      >
        {estimateError && <p role="alert" className={styles.error}>Could not load sourced estimate: {estimateError.message}</p>}
        {estimateLoading && !estimate ? <p className={styles.muted}>Loading estimate…</p> : estimate && day !== undefined && lower !== undefined && upper !== undefined && (
          <p className={styles.estimate}>Mission day {day} ≈ {(day / 30).toFixed(1)} months in flight; illustrative range: <strong>{lower.toFixed(1)}–{upper.toFixed(1)}%</strong></p>
        )}
        <p className={styles.caution}>Illustrative, not a measurement — bone density needs a DEXA scan on Earth.</p>
        <p className={styles.source}>Source: NASA, Risk of Spaceflight-Induced Bone Changes · references/nasa-bone-risk.txt · {estimate?.source}</p>
      </Card>
    </main>
  );
}
