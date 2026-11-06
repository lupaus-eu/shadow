import { useMemo } from "react";
import type { GraphNodeDto, NodeTypeMetadataDto } from "../../api/orgTwinStructure";

const FALLBACK_COLORS = ["#dbeafe", "#dcfce7", "#fef3c7", "#fce7f3", "#ede9fe", "#cffafe"];

function nodeTypeLabel(type: NodeTypeMetadataDto | undefined, id: string): string {
  return type?.displayName || type?.name || id;
}

export default function NodeList(props: {
  nodes: GraphNodeDto[];
  nodeTypes: NodeTypeMetadataDto[];
  endingNodeIds: ReadonlySet<string>;
  visibleNodeTypeIds: Set<string>;
  collapsedNodeTypeIds: Set<string>;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
  onToggleVisibleNodeType: (nodeTypeId: string) => void;
  onSelectAllNodeTypes: () => void;
  onDeselectAllNodeTypes: () => void;
  onToggleCollapsedNodeType: (nodeTypeId: string) => void;
  onCreateNodeOfType: (nodeTypeId: string) => void;
}) {
  const nodeTypesById = useMemo(
    () => new Map(props.nodeTypes.map((nodeType) => [nodeType.id, nodeType])),
    [props.nodeTypes]
  );
  const groups = useMemo(() => {
    const grouped = new Map<string, GraphNodeDto[]>();
    for (const node of props.nodes) {
      const items = grouped.get(node.nodeTypeId) ?? [];
      items.push(node);
      grouped.set(node.nodeTypeId, items);
    }

    const allNodeTypeIds = new Set<string>([
      ...props.nodeTypes.map((nodeType) => nodeType.id),
      ...props.nodes.map((node) => node.nodeTypeId)
    ]);

    return [...allNodeTypeIds]
      .map((nodeTypeId, index) => {
        const type = nodeTypesById.get(nodeTypeId);
        const nodes = grouped.get(nodeTypeId) ?? [];
        return {
          nodeTypeId,
          label: nodeTypeLabel(type, nodeTypeId),
          color: type?.color || FALLBACK_COLORS[index % FALLBACK_COLORS.length],
          nodes: [...nodes].sort((a, b) => a.name.localeCompare(b.name))
        };
      })
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [nodeTypesById, props.nodeTypes, props.nodes]);

  return (
    <aside className="structure-side-panel" aria-label="Structure nodes">
      <section className="sidebar-section">
        <div className="sidebar-section__header">
          <h3 className="secondary-title">Node types</h3>
        </div>
        <div className="structure-filter-actions">
          <button
            className="btn btn--secondary btn--compact"
            type="button"
            onClick={props.onSelectAllNodeTypes}
          >
            Select All
          </button>
          <button
            className="btn btn--secondary btn--compact"
            type="button"
            onClick={props.onDeselectAllNodeTypes}
          >
            Deselect All
          </button>
        </div>
        <div className="structure-node-groups">
          {groups.length === 0 ? <p className="muted">No nodes available.</p> : null}
          {groups.map((group) => {
            const isVisible = props.visibleNodeTypeIds.has(group.nodeTypeId);
            const isCollapsed = props.collapsedNodeTypeIds.has(group.nodeTypeId);

            return (
              <section
                key={group.nodeTypeId}
                className="structure-node-group"
                aria-label={`${group.label} nodes`}
              >
                <div className="structure-node-group__header">
                  <button
                    className="structure-type-create"
                    type="button"
                    onClick={() => props.onCreateNodeOfType(group.nodeTypeId)}
                    aria-label={`Create ${group.label} node`}
                    title={`Create ${group.label} node`}
                  >
                    <span className="structure-type-create__icon" aria-hidden="true">
                      +
                    </span>
                  </button>
                  <div className="structure-type-tag" style={{ backgroundColor: group.color }}>
                    <label className="structure-type-toggle">
                      <input
                        type="checkbox"
                        checked={isVisible}
                        onChange={() => props.onToggleVisibleNodeType(group.nodeTypeId)}
                      />
                      <span className="structure-type-toggle__label">{group.label}</span>
                      <span className="structure-type-count">({group.nodes.length})</span>
                    </label>
                    <button
                      className={`disclosure-button structure-type-caret${
                        isCollapsed ? " disclosure-button--collapsed" : ""
                      }`}
                      type="button"
                      onClick={() => props.onToggleCollapsedNodeType(group.nodeTypeId)}
                      aria-expanded={!isCollapsed}
                      aria-label={
                        isCollapsed
                          ? `Expand ${group.label} nodes`
                          : `Collapse ${group.label} nodes`
                      }
                    >
                      <span aria-hidden="true">▾</span>
                    </button>
                  </div>
                </div>
                {!isCollapsed && group.nodes.length === 0 ? (
                  <p className="muted structure-node-group__empty">No nodes</p>
                ) : null}
                {!isCollapsed ? (
                  <div className="entity-list structure-node-group__list">
                    {group.nodes.map((node) => {
                      const isSelected = node.id === props.selectedNodeId;
                      return (
                        <button
                          key={node.id}
                          className={`entity-row entity-row--compact${
                            isSelected ? " entity-row--selected" : ""
                          }`}
                          type="button"
                          onClick={() => props.onSelectNode(node.id)}
                          aria-pressed={isSelected}
                          disabled={!isVisible}
                        >
                          <span className="entity-row__main">
                            <span className="entity-row__title">
                              {node.name}
                              {props.endingNodeIds.has(node.id) ? (
                                <span className="structure-ending-badge">
                                  Ends
                                  <span className="visually-hidden"> {node.deleteDate}</span>
                                </span>
                              ) : null}
                            </span>
                            <span className="clamped-description">{node.description || ""}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
