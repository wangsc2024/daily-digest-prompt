import { describe, it, expect } from "vitest";
import { InMemoryVectorStore } from "../src/vector-store.js";

describe("InMemoryVectorStore", () => {
  it("returns 0 for empty store", () => {
    const store = new InMemoryVectorStore();
    expect(store.getDocCount()).toBe(0);
  });

  it("adds documents and returns count", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      { id: "a", content: "hello", embedding: [1, 0, 0] },
      { id: "b", content: "world", embedding: [0, 1, 0] },
    ]);
    expect(store.getDocCount()).toBe(2);
  });

  it("searches by vector similarity", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      { id: "a", content: "first", embedding: [1, 0, 0] },
      { id: "b", content: "second", embedding: [0.9, 0.1, 0] },
      { id: "c", content: "third", embedding: [0, 0, 1] },
    ]);
    const results = await store.searchByVector([1, 0, 0], 2);
    expect(results).toHaveLength(2);
    expect(results[0]?.id).toBe("a");
    expect(results[1]?.id).toBe("b");
  });

  it("supports keyword and hybrid search with metadata ranking", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      {
        id: "digest-1",
        content: "AI digest memory entry",
        embedding: [1, 1, 0],
        metadata: {
          title: "Digest",
          tags: ["daily-digest", "AI", "系統開發"],
          importance: 0.9,
          summary: "AI digest",
          taskType: "ai_sysdev",
        },
      },
      {
        id: "ref-1",
        content: "policy archive entry",
        embedding: [0, 0, 1],
        metadata: { title: "Policy", tags: ["policy"], importance: 0.4, summary: "policy" },
      },
    ]);

    const keyword = store.keywordSearch("policy archive", 2);
    expect(keyword[0]?.id).toBe("ref-1");

    const hybrid = store.hybridSearch("AI digest", [1, 1, 0], 2, {
      taskType: "ai_sysdev",
      taskTags: ["AI", "系統開發"],
      recencyHalfLifeDays: 60,
    });
    expect(hybrid[0]?.id).toBe("digest-1");
  });

  it("evicts expired memories", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      {
        id: "expired",
        content: "old",
        embedding: [1, 0, 0],
        metadata: { expiresAt: "2020-01-01T00:00:00.000Z" },
      },
      {
        id: "active",
        content: "new",
        embedding: [0, 1, 0],
        metadata: { expiresAt: "2999-01-01T00:00:00.000Z" },
      },
    ]);
    expect(store.evictExpired(new Date("2026-03-17T00:00:00.000Z"))).toBe(1);
    expect(store.getDocCount()).toBe(1);
    expect(store.listNotes(10)[0]?.id).toBe("active");
  });

  it("keeps hybrid query latency under 200ms for 10,000 entries", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments(
      Array.from({ length: 10000 }, (_, index) => ({
        id: `doc-${index}`,
        content: `daily digest memory ${index}`,
        embedding: [index % 7, index % 11, index % 13, 1],
        metadata: {
          title: `Doc ${index}`,
          tags: ["daily-digest", `bucket-${index % 10}`],
          importance: (index % 10) / 10,
          summary: `summary ${index}`,
        },
      }))
    );

    const start = performance.now();
    const results = store.hybridSearch("daily digest memory", [1, 1, 1, 1], 5);
    const elapsed = performance.now() - start;

    expect(results).toHaveLength(5);
    expect(elapsed).toBeLessThan(200);
  });

  it("filters by topic, time range, and memory layer", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      {
        id: "recent-ai",
        content: "AI digest memory entry",
        embedding: [1, 0, 0],
        metadata: {
          title: "Recent AI Digest",
          topic: "AI",
          digestDate: "2026-03-16",
          createdAt: "2026-03-16T08:00:00.000Z",
          updatedAt: "2026-03-16T08:00:00.000Z",
        },
      },
      {
        id: "archive-policy",
        content: "policy archive entry",
        embedding: [0, 1, 0],
        metadata: {
          title: "Archived Policy Digest",
          topic: "policy",
          digestDate: "2026-02-01",
          createdAt: "2026-02-01T08:00:00.000Z",
          updatedAt: "2026-02-01T08:00:00.000Z",
        },
      },
    ]);

    const recent = store.listNotes(10, { memoryLayer: "recent", topic: "AI" });
    const archived = store.listNotes(10, {
      memoryLayer: "archive",
      startDate: "2026-02-01",
      endDate: "2026-02-28",
    });

    expect(recent).toHaveLength(1);
    expect(recent[0]?.id).toBe("recent-ai");
    expect(archived).toHaveLength(1);
    expect(archived[0]?.id).toBe("archive-policy");
    expect(store.stats().layerCounts.archive).toBe(1);
  });

  it("boosts notes that match task tags while keeping time decay", async () => {
    const store = new InMemoryVectorStore();
    await store.addDocuments([
      {
        id: "matched-task",
        content: "AI system development digest memory",
        embedding: [1, 1, 0],
        metadata: {
          title: "AI Sysdev Digest",
          tags: ["AI", "系統開發", "daily-digest"],
          taskType: "ai_sysdev",
          updatedAt: "2026-03-17T08:00:00.000Z",
        },
      },
      {
        id: "older-generic",
        content: "AI digest memory",
        embedding: [1, 1, 0],
        metadata: {
          title: "Generic AI Digest",
          tags: ["AI", "daily-digest"],
          updatedAt: "2025-12-01T08:00:00.000Z",
        },
      },
    ]);

    const results = store.hybridSearch("AI digest memory", [1, 1, 0], 2, {
      taskType: "ai_sysdev",
      taskTags: ["AI", "系統開發"],
      recencyHalfLifeDays: 60,
    });

    expect(results[0]?.id).toBe("matched-task");
    expect(results[0]?.metadata.taskType).toBe("ai_sysdev");
  });
});
