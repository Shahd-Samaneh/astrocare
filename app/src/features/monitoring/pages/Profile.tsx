import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Profile() {
  return (
    <PlaceholderPage
      title="Profile"
      owners={OWNERS}
      endpoint="/profile"
      plan={['Personal baseline', 'Allergies', 'Current medications', 'Device status (GET /api/sensors)']}
    />
  );
}
