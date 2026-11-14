// Daily log: fatigue banner, sleep, exercise, check-in. Each section has an anchor (#sleep, #exercise,
// #checkin) and the page scrolls to the one named in the URL hash.
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAppStatus } from '../../../shared/api/AppStatusContext';
import { AlertBanner, PageHeader, SectionHeader } from '../../../shared/components';
import { logApi, useDailyQuery } from '../api.log';
import { CheckInPanel } from '../index';
import { ExerciseSection } from '../exercise/ExerciseSection';
import { SleepSection } from '../sleep/SleepSection';
import styles from './DailyLog.module.css';

const FATIGUE_RULE_ID = 'R-FAT-01';
const FATIGUE_TEXT = 'Possible fatigue pattern today. Consider a lighter session.';

/** Mounted only while fatigueFlag is true: finds the open R-FAT-01 alert to link to. */
function FatigueBanner() {
  const { data } = useDailyQuery('alerts', () => logApi.alerts());
  const alert = data?.find((a) => a.ruleId === FATIGUE_RULE_ID && a.status !== 'closed');

  if (!alert) return null;

  // Same shared banner; only the headline is ours so it reads as advice for today's session.
  return (
    <AlertBanner
      alert={{ ...alert, title: FATIGUE_TEXT }}
      actionLabel="See the alert"
      actionTo={`/alerts/${alert.id}`}
    />
  );
}

export default function DailyLog() {
  const { hash } = useLocation();
  const { status } = useAppStatus();

  const today = useDailyQuery('today-plan', () => logApi.todayPlan());
  const sleep = useDailyQuery('sleep-summary', () => logApi.sleepSummary(7));

  const missionDay = today.data?.missionDay ?? status?.missionDay;
  const settled = !today.loading && !sleep.loading;

  // Scroll to #sleep / #exercise / #checkin once the page has its content.
  useEffect(() => {
    if (!hash || !settled) return;

    const el = document.getElementById(hash.slice(1));
    if (!el) return;

    el.scrollIntoView({ block: 'start' });

    const heading = el.querySelector<HTMLElement>('h2');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }, [hash, settled]);

  return (
    <>
      <PageHeader
        eyebrow={missionDay !== undefined ? `Mission day ${missionDay}` : undefined}
        title="Daily log"
      />

      <div className={styles.page}>
        {today.data?.fatigueFlag && <FatigueBanner />}

        <SleepSection query={sleep} onChanged={today.reload} />

        <ExerciseSection missionDay={missionDay} onChanged={today.reload} />

        <section id="checkin" aria-label="Check-in" className={styles.anchor}>
          <SectionHeader
            title="Check-in"
            description="How you feel today. Your private note stays private."
          />

          <CheckInPanel id="daily-checkin-panel" hideBasis />
        </section>
      </div>
    </>
  );
}
