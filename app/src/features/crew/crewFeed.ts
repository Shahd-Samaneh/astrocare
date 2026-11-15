// Owner: Shahd. One shared poll of GET /api/crew/emergencies for the whole app.
// AppShell calls useCrewFeedSource() once and provides it with <CrewFeedContext.Provider>;
// the overlay, banner, side-nav dot and the Crew alerts page read it with useCrewFeed().
import { createContext, useContext, useEffect, useState } from 'react';
import { useApi } from '../../shared/api/client';
import { CREW_PATH, type CrewEmergencies } from './api.crew';
import { pollMs, secondsLeft } from './crewState';

export interface CrewFeed {
  data: CrewEmergencies | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
  /** Seconds left on a watch's countdown, from the server clock. */
  left: (deadlineTs: string) => number;
}

export function useCrewFeedSource(): CrewFeed {
  const [interval, setIntervalMs] = useState(3000);
  const feed = useApi<CrewEmergencies>(CREW_PATH, { refreshMs: interval });
  const [fetchedAt, setFetchedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!feed.data) return;
    setFetchedAt(Date.now());
    setIntervalMs(pollMs(feed.data));
  }, [feed.data]);

  const counting = feed.data?.open.some((e) => e.status === 'watch') ?? false;
  useEffect(() => {
    if (!counting) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [counting]);

  return {
    data: feed.data,
    error: feed.error,
    loading: feed.loading,
    reload: feed.reload,
    left: (deadlineTs) =>
      feed.data
        ? secondsLeft(deadlineTs, feed.data.serverTs, fetchedAt, Math.max(now, fetchedAt))
        : 0,
  };
}

const EMPTY: CrewFeed = {
  data: undefined,
  error: undefined,
  loading: false,
  reload: () => {},
  left: () => 0,
};

export const CrewFeedContext = createContext<CrewFeed>(EMPTY);

export const useCrewFeed = () => useContext(CrewFeedContext);
