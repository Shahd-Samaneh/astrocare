import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Bone() {
  return (
    <PlaceholderPage
      title="Bone & muscle"
      eyebrow="Space medicine"
      owners={OWNERS}
      endpoint="/exercise/plan"
      note="Designed — build only if the dataset supports it."
      plan={['Resistive exercise adherence', 'Bone/muscle loss risk indicators (needs a NASA source)']}
    />
  );
}
