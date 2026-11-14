// App frame: SideNav | (OfflineStatusBar over the routed page).
// Badge counts: new alerts (GET /api/alerts?status=new) and unsent reports (GET /api/reports).
import { Outlet } from 'react-router-dom';
import { AppStatusProvider } from '../api/AppStatusContext';
import { useApi } from '../api/client';
import { OfflineStatusBar } from '../components/OfflineStatusBar';
import { SideNav } from '../components/SideNav';
import type { Alert, Report } from '../types/contracts';
import styles from './AppShell.module.css';

// TODO(Haya): read real on-device storage use once the backend exposes it.
const STORAGE_USED_GB = 3.4;
const STORAGE_TOTAL_GB = 64;

export function AppShell() {
  const alerts = useApi<Alert[]>('/alerts?status=new', { refreshMs: 30_000 });
  const reports = useApi<Report[]>('/reports', { refreshMs: 30_000 });
  const pendingReports = reports.data?.filter((r) => r.status !== 'sent').length ?? 0;

  return (
    <AppStatusProvider>
      <a href="#main" className={styles.skip}>
        Skip to content
      </a>
      <div className={styles.shell}>
        <SideNav
          alertCount={alerts.data?.length ?? 0}
          reportCount={pendingReports}
          storageUsedGb={STORAGE_USED_GB}
          storageTotalGb={STORAGE_TOTAL_GB}
        />
        <div className={styles.column}>
          <OfflineStatusBar />
          <main id="main" className={styles.main} tabIndex={-1}>
            <Outlet />
          </main>
        </div>
      </div>
    </AppStatusProvider>
  );
}
