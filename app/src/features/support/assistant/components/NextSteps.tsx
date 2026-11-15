// The alert's next steps that have an in-app link, as buttons that navigate inside the app
// ("/daily#checkin", "/attention?retest=<alertId>"). The server fills `link` from the alert's
// NextStep.action.route. Steps without a link stay plain text in the answer above, so nothing is
// shown for them here; a CMO-locked step never gets a button.
import { ArrowRight } from 'lucide-react';
import { Button } from '../../../../shared/components';
import type { AnswerStep } from '../types';
import styles from './NextSteps.module.css';

/** Same-app paths only: never a host, a scheme or a protocol-relative "//" URL. */
const isInAppPath = (link: string | null | undefined): link is string =>
  !!link && link.startsWith('/') && !link.startsWith('//');

export function NextSteps({ steps }: { steps?: AnswerStep[] }) {
  const linked = (steps ?? []).filter((s) => !s.lockedForCMO && isInAppPath(s.link));
  if (!linked.length) return null;
  return (
    <div className={styles.wrap} role="group" aria-label="Next steps you can do now">
      {linked.map((s) => (
        <Button key={`${s.link}-${s.text}`} variant="secondary" to={s.link as string} icon={<ArrowRight size={16} />}>
          {s.text}
        </Button>
      ))}
    </div>
  );
}
