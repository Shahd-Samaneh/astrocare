// Left navigation. Active state comes from the router (NavLink).
//   <SideNav alertCount={2} reportCount={1} storageUsedGb={3.4} storageTotalGb={64} />
//   crewEmergencyCount / crewWatch: Crew alerts red count (unacknowledged emergencies) / yellow dot (open watch).
// Collapses to an icon-only rail below 900px (labels stay available to screen readers).
import type { LucideIcon } from 'lucide-react';
import {
  Activity, Bell, Bone, CalendarDays, Eye, FileText, LayoutGrid, Leaf, Lock, MessageSquare, Package,
  Radiation, Siren, Target, User,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { Logo } from './Logo';
import styles from './SideNav.module.css';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badge?: 'alerts' | 'reports' | 'crew';
}

export interface NavGroup {
  label: string;
  tone?: 'pink';
  items: NavItem[];
}

// eslint-disable-next-line react-refresh/only-export-components
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Monitor',
    items: [
      { to: '/', label: 'Today', icon: LayoutGrid },
      { to: '/vitals', label: 'Vitals', icon: Activity },
      { to: '/alerts', label: 'Alerts', icon: Bell, badge: 'alerts' },
    ],
  },
  {
    label: 'Daily',
    items: [
      { to: '/daily', label: 'Daily log', icon: CalendarDays },
      { to: '/attention', label: 'Attention check', icon: Target },
      { to: '/relax', label: 'Relax', icon: Leaf },
    ],
  },
  {
    label: 'Space medicine',
    tone: 'pink',
    items: [
      { to: '/radiation', label: 'Radiation', icon: Radiation },
      { to: '/bone', label: 'Bone & muscle', icon: Bone },
      { to: '/vision', label: 'Vision check', icon: Eye },
    ],
  },
  {
    label: 'Support',
    items: [
      { to: '/crew', label: 'Crew alerts', icon: Siren, badge: 'crew' },
      { to: '/assistant', label: 'Assistant', icon: MessageSquare },
      { to: '/resources', label: 'Resources', icon: Package },
      { to: '/reports', label: 'Reports', icon: FileText, badge: 'reports' },
      { to: '/profile', label: 'Profile', icon: User },
    ],
  },
];

export interface SideNavProps {
  alertCount?: number;
  reportCount?: number;
  crewEmergencyCount?: number;
  crewWatch?: boolean;
  storageUsedGb: number;
  storageTotalGb: number;
}

export function SideNav({
  alertCount = 0, reportCount = 0, crewEmergencyCount = 0, crewWatch = false, storageUsedGb, storageTotalGb,
}: SideNavProps) {
  const pct = storageTotalGb > 0 ? Math.min(100, (storageUsedGb / storageTotalGb) * 100) : 0;
  const counts = { alerts: alertCount, reports: reportCount, crew: crewEmergencyCount };

  return (
    <nav className={styles.nav} aria-label="Main">
      <div className={styles.brand}>
        <Logo size={34} />
        <div className={styles.brandText}>
          <span className={styles.name}>AstroCare</span>
          <span className={styles.tagline}>Space medicine · on-device</span>
        </div>
      </div>

      <div className={styles.groups}>
        {NAV_GROUPS.map((g) => (
          <div key={g.label} className={styles.group} role="group" aria-labelledby={`nav-${g.label}`}>
            <div id={`nav-${g.label}`} className={`${styles.groupLabel} ${g.tone === 'pink' ? styles.pink : ''}`}>
              {g.label}
            </div>
            <ul className={styles.list}>
              {g.items.map((item) => {
                const count = item.badge ? counts[item.badge] : 0;
                const Icon = item.icon;
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === '/'}
                      title={item.label}
                      className={({ isActive }) => `${styles.item} ${isActive ? styles.active : ''}`}
                    >
                      <Icon size={18} aria-hidden />
                      <span className={styles.label}>{item.label}</span>
                      {item.badge === 'crew' && crewWatch && count === 0 && (
                        <span className={styles.dotWarn} role="img" aria-label="Watch open" />
                      )}
                      {count > 0 && (
                        <span
                          className={`${styles.badge} ${item.badge === 'alerts' ? styles.badgeWarn : item.badge === 'crew' ? styles.badgeDanger : styles.badgeChip}`}
                          aria-label={`${count} ${item.badge === 'alerts' ? 'new alerts' : item.badge === 'crew' ? 'unacknowledged emergencies' : 'reports pending'}`}
                        >
                          {count}
                        </span>
                      )}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className={styles.footer}>
        <div className={styles.footerHead}>
          <Lock size={16} className={styles.lock} aria-hidden />
          <span className={styles.footerTitle}>All data on this device</span>
        </div>
        <div className={styles.footerBody}>
          <p className={styles.footerLine}>Encrypted · works without Earth link</p>
          <div
            className={styles.bar}
            role="progressbar"
            aria-label="Storage used"
            aria-valuemin={0}
            aria-valuemax={storageTotalGb}
            aria-valuenow={storageUsedGb}
          >
            <div className={styles.fill} style={{ width: `${pct}%` }} />
          </div>
          <p className={styles.footerLine}>
            Storage {storageUsedGb} of {storageTotalGb} GB
          </p>
        </div>
      </div>
    </nav>
  );
}
