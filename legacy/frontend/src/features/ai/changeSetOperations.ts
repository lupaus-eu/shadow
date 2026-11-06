import type { AiChangeSetOperationDto } from "../../api/ai";

// A readable operation line: "<action> <subjects joined by →> (<qualifier>)",
// for example "Create node Revenue (GOAL)". Subjects are AI-supplied names and
// are rendered isolated.
export type OperationDescription = {
  action: string;
  subjects: string[];
  qualifier: string | null;
};

export type OperationValue = {
  date: string;
  value: number | string | boolean;
};

type OperationJson = Record<string, unknown>;

function objectField(source: OperationJson, name: string): OperationJson {
  const value = source[name];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as OperationJson)
    : {};
}

function stringField(source: OperationJson, name: string): string | null {
  const value = source[name];
  return typeof value === "string" && value ? value : null;
}

function payloadOf(operation: AiChangeSetOperationDto): OperationJson {
  return objectField(operation.operation, "payload");
}

// Names of the nodes and timeseries the change set itself creates, so later
// operations can name them instead of repeating their client-supplied keys.
export type ChangeSetNames = {
  nodes: Map<string, string>;
  timeseries: Map<string, string>;
};

export function changeSetNames(operations: AiChangeSetOperationDto[]): ChangeSetNames {
  const nodes = new Map<string, string>();
  const timeseries = new Map<string, string>();
  for (const operation of operations) {
    const payload = payloadOf(operation);
    const id = stringField(payload, "id");
    const name = stringField(payload, "name");
    if (!id || !name) continue;
    if (operation.type === "create_node") nodes.set(id, name);
    if (operation.type === "create_timeserie") timeseries.set(id, name);
  }
  return { nodes, timeseries };
}

function nodeName(names: ChangeSetNames, key: string | null): string {
  if (!key) return "?";
  return names.nodes.get(key) ?? key;
}

function timeserieName(names: ChangeSetNames, key: string | null): string {
  if (!key) return "?";
  return names.timeseries.get(key) ?? key;
}

function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function describeOperation(
  operation: AiChangeSetOperationDto,
  names: ChangeSetNames
): OperationDescription {
  const json = operation.operation;
  const payload = payloadOf(operation);
  const name = stringField(payload, "name");

  switch (operation.type) {
    case "create_scenario":
      return { action: "Create scenario", subjects: [name ?? "?"], qualifier: null };
    case "copy_scenario":
      return {
        action: "Copy scenario",
        subjects: [stringField(payload, "sourceScenarioId") ?? "?"],
        qualifier: name ? `as ${name}` : null
      };
    case "create_org_state":
      return {
        action: "Create organisation state",
        subjects: [name ?? "?"],
        qualifier: stringField(payload, "targetDate")
      };
    case "create_event":
      return {
        action: "Create event",
        subjects: [name ?? "?"],
        qualifier: stringField(payload, "targetDate")
      };
    case "create_timeserie": {
      const units = [stringField(payload, "timeUnit"), stringField(payload, "valueUnit")].filter(
        (value): value is string => value !== null
      );
      return {
        action: "Create timeserie",
        subjects: [name ?? "?"],
        qualifier: units.length > 0 ? units.join(", ") : null
      };
    }
    case "set_timeserie_values": {
      const values = payload.values;
      return {
        action: "Set values of timeserie",
        subjects: [timeserieName(names, stringField(json, "timeserie_key"))],
        qualifier: Array.isArray(values) ? countLabel(values.length, "value") : null
      };
    }
    case "generate_timeserie_values":
      return {
        action: "Generate values for timeserie",
        subjects: [timeserieName(names, stringField(json, "timeserie_key"))],
        qualifier: operation.frozenValues
          ? countLabel(operation.frozenValues.valueCount, "value")
          : null
      };
    case "create_derived_metric":
      return {
        action: "Create derived metric",
        subjects: [name ?? "?"],
        qualifier: stringField(payload, "formula")
      };
    case "create_node":
      return {
        action: "Create node",
        subjects: [name ?? "?"],
        qualifier: stringField(payload, "nodeTypeId")
      };
    case "patch_node":
      return {
        action: "Update node",
        subjects: [nodeName(names, stringField(json, "node_key"))],
        qualifier: Object.keys(payload).join(", ") || null
      };
    case "create_edge":
      return {
        action: "Create edge",
        subjects: [
          nodeName(names, stringField(payload, "sourceNodeId")),
          nodeName(names, stringField(payload, "targetNodeId"))
        ],
        qualifier: stringField(payload, "edgeTypeId")
      };
    default:
      return { action: operation.type, subjects: [], qualifier: null };
  }
}

// The scenario, organisation state and own key the operation addresses, for
// the line under its description.
export function operationTargets(operation: AiChangeSetOperationDto): Array<[string, string]> {
  const json = operation.operation;
  const payload = payloadOf(operation);
  const targets: Array<[string, string]> = [];
  const scenario = stringField(json, "scenario_key");
  const orgState = stringField(json, "org_state_key");
  const node = stringField(json, "node_key");
  const timeserie = stringField(json, "timeserie_key");
  const id = stringField(payload, "id");
  if (scenario) targets.push(["Scenario", scenario]);
  if (orgState) targets.push(["Org state", orgState]);
  if (node) targets.push(["Node", node]);
  if (timeserie) targets.push(["Timeserie", timeserie]);
  if (id) targets.push(["Key", id]);
  if (operation.ref) targets.push(["Ref", operation.ref]);
  return targets;
}

function isOperationValue(value: unknown): value is OperationValue {
  if (!value || typeof value !== "object") return false;
  const item = value as { date?: unknown; value?: unknown };
  return (
    typeof item.date === "string" &&
    (typeof item.value === "number" ||
      typeof item.value === "string" ||
      typeof item.value === "boolean")
  );
}

// The values a timeserie operation sets: the staged values, or the generated
// values frozen on submit. Null for other operations, and for frozen values
// the detail returns only as a summary.
export function operationValues(operation: AiChangeSetOperationDto): OperationValue[] | null {
  if (operation.type === "set_timeserie_values") {
    const values = payloadOf(operation).values;
    return Array.isArray(values) ? values.filter(isOperationValue) : null;
  }
  if (operation.type === "generate_timeserie_values") {
    return operation.frozenValues?.values ?? null;
  }
  return null;
}

// The patched node fields: the proposed value from the payload next to the
// current value from the detail's recomputed replacement summary.
export function patchedFields(
  operation: AiChangeSetOperationDto
): Array<{ field: string; current: unknown; proposed: unknown }> {
  if (operation.type !== "patch_node") return [];
  const payload = payloadOf(operation);
  const current =
    operation.replaces?.kind === "node" && operation.replaces.fields
      ? operation.replaces.fields
      : {};
  return Object.keys(payload).map((field) => ({
    field,
    current: current[field],
    proposed: payload[field]
  }));
}

export function formatFieldValue(value: unknown): string {
  if (value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
