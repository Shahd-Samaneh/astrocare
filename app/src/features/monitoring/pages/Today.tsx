// Today (placeholder). Already uses the real shared components as a living example:
// AlertBanner with the seeded alert, VitalCards incl. one stale and one missing.
import { useApi } from '../../../shared/api/client';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import { AlertBanner, PlaceholderPage, SectionHeader, VitalCard } from '../../../shared/components';
import type { Alert, LatestReading, Metric } from '../../../shared/types/contracts';
import { METRIC_LABELS } from '../../../shared/utils/format';
import { OWNERS } from '../owners';
import styles from './Today.module.css';

const SHOWN: Metric[] = ['heart_rate', 'spo2', 'skin_temp', 'bp_sys'];

export default function Today() {
  const { status } = useAppStatus();
  const alerts = useApi<Alert[]>('/alerts?status=new');
  const latest = useApi<LatestReading[]>('/readings/latest');
  const weekday = new Date().toLocaleDateString('en-US', { weekday: 'long' });
  const byMetric = new Map(latest.data?.map((l) => [l.metric, l]));
  const dia = byMetric.get('bp_dia')?.reading;
  const firstAlert = alerts.data?.[0];

  return (
    <PlaceholderPage
      title="Today"
      eyebrow={status ? `Mission day ${status.missionDay} · ${weekday}` : weekday}
      owners={OWNERS}
      endpoint="/today/plan"
      plan={['Vital cards', 'Cabin conditions', 'The alert banner', "Today's plan", 'The sleep summary']}
    >
      {firstAlert && <AlertBanner alert={firstAlert} actionLabel="Review" actionTo={`/alerts/${firstAlert.id}`} />}

      <SectionHeader title="Vital signs" description="Latest value per metric (example of VitalCard states)" />
      <div className={styles.grid}>
        {SHOWN.map((m) => {
          const l = byMetric.get(m);
          if (!l) return null;
          const isBp = m === 'bp_sys';
          const value = l.reading ? (isBp && dia ? `${l.reading.value}/${dia.value}` : l.reading.value) : null;
          return (
            <VitalCard
              key={m}
              label={isBp ? 'Blood pressure' : METRIC_LABELS[m]}
              value={value}
              unit={l.reading?.unit}
              ts={l.reading?.ts}
              quality={l.quality}
              source={l.reading?.source}
              sensorName={l.sensorName}
              sensorStatus={l.sensorStatus}
              manualTo="/vitals"
            />
          );
        })}
      </div>
    </PlaceholderPage>
  );
}
