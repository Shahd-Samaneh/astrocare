import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function DailyLog() {
  return (
    <PlaceholderPage
      title="Daily log"
      owners={OWNERS}
      endpoint="/sleep?nights=7"
      plan={[
        'Sleep over 7 nights',
        'Exercise with "Couldn\'t do it" → reason → alternative (GET /api/exercise/plan, POST /api/exercise/log)',
        'Check-in (mood, stress, private note)',
      ]}
    />
  );
}
