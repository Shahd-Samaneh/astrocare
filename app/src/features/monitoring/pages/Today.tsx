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
  CheckCircle2,
  Circle,
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
import type {
  Alert,
  CabinMetric,
  CabinReading,
  CognitiveTest,
  ExercisePlan,
  LatestReading,
  Metric,
  Profile,
  Reading,
  SleepSession,
} from '../../../shared/types/contracts';
import { METRIC_LABELS } from '../../../shared/utils/format';
import styles from './Today.module.css';

type TodayPlan = {
  missionDay: number;
  exercise: ExercisePlan | null;
  exerciseLogged: boolean;
  attentionCheckDone: boolean;
  checkInDone: boolean;
  lastSleep: SleepSession | null;
};

const VITALS: Metric[] = ['heart_rate', 'spo2', 'skin_temp', 'bp_sys'];
const CABIN_METRICS: { metric: CabinMetric; label: string }[] = [
  { metric: 'co2', label: 'CO₂' },
  { metric: 'cabin_temp', label: 'Temperature' },
  { metric: 'noise', label: 'Noise' },
  { metric: 'humidity', label: 'Humidity' },
];

function duration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h} h ${m} m` : `${m} m`;
}

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

function StatusLine({ label, done, to }: { label: string; done: boolean; to: string }) {
  return (
    <Link className={styles.task} to={to}>
      {done ? <CheckCircle2 size={20} aria-label="Done" /> : <Circle size={20} aria-label="Not completed" />}
      <span>{label}</span>
      <span className={styles.taskStatus}>{done ? 'Done' : 'Open'}</span>
      <ArrowRight size={15} aria-hidden />
    </Link>
  );
}

export default function Today() {
  const { status } = useAppStatus();
  const { data: alerts, error: alertError, loading: alertsLoading, reload: reloadAlerts } =
    useApi<Alert[]>('/alerts?status=new', { refreshMs: 30_000 });
  const { data: latest, error: latestError, loading: latestLoading, reload: reloadLatest } =
    useApi<LatestReading[]>('/readings/latest', { refreshMs: 30_000 });
  const { data: readings } = useApi<Reading[]>('/readings?hours=24&limit=2000');
  const { data: cabin, error: cabinError, loading: cabinLoading } = useApi<CabinReading[]>('/cabin?hours=24');
  const { data: todayPlan, error: planError, loading: planLoading } = useApi<TodayPlan>('/today/plan');
  const { data: sleep, loading: sleepLoading } = useApi<SleepSession[]>('/sleep?nights=7');
  const { data: profile } = useApi<Profile>('/profile');
  const { data: tests } = useApi<CognitiveTest[]>('/tests?n=1');

  const [manualOpen, setManualOpen] = useState(false);
  const [systolic, setSystolic] = useState('');
  const [diastolic, setDiastolic] = useState('');
  const [saving, setSaving] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState(false);

  const byMetric = new Map<Metric, LatestReading>((latest ?? []).map((x) => [x.metric, x]));
  const heart = byMetric.get('heart_rate');
  const oxygen = byMetric.get('spo2');
  const temperature = byMetric.get('skin_temp');
  const dia = byMetric.get('bp_dia')?.reading;
  const lastSleep = todayPlan?.lastSleep ?? (sleep && sleep.length > 0 ? sleep[sleep.length - 1] : null);
  const latestTest = tests && tests.length > 0 ? tests[tests.length - 1] : undefined;
  const sleepBaselineHours = profile?.baseline.sleep_hours?.mean;
  const maxSleepMinutes = Math.max(1, ...(sleep?.map((s) => s.durationMin) ?? []));
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
          <div className={styles.systemGrid}>
            <div className={styles.systemTile}>
              <HeartPulse size={23} aria-hidden />
              <span><strong>Cardiovascular</strong><small>{heart?.reading ? `Heart rate: ${formatMetric(heart.reading.value, heart.reading.unit)} · ${heart.quality}` : 'No current heart rate data'}</small></span>
            </div>
            <div className={styles.systemTile}>
              <Wind size={23} aria-hidden />
              <span><strong>Respiratory & O₂</strong><small>{oxygen?.reading ? `SpO₂: ${formatMetric(oxygen.reading.value, oxygen.reading.unit)} · ${oxygen.quality}` : 'No current oxygen data'}</small></span>
            </div>
            <Link className={styles.systemTile} to="/daily">
              <Moon size={23} aria-hidden />
              <span><strong>Sleep & circadian</strong><small>{lastSleep ? `Last sleep: ${duration(lastSleep.durationMin)}` : 'No sleep data yet'}</small></span>
            </Link>
            <Link className={styles.systemTile} to="/attention">
              <Brain size={23} aria-hidden />
              <span><strong>Cognition & behaviour</strong><small>{latestTest ? `Last attention median: ${Math.round(latestTest.medianMs)} ms` : 'No attention result yet'}</small></span>
            </Link>
            <Link className={styles.systemTile} to="/bone">
              <Bone size={23} aria-hidden />
              <span><strong>Bone & muscle</strong><small>Open module <ArrowRight size={12} aria-hidden /></small></span>
            </Link>
            <Link className={styles.systemTile} to="/radiation">
              <Radiation size={23} aria-hidden />
              <span><strong>Radiation exposure</strong><small>Open module <ArrowRight size={12} aria-hidden /></small></span>
            </Link>
            <div className={styles.systemTile}>
              <Eye size={23} aria-hidden />
              <span><strong>Vision & fluid shift</strong><small>No connected measurements</small></span>
            </div>
            <div className={styles.systemTile}>
              <Thermometer size={23} aria-hidden />
              <span><strong>Thermoregulation</strong><small>{temperature ? `Skin temperature: ${temperature.quality}` : 'No temperature data yet'}</small></span>
            </div>
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
        <Card title="Cabin conditions" subtitle="Latest local cabin-sensor readings · context, not a confirmed cause">
          <div id="cabin-title" className={styles.visuallyHidden}>Cabin conditions</div>
          {cabinError && <p className={styles.error} role="alert">Could not load cabin readings: {cabinError.message}</p>}
          {cabinLoading && !cabin && <p className={styles.muted}>Loading cabin readings…</p>}
          <div className={styles.cabinGrid}>
            {CABIN_METRICS.map(({ metric, label }) => {
              const entries = cabin?.filter((x) => x.metric === metric);
              const entry = entries && entries.length > 0 ? entries[entries.length - 1] : undefined;
              return (
                <div className={styles.cabinTile} key={metric}>
                  <span className={styles.cabinLabel}>{label}</span>
                  <strong>{entry ? formatMetric(entry.value, entry.unit) : '—'}</strong>
                  <span className={styles.cabinMeta}>{entry ? `Recorded ${new Date(entry.ts).toLocaleString()}` : 'No data available'}</span>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <div className={styles.lowerGrid}>
        <Card title="Today's plan" subtitle="Based on local daily activity records">
          {planError && <p className={styles.error} role="alert">Could not load today's plan: {planError.message}</p>}
          {planLoading && !todayPlan && <p className={styles.muted}>Loading today's plan…</p>}
          {todayPlan && (
            <div className={styles.taskList}>
              <StatusLine label="Daily check-in" done={todayPlan.checkInDone} to="/daily" />
              <StatusLine label="Attention check" done={todayPlan.attentionCheckDone} to="/attention" />
              {todayPlan.exercise ? (
                <StatusLine label={`${todayPlan.exercise.type} · ${duration(todayPlan.exercise.durationMin)}`} done={todayPlan.exerciseLogged} to="/daily" />
              ) : (
                <p className={styles.muted}>No exercise scheduled for this mission day.</p>
              )}
            </div>
          )}
        </Card>
        <div className={styles.sleepColumn}>
          <Card title="Last recorded sleep" actions={<Link to="/daily" className={styles.inlineLink}>Details <ArrowRight size={15} aria-hidden /></Link>}>
            {sleepLoading && !lastSleep && <p className={styles.muted}>Loading sleep history…</p>}
            {lastSleep ? (
              <>
                <div className={styles.sleepValue}>
                  <strong>{duration(lastSleep.durationMin)}</strong>
                  {typeof sleepBaselineHours === 'number' && (
                    <span>Personal baseline: {duration(Math.round(sleepBaselineHours * 60))}</span>
                  )}
                </div>
                {sleep && sleep.length > 0 && (
                  <div className={styles.sleepBars} role="group" aria-label="Recent sleep durations">
                    {sleep.slice(-7).map((s) => (
                      <div className={styles.sleepBarColumn} key={s.id} title={duration(s.durationMin)}>
                        <span style={{ height: `${Math.max(6, Math.min(100, (s.durationMin / maxSleepMinutes) * 100))}%` }} aria-label={duration(s.durationMin)} />
                      </div>
                    ))}
                  </div>
                )}
                <p className={styles.muted}>{lastSleep.awakenings} wake-up(s) · {lastSleep.selfQuality != null ? `Self-rated quality ${lastSleep.selfQuality}/5` : 'Sleep quality not rated'}</p>
              </>
            ) : (!sleepLoading && <p className={styles.muted}>No sleep sessions recorded yet.</p>)}
          </Card>
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
