// App frame: SideNav | (OfflineStatusBar over the routed page).
// Badge counts: new alerts (GET /api/alerts?status=new) and unsent reports (GET /api/reports).
// Crew alerts (features/crew, R-LOC-01): one poll of GET /api/crew/emergencies feeds the side-nav
// dot/count, the red emergency banner on every page and the full-screen "Are you OK?" check.
import { Outlet } from 'react-router-dom';
import { AppStatusProvider } from '../api/AppStatusContext';
import { useApi } from '../api/client';
import { AreYouOkOverlay } from '../../features/crew/AreYouOkOverlay';
import { EmergencyBanner } from '../../features/crew/EmergencyBanner';
import { CrewFeedContext, useCrewFeedSource } from '../../features/crew/crewFeed';
import { navState } from '../../features/crew/crewState';
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
  const crew = useCrewFeedSource();
  const crewNav = navState(crew.data);

  return (
    <AppStatusProvider>
      <CrewFeedContext.Provider value={crew}>
        <a href="#main" className={styles.skip}>
          Skip to content
        </a>
        <div className={styles.shell}>
          <SideNav
            alertCount={alerts.data?.length ?? 0}
            reportCount={pendingReports}
            crewEmergencyCount={crewNav.emergencies}
            crewWatch={crewNav.watch}
            storageUsedGb={STORAGE_USED_GB}
            storageTotalGb={STORAGE_TOTAL_GB}
          />
          <div className={styles.column}>
            <OfflineStatusBar />
            <EmergencyBanner />
            <main id="main" className={styles.main} tabIndex={-1}>
              <Outlet />
            </main>
          </div>
        </div>
        <AreYouOkOverlay />
      </CrewFeedContext.Provider>
    </AppStatusProvider>
  );
}
