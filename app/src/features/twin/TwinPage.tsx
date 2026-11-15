// Digital twin page (owner: Shahd). Lazy-loaded from routes.tsx so three.js stays out of the
// other pages' bundle. Every value comes from GET /api/twin/state and /api/twin/timeline; a system
// without data shows "No data". Visual summary only: not a medical device.
import { Box, List, RotateCcw } from 'lucide-react';
import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button, ErrorState, LoadingState, PageHeader, SimulatedBadge } from '../../shared/components';
import { useApi } from '../../shared/api/client';
import { NasaBasis } from '../daily';
import { hasWebGL, readTheme, usePageVisible, useReducedMotion, type TwinTheme } from './env';
import { RegionCard } from './panel/RegionCard';
import { RegionTable } from './panel/RegionTable';
import { SummaryPanel } from './panel/SummaryPanel';
import { Timeline } from './panel/Timeline';
import { TwinCanvas, type TwinCanvasHandle } from './scene/TwinCanvas';
import type { RegionId, TwinState, TwinTimeline } from './types';
import { DISCLAIMER, PATHS, viewingLabel } from './twinView';
import styles from './TwinPage.module.css';

const WHY =
  'NASA lists sleep loss, isolation, changed gravity (bone and muscle) and radiation among the main ' +
  'risks of spaceflight. This view puts the data the app already has for each of them on one body.';
const NASA_IDS = ['nasa-hrp-hazards', 'nasa-hrp-risks', 'nasa-bone-risk', 'nasa-hrp-sleep-risk'];

/** Any error inside the 3D view falls back to the list view instead of breaking the page. */
class CanvasBoundary extends Component<{ onFail: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onFail();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function TwinPage() {
  const live = useApi<TwinState>(PATHS.state, { refreshMs: 60_000 });
  const timeline = useApi<TwinTimeline>(PATHS.timeline);
  const reducedMotion = useReducedMotion();
  const visible = usePageVisible();
  const [webgl] = useState(hasWebGL);
  const [failed, setFailed] = useState(false);
  const [listView, setListView] = useState(!webgl);
  const [selected, setSelected] = useState<RegionId | null>(null);
  const [day, setDay] = useState<number | null>(null); // null = today (live)
  const [playing, setPlaying] = useState(false);
  const [theme, setTheme] = useState<TwinTheme | null>(null);
  const canvas = useRef<TwinCanvasHandle>(null);

  useEffect(() => setTheme(readTheme()), []);
  const onFail = useCallback(() => {
    setFailed(true);
    setListView(true);
  }, []);

  const today = live.data?.missionDay ?? timeline.data?.today ?? 0;
  const from = timeline.data?.fromDay ?? today;
  const history = day !== null && day !== today;
  const regions = useMemo(() => {
    if (history) return timeline.data?.days.find((d) => d.missionDay === day)?.regions ?? [];
    return live.data?.regions ?? [];
  }, [history, day, live.data, timeline.data]);
  const region = selected ? regions.find((r) => r.id === selected) : undefined;
  const show3d = !listView && webgl && !failed;
  const label = viewingLabel(day, today);

  if (live.loading && !live.data) return <LoadingState label="Loading digital twin…" />;
  if (live.error && !live.data) return <ErrorState message={live.error.message} onRetry={live.reload} />;

  return (
    <>
      <PageHeader
        eyebrow="Monitor"
        title={`Digital twin · Mission day ${today}`}
        actions={
          <div className={styles.actions}>
            <SimulatedBadge source={live.data?.simulated ? 'simulated' : 'sensor'} />
            {webgl && !failed && (
              <Button
                variant="secondary"
                aria-pressed={listView}
                onClick={() => setListView((v) => !v)}
                icon={listView ? <Box size={16} /> : <List size={16} />}
              >
                {listView ? '3D view' : 'List view'}
              </Button>
            )}
          </div>
        }
      />
      <p className={styles.disclaimer} role="note">
        {DISCLAIMER} All data is simulated. It shows possible patterns to review, never a diagnosis.
      </p>
      {(!webgl || failed) && (
        <p className={styles.notice} role="status">
          {failed
            ? 'The 3D view stopped working on this device, so the list view is shown.'
            : '3D graphics (WebGL) are not available on this device, so the list view is shown.'}
        </p>
      )}

      <div className={show3d ? styles.layout : styles.layoutList}>
        <div className={styles.main}>
          {show3d && theme ? (
            <div className={styles.stage}>
              <CanvasBoundary onFail={onFail}>
                <TwinCanvas
                  ref={canvas}
                  regions={regions}
                  theme={theme}
                  selected={selected}
                  reducedMotion={reducedMotion}
                  visible={visible}
                  onSelect={setSelected}
                  onFail={onFail}
                />
              </CanvasBoundary>
              <div className={styles.stageBar}>
                <span className={styles.stageLabel}>{label}</span>
                <Button
                  variant="secondary"
                  icon={<RotateCcw size={16} />}
                  onClick={() => {
                    setSelected(null);
                    canvas.current?.reset();
                  }}
                >
                  Reset view
                </Button>
              </div>
            </div>
          ) : (
            <RegionTable regions={regions} caption={`Body regions · ${label}`} history={history} />
          )}
          <Timeline
            from={from}
            today={today}
            day={day}
            playing={playing}
            loading={timeline.loading && !timeline.data}
            error={!!timeline.error && !timeline.data}
            onDay={setDay}
            onPlaying={setPlaying}
          />
        </div>

        <aside className={styles.side} aria-label="Region details">
          {region ? (
            <RegionCard
              region={region}
              history={history}
              reducedMotion={reducedMotion}
              onClose={() => setSelected(null)}
            />
          ) : (
            <SummaryPanel regions={regions} onSelect={setSelected} />
          )}
          <NasaBasis ids={NASA_IDS} why={WHY} />
        </aside>
      </div>
    </>
  );
}
