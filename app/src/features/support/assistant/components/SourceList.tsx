// Numbered sources under an answer (candidate for shared/components, proposal A7).
// The number matches the [n] citations in the answer. URLs are shown as text only:
// the app never opens a remote page.
import type { AssistantSource } from '../types';
import styles from './SourceList.module.css';

export function SourceList({ sources }: { sources: AssistantSource[] }) {
  if (!sources.length) return null;
  return (
    <div className={styles.wrap}>
      <h4 className={styles.heading}>Sources</h4>
      <ol className={styles.list}>
        {sources.map((s, i) => (
          <li key={s.id} className={styles.item}>
            <span className={styles.num} aria-hidden>
              [{i + 1}]
            </span>
            <span className="sr-only">Source {i + 1}: </span>
            <span className={styles.text}>
              <span className={styles.title}>{s.title}</span>
              {s.url && <span className={styles.url}>{s.url}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
