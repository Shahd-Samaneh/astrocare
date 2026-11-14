// Support pages (Marah + Noura). Noura owns this file; Marah adds her own lines.
// routes.tsx still imports pages/*.tsx, which re-export from here-style folders.

// ---- Noura ----
export { default as ReportsPage } from './reports/ReportsPage';
export * as reportsApi from './reports/api';
export type { ReportItem, ReportItemKind, SectionId, CommsStatus } from './reports/types';

// ---- Marah ----