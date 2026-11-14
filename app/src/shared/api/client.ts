// Typed fetch wrapper for the local AstroCare API. Base path is '/api' (same origin:
// Vite proxies it in dev, FastAPI serves it in production). Never call remote hosts.
//
//   const status = await api.get<AppStatus>('/status');
//   await api.post<Reading>('/readings/manual', { metric: 'bp_sys', value: 118 });

import { useCallback, useEffect, useRef, useState } from 'react';

export const API_BASE = '/api';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError(0, 'Local service unreachable');
  }
  const text = await res.text();
  const data = text ? safeJson(text) : undefined;
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `HTTP ${res.status}`, data);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>('GET', path, undefined, signal),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
};

export interface UseApiResult<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/**
 * React hook: GET `path` on mount (and every `refreshMs` if given).
 *   const { data, error, loading } = useApi<Alert[]>('/alerts?status=new');
 * Pass `null` as path to skip the request.
 */
export function useApi<T>(path: string | null, options: { refreshMs?: number } = {}): UseApiResult<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  const ctrl = useRef<AbortController>();
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (path === null) return;
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setLoading(true);
    api
      .get<T>(path, c.signal)
      .then((d) => {
        setData(d);
        setError(undefined);
      })
      .catch((e: unknown) => {
        if ((e as Error).name !== 'AbortError') setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [path, tick]);

  useEffect(() => {
    if (!options.refreshMs || path === null) return;
    const id = window.setInterval(reload, options.refreshMs);
    return () => window.clearInterval(id);
  }, [options.refreshMs, path, reload]);

  return { data, error, loading, reload };
}
