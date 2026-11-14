// Numbered sources under an answer (candidate for shared/components, proposal A7).
// One line per source: "[1] <title>". The number matches the [n] citations in the answer.
// A reference URL is only a tooltip (text): the app never opens a remote page.
import type { AssistantSource } from '../types';
import styles from './SourceList.module.css';

export function SourceList({ sources }: { sources: AssistantSource[] }) {
  if (!sources.length) return null;
  return (
    <div className={styles.wrap}>
      <h4 className={styles.heading}>Sources</h4>
      <ol className={styles.list}>
        {sources.map((s, i) => (
          <li key={s.id} className={styles.item} title={s.url ?? undefined}>
            <span className={styles.num}>[{i + 1}]</span>{' '}
            <span className={styles.title}>{s.title}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
