// Sleep section of the Daily log: 7-night chart, last night + self-rating, manual entry, NasaBasis.
import { useState } from 'react';
import { Badge, Card, EmptyState, ErrorState, LoadingState, SectionHeader, SimulatedBadge } from '../../../shared/components';
import { errorText, logApi, type QueryState } from '../api.log';
import type { SleepSummary } from '../types.log';
import { ManualSleepForm } from './ManualSleepForm';
import { NasaBasis } from '../common/NasaBasis';
import { SleepChart } from './SleepChart';
import styles from './SleepSection.module.css';

const RATING_WORDS = ['Very poor', 'Poor', 'Okay', 'Good', 'Very good'];

export function SleepSection({ query, onChanged }: { query: QueryState<SleepSummary>; onChanged: () => void }) {
  const { data, error, loading, reload } = query;
  const [rateError, setRateError] = useState<string>();
  const [saving, setSaving] = useState(false);

  async function rate(id: string, value: number) {
    setSaving(true);
    setRateError(undefined);
    try {
      await logApi.rateSleep(id, value);
      reload();
      onChanged();
    } catch (e) {
      setRateError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  function saved() {
    reload();
    onChanged();
  }

  let body;
  if (loading && !data) body = <LoadingState label="Loading sleep…" />;
  else if (error && !data) body = <ErrorState message={error.message} onRetry={reload} />;
  else if (!data || data.nights.length === 0) {
    body = <EmptyState title="No sleep logged yet" description="Add last night's sleep below. The chart appears after your first entry." />;
  } else {
    const last = data.lastNight;
    const avg = data.personalAvgHours;
    body = (
      <>
        <Card
          title="Last 7 nights"
          subtitle="Hours of sleep. Highlighted bars are shorter than the short-sleep threshold."
          actions={<SimulatedBadge />}
        >
          <SleepChart summary={data} />
        </Card>

        {last && (
          <Card title="Last night" subtitle={`Mission day ${last.missionDay}`}>
            <div className={styles.facts}>
              <div>
                <p className={styles.big}>{last.hours} h</p>
                <p className={styles.factLabel}>
                  slept{avg !== null ? `, your average is ${avg} h` : ''}
                  {last.short && <> <Badge variant="review">Short night</Badge></>}
                </p>
              </div>
              <div>
                <p className={styles.big}>{last.awakenings}</p>
                <p className={styles.factLabel}>awakenings</p>
              </div>
            </div>
            <div role="group" aria-labelledby="rating-label">
              <p id="rating-label" className={styles.ratingLabel}>How rested do you feel? (1 to 5)</p>
              <div className={styles.rating}>
                {[1, 2, 3, 4, 5].map((v) => (
                  <button
                    key={v}
                    type="button"
                    className={styles.ratingBtn}
                    aria-pressed={last.selfQuality === v}
                    aria-label={`${v} out of 5, ${RATING_WORDS[v - 1]}`}
                    disabled={saving}
                    onClick={() => rate(last.id, v)}
                  >
                    <span className={styles.ratingNum}>{v}</span>
                    <span className={styles.ratingWord}>{RATING_WORDS[v - 1]}</span>
                  </button>
                ))}
              </div>
              {rateError && <p className={styles.err} role="alert">{rateError}</p>}
            </div>
          </Card>
        )}
      </>
    );
  }

  return (
    <section id="sleep" aria-label="Sleep" className={styles.anchor}>
      <SectionHeader title="Sleep" description="Your last nights next to your own average. A possible link to how you feel, not a diagnosis." />
      <div className={styles.stack}>
        {body}
        <ManualSleepForm onSaved={saved} />
        <NasaBasis
          ids={['nasa-hrp-sleep-risk', 'nasa-hrp-ongoing']}
          why="Short or irregular sleep can affect alertness and performance on long missions. We compare each night with your own average, and wrist-worn sleep monitoring is one way space agencies study this."
        />
      </div>
    </section>
  );
}
