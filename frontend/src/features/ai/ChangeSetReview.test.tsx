import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AiApiError, applyAiChangeSet, fetchAiChangeSet, rejectAiChangeSet } from "../../api/ai";
import type {
  AiChangeSetApplyDto,
  AiChangeSetDetailDto,
  AiChangeSetOperationDto
} from "../../api/ai";
import ChangeSetReview from "./ChangeSetReview";
import { formatAiTimestamp } from "./aiPresentation";

vi.mock("../../api/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/ai")>()),
  fetchAiChangeSet: vi.fn(),
  applyAiChangeSet: vi.fn(),
  rejectAiChangeSet: vi.fn()
}));

const fetchDetailMock = vi.mocked(fetchAiChangeSet);
const applyMock = vi.mocked(applyAiChangeSet);
const rejectMock = vi.mocked(rejectAiChangeSet);

const fingerprint = "a".repeat(64);
const newFingerprint = "b".repeat(64);

function operation(
  position: number,
  json: Record<string, unknown>,
  overrides: Partial<AiChangeSetOperationDto> = {}
): AiChangeSetOperationDto {
  return {
    position,
    type: String(json.type),
    ref: typeof json.ref === "string" ? json.ref : null,
    operation: json,
    error: null,
    frozenValues: null,
    replacesExisting: false,
    replaces: null,
    ...overrides
  };
}

const allOperations: AiChangeSetOperationDto[] = [
  operation(0, { type: "create_scenario", ref: "$plan", payload: { name: "Growth plan" } }),
  operation(1, {
    type: "copy_scenario",
    ref: "$copy",
    payload: { sourceScenarioId: "reality", sourceOrgStateId: "now", name: "Reality copy" }
  }),
  operation(2, {
    type: "create_org_state",
    ref: "$q1",
    scenario_key: "future",
    payload: { name: "Q1 state", targetDate: "2031-01-01" }
  }),
  operation(3, {
    type: "create_event",
    ref: "$launch",
    scenario_key: "future",
    payload: { name: "Launch", targetDate: "2031-02-01" }
  }),
  operation(4, {
    type: "create_timeserie",
    scenario_key: "future",
    payload: { id: "revenue", name: "Revenue", timeUnit: "month", valueUnit: "number" }
  }),
  operation(5, {
    type: "set_timeserie_values",
    scenario_key: "future",
    timeserie_key: "revenue",
    payload: {
      values: [
        { date: "2031-01-01", value: 10 },
        { date: "2031-02-01", value: 12 },
        { date: "2031-03-01", value: 15 }
      ]
    }
  }),
  operation(
    6,
    {
      type: "generate_timeserie_values",
      scenario_key: "future",
      timeserie_key: "costs",
      spec: { kind: "linear" }
    },
    {
      frozenValues: {
        generatorVersion: 1,
        valueCount: 2,
        firstDate: "2031-01-01",
        lastDate: "2031-02-01",
        values: [
          { date: "2031-01-01", value: 7.5 },
          { date: "2031-02-01", value: 8.25 }
        ]
      },
      replacesExisting: true,
      replaces: {
        kind: "timeserie",
        scenarioKey: "future",
        timeserieKey: "costs",
        missing: false,
        valueCount: 12,
        firstDate: "2030-01-01",
        lastDate: "2030-12-01",
        checksum: "c".repeat(64)
      }
    }
  ),
  operation(7, {
    type: "create_derived_metric",
    ref: "$margin",
    scenario_key: "future",
    payload: { name: "Margin", formula: "revenue - costs" }
  }),
  operation(8, {
    type: "create_node",
    scenario_key: "future",
    org_state_key: "now",
    payload: { id: "node-revenue", name: "Revenue goal", nodeTypeId: "GOAL", attributes: {} }
  }),
  operation(9, {
    type: "create_edge",
    scenario_key: "future",
    org_state_key: "now",
    payload: {
      id: "edge-1",
      name: "measures",
      edgeTypeId: "MEASURED_BY",
      sourceNodeId: "node-revenue",
      targetNodeId: "company",
      attributes: {}
    }
  }),
  operation(
    10,
    {
      type: "patch_node",
      scenario_key: "future",
      org_state_key: "now",
      node_key: "company",
      payload: { name: "Company Oy" }
    },
    {
      replacesExisting: true,
      replaces: {
        kind: "node",
        scenarioKey: "future",
        orgStateKey: "now",
        nodeKey: "company",
        missing: false,
        fields: { name: "Company" },
        checksum: "d".repeat(64)
      }
    }
  )
];

function detail(overrides: Partial<AiChangeSetDetailDto> = {}): AiChangeSetDetailDto {
  return {
    id: "cs-1",
    scenarioKey: null,
    title: "Growth model",
    rationale: "Adds a growth plan.",
    status: "submitted",
    operationCount: allOperations.length,
    clientId: "client-abc",
    clientName: "Claude ‮evil",
    createdBy: 7,
    createdByName: "Ada Consultant",
    createdTime: "2026-10-27T09:00:00Z",
    modifiedTime: "2026-10-27T09:05:00Z",
    reviewedBy: null,
    reviewedByName: null,
    reviewedTime: null,
    reviewNote: null,
    reviewedVia: null,
    reviewClientId: null,
    reviewClientName: null,
    operations: allOperations,
    reviewFingerprint: fingerprint,
    validationResult: { ok: true, operations: [], refs: {} },
    appliedResult: null,
    ...overrides
  };
}

const appliedResult: AiChangeSetApplyDto = {
  changeSet: {
    ...detail(),
    status: "applied",
    reviewedBy: 9,
    reviewedByName: "Rita Reviewer",
    reviewedTime: "2026-10-28T08:00:00Z"
  },
  operations: [
    { position: 0, opType: "create_scenario", status: "ok", scenarioKey: "scn-77", key: "scn-77" },
    { position: 8, opType: "create_node", status: "ok", scenarioKey: "future", key: "node-revenue" }
  ],
  refs: { $plan: "scn-77" }
};

function renderReview(onApplied = vi.fn(), onBack = vi.fn(), unsavedMetricRows = 0) {
  render(
    <ChangeSetReview
      orgId="acme"
      changeSetKey="cs-1"
      unsavedMetricRows={unsavedMetricRows}
      onBack={onBack}
      onApplied={onApplied}
    />
  );
  return { onApplied, onBack };
}

function applyError(status: number, code: string, message = "Conflict") {
  return new AiApiError(status, code, `Failed to apply AI change set (${status}): ${message}`);
}

async function confirmApply() {
  fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
  const dialog = screen.getByRole("alertdialog", { name: "Confirm apply" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Confirm apply" }));
}

beforeEach(() => {
  vi.resetAllMocks();
  fetchDetailMock.mockResolvedValue(detail());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChangeSetReview", () => {
  it("describes every operation type in readable form", async () => {
    renderReview();

    const list = await screen.findByRole("list", { name: "Change set operations" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => item.querySelector("p")?.textContent)).toEqual([
      "#0 Create scenario Growth plan",
      "#1 Copy scenario reality (as Reality copy)",
      "#2 Create organisation state Q1 state (2031-01-01)",
      "#3 Create event Launch (2031-02-01)",
      "#4 Create timeserie Revenue (month, number)",
      "#5 Set values of timeserie Revenue (3 values)",
      "#6 Generate values for timeserie costs (2 values)",
      "#7 Create derived metric Margin (revenue - costs)",
      "#8 Create node Revenue goal (GOAL)",
      "#9 Create edge Revenue goal → company (MEASURED_BY)",
      "#10 Update node company (name)"
    ]);
    expect(within(items[0]).getByText("$plan")).toBeVisible();
    expect(within(items[8]).getByText("Revenue goal", { selector: "bdi" })).toBeVisible();
    expect(within(items[2]).getByText("future")).toBeVisible();
  });

  it("shows a values table and a sparkline for each timeserie operation", async () => {
    renderReview();

    const setValues = await screen.findByRole("listitem", { name: /Set values of timeserie/ });
    const table = within(setValues).getByRole("table", { name: "Values of Revenue" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByText("12")).toBeVisible();
    expect(
      within(setValues).getByRole("img", {
        name: "Sparkline of 3 values from 2031-01-01 to 2031-03-01, between 10 and 15"
      })
    ).toBeInTheDocument();

    const generated = screen.getByRole("listitem", { name: /Generate values for timeserie/ });
    expect(within(generated).getByRole("table", { name: "Values of costs" })).toBeVisible();
    expect(within(generated).getByText("8.25")).toBeVisible();
    expect(within(generated).getByRole("img", { name: /Sparkline of 2 values/ })).toBeVisible();
  });

  it("flags every operation that replaces existing data and counts them before Apply", async () => {
    renderReview();

    const generated = await screen.findByRole("listitem", {
      name: /Generate values for timeserie/
    });
    expect(within(generated).getByText("Replaces existing data")).toBeVisible();
    expect(
      within(generated).getByText("Replaces 12 existing value(s) from 2030-01-01 to 2030-12-01.")
    ).toBeVisible();

    const patch = screen.getByRole("listitem", { name: /Update node/ });
    expect(within(patch).getByText("Replaces existing data")).toBeVisible();
    const fields = within(patch).getByRole("table", { name: "Patched fields" });
    const nameRow = within(fields).getByRole("row", { name: /name/ });
    expect(within(nameRow).getByText("Company")).toBeVisible();
    expect(within(nameRow).getByText("Company Oy")).toBeVisible();

    expect(screen.getAllByText("Replaces existing data")).toHaveLength(2);
    const summary = screen.getByLabelText("Apply summary");
    expect(summary).toHaveTextContent("2 of 11 operation(s) replace existing data.");
    expect(screen.getByRole("button", { name: "Apply" })).toBeVisible();
  });

  it("shows the creator and the client id next to the isolated self-declared name", async () => {
    renderReview();

    expect(await screen.findByRole("heading", { name: "Growth model" })).toBeVisible();
    expect(screen.getByText(`Ada Consultant`, { selector: "bdi" }).parentElement).toHaveTextContent(
      `Ada Consultant, ${formatAiTimestamp("2026-10-27T09:00:00Z")}`
    );
    const client = screen.getByText("client-abc").closest("dd") as HTMLElement;
    const name = within(client).getByText("Claude ‮evil");
    expect(name.tagName).toBe("BDI");
    expect(within(client).getByText("(self-declared by the client)")).toBeVisible();
    expect(screen.getByText("No single scenario")).toBeVisible();
  });

  it("shows the reviewing AI client of a change set applied through MCP", async () => {
    fetchDetailMock.mockResolvedValue(
      detail({
        status: "applied",
        reviewedBy: 8,
        reviewedByName: "Rita Reviewer",
        reviewedTime: "2026-10-28T08:00:00Z",
        reviewedVia: "mcp",
        reviewClientId: "client-review",
        reviewClientName: "Claude Code"
      })
    );
    renderReview();

    const channel = (await screen.findByText("Reviewed through")).nextElementSibling as HTMLElement;
    expect(channel).toHaveTextContent("AI client (MCP)");
    expect(within(channel).getByText("client-review")).toBeVisible();
    expect(within(channel).getByText("Claude Code").tagName).toBe("BDI");
    expect(within(channel).getByText("(self-declared by the client)")).toBeVisible();
  });

  it("shows no review channel for a change set reviewed in Schatten", async () => {
    fetchDetailMock.mockResolvedValue(
      detail({
        status: "rejected",
        reviewedBy: 8,
        reviewedByName: "Rita Reviewer",
        reviewedTime: "2026-10-28T08:00:00Z",
        reviewedVia: "web"
      })
    );
    renderReview();

    expect(await screen.findByText("Reviewed by")).toBeVisible();
    expect(screen.queryByText("Reviewed through")).not.toBeInTheDocument();
  });

  it("shows a missing target deleted after submit", async () => {
    fetchDetailMock.mockResolvedValue(
      detail({
        operations: [
          operation(
            0,
            {
              type: "patch_node",
              scenario_key: "future",
              org_state_key: "now",
              node_key: "gone",
              payload: { name: "New name" }
            },
            {
              replacesExisting: true,
              replaces: {
                kind: "node",
                scenarioKey: "future",
                orgStateKey: "now",
                nodeKey: "gone",
                missing: true,
                message: "Graph node not found."
              }
            }
          )
        ]
      })
    );

    renderReview();

    const item = await screen.findByRole("listitem", { name: /Update node gone/ });
    expect(within(item).getByText("Target missing")).toBeVisible();
    expect(
      within(item).getByText(
        "The target was deleted after the change set was submitted: Graph node not found. Apply will fail re-validation."
      )
    ).toBeVisible();
    expect(screen.getByLabelText("Apply summary")).toHaveTextContent(
      "1 operation(s) target data that no longer exists. Apply will fail re-validation."
    );
  });

  it("shows validation errors of the operations and of a failed apply", async () => {
    fetchDetailMock.mockResolvedValue(
      detail({
        status: "failed",
        operations: [
          operation(
            0,
            { type: "create_event", scenario_key: "future", payload: { name: "Dup" } },
            {
              error: {
                code: "domain_error",
                message: "An event with this name already exists.",
                statusCode: 409
              }
            }
          )
        ],
        validationResult: null,
        appliedResult: {
          status: "failed",
          step: "execute",
          error: { code: "domain_error", message: "An event with this name already exists." },
          operations: [],
          refs: {}
        }
      })
    );

    renderReview();

    const errors = await screen.findByRole("region", { name: "Validation errors" });
    expect(errors).toHaveTextContent(
      "Apply failed in step execute: An event with this name already exists."
    );
    expect(within(errors).getByRole("listitem")).toHaveTextContent(
      "#0 create_event: An event with this name already exists."
    );
    const item = screen.getByRole("listitem", { name: /Create event Dup/ });
    expect(
      within(item).getByText("domain_error: An event with this name already exists.")
    ).toBeVisible();
    expect(screen.getByText("Failed")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();

    fireEvent.click(
      within(errors).getByRole("button", { name: "Dismiss Validation errors notice" })
    );
    expect(screen.queryByLabelText("Validation errors")).not.toBeInTheDocument();
  });

  it("applies with the shown review fingerprint after confirmation and lists the created keys", async () => {
    applyMock.mockResolvedValue(appliedResult);
    const { onApplied } = renderReview();

    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    const dialog = screen.getByRole("alertdialog", { name: "Confirm apply" });
    expect(dialog).toHaveTextContent("2 of them replace existing data.");
    expect(dialog).not.toHaveTextContent("unsaved changes");
    expect(applyMock).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm apply" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Change set applied");
    const keys = within(status).getByRole("list", { name: "Created or changed keys" });
    expect(keys).toHaveTextContent("#0 create_scenario: scn-77");
    expect(keys).toHaveTextContent("#8 create_node: node-revenue in scenario future");
    expect(keys).toHaveTextContent("$plan = scn-77");
    expect(applyMock).toHaveBeenCalledWith("acme", "cs-1", fingerprint);
    expect(onApplied).toHaveBeenCalledWith(appliedResult);
    expect(screen.getByText("Applied")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
  });

  it("warns in the apply confirmation that the reload discards unsaved grid changes", async () => {
    renderReview(vi.fn(), vi.fn(), 2);

    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));

    expect(screen.getByRole("alertdialog", { name: "Confirm apply" })).toHaveTextContent(
      "The metrics grid has unsaved changes in 2 timeserie(s); the grid reloads after the apply and discards them. Save them first to keep them."
    );
  });

  it("reloads a stale review and requires a fresh confirmation", async () => {
    applyMock
      .mockRejectedValueOnce(applyError(409, "review_stale", "The data changed."))
      .mockResolvedValueOnce(appliedResult);
    fetchDetailMock
      .mockResolvedValueOnce(detail())
      .mockResolvedValueOnce(detail({ reviewFingerprint: newFingerprint }));
    renderReview();

    await confirmApply();

    expect(await screen.findByText("The replaced data changed")).toBeVisible();
    expect(fetchDetailMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    await confirmApply();

    await screen.findByText("Change set applied");
    expect(applyMock).toHaveBeenNthCalledWith(1, "acme", "cs-1", fingerprint);
    expect(applyMock).toHaveBeenNthCalledWith(2, "acme", "cs-1", newFingerprint);
  });

  it.each([
    [
      409,
      "apply_in_progress",
      "The change set is busy, normally because another apply is running."
    ],
    [503, "apply_unavailable", "The server was busy and nothing was changed."]
  ])(
    "keeps the review on a retryable %i %s and offers Try again",
    async (status, code, message) => {
      applyMock
        .mockRejectedValueOnce(applyError(status, code))
        .mockResolvedValueOnce(appliedResult);
      renderReview();

      await confirmApply();

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(message);
      expect(fetchDetailMock).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("heading", { name: "Growth model" })).toBeVisible();

      fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));

      await screen.findByText("Change set applied");
      expect(applyMock).toHaveBeenCalledTimes(2);
      expect(applyMock).toHaveBeenLastCalledWith("acme", "cs-1", fingerprint);
      expect(fetchDetailMock).toHaveBeenCalledTimes(1);
    }
  );

  it("reloads and shows the current status on a terminal 409", async () => {
    applyMock.mockRejectedValueOnce(
      applyError(409, "not_submitted", "Only a submitted change set can be applied.")
    );
    fetchDetailMock
      .mockResolvedValueOnce(detail())
      .mockResolvedValueOnce(
        detail({ status: "rejected", reviewedByName: "Rita", reviewedTime: "2026-10-28T08:00:00Z" })
      );
    renderReview();

    await confirmApply();

    expect(await screen.findByText("The change set is rejected")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Only a submitted change set can be applied."
    );
    expect(fetchDetailMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Dismiss The change set is rejected notice" })
    );
    expect(screen.queryByText("The change set is rejected")).not.toBeInTheDocument();
  });

  it("rejects with an optional note after confirmation", async () => {
    rejectMock.mockResolvedValue({
      ...detail(),
      status: "rejected",
      reviewedBy: 9,
      reviewedByName: "Rita Reviewer",
      reviewedTime: "2026-10-28T08:00:00Z",
      reviewNote: "Wrong scenario"
    });
    renderReview();

    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = screen.getByRole("alertdialog", { name: "Confirm reject" });
    fireEvent.change(within(dialog).getByLabelText("Note (optional)"), {
      target: { value: "  Wrong scenario " }
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm reject" }));

    expect(await screen.findByText("Change set rejected")).toBeVisible();
    expect(rejectMock).toHaveBeenCalledWith("acme", "cs-1", "Wrong scenario");
    expect(screen.getByText("Rejected")).toBeVisible();
    expect(screen.getByText("Wrong scenario")).toBeVisible();
    expect(applyMock).not.toHaveBeenCalled();
  });

  it("cancels a confirmation without calling the API", async () => {
    renderReview();

    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(rejectMock).not.toHaveBeenCalled();
  });

  it("shows a not-found change set and goes back to the list", async () => {
    fetchDetailMock.mockRejectedValue(new AiApiError(404, "", "Failed (404)."));
    const { onBack } = renderReview();

    expect(
      await screen.findByText("This change set does not exist in this organisation.")
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Back to change sets" }));
    await waitFor(() => expect(onBack).toHaveBeenCalledTimes(1));
  });
});
