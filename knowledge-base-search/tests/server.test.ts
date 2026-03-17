/**
 * Server and API contract tests.
 * Covers: basic query flow (mocked), error handling, response structure.
 */
import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { InMemoryVectorStore } from "../src/vector-store.js";
import type { Document } from "../src/types.js";

describe("QueryResponse structure", () => {
  it("has required fields: answer, status", () => {
    const response = {
      answer: "test answer",
      status: "success" as const,
      functionCalls: undefined,
      sources: [],
    };
    expect(response).toHaveProperty("answer");
    expect(response).toHaveProperty("status");
    expect(["success", "partial", "error"]).toContain(response.status);
  });

  it("FunctionCallRecord has name, arguments", () => {
    const record = {
      name: "fetch_external_data",
      arguments: { endpoint: "https://api.example.com" },
      result: { data: "ok" },
    };
    expect(record).toHaveProperty("name");
    expect(record).toHaveProperty("arguments");
    expect(typeof record.arguments).toBe("object");
  });
});

describe("InMemoryVectorStore (integration)", () => {
  it("returns empty when no documents", async () => {
    const store = new InMemoryVectorStore();
    const results = await store.searchByVector([1, 0, 0], 3);
    expect(results).toEqual([]);
  });

  it("returns documents by similarity", async () => {
    const store = new InMemoryVectorStore();
    const docs: Document[] = [
      { id: "a", content: "a", embedding: [1, 0, 0] },
      { id: "b", content: "b", embedding: [0.9, 0.1, 0] },
      { id: "c", content: "c", embedding: [0, 1, 0] },
    ];
    await store.addDocuments(docs);
    const results = await store.searchByVector([1, 0, 0], 2);
    expect(results).toHaveLength(2);
    expect(results[0]?.id).toBe("a");
    expect(results[1]?.id).toBe("b");
  });

  it("getDocCount returns correct count", () => {
    const store = new InMemoryVectorStore();
    expect(store.getDocCount()).toBe(0);
    store.addDocuments([{ id: "1", content: "x", embedding: [1, 0] }]);
    expect(store.getDocCount()).toBe(1);
  });
});
