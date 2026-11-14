// Sources inside the answer bubble (candidate for shared/components, proposal A7).
// One chip per source: "[n] <title>", in the order of the [n] citations in the answer.
// Alerts and three "Your data" areas link to their page; a reference URL is only a tooltip
// (text): the app never opens a remote page.
import { Link } from 'react-router-dom';
import { chipLabel, isReference, sourceLink } from '../chatView';
import type { AssistantSource } from '../types';
import styles from './SourceList.module.css';

export function SourceList({ sources }: { sources: AssistantSource[] }) {
  if (!sources.length) return null;
  return (
    <div className={styles.wrap}>
      <span className={styles.heading} aria-hidden>
        Sources:
      </span>
      <ol className={styles.list} aria-label="Sources">
        {sources.map((s, i) => {
          const to = sourceLink(s);
          const chip = (
            // the number and the label are each isolated (<bdi>): an Arabic or English title keeps
            // its own direction and never reorders the [n] or the text around it
            <span className={`${styles.chip} ${to ? styles.linked : ''}`}>
              <bdi className={styles.num}>[{i + 1}]</bdi>
              <bdi className={styles.title}>{chipLabel(s)}</bdi>
            </span>
          );
          return (
            <li key={s.id} className={styles.item}>
              {to ? (
                <Link to={to} className={styles.hit}>
                  {chip}
                </Link>
              ) : (
                <span className={styles.hit} title={isReference(s) ? (s.url ?? undefined) : undefined}>
                  {chip}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
