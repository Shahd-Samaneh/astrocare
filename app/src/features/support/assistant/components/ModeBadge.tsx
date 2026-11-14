// Answer badge: "Local model" / "Template" / "From alert R-…" / "From your data" / "Safety reply"
// (candidate for shared/components, proposal A7).
import { Badge } from '../../../../shared/components';
import type { AnswerMode } from '../types';

export function ModeBadge({
  mode,
  refused = false,
  alertRuleId,
}: {
  mode: AnswerMode;
  refused?: boolean;
  alertRuleId?: string | null;
}) {
  if (refused) {
    return (
      <Badge variant="review" title="Fixed safety reply: the question was not sent to the model">
        Safety reply
      </Badge>
    );
  }
  switch (mode) {
    case 'llm':
      return (
        <Badge
          variant="pink"
          title="Answered by the local model on this device (llama3.2:3b via Ollama)"
        >
          Local model
        </Badge>
      );
    case 'alert':
      return (
        <Badge
          variant="info"
          title="Built from the alert's own fields on this device, without the model"
        >
          {alertRuleId ? `From alert ${alertRuleId}` : 'From your alerts'}
        </Badge>
      );
    case 'data':
      return (
        <Badge
          variant="good"
          title="Built from your recorded data on this device, without the model"
        >
          From your data
        </Badge>
      );
    default:
      return (
        <Badge
          variant="neutral"
          title="The local model was not available: template explanation from your most important alert"
        >
          Template
        </Badge>
      );
  }
}
