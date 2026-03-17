import { describe, it, expect, vi } from "vitest";
import { executeFunction } from "../src/function-executor.js";
import type { InMemoryVectorStore } from "../src/vector-store.js";

const mockVectorStore = {
  searchByVector: vi.fn(),
  addDocuments: vi.fn(),
  getDocCount: vi.fn(() => 5),
} as unknown as InMemoryVectorStore;

const mockMistral = {} as any;

describe("executeFunction", () => {
  it("executes fetch_external_data with valid URL", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      text: async () => '{"status":"ok"}',
    } as Response);

    const { result, record } = await executeFunction(
      "fetch_external_data",
      { endpoint: "https://httpbin.org/get" },
      { vectorStore: mockVectorStore, mistralClient: mockMistral }
    );

    expect(record.name).toBe("fetch_external_data");
    expect(record.arguments).toEqual({ endpoint: "https://httpbin.org/get" });
    expect(result).toEqual({ status: "ok" });
    fetchSpy.mockRestore();
  });

  it("rejects invalid endpoint for fetch_external_data", async () => {
    const { record } = await executeFunction(
      "fetch_external_data",
      { endpoint: "not-a-url" },
      { vectorStore: mockVectorStore, mistralClient: mockMistral }
    );
    expect(record.result).toMatchObject({ error: expect.any(String) });
  });

  it("returns error for unknown function", async () => {
    const { record } = await executeFunction(
      "unknown_fn",
      {},
      { vectorStore: mockVectorStore, mistralClient: mockMistral }
    );
    expect(record.result).toEqual({ error: "Unknown function: unknown_fn" });
  });
});
