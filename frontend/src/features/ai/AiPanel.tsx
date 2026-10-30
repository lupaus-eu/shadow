import { useId, useState } from "react";
import type { AiChangeSetApplyDto } from "../../api/ai";
import type { WorkspaceScenarioSummary } from "../../workspace/WorkspaceSelectionContext";
import ChangeSetList from "./ChangeSetList";
import ChangeSetReview from "./ChangeSetReview";
import ConnectInstructions from "./ConnectInstructions";
import ConnectionsList from "./ConnectionsList";

// What the workspace route gives the Metrics tab: the session's `features.mcp`
// and `features.mcpChangeSetReview`, and the `changeSet` query parameter,
// which the review URL of `submit_change_set` sets and which names the
// reviewed change set.
export type AiPanelOptions = {
  mcpEnabled: boolean;
  mcpChangeSetReview: boolean;
  changeSetKey: string | null;
  onChangeSetKeyChange: (changeSetKey: string | null) => void;
};

type AiPanelSection = "change-sets" | "connections" | "connect";

// The Metrics tab AI panel (ADR-015). The AI chat happens in the user's own
// client; here the user connects it and reviews, applies or rejects what it
// staged. With `features.mcp` false the Connect section is hidden, while the
// connections list and change-set review keep working.
export default function AiPanel(props: {
  id: string;
  orgId: string;
  scenario: WorkspaceScenarioSummary | null;
  options: AiPanelOptions;
  // Rows of the metrics grid with unsaved edits, which an apply's reload
  // discards.
  unsavedMetricRows: number;
  onApplied: (result: AiChangeSetApplyDto) => void;
  onClose: () => void;
}) {
  const titleId = useId();
  const [section, setSection] = useState<AiPanelSection>("change-sets");
  const { mcpEnabled, mcpChangeSetReview, changeSetKey, onChangeSetKeyChange } = props.options;
  const sections: Array<[AiPanelSection, string]> = [
    ["change-sets", "Change sets"],
    ["connections", "Connections"],
    ...(mcpEnabled ? [["connect", "Connect"] as [AiPanelSection, string]] : [])
  ];
  const activeSection = section === "connect" && !mcpEnabled ? "change-sets" : section;

  return (
    <aside id={props.id} className="ai-panel" aria-labelledby={titleId}>
      <div className="ai-panel__header">
        <h2 id={titleId} className="section-title">
          AI
        </h2>
        <button
          className="ai-panel__close"
          type="button"
          aria-label="Close AI panel"
          onClick={props.onClose}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>

      <div
        className="detail-mode-switch ai-panel__sections"
        role="group"
        aria-label="AI panel section"
      >
        {sections.map(([value, label]) => (
          <button
            key={value}
            className={`detail-mode-switch__button${
              activeSection === value ? " detail-mode-switch__button--active" : ""
            }`}
            type="button"
            aria-pressed={activeSection === value}
            onClick={() => setSection(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {activeSection === "change-sets" ? (
        changeSetKey ? (
          <ChangeSetReview
            key={changeSetKey}
            orgId={props.orgId}
            changeSetKey={changeSetKey}
            unsavedMetricRows={props.unsavedMetricRows}
            onBack={() => onChangeSetKeyChange(null)}
            onApplied={props.onApplied}
          />
        ) : (
          <ChangeSetList
            orgId={props.orgId}
            scenario={props.scenario}
            onSelect={(key) => onChangeSetKeyChange(key)}
          />
        )
      ) : null}
      {activeSection === "connections" ? (
        <ConnectionsList changeSetReview={mcpChangeSetReview} />
      ) : null}
      {activeSection === "connect" ? (
        <ConnectInstructions changeSetReview={mcpChangeSetReview} />
      ) : null}
    </aside>
  );
}
