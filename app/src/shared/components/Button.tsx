// Button, or a router link styled as a button when `to` is given.
//   <Button onClick={save}>Save</Button>
//   <Button variant="secondary" to="/vitals" icon={<Activity size={16} />}>Open vitals</Button>
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'warn' | 'ghost';

interface Common {
  variant?: ButtonVariant;
  icon?: ReactNode;
  children?: ReactNode;
  className?: string;
}

type AsButton = Common & ButtonHTMLAttributes<HTMLButtonElement> & { to?: undefined };
type AsLink = Common & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { to: string };

export type ButtonProps = AsButton | AsLink;

export function Button(props: ButtonProps) {
  const { variant = 'primary', icon, children, className = '' } = props;
  const cls = `${styles.button} ${styles[variant]} ${className}`;
  const content = (
    <>
      {icon && (
        <span className={styles.icon} aria-hidden>
          {icon}
        </span>
      )}
      {children}
    </>
  );

  if (props.to !== undefined) {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { to, variant: _v, icon: _i, children: _c, className: _cn, ...rest } = props;
    return (
      <Link to={to} className={cls} {...rest}>
        {content}
      </Link>
    );
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { variant: _v, icon: _i, children: _c, className: _cn, to: _t, type = 'button', ...rest } = props;
  return (
    <button type={type} className={cls} {...rest}>
      {content}
    </button>
  );
}
