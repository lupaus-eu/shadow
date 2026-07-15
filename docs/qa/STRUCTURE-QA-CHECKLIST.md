# Structure QA Checklist

Use this checklist for manual verification of the Structure graph feature after
backend or frontend Structure changes.

Related task specs:

- [TASK-025A Backend Structure API](../../tasks/TASK-025A-backend-structure-api.md)
- [TASK-025B Frontend Structure UI](../../tasks/TASK-025B-frontend-structure-ui.md)
- [TASK-025C Documentation & Task Specs for Structure Feature](../../tasks/TASK-025C-docs-structure.md)

Authorization and permission enforcement are out of scope for the TASK-025A and
TASK-025B baseline. Verify authorization separately when the dedicated follow-up
task is implemented.

---

# Preconditions

- Backend, frontend and database are running locally.
- Test data includes an organisation with at least one scenario and one
  organisation state.
- The organisation has an active metamodel with node types, edge types and
  allowed connections.
- Browser developer tools are available for checking failed API requests.

---

# Graph Loading

- [ ] Open the workspace for an organisation.
- [ ] Select a scenario and an organisation state.
- [ ] Open the `Structure` tab.
- [ ] Verify the graph loads without an error state.
- [ ] Verify node labels, colors and shapes match the graph type catalog.
- [ ] Verify edge labels and arrow endings match the graph type catalog.
- [ ] Refresh the page and verify the same graph data loads again.

---

# Node Operations

- [ ] Switch to `Create` mode.
- [ ] Create a node with a valid type, name, description and attributes.
- [ ] Verify the node appears in the graph viewer.
- [ ] Verify the node appears in the left node list under the correct type.
- [ ] Select the node and update its editable fields.
- [ ] Refresh the page and verify the node update persisted.
- [ ] Delete the node.
- [ ] Refresh the page and verify the deleted node no longer appears.

---

# Edge Operations

- [ ] Create two nodes whose types allow at least one connection.
- [ ] Create an edge between the nodes with a valid edge type.
- [ ] Verify the edge appears in the graph viewer with the expected label and
      arrow styling.
- [ ] Select the edge and update its editable fields.
- [ ] Refresh the page and verify the edge update persisted.
- [ ] Delete the edge.
- [ ] Refresh the page and verify the deleted edge no longer appears.
- [ ] Attempt to create an edge for a disallowed connection and verify the UI
      prevents it or the backend rejects it clearly.

---

# Position Updates

- [ ] Drag a node to a new position.
- [ ] Verify the node moves immediately in the UI.
- [ ] Wait for the debounced position save to complete.
- [ ] Refresh the page and verify the node remains in the new position.
- [ ] Drag multiple nodes in quick succession.
- [ ] Verify the graph remains responsive and the final positions persist.

---

# Navigation And Filtering

- [ ] Verify the left node list groups nodes by type.
- [ ] Verify each group shows a correct counter.
- [ ] Collapse and expand at least one node type group.
- [ ] Use node type checkboxes to hide and show a type.
- [ ] Use `Select All` and verify all node types are visible.
- [ ] Use `Deselect All` and verify graph visibility updates accordingly.
- [ ] Click a node in the node list and verify the graph centers or focuses it.
- [ ] Use native graph pan and zoom interactions.
- [ ] Use `Zoom to Fit` and verify the visible graph fits the viewer.

---

# Modes And Empty States

- [ ] Verify `Create` is the default mode.
- [ ] Switch to `Show and Edit` and verify selecting nodes or edges shows the
      relevant edit controls.
- [ ] Switch to `AI Assistant` and verify the future-work empty state appears.
- [ ] Clear scenario or organisation state selection and verify the workspace
      gating prevents Structure content from loading.

---

# Regression Notes

Record in the PR:

- browser and viewport used for manual QA
- test organisation, scenario and organisation state identifiers
- any failed API responses or console errors
- any skipped checklist items and why they were skipped
