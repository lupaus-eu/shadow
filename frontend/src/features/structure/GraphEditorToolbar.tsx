export type StructureMode = "edit" | "create" | "timeserie" | "assistant";

type ModeOption = {
  mode: StructureMode;
  label: string;
};

const MODE_OPTIONS: ModeOption[] = [
  { mode: "create", label: "Create" },
  { mode: "edit", label: "Show & Edit" },
  { mode: "timeserie", label: "Timeserie" },
  { mode: "assistant", label: "AI Assistant" }
];

export default function GraphEditorToolbar(props: {
  loading: boolean;
  saving: boolean;
  nodeCount: number;
  edgeCount: number;
  onRefresh: () => void;
}) {
  return (
    <section className="tab-toolbar structure-toolbar" aria-label="Structure overview">
      <div className="tab-toolbar__title structure-toolbar__title">
        <h1 className="page-title">Structure</h1>
        <span className="tab-toolbar__count">
          {props.nodeCount} node(s), {props.edgeCount} edge(s)
        </span>
      </div>
      <div className="structure-toolbar__actions">
        <button
          className="btn btn--secondary"
          type="button"
          onClick={props.onRefresh}
          disabled={props.loading || props.saving}
        >
          {props.loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>
    </section>
  );
}

export function EditorModeSelector(props: {
  mode: StructureMode;
  showTimeserie: boolean;
  onModeChange: (mode: StructureMode) => void;
}) {
  const options = MODE_OPTIONS.filter(
    (option) => option.mode !== "timeserie" || props.showTimeserie
  );

  return (
    <div className="detail-mode-switch" role="group" aria-label="Structure mode">
      {options.map((option) => (
        <button
          key={option.mode}
          className={`detail-mode-switch__button${
            props.mode === option.mode
              ? " detail-mode-switch__button--active"
              : ""
          }`}
          type="button"
          onClick={() => props.onModeChange(option.mode)}
          aria-pressed={props.mode === option.mode}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
