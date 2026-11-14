// "Add the question to the report for the CMO" (medication refusals) -> POST /api/reports/items.
import { cmoReportItem } from '../reportItems';
import { ReportButton } from './ReportButton';

export function CmoButton({ question, done, onDone }: { question: string; done?: boolean; onDone?: () => void }) {
  return (
    <ReportButton
      item={cmoReportItem(question)}
      label="Add the question to the report for the CMO"
      doneText="Added to the report for the CMO. It will be sent at the next comm window."
      what="question"
      variant="warn"
      done={done}
      onDone={onDone}
    />
  );
}
