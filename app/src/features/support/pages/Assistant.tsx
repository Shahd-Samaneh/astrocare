import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Assistant() {
  return (
    <PlaceholderPage
      title="Assistant"
      owners={OWNERS}
      endpoint="/assistant/info"
      plan={[
        'Chat with sources (POST /api/assistant/ask)',
        'Missing information',
        'Refusing medication questions',
        'A local model badge',
      ]}
    />
  );
}
