// Assistant screen (owner: Marah): local chat with sources, missing info, refusals + CMO button.
// The conversation lives in chatStore (kept when you leave the page and come back).
// /assistant?q=<text> asks that question once, on arrival (proposal A14).
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bot, Send, Trash2, User } from 'lucide-react';
import { useApi } from '../../../shared/api/client';
import { Button, Card, PageHeader } from '../../../shared/components';
import type { Alert } from '../../../shared/types/contracts';
import { warmUpAssistant } from './api';
import { askQuestion, clearChat, getChat, markReported, useChat, type Turn } from './chatStore';
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
import styles from './AssistantPage.module.css';

export default function AssistantPage() {
  const { turns, busy, slow, answered } = useChat();
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const [params, setParams] = useSearchParams();
  const askedFromUrl = useRef<string | null>(null);
  const { data: alerts } = useApi<Alert[]>('/alerts', { refreshMs: 60000 });
  const chips = readyQuestions(alerts, uiLang());

  useEffect(() => {
    void warmUpAssistant(); // load the models while the user reads the screen
  }, []);

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
          subtitle="Answers use only your data and the NASA/CSA references on board. No medication, dose or diagnosis advice."
          className={styles.chatCard}
          actions={
            turns.length > 0 && (
              <Button variant="ghost" icon={<Trash2 size={16} />} onClick={clearChat} disabled={busy}>
                Clear chat
              </Button>
            )
          }
        >
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

          <div className={styles.log} role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation">
            {turns.length === 0 && (
              <p className={styles.empty}>Pick a question above or type your own. You can ask in English or Arabic.</p>
            )}
            {turns.map((t) => (
              <TurnView key={t.id} turn={t} slow={slow} />
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
                  ask(draft);
                }
              }}
            />
            <Button type="submit" disabled={busy || !draft.trim()} icon={<Send size={16} />} aria-label="Send question">
              Send
            </Button>
          </form>
        </Card>

        <aside className={styles.side} aria-label="Assistant settings">
          <ModelInfoPanel refreshKey={answered} />
          <PermissionsPanel />
        </aside>
      </div>
    </div>
  );
}

function TurnView({ turn: t, slow }: { turn: Turn; slow: boolean }) {
  const pending = !t.answer && !t.error && !t.interrupted;
  return (
    <div className={styles.turn}>
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
    </div>
  );
}

function AnswerView({ turn }: { turn: Turn }) {
  const { question, firstTokenMs, reported } = turn;
  const answer = turn.answer!;
  const cmo = answer.refused && answer.refusalReason === 'medication';
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

      {answer.refused ? (
        <div className={styles.refusal} role="note">
          <AnswerText text={answer.answer} />
          {cmo && <CmoButton question={question} done={reported} onDone={onDone} />}
        </div>
      ) : (
        <AnswerText text={answer.answer} />
      )}
      <NextSteps steps={answer.nextSteps} />

      {answer.missing.length > 0 && (
        <p className={styles.missing}>
          <strong>Missing information:</strong> {answer.missing.join(' · ')}
        </p>
      )}
      <SourceList sources={answer.sources} />
      {/* a medication refusal already has its CMO button (which also adds to the report) */}
      {!cmo && (
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
