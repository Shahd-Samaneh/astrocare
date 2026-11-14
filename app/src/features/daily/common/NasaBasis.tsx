// Owner: Shahd. "Why we track this" panel: our own sentence + the titles of the public
// NASA pages behind a feature. Collapsed by default to one subtle line; the button
// expands it. Titles come from GET /api/daily/sources (loaded on first open), so no
// URL is ever bundled into the frontend. Listing a source does not mean NASA endorses the app.
//   <NasaBasis variant="test" ids={['nasa-pvt-iss']} why="A short reaction test can show tiredness early." />
import { ChevronDown, Info } from 'lucide-react';
import { useId, useState } from 'react';
import { useApi } from '../../../shared/api/client';
import { paths, type NasaSource } from '../api.attention';
import styles from './NasaBasis.module.css';

export interface NasaBasisProps {
  ids: string[];
  /** One or two sentences in our own words. Defaults to the first source's `why`. */
  why?: string;
  /** 'test' → "Why this test?"; 'tracking' (default) → "Why we track this". */
  variant?: 'test' | 'tracking';
  /** Start expanded. Default false (collapsed). */
  defaultOpen?: boolean;
}

export function NasaBasis({ ids, why, variant = 'tracking', defaultOpen = false }: NasaBasisProps) {
  const contentId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const [loaded, setLoaded] = useState(defaultOpen);
  const { data, error, loading } = useApi<NasaSource[]>(loaded ? paths.sources : null);
  const matches = (data ?? []).filter((s) => ids.includes(s.id));
  const sentence = why ?? matches[0]?.why;
  const label = variant === 'test' ? 'Why this test?' : 'Why we track this';

  const toggle = () => {
    setOpen((o) => !o);
    setLoaded(true);
  };

  return (
    <aside className={`${styles.panel} ${open ? styles.open : ''}`} aria-label={label}>
      <h3 className={styles.heading}>
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={open}
          aria-controls={contentId}
          onClick={toggle}
        >
          <Info size={16} aria-hidden />
          <span className={styles.label}>{label}</span>
          <span className={styles.sep} aria-hidden>
            ·
          </span>
          <span className={styles.sub}>Based on NASA research</span>
          <ChevronDown size={16} aria-hidden className={styles.chevron} />
        </button>
      </h3>
      <div id={contentId} className={styles.content} hidden={!open}>
        {sentence && <p className={styles.why}>{sentence}</p>}
        {loading && !data && <p className={styles.muted}>Loading sources…</p>}
        {error && <p className={styles.muted}>Sources unavailable right now.</p>}
        {matches.length > 0 && (
          <ul className={styles.list} aria-label="Public sources">
            {matches.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
        )}
        <p className={styles.fine}>
          Public NASA material, summarised in our own words. Not an endorsement.
        </p>
      </div>
    </aside>
  );
}
