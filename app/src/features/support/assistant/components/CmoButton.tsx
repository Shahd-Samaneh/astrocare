// "Add question to report for the CMO" (medication refusals) -> POST /api/reports/items.
import { cmoReportItem } from '../reportItems';
import { ReportButton } from './ReportButton';

export function CmoButton({ question, done, onDone }: { question: string; done?: boolean; onDone?: () => void }) {
  return (
    <ReportButton
      item={cmoReportItem(question)}
      label="Add question to report for the CMO"
      doneText="Added to the report for the CMO. It will be sent at the next comm window."
      what="question"
      variant="primary"
      done={done}
      onDone={onDone}
    />
  );
}
