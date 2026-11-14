// Heading for a group of cards inside a page.
//   <SectionHeader title="Vital signs" description="Latest values" actions={<Button variant="ghost">All</Button>} />
import type { ReactNode } from 'react';
import styles from './SectionHeader.module.css';

export interface SectionHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  as?: 'h2' | 'h3';
}

export function SectionHeader({ title, description, actions, as: H = 'h2' }: SectionHeaderProps) {
  return (
    <div className={styles.section}>
      <div>
        <H className={styles.title}>{title}</H>
        {description && <p className={styles.desc}>{description}</p>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
