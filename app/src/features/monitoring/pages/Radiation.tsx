import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Radiation() {
  return (
    <PlaceholderPage
      title="Radiation"
      eyebrow="Space medicine"
      owners={OWNERS}
      endpoint="/sensors"
      note="Designed — build only if the dataset supports it."
      plan={['Cumulative dose vs mission limits (needs a NASA source)', 'Events timeline']}
    />
  );
}
