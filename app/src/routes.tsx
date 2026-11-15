// All routes. Each SideNav item has a route here (see NAV_GROUPS in shared/components/SideNav.tsx).
import type { RouteObject } from 'react-router-dom';
import AttentionCheck from './features/daily/pages/AttentionCheck';
import DailyLog from './features/daily/pages/DailyLog';
import AlertDetail from './features/monitoring/pages/AlertDetail';
import Bone from './features/monitoring/pages/Bone';
import Profile from './features/monitoring/pages/Profile';
import Radiation from './features/monitoring/pages/Radiation';
import Resources from './features/monitoring/pages/Resources';
import Today from './features/monitoring/pages/Today';
import Vision from './features/monitoring/pages/Vision';
import Vitals from './features/monitoring/pages/Vitals';
import Assistant from './features/support/pages/Assistant';
import Relax from './features/support/pages/Relax';
import Reports from './features/support/pages/Reports';
import { EmptyState, Button } from './shared/components';
import { AppShell } from './shared/layout/AppShell';

export const pageRoutes: RouteObject[] = [
  { index: true, element: <Today /> },
  { path: 'vitals', element: <Vitals /> },
  { path: 'alerts', element: <AlertDetail /> },
  { path: 'alerts/:id', element: <AlertDetail /> },
  { path: 'daily', element: <DailyLog /> },
  { path: 'attention', element: <AttentionCheck /> },
  { path: 'relax', element: <Relax /> },
  { path: 'radiation', element: <Radiation /> },
  { path: 'bone', element: <Bone /> },
  { path: 'vision', element: <Vision /> },
  { path: 'assistant', element: <Assistant /> },
  { path: 'resources', element: <Resources /> },
  { path: 'reports', element: <Reports /> },
  { path: 'profile', element: <Profile /> },
  {
    path: '*',
    element: <EmptyState title="Page not found" action={<Button to="/">Back to Today</Button>} />,
  },
];

export const routes: RouteObject[] = [{ path: '/', element: <AppShell />, children: pageRoutes }];
