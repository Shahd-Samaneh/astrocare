// P1: which data the assistant (and reports) may use. Check-ins are off by default.
import { useEffect, useState } from 'react';
import { Card, ErrorState, LoadingState } from '../../../shared/components';
import { getPermissions, putPermissions } from './api';
import type { AssistantPermissions } from './types';
import styles from './AssistantPage.module.css';

type Group = keyof AssistantPermissions;

const ITEMS: { group: Group; key: string; label: string; hint?: string }[] = [
  { group: 'assistant', key: 'vitals', label: 'Vital signs' },
  { group: 'assistant', key: 'sleep', label: 'Sleep' },
  { group: 'assistant', key: 'tests', label: 'Attention tests' },
  { group: 'assistant', key: 'exercise', label: 'Exercise' },
  { group: 'assistant', key: 'checkins', label: 'Check-ins (mood, stress)', hint: 'Private notes are never shared.' },
  { group: 'report', key: 'checkins', label: 'Include check-ins in reports', hint: 'Reports go to Earth at the next comm window.' },
];

export function PermissionsPanel() {
  const [perms, setPerms] = useState<AssistantPermissions>();
  const [error, setError] = useState<string>();
  const [saveError, setSaveError] = useState<string>();
  const [saving, setSaving] = useState<string>();

  const load = () => {
    setError(undefined);
    getPermissions()
      .then(setPerms)
      .catch((e: Error) => setError(e.message));
  };
  useEffect(load, []);

  async function toggle(group: Group, key: string) {
    if (!perms) return;
    const current = (perms[group] as Record<string, boolean>)[key];
    const id = `${group}.${key}`;
    const previous = perms;
    setSaving(id);
    setSaveError(undefined);
    setPerms({ ...perms, [group]: { ...perms[group], [key]: !current } }); // optimistic
    try {
      setPerms(await putPermissions({ [group]: { [key]: !current } }));
    } catch (e) {
      setPerms(previous);
      setSaveError(`Could not save (${(e as Error).message}).`);
    } finally {
      setSaving(undefined);
    }
  }

  return (
    <Card title="Data permissions" subtitle="What the assistant may read">
      {!perms && !error && <LoadingState label="Loading permissions…" />}
      {error && <ErrorState message={error} onRetry={load} />}
      {perms && (
        <ul className={styles.toggles}>
          {ITEMS.map(({ group, key, label, hint }) => {
            const id = `${group}.${key}`;
            const on = (perms[group] as Record<string, boolean>)[key];
            return (
              <li key={id}>
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  className={styles.toggle}
                  disabled={saving === id}
                  onClick={() => void toggle(group, key)}
                >
                  <span className={styles.toggleText}>
                    <span>{label}</span>
                    {hint && <span className={styles.hint}>{hint}</span>}
                  </span>
                  <span className={`${styles.switch} ${on ? styles.switchOn : ''}`} aria-hidden>
                    <span className={styles.knob} />
                  </span>
                  <span className="sr-only">{on ? 'on' : 'off'}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {saveError && (
        <p className={styles.saveError} role="alert">
          {saveError}
        </p>
      )}
    </Card>
  );
}
