import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Resources() {
  return (
    <PlaceholderPage
      title="Resources"
      owners={OWNERS}
      endpoint="/resources"
      plan={['Medicines and equipment', 'Filters (kind, status, allergy conflicts)']}
    />
  );
}
