import type { PlannerMessages } from "../../i18n";
import { SegmentedControl } from "../../ui";
import { AVAILABLE_DISPLAYS, type Display } from "./display-mode";

/** The Display choice in the planner toolbar; hidden while only the circle exists. */
export function DisplaySwitch({ value, onChange, copy, available = AVAILABLE_DISPLAYS }: { value: Display; onChange: (display: Display) => void; copy: PlannerMessages["display"]; available?: readonly Display[] }) {
  if (available.length < 2) return null;
  return <SegmentedControl label={copy.label} value={value} options={available.map((display) => ({ value: display, label: copy[display] }))} onChange={onChange} />;
}
