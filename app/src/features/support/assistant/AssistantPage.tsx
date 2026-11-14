// Assistant screen (owner: Marah): local chat with sources, missing info, refusals + CMO button.
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Bot, Send, User } from 'lucide-react';
import { Button, Card, PageHeader } from '../../../shared/components';
import { askAssistantStream, warmUpAssistant } from './api';
import { AnswerText } from './components/AnswerText';
import { CmoButton } from './components/CmoButton';
import { ModeBadge } from './components/ModeBadge';
import { SourceList } from './components/SourceList';
import { ModelInfoPanel } from './ModelInfoPanel';
import { PermissionsPanel } from './PermissionsPanel';
import type { AssistantAnswer } from './types';
import styles from './AssistantPage.module.css';

// After this long the UI says the local model is still working (proposal A5: assistant_slow_reply_ms).
const SLOW_REPLY_MS = 10000;

const READY_QUESTIONS = [
  'Why did I get the alert?',
  'How can sleep loss affect my performance on the mission?',
  'What does my data from the last 7 days show?',
  'Can I take melatonin to sleep better?', // shows the medication refusal
];

interface Turn {
  id: number;
  question: string;
  answer?: AssistantAnswer;
  partial?: string; // streamed text so far (before the final answer)
  firstTokenMs?: number | null;
  error?: string;
}

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [infoTick, setInfoTick] = useState(0);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void warmUpAssistant(); // load the models while the user reads the screen
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' });
  }, [turns, slow]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: q }]);
    setDraft('');
    setBusy(true);
    setSlow(false);
    const timer = window.setTimeout(() => setSlow(true), SLOW_REPLY_MS);
    try {
      const update = (f: (x: Turn) => Turn) => setTurns((t) => t.map((x) => (x.id === id ? f(x) : x)));
      const answer = await askAssistantStream(q, (ev) => {
        if (ev.type === 'token') {
          window.clearTimeout(timer);
          setSlow(false);
          update((x) => ({ ...x, partial: (x.partial ?? '') + ev.text }));
        } else if (ev.type === 'reset') {
          update((x) => ({ ...x, partial: undefined }));
        } else {
          update((x) => ({ ...x, answer: ev.answer, partial: undefined, firstTokenMs: ev.stats?.firstTokenMs ?? null }));
        }
      });
      update((x) => (x.answer ? x : { ...x, answer, partial: undefined }));
    } catch (e) {
      const msg = (e as Error).message || 'Unknown error';
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: msg } : x)));
    } finally {
      window.clearTimeout(timer);
      setBusy(false);
      setSlow(false);
      setInfoTick((n) => n + 1); // refresh measured latency / tokens per second
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(draft);
  }

  return (
    <div className={styles.page}>
      <PageHeader eyebrow="Runs on this device · no Earth link needed" title="Assistant" />

      <div className={styles.layout}>
        <Card
          title="Ask about your data"
          subtitle="Answers use only your data and the NASA/CSA references on board. No medication, dose or diagnosis advice."
          className={styles.chatCard}
        >
          <div className={styles.ready} role="group" aria-label="Ready-made questions">
            {READY_QUESTIONS.map((q) => (
              <Button key={q} variant="secondary" onClick={() => void ask(q)} disabled={busy} className={styles.readyBtn}>
                {q}
              </Button>
            ))}
          </div>

          <div className={styles.log} role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation">
            {turns.length === 0 && (
              <p className={styles.empty}>Pick a question above or type your own. You can ask in English or Arabic.</p>
            )}
            {turns.map((t) => (
              <div key={t.id} className={styles.turn}>
                <div className={`${styles.msg} ${styles.user}`}>
                  <User size={16} aria-hidden className={styles.avatar} />
                  <span className="sr-only">You asked: </span>
                  <p className={styles.question} dir="auto">
                    {t.question}
                  </p>
                </div>
                <div className={`${styles.msg} ${styles.bot}`}>
                  <Bot size={16} aria-hidden className={styles.avatar} />
                  <div className={styles.botBody}>
                    {!t.answer && !t.error && t.partial && (
                      <div className={styles.answerWrap} aria-busy="true">
                        <AnswerText text={stripCitations(t.partial)} />
                        <span className={styles.writing} role="status">
                          Writing on this device…
                        </span>
                      </div>
                    )}
                    {!t.answer && !t.error && !t.partial && (
                      <div role="status" className={styles.thinking}>
                        <span className={styles.dots} aria-hidden>
                          <span />
                          <span />
                          <span />
                        </span>
                        {slow
                          ? 'The local model is reading your data and the references…'
                          : 'Thinking on this device…'}
                      </div>
                    )}
                    {t.error && (
                      <div role="alert" className={styles.error}>
                        The assistant is not reachable right now ({t.error}). Check that the local AstroCare service is running.
                      </div>
                    )}
                    {t.answer && <AnswerView question={t.question} answer={t.answer} firstTokenMs={t.firstTokenMs} />}
                  </div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <form className={styles.form} onSubmit={onSubmit}>
            <label htmlFor="assistant-q" className="sr-only">
              Your question
            </label>
            <textarea
              id="assistant-q"
              className={styles.input}
              value={draft}
              dir="auto"
              rows={2}
              maxLength={2000}
              placeholder="Ask a question…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void ask(draft);
                }
              }}
            />
            <Button type="submit" disabled={busy || !draft.trim()} icon={<Send size={16} />} aria-label="Send question">
              Send
            </Button>
          </form>
        </Card>

        <aside className={styles.side} aria-label="Assistant settings">
          <ModelInfoPanel refreshKey={infoTick} />
          <PermissionsPanel />
        </aside>
      </div>
    </div>
  );
}

// While streaming, the model's own [n] numbers are hidden: the final answer renumbers them
// to match the source list.
const stripCitations = (s: string) => s.replace(/\s*\[\d+(?:,\s*\d+)*\]/g, '');

function AnswerView({
  question,
  answer,
  firstTokenMs,
}: {
  question: string;
  answer: AssistantAnswer;
  firstTokenMs?: number | null;
}) {
  return (
    <div className={styles.answerWrap}>
      <div className={styles.meta}>
        <ModeBadge mode={answer.mode} refused={answer.refused} />
        <span className={styles.latency}>
          {firstTokenMs != null && answer.mode === 'llm' && `first words ${(firstTokenMs / 1000).toFixed(1)} s · `}
          {(answer.latencyMs / 1000).toFixed(1)} s total
        </span>
      </div>

      {answer.refused ? (
        <div className={styles.refusal} role="note">
          <AnswerText text={answer.answer} />
          {answer.refusalReason === 'medication' && <CmoButton question={question} />}
        </div>
      ) : (
        <AnswerText text={answer.answer} />
      )}

      {answer.missing.length > 0 && (
        <p className={styles.missing}>
          <strong>Missing information:</strong> {answer.missing.join(' · ')}
        </p>
      )}
      <SourceList sources={answer.sources} />
    </div>
  );
}
