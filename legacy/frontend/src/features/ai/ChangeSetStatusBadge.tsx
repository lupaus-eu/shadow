import type { AiChangeSetStatus } from "../../api/ai";
import { changeSetStatusLabel } from "./aiPresentation";

export default function ChangeSetStatusBadge(props: { status: AiChangeSetStatus }) {
  return (
    <span className={`badge ai-panel-status ai-panel-status--${props.status}`}>
      {changeSetStatusLabel(props.status)}
    </span>
  );
}
