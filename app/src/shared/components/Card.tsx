// Content container.
//   <Card title="Cabin conditions" subtitle="Last 24 h" actions={<Button variant="ghost">More</Button>}>…</Card>
import type { HTMLAttributes, ReactNode } from 'react';
import { useId } from 'react';
import styles from './Card.module.css';

export interface CardProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

export function Card({ title, subtitle, actions, children, className = '', ...rest }: CardProps) {
  const id = useId();
  return (
    <section className={`${styles.card} ${className}`} aria-labelledby={title ? id : undefined} {...rest}>
      {(title || actions) && (
        <div className={styles.head}>
          <div>
            {title && (
              <h2 id={id} className={styles.title}>
                {title}
              </h2>
            )}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
