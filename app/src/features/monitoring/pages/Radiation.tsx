/** Radiation: cumulative dose estimate against the NASA career limit.
 * Every number comes from GET /radiation/estimate (mission day × MSL RAD cruise rate, limit from
 * config/thresholds.yaml). No dosimeter is connected, so the page always says "estimate".
 */
import { Card, ErrorState, LoadingState, PageHeader, SimulatedBadge } from '../../../shared/components';
import { useApi } from '../../../shared/api/client';
import type { RadiationEstimate } from '../../../shared/types/contracts';
import styles from './Radiation.module.css';

export default function Radiation() {
  const { data: est, error, loading, reload } = useApi<RadiationEstimate>('/radiation/estimate', { refreshMs: 60_000 });

  return (
    <>
      <PageHeader eyebrow="Space medicine" title="Radiation" />
      {loading && !est ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : est ? (
        <Card
          title="Cumulative dose (estimate)"
          subtitle={est.label}
          actions={<SimulatedBadge source={est.source} />}
        >
          <p className={styles.note} role="note">{est.note}</p>
          {est.available && est.cumulativeMsv != null && est.careerLimitMsv != null && est.pctOfLimit != null ? (
            <>
              <p className={styles.value}>
                <strong>{est.cumulativeMsv} mSv</strong>
                <span>
                  {est.pctOfLimit}% of the {est.careerLimitMsv} mSv career limit · {est.withinLimit ? 'within limit' : 'at or above career limit'}
                </span>
              </p>
              <div
                className={styles.bar}
                role="meter"
                aria-label="Estimated cumulative dose against the career limit"
                aria-valuemin={0}
                aria-valuemax={est.careerLimitMsv}
                aria-valuenow={Math.min(est.cumulativeMsv, est.careerLimitMsv)}
                aria-valuetext={`${est.cumulativeMsv} of ${est.careerLimitMsv} mSv (estimate)`}
              >
                <span className={styles.fill} style={{ width: `${Math.min(est.pctOfLimit, 100)}%` }} />
              </div>
              <div className={styles.scale} aria-hidden="true">
                <span>0 mSv</span>
                <span>{est.careerLimitMsv} mSv</span>
              </div>
              <p className={styles.muted}>
                Mission day {est.missionDay} × {est.rateMsvPerDay} mSv/day. {est.scopeNote}
              </p>
              <ul className={styles.sources}>
                <li><strong>Rate {est.rateMsvPerDay} mSv/day</strong> (simulated estimate): {est.rateSource}</li>
                <li><strong>Career limit {est.careerLimitMsv} mSv</strong>: {est.limitSource}</li>
              </ul>
            </>
          ) : (
            <p className={styles.muted}>No estimate: the rate or the career limit has no sourced value in thresholds.yaml.</p>
          )}
          <p className={styles.comparison}>
            {est.comparison}. <span className={styles.muted}>Source: {est.comparisonSource}. Not this mission's value.</span>
          </p>
        </Card>
      ) : null}
    </>
  );
}
