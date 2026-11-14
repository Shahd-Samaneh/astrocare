import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function AttentionCheck() {
  return (
    <PlaceholderPage
      title="Attention check"
      owners={OWNERS}
      endpoint="/tests?n=5"
      plan={[
        'A 5-trial reaction test',
        'Median, lapses, false starts',
        'Comparison with personal baseline',
        'An "experimental" note',
      ]}
    />
  );
}
