// P1: local model info, measured from real answers (assistant_log + Ollama eval stats).
import { useEffect } from 'react';
import { useApi } from '../../../shared/api/client';
import { Badge, Card, LoadingState } from '../../../shared/components';
import type { AssistantInfo } from './types';
import styles from './AssistantPage.module.css';

const gb = (b?: number | null) => (b ? `${(b / 1024 ** 3).toFixed(1)} GB` : null);

export function ModelInfoPanel({ refreshKey }: { refreshKey: number }) {
  const { data, error, loading, reload } = useApi<AssistantInfo>('/assistant/info');
  useEffect(() => {
    if (refreshKey) reload();
  }, [refreshKey, reload]);

  const rows: [string, string | null][] = data
    ? [
        ['Model', data.chatModel],
        ['Size on disk', gb(data.modelSizeBytes)],
        ['RAM in use', gb(data.ramBytes) ?? (data.reachable ? 'not loaded yet' : null)],
        ['Average time to first words', data.avgFirstTokenMs != null ? `${(data.avgFirstTokenMs / 1000).toFixed(1)} s` : null],
        ['Average answer time',data.avgLatencyMs != null ? `${(data.avgLatencyMs / 1000).toFixed(1)} s` : null],
        ['Speed', data.tokensPerSec != null ? `${data.tokensPerSec} tokens/s` : null],
        ['Reference passages', String(data.chunksIndexed)],
        ['Answers logged', String(data.answersLogged)],
      ]
    : [];

  return (
    <Card
      title="Local model"
      subtitle="Measured on this device"
      actions={
        data && (
          <Badge variant={data.reachable ? 'good' : 'missing'}>{data.reachable ? 'Running' : 'Off: template mode'}</Badge>
        )
      }
    >
      {loading && !data && <LoadingState label="Reading model info…" />}
      {error && !data && <p className={styles.muted}>Model info is not available ({error.message}).</p>}
      {data && (
        <dl className={styles.dl}>
          {rows.map(([k, v]) => (
            <div key={k} className={styles.dlRow}>
              <dt>{k}</dt>
              <dd>{v ?? <span className={styles.muted}>not measured yet</span>}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}
