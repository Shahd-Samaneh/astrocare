// Calls for the Reports screen. Relative /api paths only (same origin, offline).
import { api, API_BASE, ApiError } from '../../../shared/api/client';
import type { ReportItem, ReportOut, SectionId, SourceFeature, ReportItemKind } from './types';

export const createReport = (sections: SectionId[], itemIds: string[]) =>
  api.post<ReportOut>('/reports', { sections, itemIds });

export const queueReport = (id: string) => api.post<ReportOut>(`/reports/${id}/queue`);

export const simulateWindow = () =>
  api.post<{ windowId: string; openedTs: string; sentReportIds: string[] }>('/comms/simulate-window');

export const addReportItem = (body: {
  kind: ReportItemKind;
  title: string;
  text: string;
  sourceFeature: SourceFeature;
  refId?: string;
}) => api.post<ReportItem>('/reports/items', body);

// shared api has no DELETE yet (proposal N3), so use fetch directly.
export async function deleteReportItem(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/items/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
}

export const reportFileUrl = (id: string, format: 'pdf' | 'json' = 'pdf') =>
  `${API_BASE}/reports/${id}/file?format=${format}`;