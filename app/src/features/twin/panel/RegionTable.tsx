// Accessible alternative to the 3D view: the same regions as a table.
import { Link } from 'react-router-dom';
import type { TwinRegion } from '../types';
import { ESTIMATE_LABEL, STATUS_LABEL, formatValue, qualityLabel, regionOpenLabel } from '../twinView';
import { StatusBadge } from './RegionCard';
import styles from './Panel.module.css';

export function RegionTable({ regions, caption, history }: { regions: TwinRegion[]; caption: string; history: boolean }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <caption className={styles.caption}>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Region</th>
            <th scope="col">Status</th>
            <th scope="col">Summary</th>
            <th scope="col">Values</th>
            <th scope="col">{history ? 'Rule conditions' : 'Open alerts'}</th>
            <th scope="col">Page</th>
          </tr>
        </thead>
        <tbody>
          {regions.map((r) => (
            <tr key={r.id}>
              <th scope="row">{r.label}</th>
              <td>
                <StatusBadge region={r} />
                <span className="sr-only"> {STATUS_LABEL[r.status]}</span>
              </td>
              <td>
                {r.headline}
                {r.estimate && <span className={styles.quality}>{ESTIMATE_LABEL}</span>}
              </td>
              <td>
                <ul className={styles.plain}>
                  {/* the sensors region lists each sensor below (with its location) instead */}
                  {(r.sensors?.length ? [] : r.values).map((v) => {
                    const q = qualityLabel(v.quality);
                    return (
                      <li key={v.label}>
                        {v.label}: {formatValue(v)}
                        {q ? ` (${q})` : ''}
                      </li>
                    );
                  })}
                  {r.sensors?.map((s) => (
                    <li key={s.id}>
                      {s.name}: {s.status.replace('_', ' ')} · {s.location}
                      {s.anchor ? '' : ' (not worn)'}
                    </li>
                  ))}
                </ul>
              </td>
              <td>
                {history ? (
                  r.alerts.join(', ') || 'None'
                ) : r.alertRefs.length ? (
                  <ul className={styles.plain}>
                    {r.alertRefs.map((a) => (
                      <li key={a.id}>
                        <Link to={`/alerts/${encodeURIComponent(a.id)}`} className={styles.alertLink}>
                          {a.ruleId}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  'None'
                )}
              </td>
              <td>
                <Link to={r.route} className={styles.alertLink}>
                  {regionOpenLabel(r)}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
