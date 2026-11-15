// Details for one body region: status, headline, values (with units and quality), related alerts,
// NASA source titles and a link to the region's page.
import { ArrowRight, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, Button, SimulatedBadge } from '../../../shared/components';
import type { TwinRegion } from '../types';
import {
  ESTIMATE_LABEL, STATUS_BADGE, STATUS_LABEL, formatValue, numberSensors, qualityLabel, regionOpenLabel,
  sensorStatusLabel,
} from '../twinView';
import styles from './Panel.module.css';

export function StatusBadge({ region }: { region: Pick<TwinRegion, 'status'> }) {
  return <Badge variant={STATUS_BADGE[region.status]}>{STATUS_LABEL[region.status]}</Badge>;
}

export interface RegionCardProps {
  region: TwinRegion;
  history: boolean;
  reducedMotion: boolean;
  onClose: () => void;
}

export function RegionCard({ region, history, reducedMotion, onClose }: RegionCardProps) {
  const headingId = `twin-card-${region.id}`;
  return (
    <section className={styles.card} aria-labelledby={headingId}>
      <div className={styles.cardHead}>
        <div>
          <h2 id={headingId} className={styles.title}>
            {region.label}
          </h2>
          <div className={styles.chips}>
            <StatusBadge region={region} />
            {region.estimate && <Badge variant="neutral">{ESTIMATE_LABEL}</Badge>}
            <SimulatedBadge source="simulated" />
          </div>
        </div>
        <button type="button" className={styles.iconButton} onClick={onClose} aria-label="Close region details">
          <X size={18} aria-hidden />
        </button>
      </div>

      <p className={styles.headline}>{region.headline}</p>

      {region.id === 'heart' && (
        <p className={styles.muted}>
          {region.pulseBpm !== null
            ? reducedMotion
              ? `Heart rate ${region.pulseBpm} bpm (animation off: reduced motion).`
              : `The heart pulses at ${region.pulseBpm} beats per minute.`
            : 'No recent data: the heart does not pulse.'}
        </p>
      )}

      {region.values.length > 0 && !region.sensors?.length && (
        <dl className={styles.values}>
          {region.values.map((v) => {
            const q = qualityLabel(v.quality);
            const empty = v.value === null || v.value === '';
            return (
              <div key={v.label} className={styles.valueRow}>
                <dt>{v.label}</dt>
                <dd className={empty ? styles.nodata : undefined}>
                  {formatValue(v)}
                  {q && <span className={styles.quality}>{q}</span>}
                </dd>
              </div>
            );
          })}
        </dl>
      )}

      {region.id === 'sensors' && region.sensors && region.sensors.length > 0 && (
        <ul className={styles.sensorList} aria-label="Sensors">
          {numberSensors(region.sensors).map(({ sensor, marker }) => (
            <li key={sensor.id}>
              <span className={`${styles.marker} ${styles[sensor.status] ?? ''}`} aria-hidden>
                {marker ?? '–'}
              </span>
              <span>
                <strong>{sensor.name}</strong>
                <span className={styles.muted}> {sensorStatusLabel(sensor)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className={styles.block}>
        <h3 className={styles.subhead}>{history ? 'Rule conditions that day' : 'Related open alerts'}</h3>
        {history ? (
          region.alerts.length ? (
            <ul className={styles.plain}>
              {region.alerts.map((r) => (
                <li key={r}>
                  <strong className="mono">{r}</strong> <span className={styles.muted}>condition held (history, no alert link)</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.muted}>None</p>
          )
        ) : region.alertRefs.length ? (
          <ul className={styles.plain}>
            {region.alertRefs.map((a) => (
              <li key={a.id}>
                <Link to={`/alerts/${encodeURIComponent(a.id)}`} className={styles.alertLink}>
                  <span className="mono">{a.ruleId}</span> {a.title}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>None open</p>
        )}
      </div>

      <div className={styles.block}>
        <h3 className={styles.subhead}>Sources</h3>
        {region.sourceTitles.length ? (
          <ul className={styles.sources}>
            {region.sourceTitles.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>No NASA source for this view (thresholds are team decisions).</p>
        )}
      </div>

      <p className={styles.fine}>Possible patterns for review, not a diagnosis.</p>
      <Button variant="secondary" to={region.route} icon={<ArrowRight size={16} />}>
        {regionOpenLabel(region)}
      </Button>
    </section>
  );
}
