// Relax (owner: Noura).
// Scene -> sound -> duration -> stress before (1–10) -> full screen with timer -> stress after -> saved.
// The session is saved when it STARTS, so an interrupted one is kept without "after".
import { useCallback, useEffect, useState } from 'react';
import { HeartHandshake, Leaf, Play, X } from 'lucide-react';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SimulatedBadge,
} from '../../../shared/components';
import { useApi } from '../../../shared/api/client';
import type { AudioMode } from '../../../shared/types/contracts';
import { addReportItem } from '../reports/api';
import { finishSession, startSession } from './api';
import { AUDIO_LABEL, DURATIONS, type Duration, type RelaxSession, type Scene } from './types';
import styles from './RelaxPage.module.css';

type Step = 'setup' | 'session' | 'after';

function sceneBg(scene: Scene | undefined) {
  if (!scene) return { className: styles.gDefault, style: undefined };
  if (scene.image) return { className: styles.imageBg, style: { backgroundImage: `url(${scene.image})` } };
  return { className: styles[`g-${scene.id}`] ?? styles.gDefault, style: undefined };
}

function mmss(sec: number) {
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

function StressScale({
  name,
  label,
  value,
  onChange,
}: {
  name: string;
  label: string;
  value: number | null;
  onChange: (n: number) => void;
}) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>{label}</legend>
      <div className={styles.scale}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
          <label key={n} className={`${styles.scaleBtn} ${value === n ? styles.scaleOn : ''}`}>
            <input
              type="radio"
              name={name}
              value={n}
              checked={value === n}
              onChange={() => onChange(n)}
              className="sr-only"
            />
            {n}
          </label>
        ))}
      </div>
      <div className={styles.scaleEnds} aria-hidden>
        <span>1 · calm</span>
        <span>10 · very stressed</span>
      </div>
    </fieldset>
  );
}

export default function RelaxPage() {
  const scenes = useApi<Scene[]>('/relax/scenes');
  const history = useApi<RelaxSession[]>('/relax/sessions?n=10');

  const [sceneId, setSceneId] = useState<string | null>(null);
  const [audioMode, setAudioMode] = useState<AudioMode>('nature');
  const [duration, setDuration] = useState<Duration>(5);
  const [before, setBefore] = useState<number | null>(null);
  const [after, setAfter] = useState<number | null>(null);
  const [step, setStep] = useState<Step>('setup');
  const [session, setSession] = useState<RelaxSession | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [endedEarly, setEndedEarly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const scene = scenes.data?.find((s) => s.id === sceneId) ?? scenes.data?.[0];
  const mode: AudioMode = scene && scene.audio.includes(audioMode) ? audioMode : (scene?.audio[0] ?? 'none');
  const audioSrc = mode === 'none' ? null : (scene?.audioFiles[mode] ?? null);
  const sceneName = (id: string) => scenes.data?.find((s) => s.id === id)?.name ?? id;

  const endSession = useCallback((early: boolean) => {
    setEndedEarly(early);
    setStep('after');
    if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
  }, []);

  // countdown
  useEffect(() => {
    if (step !== 'session') return;
    const id = window.setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => window.clearInterval(id);
  }, [step]);

  useEffect(() => {
    if (step === 'session' && remaining === 0) endSession(false);
  }, [step, remaining, endSession]);

  // leaving full screen (Esc) ends the session early
  useEffect(() => {
    if (step !== 'session') return;
    document.getElementById('relax-exit')?.focus();
    const onChange = () => {
      if (!document.fullscreenElement) endSession(true);
    };
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, [step, endSession]);

  async function start() {
    if (!scene || before === null) return;
    setBusy(true);
    setMessage(null);
    document.documentElement.requestFullscreen?.().catch(() => undefined); // must run inside the click
    try {
      const s = await startSession({ sceneId: scene.id, audioMode: mode, durationMin: duration, stressBefore: before });
      setSession(s);
      setAfter(null);
      setRemaining(duration * 60);
      setStep('session');
    } catch (e) {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
      setMessage({ kind: 'error', text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  function reset(text: string) {
    setStep('setup');
    setSession(null);
    setBefore(null);
    setAfter(null);
    setMessage({ kind: 'ok', text });
    history.reload();
  }

  async function saveAfter() {
    if (!session || after === null) return;
    setBusy(true);
    try {
      await finishSession(session.id, after);
      reset(`Saved: stress ${session.stressBefore} → ${after}.`);
    } catch (e) {
      setMessage({ kind: 'error', text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function requestSupport() {
    setBusy(true);
    try {
      await addReportItem({
        kind: 'note',
        title: 'Crew member requested support',
        text: 'Requested from the Relax screen. Please follow up at the next comm window.',
        sourceFeature: 'relax',
      });
      setMessage({ kind: 'ok', text: 'Support request added to the next report for the flight surgeon.' });
    } catch (e) {
      setMessage({ kind: 'error', text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const bg = sceneBg(scene);

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Support · Wellbeing"
        title="Relax"
        actions={
          <Button variant="secondary" icon={<HeartHandshake size={16} />} onClick={requestSupport} disabled={busy}>
            Request support
          </Button>
        }
      />

      {message && (
        <p className={message.kind === 'ok' ? styles.ok : styles.error} role={message.kind === 'ok' ? 'status' : 'alert'}>
          {message.text}
        </p>
      )}

      {/* ---- full-screen session ---- */}
      {step === 'session' && (
        <div
          className={`${styles.overlay} ${bg.className}`}
          style={bg.style}
          role="dialog"
          aria-modal="true"
          aria-label={`Relaxation session: ${scene?.name ?? ''}`}
          onKeyDown={(e) => e.key === 'Escape' && endSession(true)}
        >
          {audioSrc && <audio src={audioSrc} autoPlay loop />}
          <div className={styles.breath} aria-hidden />
          <p className={styles.overlayScene}>{scene?.name}</p>
          <p className={styles.timer} aria-live="off">
            {mmss(remaining)}
          </p>
          <p className={styles.overlayHint}>
            Breathe in as the circle grows, out as it shrinks · {AUDIO_LABEL[mode]}
            {mode !== 'none' && !audioSrc && ' (audio file not added yet)'}
          </p>
          <Button id="relax-exit" variant="secondary" icon={<X size={16} />} onClick={() => endSession(true)}>
            End session
          </Button>
        </div>
      )}

      {/* ---- after ---- */}
      {step === 'after' && session && (
        <Card
          title={endedEarly ? 'Session ended early' : 'Session complete'}
          subtitle="Your session is already saved. Rating how you feel now is optional."
        >
          <StressScale name="after" label="Stress now (1–10)" value={after} onChange={setAfter} />
          <div className={styles.actions}>
            <Button onClick={saveAfter} disabled={after === null || busy}>
              Save rating
            </Button>
            <Button variant="ghost" onClick={() => reset('Saved without an “after” rating.')}>
              Skip
            </Button>
          </div>
        </Card>
      )}

      {/* ---- setup ---- */}
      {step === 'setup' && (
        <Card title="New session" subtitle="Pick a scene, a sound and a length. Everything plays from this device.">
          {scenes.loading && !scenes.data && <LoadingState />}
          {scenes.error && <ErrorState message={scenes.error.message} onRetry={scenes.reload} />}
          {scenes.data && (
            <div className={styles.form}>
              <fieldset className={styles.fieldset}>
                <legend className={styles.legend}>Scene</legend>
                <div className={styles.scenes}>
                  {scenes.data.map((s) => {
                    const b = sceneBg(s);
                    return (
                      <label
                        key={s.id}
                        className={`${styles.sceneCard} ${b.className} ${scene?.id === s.id ? styles.sceneOn : ''}`}
                        style={b.style}
                      >
                        <input
                          type="radio"
                          name="scene"
                          value={s.id}
                          checked={scene?.id === s.id}
                          onChange={() => setSceneId(s.id)}
                          className="sr-only"
                        />
                        <span className={styles.sceneName}>{s.name}</span>
                        <span className={styles.sceneDesc}>{s.description}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <div className={styles.row2}>
                <fieldset className={styles.fieldset}>
                  <legend className={styles.legend}>Sound</legend>
                  <div className={styles.pills}>
                    {(scene?.audio ?? []).map((m) => (
                      <label key={m} className={`${styles.pill} ${mode === m ? styles.pillOn : ''}`}>
                        <input
                          type="radio"
                          name="audio"
                          value={m}
                          checked={mode === m}
                          onChange={() => setAudioMode(m)}
                          className="sr-only"
                        />
                        {AUDIO_LABEL[m]}
                      </label>
                    ))}
                  </div>
                </fieldset>

                <fieldset className={styles.fieldset}>
                  <legend className={styles.legend}>Length</legend>
                  <div className={styles.pills}>
                    {DURATIONS.map((d) => (
                      <label key={d} className={`${styles.pill} ${duration === d ? styles.pillOn : ''}`}>
                        <input
                          type="radio"
                          name="duration"
                          value={d}
                          checked={duration === d}
                          onChange={() => setDuration(d)}
                          className="sr-only"
                        />
                        {d} min
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>

              <StressScale name="before" label="Stress right now (1–10)" value={before} onChange={setBefore} />

              <div className={styles.actions}>
                <Button icon={<Play size={16} />} onClick={start} disabled={before === null || busy}>
                  Start {duration}-minute session
                </Button>
                {before === null && <span className={styles.hint}>Rate your stress first.</span>}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ---- history ---- */}
      <Card
        title="Past sessions"
        subtitle="Stress before → after"
        actions={
          <span className={styles.simLine}>
            <SimulatedBadge /> includes simulated data
          </span>
        }
      >
        {history.loading && !history.data && <LoadingState />}
        {history.error && <ErrorState message={history.error.message} onRetry={history.reload} />}
        {history.data && history.data.length === 0 && <EmptyState title="No sessions yet" />}
        {history.data && history.data.length > 0 && (
          <ul className={styles.history}>
            {history.data.map((s) => (
              <li key={s.id} className={styles.histRow}>
                <Leaf size={16} aria-hidden className={styles.histIcon} />
                <span className={styles.histMain}>
                  <strong>{sceneName(s.sceneId)}</strong>
                  <span className={styles.hint}>
                    {new Date(s.ts).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    {' · '}
                    {s.durationMin} min · {AUDIO_LABEL[s.audioMode]}
                  </span>
                </span>
                <span className={styles.histStress}>
                  {s.stressBefore} → {s.stressAfter ?? <em className={styles.hint}>not rated</em>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}