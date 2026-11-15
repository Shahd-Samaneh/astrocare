/** Local inventory view. Read-only: it does not prescribe or reserve medicines. */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Boxes,
  CheckCircle2,
  ClipboardList,
  Package,
  Pill,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { useApi } from '../../../shared/api/client';
import type { Profile, Resource, ResourceKind, ResourceStatus } from '../../../shared/types/contracts';
import styles from './Resources.module.css';

type KindFilter = 'all' | ResourceKind;
type StatusFilter = 'all' | ResourceStatus | 'allergy_conflict';

const STATUS_TEXT: Record<ResourceStatus, string> = {
  available: 'Available',
  low: 'Low stock',
  out_of_stock: 'Out of stock',
  expired: 'Expired',
};

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'available', label: 'Available' },
  { value: 'low', label: 'Low stock' },
  { value: 'out_of_stock', label: 'Out of stock' },
  { value: 'expired', label: 'Expired' },
  { value: 'allergy_conflict', label: 'Allergy conflict' },
];

function normalized(text: string): string {
  return text.trim().toLocaleLowerCase();
}

function conflictsFor(resource: Resource, profile: Profile | undefined): string[] {
  if (!profile) return [];
  const allergies = new Set(profile.allergies.map(normalized));
  return resource.contraindicatedAllergies.filter((allergy) => allergies.has(normalized(allergy)));
}

function effectiveStatus(resource: Resource): ResourceStatus {
  // The API supplies the status; an explicitly elapsed expiry date is additionally
  // treated as expired if stock data is stale. A date-only expiry is valid that day.
  if (resource.status === 'expired') return 'expired';
  const date = resource.expiry?.slice(0, 10);
  if (date && /^\d{4}-\d{2}-\d{2}$/.test(date) && date < new Date().toISOString().slice(0, 10)) {
    return 'expired';
  }
  return resource.status;
}

function expiryLabel(expiry: string | null | undefined): string {
  if (!expiry) return 'Not recorded';
  const date = new Date(expiry);
  return Number.isNaN(date.getTime()) ? expiry : date.toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  });
}

export default function Resources() {
  const inventory = useApi<Resource[]>('/resources');
  const profile = useApi<Profile>('/profile');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState<KindFilter>('all');
  const [status, setStatus] = useState<StatusFilter>('all');

  const resources = useMemo(() => inventory.data ?? [], [inventory.data]);
  const filtered = useMemo(() => resources.filter((resource) => {
    const matchesText = `${resource.name} ${resource.id}`.toLocaleLowerCase().includes(normalized(search));
    const matchesKind = kind === 'all' || resource.kind === kind;
    const matchesStatus = status === 'all'
      || (status === 'allergy_conflict'
        ? !!profile.data && conflictsFor(resource, profile.data).length > 0
        : effectiveStatus(resource) === status);
    return matchesText && matchesKind && matchesStatus;
  }), [resources, search, kind, status, profile.data]);

  const total = resources.length;
  const available = resources.filter((r) => effectiveStatus(r) === 'available').length;
  const low = resources.filter((r) => effectiveStatus(r) === 'low').length;
  const unavailable = resources.filter((r) => ['expired', 'out_of_stock'].includes(effectiveStatus(r))).length;
  const conflicts = profile.data ? resources.filter((r) => conflictsFor(r, profile.data).length > 0).length : null;

  const refresh = () => { inventory.reload(); profile.reload(); };

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link className={styles.back} to="/"> <ArrowLeft size={16} /> Today dashboard</Link>
          <p className={styles.eyebrow}>MISSION SUPPORT · LOCAL INVENTORY</p>
          <h1>Medicines &amp; equipment</h1>
          <p className={styles.description}>Check what is stored on this device before following a review-safe next step.</p>
        </div>
        <button type="button" className={styles.button} onClick={refresh} disabled={inventory.loading || profile.loading}>
          <RefreshCw size={16} /> Refresh inventory
        </button>
      </header>

      <div className={styles.notice} role="note">
        <ShieldAlert size={19} />
        <span><strong>Inventory information only.</strong> Stock status is not a medical recommendation. Medication decisions require Crew Medical Officer (CMO) review.</span>
      </div>

      <section className={styles.stats} aria-label="Inventory summary">
        <div className={styles.stat}><span><Boxes size={17} /> Total items</span><strong>{inventory.loading && !inventory.data ? '—' : total}</strong><small>Recorded locally</small></div>
        <div className={styles.stat}><span><CheckCircle2 size={17} /> Available</span><strong>{inventory.loading && !inventory.data ? '—' : available}</strong><small>Inventory status</small></div>
        <div className={styles.stat}><span><Package size={17} /> Low stock</span><strong>{inventory.loading && !inventory.data ? '—' : low}</strong><small>Check before use</small></div>
        <div className={styles.stat}><span><AlertTriangle size={17} /> Unavailable</span><strong>{inventory.loading && !inventory.data ? '—' : unavailable}</strong><small>Expired or out of stock</small></div>
      </section>

      <section className={styles.panel} aria-labelledby="inventory-heading">
        <div className={styles.sectionTop}>
          <div>
            <h2 id="inventory-heading">Crew kit inventory</h2>
            <p className={styles.muted}>Search by name, filter resources, and review expiry and allergy warnings.</p>
          </div>
          <span className={styles.resultCount}>{filtered.length} of {total} items</span>
        </div>

        <div className={styles.filters}>
          <label className={styles.searchBox}>
            <Search size={18} aria-hidden="true" />
            <span className={styles.srOnly}>Search inventory</span>
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search medicines or equipment" />
          </label>
          <div className={styles.kindFilters} role="group" aria-label="Resource type">
            {([['all', 'All'], ['medicine', 'Medicines'], ['equipment', 'Equipment']] as const).map(([value, label]) => (
              <button key={value} type="button" className={`${styles.chip} ${kind === value ? styles.active : ''}`}
                aria-pressed={kind === value} onClick={() => setKind(value)}>{label}</button>
            ))}
          </div>
          <label className={styles.selectWrap}>
            <span className={styles.srOnly}>Filter by status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
              {STATUS_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>

        {profile.error && (
          <p role="status" className={styles.caution}><ShieldAlert size={16} /> Allergy checks unavailable: crew profile could not be loaded. <button type="button" onClick={profile.reload}>Retry</button></p>
        )}
        {!profile.error && !profile.data && !profile.loading && (
          <p className={styles.caution}>Crew profile is unavailable; allergy compatibility cannot be verified.</p>
        )}
        {profile.data && (
          <p className={styles.profileNote}><ShieldCheck size={15} /> Allergy comparison uses the crew profile on this device. {conflicts === 0 ? 'No exact matches found in listed resource contraindications.' : `${conflicts} item${conflicts === 1 ? '' : 's'} flagged for potential allergy conflict.`} <Link to="/profile">View profile <ArrowRight size={13} /></Link></p>
        )}

        {inventory.loading && !inventory.data ? (
          <div className={styles.empty}>Loading local inventory…</div>
        ) : inventory.error ? (
          <div className={styles.empty} role="alert">Local inventory unavailable: {inventory.error.message}. <button type="button" className={styles.inlineButton} onClick={inventory.reload}>Try again</button></div>
        ) : total === 0 ? (
          <div className={styles.empty}><ClipboardList size={27} /> No resources have been recorded yet.</div>
        ) : filtered.length === 0 ? (
          <div className={styles.empty}><Search size={26} /> No resources match these filters. <button type="button" className={styles.inlineButton} onClick={() => {setSearch(''); setKind('all'); setStatus('all');}}>Clear filters</button></div>
        ) : (
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead><tr><th scope="col">Resource</th><th scope="col">On hand</th><th scope="col">Stock status</th><th scope="col">Expiry</th><th scope="col">Allergy review</th></tr></thead>
              <tbody>
                {filtered.map((resource) => {
                  const effective = effectiveStatus(resource);
                  const matched = conflictsFor(resource, profile.data);
                  return (
                    <tr key={resource.id}>
                      <td><div className={styles.resourceTitle}>
                        <span className={styles.resourceIcon}>{resource.kind === 'medicine' ? <Pill size={19} /> : <Package size={19} />}</span>
                        <span><strong>{resource.name}</strong><small>{resource.kind === 'medicine' ? 'Medicine · CMO review required' : 'Equipment'}</small></span>
                      </div></td>
                      <td><strong className={styles.quantity}>{resource.qty.toLocaleString()}</strong> <span className={styles.muted}>{resource.unit}</span></td>
                      <td><span className={`${styles.pill} ${styles[`status_${effective}`]}`}><span className={styles.dot} />{STATUS_TEXT[effective]}</span></td>
                      <td><span className={effective === 'expired' ? styles.danger : ''}>{expiryLabel(resource.expiry)}</span></td>
                      <td>{!profile.data ? (
                        <span className={styles.muted}>Not verified</span>
                      ) : matched.length ? (
                        <span className={`${styles.pill} ${styles.conflict}`} title={matched.join(', ')}><AlertTriangle size={14} /> Conflict: {matched.join(', ')}</span>
                      ) : resource.contraindicatedAllergies.length ? (
                        <span className={styles.muted}>No listed match</span>
                      ) : (
                        <span className={styles.muted}>No contraindications listed</span>
                      )}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <footer className={styles.footer}><ShieldAlert size={15} /> Inventory and allergy flags only support crew review; they do not establish that any medicine is safe or appropriate.</footer>
    </main>
  );
}
