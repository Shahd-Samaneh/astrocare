// Provides GET /api/status to the whole app, refreshed every 30 s.
//   const { status, error } = useAppStatus();
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { AppStatus } from '../types/contracts';
import { useApi, type ApiError } from './client';

interface AppStatusValue {
  status: AppStatus | undefined;
  error: ApiError | undefined;
  /** Date.now() when `status` was last received (used to tick the MET clock). */
  receivedAt: number;
}

const Ctx = createContext<AppStatusValue>({ status: undefined, error: undefined, receivedAt: 0 });

export function AppStatusProvider({ children }: { children: ReactNode }) {
  const { data, error } = useApi<AppStatus>('/status', { refreshMs: 30_000 });
  const [receivedAt, setReceivedAt] = useState(() => Date.now());
  useEffect(() => {
    if (data) setReceivedAt(Date.now());
  }, [data]);
  return <Ctx.Provider value={{ status: data, error, receivedAt }}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAppStatus = () => useContext(Ctx);
