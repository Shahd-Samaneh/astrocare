import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Reports() {
  return (
    <PlaceholderPage
      title="Reports"
      owners={OWNERS}
      endpoint="/comms"
      plan={['Comm status', 'Outbox', 'A new report with sections (POST /api/reports)']}
    />
  );
}
