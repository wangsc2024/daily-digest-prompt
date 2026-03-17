import { describe, it, expect } from "vitest";
import { TOOLS } from "../src/tools.js";

describe("TOOLS", () => {
  it("defines fetch_external_data tool", () => {
    const tool = TOOLS.find((t) => t.function?.name === "fetch_external_data");
    expect(tool).toBeDefined();
    expect(tool?.function?.parameters?.required).toContain("endpoint");
  });

  it("defines search_knowledge_base tool", () => {
    const tool = TOOLS.find((t) => t.function?.name === "search_knowledge_base");
    expect(tool).toBeDefined();
    expect(tool?.function?.parameters?.required).toContain("query");
  });

  it("has valid JSON schema structure", () => {
    for (const t of TOOLS) {
      expect(t.type).toBe("function");
      expect(t.function?.name).toBeTruthy();
      expect(t.function?.description).toBeTruthy();
      expect(t.function?.parameters?.type).toBe("object");
    }
  });
});
