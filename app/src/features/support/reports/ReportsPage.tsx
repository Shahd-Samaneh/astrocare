// Reports & Earth sync (owner: Noura).
// Comms status + countdown · New report (sections + pending items -> PDF/JSON) · Outbox (draft/ready/queued/sent).
import { useState } from 'react';
import { FileText, Radio, Send, Satellite, Trash2 } from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SimulatedBadge,
} from '../../../shared/components';
import { useApi } from '../../../shared/api/client';
import type { ReportStatus } from '../../../shared/types/contracts';
import { formatDuration, relativeTime, useNow } from '../../../shared/utils/format';
import { createReport, deleteReportItem, queueReport, reportFileUrl, simulateWindow } from './api';
import { SECTIONS, type CommsStatus, type ReportItem, type ReportOut, type SectionId } from './types';
import styles from './ReportsPage.module.css';

const STATUS_BADGE: Record<ReportStatus, { variant: 'neutral' | 'info' | 'review' | 'good'; label: string }> = {
  draft: { variant: 'neutral', label: 'Draft' },
  ready: { variant: 'info', label: 'Ready' },
  queued: { variant: 'review', label: 'Queued' },
  sent: { variant: 'good', label: 'Sent' },
};

const ITEM_LABEL: Record<ReportItem['kind'], string> = {
  alert: 'Alert',
  cmo_question: 'Question for CMO',
  note: 'Crew note',
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function ReportsPage() {
  const comms = useApi<CommsStatus>('/comms', { refreshMs: 30_000 });
  const reports = useApi<ReportOut[]>('/reports');
  const items = useApi<ReportItem[]>('/reports/items?pending=true');
  const now = useNow(1000);

  const [composing, setComposing] = useState(false);
  const [sections, setSections] = useState<Set<SectionId>>(
    () => new Set(SECTIONS.filter((s) => s.defaultOn).map((s) => s.id)),
  );
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [lastCreated, setLastCreated] = useState<ReportOut | null>(null);

  const reloadAll = () => {
    comms.reload();
    reports.reload();
    items.reload();
  };

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setMessage(null);
    try {
      await fn();
    } catch (e) {
      setMessage({ kind: 'error', text: (e as Error).message || 'Something went wrong' });
    } finally {
      setBusy(null);
      reloadAll();
    }
  }

  const toggle = <T,>(set: Set<T>, value: T) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  };

  const pending = items.data ?? [];
  const chosenItems = pending.filter((i) => !excluded.has(i.id)).map((i) => i.id);

  const onGenerate = () =>
    run('generate', async () => {
      const ordered = SECTIONS.map((s) => s.id).filter((id) => sections.has(id));
      const rep = await createReport(ordered, chosenItems);
      setLastCreated(rep);
      setComposing(false);
      setExcluded(new Set());
      setMessage({ kind: 'ok', text: 'Report ready. Open the PDF or queue it for the next comm window.' });
    });

  const onQueue = (id: string) =>
    run(`queue-${id}`, async () => {
      await queueReport(id);
      setMessage({ kind: 'ok', text: 'Queued. It will be sent when the comm window opens.' });
    });

  const onSimulate = () =>
    run('simulate', async () => {
      const r = await simulateWindow();
      setMessage({
        kind: 'ok',
        text: `Simulated comm window opened: ${r.sentReportIds.length} report${r.sentReportIds.length === 1 ? '' : 's'} sent.`,
      });
    });

  const onDeleteItem = (id: string) => run(`del-${id}`, () => deleteReportItem(id));

  // ---- comms card ----
  const c = comms.data;
  const secondsToWindow = c ? (new Date(c.nextWindowTs).getTime() - now) / 1000 : 0;

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Support · Earth sync"
        title="Reports"
        actions={
          <span className={styles.simLine}>
            <SimulatedBadge /> All data is simulated
          </span>
        }
      />

      {message && (
        <p className={message.kind === 'ok' ? styles.ok : styles.error} role={message.kind === 'ok' ? 'status' : 'alert'}>
          {message.text}
        </p>
      )}

      {/* ---- Earth link ---- */}
      <Card
        title="Earth link"
        subtitle="Reports wait in the outbox until a comm window opens."
        actions={
          <Button
            variant="secondary"
            icon={<Radio size={16} />}
            onClick={onSimulate}
            disabled={busy !== null}
            aria-describedby="sim-note"
          >
            {busy === 'simulate' ? 'Opening…' : 'Simulate comm window'}
          </Button>
        }
      >
        {comms.loading && !c && <LoadingState />}
        {comms.error && <ErrorState message={comms.error.message} onRetry={comms.reload} />}
        {c && (
          <div className={styles.linkGrid}>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Status</span>
              <span className={c.connected ? styles.connected : styles.disconnected}>
                <Satellite size={16} aria-hidden />
                {c.connected ? (c.simulatedWindow ? 'Window open (simulated)' : 'Window open') : 'No Earth link'}
              </span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Next window</span>
              <span className={styles.statValue} aria-live="off">
                {secondsToWindow > 0 ? `in ${formatDuration(secondsToWindow)}` : 'now'}
              </span>
              <span className={styles.statHint}>{c.windowDurationMin} min long</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Signal delay</span>
              <span className={styles.statValue}>{formatDuration(c.signalDelaySec)}</span>
              <span className={styles.statHint}>one way</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Queued</span>
              <span className={styles.statValue}>{c.queuedCount}</span>
              <span className={styles.statHint}>
                {c.lastWindowTs ? `last window ${relativeTime(c.lastWindowTs, now)}` : 'no window yet'}
              </span>
            </div>
          </div>
        )}
        <p id="sim-note" className={styles.note}>
          Demo only: “Simulate comm window” opens a window now. The app never makes a real network call.
        </p>
      </Card>

      {/* ---- New report ---- */}
      <Card
        title="New report"
        subtitle="Pick the sections, check the items for the flight surgeon, then generate a PDF + JSON."
        actions={
          !composing && (
            <Button icon={<FileText size={16} />} onClick={() => setComposing(true)}>
              New report
            </Button>
          )
        }
      >
        {lastCreated && !composing && (
          <div className={styles.created}>
            <span>
              Created <strong className="mono">{lastCreated.id}</strong>
            </span>
            <a className={styles.link} href={reportFileUrl(lastCreated.id)} target="_blank" rel="noopener">
              Open PDF
            </a>
            <a className={styles.link} href={reportFileUrl(lastCreated.id, 'json')} target="_blank" rel="noopener">
              JSON
            </a>
          </div>
        )}

        {composing && (
          <form
            className={styles.form}
            onSubmit={(e) => {
              e.preventDefault();
              onGenerate();
            }}
          >
            <fieldset className={styles.fieldset}>
              <legend className={styles.legend}>Sections</legend>
              <div className={styles.checkGrid}>
                {SECTIONS.map((s) => (
                  <label key={s.id} className={styles.check}>
                    <input
                      type="checkbox"
                      checked={sections.has(s.id)}
                      onChange={() => setSections((prev) => toggle(prev, s.id))}
                    />
                    <span>
                      {s.label}
                      {s.note && <span className={styles.checkNote}>{s.note}</span>}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset className={styles.fieldset} disabled={!sections.has('items')}>
              <legend className={styles.legend}>
                Pending items ({chosenItems.length} of {pending.length})
              </legend>
              {!sections.has('items') && <p className={styles.note}>Turn on “Items for the CMO” to include them.</p>}
              {items.loading && !items.data && <LoadingState />}
              {pending.length === 0 && !items.loading && (
                <p className={styles.note}>No pending items. “Add to report” buttons in Alerts and the Assistant add them here.</p>
              )}
              <ul className={styles.itemList}>
                {pending.map((i) => (
                  <li key={i.id} className={styles.item}>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={!excluded.has(i.id)}
                        onChange={() => setExcluded((prev) => toggle(prev, i.id))}
                      />
                      <span>
                        <Badge variant={i.kind === 'cmo_question' ? 'pink' : i.kind === 'alert' ? 'review' : 'neutral'}>
                          {ITEM_LABEL[i.kind]}
                        </Badge>{' '}
                        <strong>{i.title}</strong>
                        {i.text && <span className={styles.itemText}>{i.text}</span>}
                        <span className={styles.statHint}>
                          from {i.sourceFeature} · {relativeTime(i.createdTs, now)}
                        </span>
                      </span>
                    </label>
                    <Button
                      variant="ghost"
                      icon={<Trash2 size={16} />}
                      aria-label={`Delete item: ${i.title}`}
                      onClick={() => onDeleteItem(i.id)}
                      disabled={busy !== null}
                    />
                  </li>
                ))}
              </ul>
            </fieldset>

            <div className={styles.formActions}>
              <Button type="submit" icon={<FileText size={16} />} disabled={sections.size === 0 || busy !== null}>
                {busy === 'generate' ? 'Generating…' : 'Generate PDF + JSON'}
              </Button>
              <Button variant="ghost" onClick={() => setComposing(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </Card>

      {/* ---- Outbox ---- */}
      <Card title="Outbox" subtitle="Draft → Ready → Queued → Sent (when the comm window opens)">
        {reports.loading && !reports.data && <LoadingState />}
        {reports.error && <ErrorState message={reports.error.message} onRetry={reports.reload} />}
        {reports.data && reports.data.length === 0 && <EmptyState title="No reports yet" />}
        {reports.data && reports.data.length > 0 && (
          <ul className={styles.outbox}>
            {reports.data.map((r) => {
              const b = STATUS_BADGE[r.status];
              return (
                <li key={r.id} className={styles.row}>
                  <div className={styles.rowMain}>
                    <Badge variant={b.variant}>{b.label}</Badge>
                    <div>
                      <div className={styles.rowTitle}>
                        {r.sections.map((s) => s.title).join(' · ') || 'Report'}
                      </div>
                      <div className={styles.statHint}>
                        <span className="mono">{r.id}</span> · created {fmtDate(r.createdTs)}
                        {r.sentTs && <> · sent {fmtDate(r.sentTs)}</>}
                      </div>
                    </div>
                  </div>
                  <div className={styles.rowActions}>
                    {r.filePath && (
                      <a className={styles.link} href={reportFileUrl(r.id)} target="_blank" rel="noopener">
                        Open PDF
                      </a>
                    )}
                    {r.status === 'ready' && (
                      <Button
                        variant="secondary"
                        icon={<Send size={16} />}
                        onClick={() => onQueue(r.id)}
                        disabled={busy !== null}
                      >
                        {busy === `queue-${r.id}` ? 'Queuing…' : 'Queue for send'}
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}