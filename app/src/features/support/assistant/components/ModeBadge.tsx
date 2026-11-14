// "Local model" / "Template" badge for an answer (candidate for shared/components, proposal A7).
import { Badge } from '../../../../shared/components';
import type { AnswerMode } from '../types';

export function ModeBadge({ mode, refused = false }: { mode: AnswerMode; refused?: boolean }) {
  if (refused) {
    return (
      <Badge variant="review" title="Fixed safety reply: the question was not sent to the model">
        Safety reply
      </Badge>
    );
  }
  return mode === 'llm' ? (
    <Badge variant="pink" title="Answered by the local model on this device (llama3.2:3b via Ollama)">
      Local model
    </Badge>
  ) : (
    <Badge variant="neutral" title="The local model was not available: template explanation from your latest alert">
      Template
    </Badge>
  );
}
