import { PlaceholderPage } from '../../../shared/components';
import { OWNERS } from '../owners';

export default function Relax() {
  return (
    <PlaceholderPage
      title="Relax"
      owners={OWNERS}
      endpoint="/relax/scenes"
      plan={['Scenes', 'Audio mode (nature / music / none)', 'Stress rating before and after', 'History']}
    />
  );
}
