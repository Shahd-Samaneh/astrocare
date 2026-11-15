/** AstroCare Today dashboard — Haya's monitoring frontend.
 * All displayed measurements and mission information come from local APIs.
 * The shared contracts, shared components, and backend are intentionally untouched.
 */
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Bone,
  Brain,
  Eye,
  HeartPulse,
  Moon,
  Radiation,
  Thermometer,
  Wind,
} from 'lucide-react';
import { api, useApi } from '../../../shared/api/client';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import { AlertBanner, Card, VitalCard } from '../../../shared/components';
import { SleepSummaryCard, TodayPlanCard } from '../../daily';
import type {
  Alert,
  CabinMetric,
  CabinLatest,
  BodySystem,
  LatestReading,
  Metric,
  Profile,
  Reading,
} from '../../../shared/types/contracts';
import { METRIC_LABELS } from '../../../shared/utils/format';
import styles from './Today.module.css';

const VITALS: Metric[] = ['heart_rate', 'spo2', 'skin_temp', 'bp_sys'];
const CABIN_METRICS: { metric: CabinMetric; label: string }[] = [
  { metric: 'co2', label: 'CO₂' },
  { metric: 'cabin_temp', label: 'Temperature' },
  { metric: 'noise', label: 'Noise' },
  { metric: 'humidity', label: 'Humidity' },
];

/** Presentation only: status and explanation come exclusively from GET /body-systems. */
const BODY_SYSTEM_TILES = [
  { id: 'cardiovascular', label: 'Cardiovascular', Icon: HeartPulse },
  { id: 'respiratory', label: 'Respiratory & O₂', Icon: Wind },
  { id: 'sleep', label: 'Sleep & circadian', Icon: Moon },
  { id: 'cognition', label: 'Cognition & behaviour', Icon: Brain },
  { id: 'bone_muscle', label: 'Bone & muscle', Icon: Bone },
  { id: 'radiation', label: 'Radiation exposure', Icon: Radiation },
  { id: 'vision', label: 'Vision & fluid shift', Icon: Eye },
  { id: 'thermoregulation', label: 'Thermoregulation', Icon: Thermometer },
] as const;

const BODY_STATUS_LABELS: Record<BodySystem['status'], string> = {
  stable: 'Stable',
  review: 'Review',
  no_data: 'No data',
};
const CABIN_STATUS_LABELS: Record<CabinLatest['status'], string> = {
  usual: 'Usual',
  above_usual: 'Above usual',
  below_usual: 'Below usual',
  missing: 'No data',
};


function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
}

function formatMetric(value: number, unit: string): string {
  return `${Number(value.toFixed(1))} ${unit}`.trim();
}

/** Small plot built from actual readings; no sample values are inserted. */
function MiniTrend({ metric, readings }: { metric: Metric; readings: Reading[] }) {
  const values = readings
    .filter((r) => r.metric === metric && Number.isFinite(r.value))
    .slice(-32)
    .map((r) => r.value);
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const points = values
    .map((value, i) => `${(i / (values.length - 1)) * 170},${36 - ((value - min) / range) * 28}`)
    .join(' ');
  return (
    <svg className={styles.miniTrend} viewBox="0 0 170 44" role="img" aria-label={`Recent ${METRIC_LABELS[metric]} trend`}>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Today() {
  const { status } = useAppStatus();
  const { data: alerts, error: alertError, loading: alertsLoading, reload: reloadAlerts } =
    useApi<Alert[]>('/alerts?status=new', { refreshMs: 30_000 });
  const { data: latest, error: latestError, loading: latestLoading, reload: reloadLatest } =
    useApi<LatestReading[]>('/readings/latest', { refreshMs: 30_000 });
  const { data: readings } = useApi<Reading[]>('/readings?hours=24&limit=2000');
  const { data: cabin, error: cabinError, loading: cabinLoading } =
    useApi<CabinLatest[]>('/cabin/latest', { refreshMs: 30_000 });
  const { data: bodySystems, error: systemsError, loading: systemsLoading } =
    useApi<BodySystem[]>('/body-systems', { refreshMs: 30_000 });
  const { data: profile } = useApi<Profile>('/profile');

  const [manualOpen, setManualOpen] = useState(false);
  const [systolic, setSystolic] = useState('');
  const [diastolic, setDiastolic] = useState('');
  const [saving, setSaving] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState(false);

  const byMetric = new Map<Metric, LatestReading>((latest ?? []).map((x) => [x.metric, x]));
  const dia = byMetric.get('bp_dia')?.reading;
  const mostRelevantAlert =
    alerts?.find((a) => a.ruleId === 'R-FAT-01') ??
    alerts?.find((a) => a.level === 'urgent') ??
    alerts?.find((a) => a.level === 'review') ??
    alerts?.[0];

  async function submitPressure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setManualError(null);
    const sys = Number(systolic);
    const diaValue = Number(diastolic);
    if (!Number.isFinite(sys) || !Number.isFinite(diaValue) || sys <= 0 || diaValue <= 0 || sys <= diaValue) {
      setManualError('Enter positive values with systolic greater than diastolic.');
      return;
    }
    setSaving(true);
    try {
      await api.post<Reading>('/readings/manual', { metric: 'bp_sys', value: sys });
      await api.post<Reading>('/readings/manual', { metric: 'bp_dia', value: diaValue });
      setManualOpen(false);
      setSystolic('');
      setDiastolic('');
      setManualSuccess(true);
      reloadLatest();
      reloadAlerts();
    } catch (error) {
      setManualError(`Could not save both readings: ${error instanceof Error ? error.message : 'Unknown error'}. Check the readings before retrying.`);
    } finally {
      setSaving(false);
    }
  }

  const weekday = new Date().toLocaleDateString('en-US', { weekday: 'long' });

  return (
    <div className={styles.page}>
      <div className={styles.welcome}>
        <div>
          <p className={styles.eyebrow}>MISSION DAY {status?.missionDay ?? '—'} · {weekday.toUpperCase()}</p>
          <h1>{greeting()}, {status?.crewName || profile?.name || 'Crew member'}</h1>
        </div>
        <div className={styles.actions}>
          <Link className={styles.secondaryAction} to="/daily">Open daily log</Link>
          <Link className={styles.primaryAction} to="/relax">Start relaxation</Link>
        </div>
      </div>

      {alertError ? (
        <p className={styles.error} role="alert">Could not load alerts: {alertError.message}</p>
      ) : mostRelevantAlert ? (
        <AlertBanner alert={mostRelevantAlert} actionLabel="Review alert" actionTo={`/alerts/${mostRelevantAlert.id}`} />
      ) : (
        <div className={styles.quietStatus} role="status">
          {alertsLoading ? 'Loading alerts…' : 'No new alerts in the local system.'}
        </div>
      )}

      <section className={styles.overview} aria-labelledby="systems-title">
        <div className={styles.crewIllustration} aria-hidden="true">
          <div className={styles.helmet}><span /></div>
          <div className={styles.suit}><span>+</span></div>
          <div className={styles.leftArm} />
          <div className={styles.rightArm} />
          <div className={styles.leftLeg} />
          <div className={styles.rightLeg} />
          <span className={`${styles.pin} ${styles.pinOne}`}>1</span>
          <span className={`${styles.pin} ${styles.pinTwo}`}>2</span>
          <span className={`${styles.pin} ${styles.pinThree}`}>3</span>
          <span className={`${styles.pin} ${styles.pinFour}`}>4</span>
          <p>Illustrative sensor layout</p>
        </div>
        <div className={styles.overviewContent}>
          <p className={styles.kicker}>+ SPACE MEDICINE OVERVIEW</p>
          <h2 id="systems-title">Body systems affected by spaceflight</h2>
          {systemsError && <p className={styles.error} role="alert">Could not load body-system status: {systemsError.message}</p>}
          {systemsLoading && !bodySystems && <p className={styles.muted}>Loading body-system status…</p>}
          <div className={styles.systemGrid}>
            {BODY_SYSTEM_TILES.map(({ id, label, Icon }) => {
              // If the backend is unavailable, never infer a stable state from old vitals.
              const entry = systemsError ? undefined : bodySystems?.find((system) => system.id === id);
              const stateClass = entry?.status === 'stable' ? styles.systemStable
                : entry?.status === 'review' ? styles.systemReview : styles.systemNoData;
              const content = (
                <>
                  <Icon size={23} aria-hidden />
                  <span className={styles.systemDetails}>
                    <strong>{label}</strong>
                    <small>{entry?.text ?? (systemsLoading ? 'Loading…' : 'Status unavailable')}</small>
                    <span className={styles.systemStatus}>
                      {entry ? BODY_STATUS_LABELS[entry.status] : 'Unavailable'}
                    </span>
                  </span>
                  {entry?.alertId && <ArrowRight size={15} className={styles.systemArrow} aria-hidden />}
                </>
              );
              return entry?.alertId ? (
                <Link key={id} className={`${styles.systemTile} ${stateClass}`} to={`/alerts/${encodeURIComponent(entry.alertId)}`}>
                  {content}
                </Link>
              ) : (
                <div key={id} className={`${styles.systemTile} ${stateClass}`}>
                  {content}
                </div>
              );
            })}
          </div>
          <p className={styles.caption}>Statuses reflect available simulated readings, not a medical diagnosis.</p>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="vitals-title">
        <div className={styles.sectionHead}>
          <div>
            <h2 id="vitals-title">Vitals <span>compared with your own baseline</span></h2>
          </div>
          <Link to="/vitals" className={styles.inlineLink}>View trends <ArrowRight size={16} aria-hidden /></Link>
        </div>
        {latestError && <p className={styles.error} role="alert">Could not load vital signs: {latestError.message}</p>}
        {latestLoading && !latest && <p className={styles.muted}>Loading vital signs…</p>}
        <div className={styles.vitalsGrid}>
          {VITALS.map((metric) => {
            const item = byMetric.get(metric);
            const isPressure = metric === 'bp_sys';
            const value = item?.reading
              ? isPressure && dia ? `${item.reading.value}/${dia.value}` : item.reading.value
              : null;
            return (
              <VitalCard
                key={metric}
                label={isPressure ? 'Blood pressure' : METRIC_LABELS[metric]}
                value={value}
                unit={isPressure && dia ? 'mmHg' : item?.reading?.unit}
                ts={item?.reading?.ts}
                quality={item?.quality ?? 'missing'}
                source={item?.reading?.source}
                sensorName={item?.sensorName}
                sensorStatus={item?.sensorStatus}
                sparkline={!isPressure && readings ? <MiniTrend metric={metric} readings={readings} /> : undefined}
                onEnterManually={isPressure ? () => { setManualOpen(true); setManualSuccess(false); } : undefined}
              />
            );
          })}
        </div>
        {manualSuccess && <p className={styles.success} role="status">Blood-pressure readings saved locally.</p>}
        {manualOpen && (
          <form className={styles.manualForm} onSubmit={submitPressure}>
            <h3>Enter blood-pressure reading</h3>
            <div className={styles.manualFields}>
              <label>Systolic (mmHg)<input type="number" min="1" step="1" required value={systolic} onChange={(e) => setSystolic(e.target.value)} /></label>
              <label>Diastolic (mmHg)<input type="number" min="1" step="1" required value={diastolic} onChange={(e) => setDiastolic(e.target.value)} /></label>
            </div>
            {manualError && <p className={styles.error} role="alert">{manualError}</p>}
            <div className={styles.actions}>
              <button type="submit" className={styles.primaryAction} disabled={saving}>{saving ? 'Saving…' : 'Save readings'}</button>
              <button type="button" className={styles.secondaryAction} onClick={() => { setManualOpen(false); setManualError(null); }}>Cancel</button>
            </div>
          </form>
        )}
      </section>

      <section className={styles.section} aria-labelledby="cabin-title">
        <Card title="Cabin conditions" subtitle="Latest cabin conditions · status from local monitoring service">
          <div id="cabin-title" className={styles.visuallyHidden}>Cabin conditions</div>
          {cabinError && <p className={styles.error} role="alert">Could not load cabin readings: {cabinError.message}</p>}
          {cabinLoading && !cabin && <p className={styles.muted}>Loading cabin readings…</p>}
          <div className={styles.cabinGrid}>
            {CABIN_METRICS.map(({ metric, label }) => {
              const entry = cabinError ? undefined : cabin?.find((x) => x.metric === metric);
              const statusText = cabinError ? 'Unavailable' : entry ? CABIN_STATUS_LABELS[entry.status] : cabinLoading ? 'Loading…' : 'No data';
              const statusClass = entry?.status === 'usual' ? styles.cabinUsual
                : entry?.status === 'above_usual' || entry?.status === 'below_usual' ? styles.cabinOutOfRange
                  : styles.cabinMissing;
              return (
                <div className={styles.cabinTile} key={metric}>
                  <span className={styles.cabinLabel}>{label}</span>
                  <strong>{entry?.value != null ? formatMetric(entry.value, entry.unit) : '—'}</strong>
                  <span className={`${styles.cabinStatus} ${statusClass}`}>{statusText}</span>
                  <span className={styles.cabinMeta}>
                    {entry?.ts ? `Recorded ${new Date(entry.ts).toLocaleString()}` : 'No recent reading timestamp'}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <div className={styles.lowerGrid}>
        {/* Daily pair's cards: fetch /api/today/plan and /api/sleep/summary themselves. */}
        <TodayPlanCard />
        <div className={styles.sleepColumn}>
          <SleepSummaryCard />
          <Link className={styles.assistantLink} to="/assistant">
            <Activity size={22} aria-hidden />
            <span><strong>Ask about your data</strong><small>Local assistant · on-device sources</small></span>
            <ArrowRight size={20} aria-hidden />
          </Link>
        </div>
      </div>
      <p className={styles.disclaimer}>Decision support only. AstroCare does not diagnose or prescribe treatment. Simulated readings are labeled by their source.</p>
    </div>
  );
}
