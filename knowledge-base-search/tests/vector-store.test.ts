import { describe, it, expect } from "vitest";
import { InMemoryVectorStore } from "../src/vector-store.js";

describe("InMemoryVectorStore", () => {
  it("returns 0 for empty store", () => {
    const store = new InMemoryVectorStore();
    expect(store.getDocCount()).toBe(0);
  });

  it("adds documents and returns count", async () => {
    const store = new InMemoryVectorStore();
    const docs = [
      { id: "a", content: "hello", embedding: [1, 0, 0] },
      { id: "b", content: "world", embedding: [0, 1, 0] },
    ];
    await store.addDocuments(docs);
    expect(store.getDocCount()).toBe(2);
  });

  it("searches by vector similarity", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      { id: "a", content: "first", embedding: [1, 0, 0] },
      { id: "b", content: "second", embedding: [0.9, 0.1, 0] },
      { id: "c", content: "third", embedding: [0, 0, 1] },
    ]);
    // Query similar to [1,0,0] should return a, then b
    const results = await store.searchByVector([1, 0, 0], 2);
    expect(results).toHaveLength(2);
    expect(results[0]?.id).toBe("a");
    expect(results[1]?.id).toBe("b");
  });

  it("returns empty when store empty", async () => {
    const store = new InMemoryVectorStore();
    const results = await store.searchByVector([1, 2, 3], 5);
    expect(results).toHaveLength(0);
  });
});
