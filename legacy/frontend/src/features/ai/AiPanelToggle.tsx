import { useEffect, useState } from "react";
import { fetchAiChangeSets, fetchAiConnections } from "../../api/ai";

// With MCP enabled the panel is always offered, so users can connect a client.
// With MCP disabled it is offered only when there is something to show: a
// change set of the organisation or a connection of the User (ADR-015).
function useAiPanelAvailable(orgId: string, mcpEnabled: boolean): boolean {
  const [hasRows, setHasRows] = useState(false);

  useEffect(() => {
    if (mcpEnabled) return;
    const controller = new AbortController();

    async function loadRows() {
      const [changeSets, connections] = await Promise.allSettled([
        fetchAiChangeSets(orgId, { limit: 1 }, controller.signal),
        fetchAiConnections(controller.signal)
      ]);
      if (controller.signal.aborted) return;
      setHasRows(
        (changeSets.status === "fulfilled" && changeSets.value.length > 0) ||
          (connections.status === "fulfilled" && connections.value.length > 0)
      );
    }

    void loadRows();
    return () => controller.abort();
  }, [mcpEnabled, orgId]);

  return mcpEnabled || hasRows;
}

export default function AiPanelToggle(props: {
  orgId: string;
  mcpEnabled: boolean;
  open: boolean;
  panelId: string;
  onToggle: () => void;
}) {
  const available = useAiPanelAvailable(props.orgId, props.mcpEnabled);
  if (!available && !props.open) return null;

  return (
    <button
      className={`btn btn--secondary ai-panel-toggle${props.open ? " ai-panel-toggle--open" : ""}`}
      type="button"
      aria-expanded={props.open}
      aria-controls={props.open ? props.panelId : undefined}
      onClick={props.onToggle}
    >
      AI panel
    </button>
  );
}
