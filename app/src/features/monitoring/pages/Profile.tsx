/** Crew profile: read-only view of local profile, personal baselines and sensors. */
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  HeartPulse,
  Pill,
  RefreshCw,
  Shield,
  Stethoscope,
  UserRound,
  WifiOff,
} from 'lucide-react';
import { useApi } from '../../../shared/api/client';
import type { BaselineKey, Metric, Profile as CrewProfile, Sensor, SensorStatus } from '../../../shared/types/contracts';
import styles from './Profile.module.css';

const BASELINE_LABELS: Record<BaselineKey, string> = {
  heart_rate: 'Heart rate',
  spo2: 'Oxygen saturation (SpO₂)',
  skin_temp: 'Skin temperature',
  bp_sys: 'Systolic blood pressure',
  bp_dia: 'Diastolic blood pressure',
  resp_rate: 'Respiratory rate',
  pvt_median_ms: 'Reaction time (median)',
  sleep_hours: 'Sleep duration',
};
const BASELINE_UNITS: Record<BaselineKey, string> = {
  heart_rate: 'bpm',
  spo2: '%',
  skin_temp: '°C',
  bp_sys: 'mmHg',
  bp_dia: 'mmHg',
  resp_rate: 'breaths/min',
  pvt_median_ms: 'ms',
  sleep_hours: 'h',
};
const METRIC_LABELS: Record<Metric, string> = {
  heart_rate: 'Heart rate', spo2: 'SpO₂', skin_temp: 'Skin temperature',
  bp_sys: 'BP (systolic)', bp_dia: 'BP (diastolic)', resp_rate: 'Respiratory rate',
};
const SENSOR_LABELS: Record<SensorStatus, string> = {
  connected: 'Reported connected', disconnected: 'Disconnected', low_battery: 'Low battery',
};

function number(value: number): string {
  if (!Number.isFinite(value)) return '—';
  return Number(value.toFixed(2)).toLocaleString();
}
function showDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
function wordsOrFallback(items: string[], emptyText: string, className: string) {
  return items.length ? <div className={className}>{items.map((item, i) => <span key={`${item}-${i}`}>{item}</span>)}</div>
    : <p className={styles.emptyValue}>{emptyText}</p>;
}

export default function Profile() {
  const profile = useApi<CrewProfile>('/profile');
  const sensors = useApi<Sensor[]>('/sensors');
  const person = profile.data;
  const sensorList = sensors.data ?? [];
  const connected = sensorList.filter((sensor) => sensor.status === 'connected').length;
  const needsAttention = sensorList.filter((sensor) => sensor.status !== 'connected').length;
  const baselines = Object.entries(person?.baseline ?? {}).flatMap(([key, value]) =>
    value ? [{ key: key as BaselineKey, mean: value.mean, sd: value.sd, n: value.n }] : []);
  const initials = person?.name?.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase() || 'C2';
  const reload = () => { profile.reload(); sensors.reload(); };

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link className={styles.back} to="/"><ArrowLeft size={16} /> Today dashboard</Link>
          <p className={styles.eyebrow}>MISSION RECORD · PERSONAL BASELINE</p>
          <h1>Crew profile</h1>
          <p className={styles.description}>Review the locally stored crew record, personal ranges, and sensor connections.</p>
        </div>
        <button type="button" className={styles.button} disabled={profile.loading || sensors.loading} onClick={reload}>
          <RefreshCw size={16} /> Refresh profile
        </button>
      </header>

      {profile.loading && !person ? (
        <div className={styles.panel} role="status">Loading crew profile from this device…</div>
      ) : profile.error ? (
        <div className={styles.failure} role="alert">Crew profile unavailable: {profile.error.message}. <button type="button" onClick={profile.reload}>Try again</button></div>
      ) : !person ? (
        <div className={styles.panel}>No crew profile has been recorded.</div>
      ) : (
        <>
          <section className={styles.hero} aria-labelledby="crew-name">
            <div className={styles.avatar} aria-hidden="true">{initials}</div>
            <div className={styles.identity}>
              <span className={styles.label}>CURRENT CREW MEMBER</span>
              <h2 id="crew-name">{person.name}</h2>
              <span className={styles.crewId}><UserRound size={14} /> Crew ID: {person.id}</span>
              <span className={styles.crewNote}>Local profile record · For mission decision support</span>
            </div>
            <div className={styles.day}><CalendarDays size={20} /><span>MISSION DAY</span><strong>{person.missionDay}</strong></div>
          </section>

          <section className={styles.stats} aria-label="Crew profile summary">
            <div className={styles.stat}><span><HeartPulse size={17}/> Personal baselines</span><strong>{baselines.length}</strong><small>Recorded reference metrics</small></div>
            <div className={styles.stat}><span><Shield size={17}/> Allergies recorded</span><strong>{person.allergies.length}</strong><small>Check against listed resources</small></div>
            <div className={styles.stat}><span><Pill size={17}/> Current medications</span><strong>{person.currentMeds.length}</strong><small>Profile record only</small></div>
            <div className={styles.stat}><span><Activity size={17}/> Sensor connections</span><strong>{sensors.loading && !sensors.data ? '—' : `${connected}/${sensorList.length}`}</strong><small>Reported as connected</small></div>
          </section>

          <section className={styles.grid} aria-label="Health record">
            <article className={styles.panel}>
              <div className={styles.sectionHeader}><h2><Shield size={19}/> Recorded allergies</h2><Link to="/resources">Check resources <ArrowRight size={15}/></Link></div>
              {wordsOrFallback(person.allergies, 'No allergies listed in this record. This is not proof of no allergies.', styles.warningTags)}
              <p className={styles.note}>Any matching medicine contraindication will be flagged in Resources. Compatibility must be reviewed by the crew medical team.</p>
            </article>
            <article className={styles.panel}>
              <div className={styles.sectionHeader}><h2><Pill size={19}/> Current medications</h2><Link to="/resources">Inventory <ArrowRight size={15}/></Link></div>
              {wordsOrFallback(person.currentMeds, 'No current medications listed in this record.', styles.tags)}
              <p className={styles.note}>Shown from the crew profile; this is not an instruction to start, stop, or change medication.</p>
            </article>
          </section>

          <section className={styles.panel} aria-labelledby="baselines-heading">
            <div className={styles.sectionHeader}>
              <div><h2 id="baselines-heading"><HeartPulse size={19}/> Personal baseline ranges</h2><p className={styles.subheading}>Calculated from the recorded mean ± 2 standard deviations; not general clinical thresholds.</p></div>
              <Link to="/vitals">View trends <ArrowRight size={15}/></Link>
            </div>
            {baselines.length ? (
              <div className={styles.tableScroll}><table className={styles.table}>
                <thead><tr><th scope="col">Measurement</th><th scope="col">Mean</th><th scope="col">SD</th><th scope="col">Personal range (±2 SD)</th><th scope="col">Samples</th></tr></thead>
                <tbody>{baselines.map(({ key, mean, sd, n }) => (
                  <tr key={key}>
                    <td><strong>{BASELINE_LABELS[key] ?? key}</strong></td>
                    <td>{number(mean)} <span className={styles.unit}>{BASELINE_UNITS[key] ?? ''}</span></td>
                    <td>{number(sd)}</td>
                    <td><strong>{number(mean - 2 * sd)} – {number(mean + 2 * sd)}</strong> <span className={styles.unit}>{BASELINE_UNITS[key] ?? ''}</span></td>
                    <td><span className={styles.sampleCount}>{n}</span></td>
                  </tr>
                ))}</tbody>
              </table></div>
            ) : <p className={styles.emptyValue}>No personal baseline values have been recorded yet.</p>}
            <p className={styles.note}><AlertTriangle size={15}/> A small sample size or unavailable readings can limit the reliability of a baseline. The displayed range is descriptive, not a diagnosis.</p>
          </section>

          <section className={styles.grid} aria-label="Medical context and devices">
            <article className={styles.panel}>
              <div className={styles.sectionHeader}><h2><Stethoscope size={19}/> Medical history</h2></div>
              {person.history.length ? <ul className={styles.history}>{person.history.map((item, i) => <li key={`${item}-${i}`}>{item}</li>)}</ul>
                : <p className={styles.emptyValue}>No history entries listed in this record.</p>}
            </article>
            <article className={styles.panel}>
              <div className={styles.sectionHeader}><div><h2><Activity size={19}/> Device status</h2><p className={styles.subheading}>{sensors.data ? `${needsAttention} of ${sensorList.length} need attention` : 'Reported sensor states'}</p></div><Link to="/vitals">Vitals <ArrowRight size={15}/></Link></div>
              {sensors.loading && !sensors.data ? <p className={styles.emptyValue}>Loading sensor data…</p> : sensors.error ? (
                <p className={styles.error} role="alert">Unable to load device status: {sensors.error.message}. <button type="button" onClick={sensors.reload}>Retry</button></p>
              ) : !sensorList.length ? <p className={styles.emptyValue}>No sensors recorded.</p> : (
                <ul className={styles.sensorList}>{sensorList.map((sensor) => (
                  <li key={sensor.id}>
                    <span className={styles.sensorIcon}>{sensor.status === 'connected' ? <CheckCircle2 size={18}/> : sensor.status === 'disconnected' ? <WifiOff size={18}/> : <AlertTriangle size={18}/>}</span>
                    <div className={styles.sensorInfo}>
                      <strong>{sensor.name}</strong>
                      <small>{sensor.location} · {sensor.metrics.map((metric) => METRIC_LABELS[metric as Metric] ?? metric).join(', ') || 'Metrics not specified'}</small>
                      <small className={styles.lastSeen}><Clock3 size={12}/> Last reported: {showDate(sensor.lastSeen)}</small>
                    </div>
                    <span className={`${styles.sensorStatus} ${styles[`sensor_${sensor.status}`]}`}>{SENSOR_LABELS[sensor.status]}</span>
                  </li>
                ))}</ul>
              )}
            </article>
          </section>
        </>
      )}
      <p className={styles.footer}>AstroCare provides on-device decision support only. Profile information and baseline comparisons do not diagnose illness or determine fitness for duty.</p>
    </main>
  );
}
