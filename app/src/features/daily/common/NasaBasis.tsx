// Owner: Shahd. "Why we track this" panel: our own sentence + the titles of the public
// NASA pages behind a feature. Titles come from GET /api/daily/sources, so no URL is
// ever bundled into the frontend. Listing a source does not mean NASA endorses the app.
//   <NasaBasis ids={['nasa-pvt-iss']} why="A short reaction test can show tiredness early." />
import { BookOpen } from 'lucide-react';
import { useId } from 'react';
import { useApi } from '../../../shared/api/client';
import { paths, type NasaSource } from '../api.attention';
import styles from './NasaBasis.module.css';

export interface NasaBasisProps {
  ids: string[];
  /** One or two sentences in our own words. Defaults to the first source's `why`. */
  why?: string;
}

export function NasaBasis({ ids, why }: NasaBasisProps) {
  const headingId = useId();
  const { data, error, loading } = useApi<NasaSource[]>(paths.sources);
  const matches = (data ?? []).filter((s) => ids.includes(s.id));
  const sentence = why ?? matches[0]?.why;

  return (
    <aside className={styles.panel} aria-labelledby={headingId}>
      <h3 id={headingId} className={styles.title}>
        <BookOpen size={16} aria-hidden /> Why we track this
      </h3>
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
      <p className={styles.fine}>Public NASA material, summarised in our own words. Not an endorsement.</p>
    </aside>
  );
}
