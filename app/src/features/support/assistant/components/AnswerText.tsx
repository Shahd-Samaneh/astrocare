// Renders an answer: paragraphs, "- " bullet lists, **bold**, and [n] citations.
// Plain React elements only (no HTML injection).
import type { ReactNode } from 'react';
import styles from './AnswerText.module.css';

function inline(text: string, key: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+(?:,\s*\d+)*\])/g);
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={`${key}-${i}`}>{p.slice(2, -2)}</strong>;
    if (/^\[\d+(?:,\s*\d+)*\]$/.test(p)) {
      return (
        <sup key={`${key}-${i}`} className={styles.cite} aria-label={`source ${p.slice(1, -1)}`}>
          {p}
        </sup>
      );
    }
    return p;
  });
}

export function AnswerText({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).filter((b) => b.trim());
  return (
    <div className={styles.answer} dir="auto">
      {blocks.map((block, bi) => {
        const lines = block.split('\n');
        const head = lines[0].startsWith('- ') ? null : lines[0];
        const bullets = lines.filter((l) => l.startsWith('- '));
        const rest = lines.slice(head === null ? 0 : 1).filter((l) => !l.startsWith('- '));
        return (
          <div key={bi} className={styles.block}>
            {head !== null && <p className={styles.p}>{inline(head, `h${bi}`)}</p>}
            {rest.map((l, li) => (
              <p key={li} className={styles.p}>
                {inline(l, `r${bi}-${li}`)}
              </p>
            ))}
            {bullets.length > 0 && (
              <ul className={styles.ul}>
                {bullets.map((b, li) => (
                  <li key={li}>{inline(b.slice(2), `b${bi}-${li}`)}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
