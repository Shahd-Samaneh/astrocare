// Assistant screen (owner: Marah): local chat with sources, missing info, refusals + CMO button.
// Layout: question bubbles on the end side, answer bubbles (sources, missing, health note inside)
// on the start side, ready-made chips just above the composer.
// The conversation lives in chatStore (kept when you leave the page and come back).
// /assistant?q=<text> asks that question once, on arrival (proposal A14).
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowUp, Pill, Trash2 } from 'lucide-react';
import { useApi } from '../../../shared/api/client';
import { Button, Card, PageHeader } from '../../../shared/components';
import type { Alert } from '../../../shared/types/contracts';
import { warmUpAssistant } from './api';
import { askQuestion, clearChat, getChat, markReported, useChat, type Turn } from './chatStore';
import { EMPTY_STATE, HEALTH_NOTE, isArabic, MODEL_STATUS_TEXT, modelStatus, showsHealthNote, type ModelStatus } from './chatView';
import { AnswerText } from './components/AnswerText';
import { CmoButton } from './components/CmoButton';
import { ModeBadge } from './components/ModeBadge';
import { NextSteps } from './components/NextSteps';
import { ReportButton } from './components/ReportButton';
import { SourceList } from './components/SourceList';
import { ModelInfoPanel } from './ModelInfoPanel';
import { PermissionsPanel } from './PermissionsPanel';
import { readyQuestions, uiLang } from './readyQuestions';
import { noteReportItem, stripCitations } from './reportItems';
import type { AssistantInfo } from './types';
import styles from './AssistantPage.module.css';

export default function AssistantPage() {
  const { turns, busy, slow, answered } = useChat();
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const [params, setParams] = useSearchParams();
  const askedFromUrl = useRef<string | null>(null);
  const { data: alerts } = useApi<Alert[]>('/alerts', { refreshMs: 60000 });
  const lang = uiLang();
  const chips = readyQuestions(alerts, lang);
  // one /assistant/info read, shared by the header pill and the "Local model" panel
  const info = useApi<AssistantInfo>('/assistant/info');
  const reloadInfo = info.reload;
  const [warming, setWarming] = useState(true);
  const status = modelStatus({ reachable: info.data?.reachable, warming, failed: !!info.error });

  useEffect(() => {
    let live = true;
    // load the models while the user reads the screen, then re-read the model info
    void warmUpAssistant().finally(() => {
      if (!live) return;
      setWarming(false);
      reloadInfo();
    });
    return () => {
      live = false;
    };
  }, [reloadInfo]);

  useEffect(() => {
    if (answered) reloadInfo(); // the measured latency changes after each answer
  }, [answered, reloadInfo]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' });
  }, [turns, slow]);

  // /assistant?q=...: ask it once, then drop ?q from the URL (replace: Back and reload don't re-ask)
  useEffect(() => {
    const q = params.get('q')?.trim();
    if (!q) {
      askedFromUrl.current = null; // ?q is gone: the same link may ask again later
      return;
    }
    if (askedFromUrl.current === q) return; // StrictMode runs this effect twice: ask once
    askedFromUrl.current = q;
    const next = new URLSearchParams(params);
    next.delete('q');
    setParams(next, { replace: true });
    if (getChat().busy || !askQuestion(q)) setDraft(q); // another answer is still coming: keep it ready to send
  }, [params, setParams]);

  function ask(question: string) {
    if (askQuestion(question)) setDraft('');
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    ask(draft);
  }

  return (
    <div className={styles.page}>
      <PageHeader eyebrow="Runs on this device · no Earth link needed" title="Assistant" />

      <div className={styles.layout}>
        <Card
          title="Ask about your data"
          subtitle="Explains your data using references stored on this device"
          className={styles.chatCard}
          actions={
            <div className={styles.headActions}>
              <StatusPill status={status} />
              {turns.length > 0 && (
                <Button
                  variant="ghost"
                  icon={<Trash2 size={18} />}
                  onClick={clearChat}
                  disabled={busy}
                  aria-label="Clear chat"
                  title="Clear chat"
                  className={styles.iconBtn}
                />
              )}
            </div>
          }
        >
          <div className={styles.log} role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation">
            {turns.length === 0 && (
              <div className={styles.empty} lang={lang} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
                {EMPTY_STATE[lang].map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
            )}
            {turns.map((t) => (
              <TurnView key={t.id} turn={t} slow={slow} />
            ))}
            <div ref={endRef} />
          </div>

          <div className={styles.composer}>
            <div className={styles.ready} role="group" aria-label="Ready-made questions">
              {chips.map((q) => (
                <Button
                  key={q}
                  variant="secondary"
                  onClick={() => ask(q)}
                  disabled={busy}
                  className={styles.readyBtn}
                  dir="auto"
                >
                  {q}
                </Button>
              ))}
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
                rows={1}
                maxLength={2000}
                placeholder="Ask a question…"
                aria-describedby="assistant-q-privacy"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    ask(draft);
                  }
                }}
              />
              <Button
                type="submit"
                disabled={busy || !draft.trim()}
                icon={<ArrowUp size={20} />}
                aria-label="Send"
                className={styles.send}
              />
            </form>
            <p id="assistant-q-privacy" className={styles.privacy}>
              Runs on this device. Nothing you type leaves it.
            </p>
          </div>
        </Card>

        <aside className={styles.side} aria-label="Assistant settings">
          <ModelInfoPanel data={info.data} error={info.error} loading={info.loading} />
          <PermissionsPanel />
          <p className={styles.sideNote}>
            The assistant explains and summarises. It never decides treatment and always shows its sources.
          </p>
        </aside>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: ModelStatus }) {
  const tone = { ready: styles.pillReady, loading: styles.pillLoading, off: styles.pillOff }[status];
  return (
    <span className={`${styles.pill} ${tone}`} role="status">
      <span className={styles.dot} aria-hidden />
      {MODEL_STATUS_TEXT[status]}
    </span>
  );
}

function TurnView({ turn: t, slow }: { turn: Turn; slow: boolean }) {
  const pending = !t.answer && !t.error && !t.interrupted;
  const refused = !!t.answer?.refused;
  return (
    <div className={styles.turn}>
      <div className={`${styles.bubble} ${styles.user}`}>
        <span className="sr-only">You asked: </span>
        <p className={styles.question} dir="auto">
          {t.question}
        </p>
      </div>
      <div className={`${styles.bubble} ${styles.bot} ${refused ? styles.refusal : ''}`}>
        <span className="sr-only">Assistant: </span>
        {pending && t.partial && (
          <div className={styles.answerWrap} aria-busy="true">
            {/* while streaming, the model's own [n] numbers are hidden: the final answer renumbers them */}
            <AnswerText text={stripCitations(t.partial)} />
            <span className={styles.writing} role="status">
              Writing on this device…
            </span>
          </div>
        )}
        {pending && !t.partial && (
          <div role="status" className={styles.thinking}>
            <span className={styles.dots} aria-hidden>
              <span />
              <span />
              <span />
            </span>
            {slow ? 'The local model is reading your data and the references…' : 'Thinking on this device…'}
          </div>
        )}
        {t.error && (
          <div role="alert" className={styles.error}>
            The assistant is not reachable right now ({t.error}). Check that the local AstroCare service is running.
          </div>
        )}
        {t.interrupted && !t.answer && !t.error && (
          <p className={styles.note}>This question was still being answered when the page reloaded. Ask it again.</p>
        )}
        {t.answer && <AnswerView turn={t} />}
      </div>
    </div>
  );
}

function AnswerView({ turn }: { turn: Turn }) {
  const { question, firstTokenMs, reported } = turn;
  const answer = turn.answer!;
  const cmo = answer.refused && answer.refusalReason === 'medication';
  const lang = isArabic(answer.answer) ? 'ar' : 'en';
  const onDone = () => markReported(turn.id);
  return (
    <div className={styles.answerWrap}>
      <div className={styles.meta}>
        <ModeBadge mode={answer.mode} refused={answer.refused} alertRuleId={answer.alertRuleId} />
        <span className={styles.latency}>
          {firstTokenMs != null && answer.mode === 'llm' && `first words ${(firstTokenMs / 1000).toFixed(1)} s · `}
          {(answer.latencyMs / 1000).toFixed(1)} s total
        </span>
      </div>
      {answer.note && (
        <p className={styles.note} dir="auto">
          {answer.note}
        </p>
      )}

      <div role={answer.refused ? 'note' : undefined}>
        <AnswerText text={answer.answer} />
      </div>
      <NextSteps steps={answer.nextSteps} />

      {answer.missing.length > 0 && (
        <p className={styles.missing} dir="auto">
          <strong>Missing:</strong> {answer.missing.join(' · ')}
        </p>
      )}
      {showsHealthNote(answer) && (
        <p className={styles.healthNote} lang={lang} dir={lang === 'ar' ? 'rtl' : 'ltr'}>
          {HEALTH_NOTE[lang]}
        </p>
      )}
      <SourceList sources={answer.sources} />

      {cmo ? (
        // a medication refusal: its CMO button also adds the question to the report
        <div className={styles.refusalActions}>
          <Button variant="secondary" to="/resources" icon={<Pill size={16} />}>
            View medicines &amp; equipment
          </Button>
          <CmoButton question={question} done={reported} onDone={onDone} />
        </div>
      ) : (
        <ReportButton
          item={noteReportItem(question, answer)}
          label="Add to report"
          doneText="Added to the report."
          what="answer"
          variant="ghost"
          done={reported}
          onDone={onDone}
        />
      )}
    </div>
  );
}
