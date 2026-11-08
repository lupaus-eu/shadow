import Diagram from "diagram-js";
import AlignElementsModule from "diagram-js/lib/features/align-elements/index.js";
import ConnectModule from "diagram-js/lib/features/connect/index.js";
import ContextPadModule from "diagram-js/lib/features/context-pad/index.js";
import CreateModule from "diagram-js/lib/features/create/index.js";
import DistributeElementsModule from "diagram-js/lib/features/distribute-elements/index.js";
import EditorActionsModule from "diagram-js/lib/features/editor-actions/index.js";
import GridSnappingModule from "diagram-js/lib/features/grid-snapping/index.js";
import HandToolModule from "diagram-js/lib/features/hand-tool/index.js";
import KeyboardModule from "diagram-js/lib/features/keyboard/index.js";
import LassoToolModule from "diagram-js/lib/features/lasso-tool/index.js";
import ModelingModule from "diagram-js/lib/features/modeling/index.js";
import MoveModule from "diagram-js/lib/features/move/index.js";
import OutlineModule from "diagram-js/lib/features/outline/index.js";
import OverlaysModule from "diagram-js/lib/features/overlays/index.js";
import PaletteModule from "diagram-js/lib/features/palette/index.js";
import RulesModule from "diagram-js/lib/features/rules/index.js";
import SelectionModule from "diagram-js/lib/features/selection/index.js";
import SnappingModule from "diagram-js/lib/features/snapping/index.js";
import CommandModule from "diagram-js/lib/command/index.js";
import MoveCanvasModule from "diagram-js/lib/navigation/movecanvas/index.js";
import ZoomScrollModule from "diagram-js/lib/navigation/zoomscroll/index.js";
import { describe, expect, it } from "vitest";

// The module check the Structure canvas design asks for (ADR-0051, structure-canvas ticket 02): every diagram-js module the later tickets
// plan to use exists in the installed version, loads under a Diagram (on top of `modeling`, which several of them need and do not bring
// themselves), and provides the service the design names.
const modules: [string, object, string[]][] = [
  ["selection", SelectionModule, ["selection"]],
  ["move", MoveModule, ["move"]],
  ["movecanvas", MoveCanvasModule, ["moveCanvas"]],
  ["zoomscroll", ZoomScrollModule, ["zoomScroll"]],
  ["lasso-tool", LassoToolModule, ["lassoTool"]],
  ["create", CreateModule, ["create"]],
  ["connect", ConnectModule, ["connect"]],
  ["context-pad", ContextPadModule, ["contextPad"]],
  ["palette", PaletteModule, ["palette"]],
  ["rules", RulesModule, ["rules"]],
  ["modeling", ModelingModule, ["modeling"]],
  ["align-elements", AlignElementsModule, ["alignElements"]],
  ["distribute-elements", DistributeElementsModule, ["distributeElements"]],
  ["grid-snapping", GridSnappingModule, ["gridSnapping"]],
  ["snapping", SnappingModule, ["snapping"]],
  ["keyboard", KeyboardModule, ["keyboard"]],
  ["editor-actions", EditorActionsModule, ["editorActions"]],
  ["overlays", OverlaysModule, ["overlays"]],
  ["outline", OutlineModule, ["outline"]],
  ["hand-tool", HandToolModule, ["handTool"]],
  ["command (command stack)", CommandModule, ["commandStack"]],
];

describe("diagram-js modules the Structure canvas design expects", () => {
  it.each(modules)("%s exists and provides its service", (_name, module, services) => {
    const host = document.createElement("div");
    document.body.append(host);
    const diagram = new Diagram({ canvas: { container: host }, modules: [ModelingModule as never, module as never] });
    for (const service of services) expect(diagram.get(service), service).toBeTruthy();
    diagram.destroy();
    host.remove();
  });

  it("loads all of them together (ticket 03 to 07 combine them)", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const diagram = new Diagram({ canvas: { container: host }, modules: modules.map(([, module]) => module as never) });
    expect(diagram.get("editorActions")).toBeTruthy();
    diagram.destroy();
    host.remove();
  });
});
