// Owner: Shahd. Full-screen "Are you OK?" check on the crew member's screen, on any page.
// Shown while an R-LOC-01 Watch is open. "I'm OK" works with click, tap, Enter and Space
// (Enter/Space handled on window, so they work wherever focus is). Focus stays on the button.
// The countdown comes from the server deadline; when it ends the server escalates and this
// closes (the red banner takes over). Experimental. Not a medical device.
import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../shared/api/client';
import { Button } from '../../shared/components';
import { EXPERIMENTAL_LABEL, respond } from './api.crew';
import { activeCheck } from './crewState';
import { useCrewFeed } from './crewFeed';
import styles from './Crew.module.css';

const OK_ID = 'loc-im-ok';
const ANNOUNCE_AT = new Set([30, 20, 10, 5]);

export function AreYouOkOverlay() {
  const feed = useCrewFeed();
  const check = activeCheck(feed.data);
  const [sentFor, setSentFor] = useState<string>();
  const [error, setError] = useState<string>();
  const [live, setLive] = useState('');
  const busy = useRef(false);

  const visible = !!check && sentFor !== check.id;
  const left = check ? feed.left(check.deadlineTs) : 0;
  const checkId = check?.id;
  const { reload } = feed;

  const ok = useRef<() => Promise<void>>(async () => {});
  ok.current = async () => {
    if (!checkId || busy.current) return;
    busy.current = true;
    setError(undefined);
    try {
      await respond(checkId);
      setSentFor(checkId);
    } catch (e) {
      setError(`Not sent: ${e instanceof ApiError ? e.message : String(e)}. Press “I'm OK” again.`);
    } finally {
      busy.current = false;
      reload();
    }
  };

  // Screen readers: announce as soon as the check opens, then at a few points, not every second.
  const announced = useRef<string>();
  useEffect(() => {
    if (!visible) return;
    if (announced.current !== checkId) {
      announced.current = checkId;
      setLive(`Are you OK? Press I'm OK. ${left} seconds to respond.`);
    } else if (ANNOUNCE_AT.has(left)) setLive(`Are you OK? Press I'm OK. ${left} seconds left.`);
    else if (left === 0)
      setLive(
        'No response. The CMO and the Commander are being alerted. You can still press I’m OK.',
      );
  }, [visible, left, checkId]);

  useEffect(() => {
    if (!visible) return;
    document.getElementById(OK_ID)?.focus();
    // Enter and Space answer from anywhere (preventDefault stops the button's own key click, so
    // one key press sends one response; mouse/touch use onClick). Tab keeps focus on the button.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        document.getElementById(OK_ID)?.focus();
      } else if (e.key === 'Enter' || e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        if (!e.repeat) void ok.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [visible, checkId]);

  if (!visible || !check) return null;

  return (
    <div
      className={styles.overlay}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="loc-question"
      aria-describedby="loc-desc"
    >
      <div className={styles.overlayBox}>
        <p className={styles.overlayEyebrow}>Safety check · {check.crewName}</p>
        <h2 id="loc-question" className={styles.question}>
          Are you OK?
        </h2>
        <p id="loc-desc" className={styles.overlayText}>
          Your sensors showed a sudden change. If you are all right, press “I'm OK”.
        </p>
        <Button id={OK_ID} className={styles.okButton} onClick={() => void ok.current()}>
          I'm OK
        </Button>
        <p className={`${styles.count} ${left === 0 ? styles.countZero : ''}`} aria-hidden>
          {left} s
        </p>
        <p className={styles.overlayText}>
          {left > 0
            ? `If there is no answer in ${left} seconds, the CMO and the Commander are alerted.`
            : 'No response: alerting the CMO and the Commander. You can still press “I’m OK”.'}
        </p>
        {error && (
          <p className={styles.overlayError} role="alert">
            {error}
          </p>
        )}
        <p className="sr-only" aria-live="assertive" aria-atomic="true">
          {live}
        </p>
        <p className={styles.experimental}>{EXPERIMENTAL_LABEL}</p>
      </div>
    </div>
  );
}
