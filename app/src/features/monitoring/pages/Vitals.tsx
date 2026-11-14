/**
 * AstroCare Vitals — monitoring frontend (Haya).
 * Reads from local APIs only. No simulated values are added in this page.
 * Data quality is kept separate from clinical interpretation.
 */
import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowLeft, ArrowRight, Clock3, PenLine, RefreshCw } from 'lucide-react';
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts';
import { api, useApi } from '../../../shared/api/client';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import { Card, ChartFrame, baselineBand, useChartTheme } from '../../../shared/components';
import type { Baseline, Metric, Profile, Quality, Reading } from '../../../shared/types/contracts';
import styles from './Vitals.module.css';

type Period = '24h' | '7d' | 'mission';

const METRICS: { id: Metric; label: string; unit: string; short: string }[] = [
  { id: 'heart_rate', label: 'Heart rate', unit: 'bpm', short: 'Heart rate' },
  { id: 'spo2', label: 'Blood oxygen (SpO₂)', unit: '%', short: 'SpO₂' },
  { id: 'skin_temp', label: 'Skin temperature', unit: '°C', short: 'Skin temp' },
  { id: 'bp_sys', label: 'Blood pressure — systolic', unit: 'mmHg', short: 'BP systolic' },
  { id: 'bp_dia', label: 'Blood pressure — diastolic', unit: 'mmHg', short: 'BP diastolic' },
  { id: 'resp_rate', label: 'Respiratory rate', unit: 'breaths/min', short: 'Resp. rate' },
];

const PERIODS: { id: Period; label: string }[] = [
  { id: '24h', label: '24 hours' },
  { id: '7d', label: '7 days' },
  { id: 'mission', label: 'Mission' },
];

const GAP_HOURS: Record<Period, number> = { '24h': 1, '7d': 6, mission: 24 };

function displayTime(ts: string, long = false): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString('en-US', long
    ? { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function displayNumber(value: number): string {
  return Number(value.toFixed(1)).toString();
}

function qualityLabel(quality: Quality): string {
  switch (quality) {
    case 'good': return 'Good quality';
    case 'low': return 'Low quality';
    case 'stale': return 'Stale';
    case 'missing': return 'Missing';
  }
}

type GraphPoint = { tsMs: number; goodValue: number | null; lowValue: number | null };

function prepareGraph(readings: Reading[], gapHours: number): { points: GraphPoint[]; gaps: number } {
  const points: GraphPoint[] = [];
  let gaps = 0;
  const thresholdMs = gapHours * 60 * 60 * 1000;
  for (const reading of readings) {
    const timestamp = new Date(reading.ts).getTime();
    if (!Number.isFinite(timestamp) || !Number.isFinite(reading.value)) continue;
    const previous = points[points.length - 1];
    if (previous && timestamp - previous.tsMs > thresholdMs) {
      points.push({ tsMs: previous.tsMs + (timestamp - previous.tsMs) / 2, goodValue: null, lowValue: null });
      gaps += 1;
    }
    points.push({
      tsMs: timestamp,
      goodValue: reading.quality === 'good' ? reading.value : null,
      lowValue: reading.quality === 'low' ? reading.value : null,
    });
  }
  return { points, gaps };
}

function BaselineSummary({ baseline, unit }: { baseline: Baseline | undefined; unit: string }) {
  if (!baseline) return <p className={styles.muted}>Personal baseline not available for this metric.</p>;
  const lower = baseline.mean - 2 * baseline.sd;
  const upper = baseline.mean + 2 * baseline.sd;
  return (
    <div className={styles.baselineDetails}>
      <div><span>Personal mean</span><strong>{displayNumber(baseline.mean)} {unit}</strong></div>
      <div><span>Reference band (mean ± 2 SD)</span><strong>{displayNumber(lower)}–{displayNumber(upper)} {unit}</strong></div>
      <div><span>Baseline observations</span><strong>{baseline.n}</strong></div>
    </div>
  );
}

export default function Vitals() {
  const t = useChartTheme();
  const { status } = useAppStatus();
  const [metric, setMetric] = useState<Metric>('heart_rate');
  const [period, setPeriod] = useState<Period>('7d');
  const [manualOpen, setManualOpen] = useState(false);
  const [sys, setSys] = useState('');
  const [dia, setDia] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  // API supports look-back in hours, including the mission window.
  const missionHours = Math.max(24, (status?.missionDay ?? 365) * 24);
  const hours = period === '24h' ? 24 : period === '7d' ? 168 : missionHours;
  const apiPath = `/readings?metric=${metric}&hours=${hours}&limit=20000`;
  const readingsRequest = useApi<Reading[]>(apiPath);
  const profileRequest = useApi<Profile>('/profile');
  const selection = METRICS.find((entry) => entry.id === metric) ?? METRICS[0];
  const baseline = profileRequest.data?.baseline[metric];

  const readings = useMemo(() =>
    (readingsRequest.data ?? [])
      .filter((reading) => reading.metric === metric)
      .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()),
    [readingsRequest.data, metric]
  );
  const graph = useMemo(() => prepareGraph(readings, GAP_HOURS[period]), [readings, period]);
  const good = readings.filter((r) => r.quality === 'good' && Number.isFinite(r.value));
  const low = readings.filter((r) => r.quality === 'low').length;
  const latest = readings.length > 0 ? readings[readings.length - 1] : undefined;
  const goodMean = good.length > 0 ? good.reduce((sum, r) => sum + r.value, 0) / good.length : undefined;
  const latestGood = [...readings].reverse().find((r) => r.quality === 'good');
  const recent = [...readings].reverse().slice(0, 12);

  async function submitBloodPressure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setFormError(null);
    setFormSuccess(null);
    const systolic = Number(sys);
    const diastolic = Number(dia);
    if (!sys.trim() || !dia.trim() || !Number.isFinite(systolic) || !Number.isFinite(diastolic) ||
      systolic <= 0 || diastolic <= 0 || systolic <= diastolic) {
      setFormError('Enter positive values with systolic greater than diastolic.');
      return;
    }
    setSaving(true);
    let systolicSaved = false;
    try {
      await api.post<Reading>('/readings/manual', { metric: 'bp_sys', value: systolic });
      systolicSaved = true;
      await api.post<Reading>('/readings/manual', { metric: 'bp_dia', value: diastolic });
      setFormSuccess(`Saved manual blood pressure: ${systolic}/${diastolic} mmHg.`);
      setSys('');
      setDia('');
      setManualOpen(false);
      setMetric('bp_sys');
      readingsRequest.reload();
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown error';
      setFormError(systolicSaved
        ? `Systolic was saved, but diastolic failed (${reason}). Check stored readings before retrying to avoid duplicates.`
        : `Could not save blood pressure (${reason}).`);
      readingsRequest.reload();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <Link to="/" className={styles.back}><ArrowLeft size={15} /> Today dashboard</Link>
          <p className={styles.eyebrow}>HEALTH MONITORING · MISSION DAY {status?.missionDay ?? '—'}</p>
          <h1>Vitals detail</h1>
          <p className={styles.muted}>Explore local measurements, data quality, and personal baseline trends.</p>
        </div>
        <button type="button" className={styles.primaryAction} onClick={() => { setManualOpen((open) => !open); setFormError(null); setFormSuccess(null); }}>
          <PenLine size={17} /> {manualOpen ? 'Close manual entry' : 'Enter blood pressure'}
        </button>
      </header>

      {formSuccess && <div role="status" className={styles.success}>{formSuccess}</div>}
      {manualOpen && (
        <Card title="Manual blood pressure reading" subtitle="Systolic and diastolic values are stored in the local database as separate readings.">
          <form onSubmit={submitBloodPressure} className={styles.manualForm}>
            <div className={styles.manualFields}>
              <label>Systolic (mmHg)
                <input type="number" required min="1" step="1" value={sys} onChange={(e) => setSys(e.target.value)} placeholder="Systolic" />
              </label>
              <label>Diastolic (mmHg)
                <input type="number" required min="1" step="1" value={dia} onChange={(e) => setDia(e.target.value)} placeholder="Diastolic" />
              </label>
              <button type="submit" disabled={saving} className={styles.primaryAction}>{saving ? 'Saving…' : 'Save reading'}</button>
            </div>
            {formError && <p className={styles.error} role="alert">{formError}</p>}
            <p className={styles.disclaimer}>Manual entry is for recorded measurements only. AstroCare does not diagnose or prescribe treatment.</p>
          </form>
        </Card>
      )}

      <section className={styles.section} aria-labelledby="metric-heading">
        <div className={styles.sectionHead}>
          <h2 id="metric-heading">Select a vital sign</h2>
          <span className={styles.muted}>Data from local sensors and manual logs</span>
        </div>
        <div className={styles.tabs} role="group" aria-label="Vital sign">
          {METRICS.map((item) => (
            <button key={item.id} type="button" aria-pressed={metric === item.id}
              className={`${styles.tab} ${metric === item.id ? styles.selected : ''}`}
              onClick={() => setMetric(item.id)}>{item.short}</button>
          ))}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="trend-heading">
        <div className={styles.sectionHead}>
          <div>
            <h2 id="trend-heading">{selection.label} trend</h2>
            <p className={styles.muted}>Historical values are not a diagnosis. Data quality is shown separately.</p>
          </div>
          <div className={styles.periods} role="group" aria-label="Time range">
            {PERIODS.map((item) => (
              <button key={item.id} type="button" aria-pressed={period === item.id}
                className={`${styles.periodButton} ${period === item.id ? styles.selected : ''}`}
                onClick={() => setPeriod(item.id)}>{item.label}</button>
            ))}
          </div>
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summary}><span><Activity size={15} /> Latest recorded</span><strong>{latest ? `${displayNumber(latest.value)} ${latest.unit}` : '—'}</strong><small>{latest ? `${qualityLabel(latest.quality)} · ${displayTime(latest.ts)}` : 'No data in selected time range'}</small></div>
          <div className={styles.summary}><span>Good-quality average</span><strong>{goodMean !== undefined ? `${displayNumber(goodMean)} ${selection.unit}` : '—'}</strong><small>From {good.length} good-quality readings</small></div>
          <div className={styles.summary}><span>Low-quality readings</span><strong>{low}</strong><small>Not included in the average or main trend</small></div>
          <div className={styles.summary}><span><Clock3 size={15} /> Long recording intervals</span><strong>{graph.gaps}</strong><small>Over {GAP_HOURS[period]} hour{GAP_HOURS[period] === 1 ? '' : 's'} between records</small></div>
        </div>

        <Card title={`${selection.label} · ${PERIODS.find((item) => item.id === period)?.label ?? period}`}
          subtitle="Shaded area: personal baseline mean ± 2 SD when available">
          {readingsRequest.loading ? (
            <p className={styles.message} role="status">Loading local readings…</p>
          ) : readingsRequest.error ? (
            <div className={styles.message} role="alert">Could not load readings: {readingsRequest.error.message} <button className={styles.textButton} type="button" onClick={readingsRequest.reload}><RefreshCw size={14} /> Retry</button></div>
          ) : graph.points.length === 0 ? (
            <p className={styles.message}>No readings found in this time range. Try a longer range or enter a manual measurement.</p>
          ) : (
            <>
              <ChartFrame label={`${selection.label} over ${period}; baseline band where available; low-quality readings shown separately`} height={300}>
                <LineChart data={graph.points} margin={{ top: 12, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid {...t.grid} />
                  <XAxis dataKey="tsMs" type="number" domain={['dataMin', 'dataMax']} scale="time"
                    tickFormatter={(value: number) => displayTime(new Date(value).toISOString())}
                    {...t.axis} minTickGap={56} />
                  <YAxis {...t.axis} width={42} domain={['auto', 'auto']} />
                  <Tooltip {...t.tooltip}
                    labelFormatter={(value) => displayTime(new Date(Number(value)).toISOString(), true)}
                    formatter={(value, name) => [`${value} ${selection.unit}`, name === 'lowValue' ? 'Low-quality reading' : 'Good-quality reading']} />
                  {baselineBand(baseline, 2, t)}
                  <Line type="linear" dataKey="goodValue" name="Good-quality reading" stroke={t.colors.accent}
                    dot={graph.points.length < 65 ? { r: 2 } : false} activeDot={{ r: 5 }} strokeWidth={2.3} connectNulls={false} isAnimationActive={false} />
                  <Line type="linear" dataKey="lowValue" name="Low-quality reading" stroke="none"
                    dot={{ r: 3, fill: t.colors.warn, stroke: t.colors.warn }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />
                </LineChart>
              </ChartFrame>
              <div className={styles.legend}><span><i className={styles.goodDot} /> Good-quality measurements</span><span><i className={styles.lowDot} /> Low-quality (not joined)</span><span><i className={styles.bandKey} /> Personal baseline band</span></div>
              {latestGood && <p className={styles.muted}>Latest good-quality reading: {displayNumber(latestGood.value)} {latestGood.unit} at {displayTime(latestGood.ts, true)}</p>}
              {graph.gaps > 0 && <p className={styles.gapNote}>The line is interrupted across {graph.gaps} long interval{graph.gaps === 1 ? '' : 's'} without records. Intervals depend on the selected range and are not sensor-status diagnoses.</p>}
            </>
          )}
        </Card>
      </section>

      <Card title="Your personal baseline" subtitle="Based on the profile's stored reference measurements — not a population cutoff">
        {profileRequest.loading ? <p className={styles.muted}>Loading baseline…</p> :
          profileRequest.error ? <p role="alert" className={styles.error}>Could not load baseline: {profileRequest.error.message}</p> :
          <BaselineSummary baseline={baseline} unit={selection.unit} />}
      </Card>

      <Card title="Recent readings" subtitle={`Latest ${Math.min(12, readings.length)} records for ${selection.label}`}>
        {readingsRequest.loading ? <p className={styles.muted}>Loading readings…</p> :
          readingsRequest.error ? <p role="alert" className={styles.error}>Could not load readings.</p> :
          recent.length === 0 ? <p className={styles.muted}>No readings available in this range.</p> : (
            <div className={styles.tableScroll}>
              <table className={styles.table}>
                <thead><tr><th scope="col">Recorded at</th><th scope="col">Value</th><th scope="col">Data quality</th><th scope="col">Source</th></tr></thead>
                <tbody>{recent.map((reading) => (
                  <tr key={reading.id}>
                    <td>{displayTime(reading.ts, true)}</td>
                    <td className={styles.readingValue}>{displayNumber(reading.value)} {reading.unit}</td>
                    <td><span className={`${styles.quality} ${reading.quality === 'good' ? styles.qualityGood : styles.qualityLow}`}>{qualityLabel(reading.quality)}</span></td>
                    <td>{reading.source}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
      </Card>

      <p className={styles.footer}><span>SIMULATED / local mission data where labeled by source.</span> <Link to="/alerts">View alerts <ArrowRight size={14} /></Link></p>
    </div>
  );
}
