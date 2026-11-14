// Alert detail (placeholder). /alerts lists alerts, /alerts/:id shows one.
import { useParams } from 'react-router-dom';
import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function AlertDetail() {
  const { id } = useParams();
  return (
    <PlaceholderPage
      title={id ? 'Alert detail' : 'Alerts'}
      owners={OWNERS}
      endpoint={id ? `/alerts/${encodeURIComponent(id)}` : '/alerts'}
      plan={[
        'The five sections: what changed, data used, missing or unreliable, possible factors, next steps',
        'Next steps with resource checks (available / out of stock / expired / allergy conflict) and CMO lock',
        'Acknowledge (POST /api/alerts/{id}/ack)',
        'Sources',
      ]}
    />
  );
}
