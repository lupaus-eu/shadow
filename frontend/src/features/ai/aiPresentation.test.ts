import { describe, expect, it } from "vitest";
import { aiAccessFromScope, aiScopeLabel } from "./aiPresentation";

describe("aiAccessFromScope", () => {
  it("parses the scope as a set, in any order", () => {
    expect(aiAccessFromScope("schatten.read")).toBe("read");
    expect(aiAccessFromScope("schatten.read schatten.write")).toBe("readWrite");
    expect(aiAccessFromScope("schatten.write schatten.read")).toBe("readWrite");
  });

  it("reports no access for an empty scope, which a role without AI access gets", () => {
    expect(aiAccessFromScope("")).toBe("none");
  });

  it("rejects write without read and unknown scopes", () => {
    expect(aiAccessFromScope("schatten.write")).toBeNull();
    expect(aiAccessFromScope("schatten.read schatten.admin")).toBeNull();
  });
});

describe("aiScopeLabel", () => {
  it("labels read-only access, also with MCP change-set review on", () => {
    expect(aiScopeLabel("schatten.read")).toBe("Read access");
    expect(aiScopeLabel("schatten.read", true)).toBe("Read access");
  });

  it("labels read and write access in either order by the review flag", () => {
    expect(aiScopeLabel("schatten.read schatten.write")).toBe("Read and propose changes");
    expect(aiScopeLabel("schatten.write schatten.read")).toBe("Read and propose changes");
    expect(aiScopeLabel("schatten.write schatten.read", true)).toBe(
      "Read, propose, apply and reject changes"
    );
  });

  it("labels an empty scope as no access", () => {
    expect(aiScopeLabel("")).toBe("No access");
    expect(aiScopeLabel("", true)).toBe("No access");
  });

  it("shows any other scope verbatim", () => {
    expect(aiScopeLabel("schatten.write")).toBe("schatten.write");
    expect(aiScopeLabel("other.scope")).toBe("other.scope");
  });
});
