import { describe, it, expect } from "vitest";
import { buildApp } from "../src/server.js";
import { InMemoryVectorStore } from "../src/vector-store.js";

class FakeEmbedder {
  async embed(input: string): Promise<number[]> {
    const tokens = input.toLowerCase();
    return [
      tokens.includes("digest") ? 1 : 0,
      tokens.includes("ai") ? 1 : 0,
      tokens.includes("policy") ? 1 : 0,
      Math.min(input.length / 100, 1),
    ];
  }
}

const fakeMistral = {
  chat: {
    complete: async () => ({
      choices: [{ message: { content: "stubbed answer" } }],
    }),
  },
  embeddings: {
    create: async ({ inputs }: { inputs: string[] }) => ({
      data: inputs.map((input) => ({
        embedding: [
          input.includes("digest") ? 1 : 0,
          input.includes("AI") || input.includes("ai") ? 1 : 0,
          input.includes("政策") || input.includes("policy") ? 1 : 0,
          Math.min(input.length / 100, 1),
        ],
      })),
    }),
  },
} as any;

function createApp() {
  const store = new InMemoryVectorStore();
  const app = buildApp({
    mistralClient: fakeMistral,
    vectorStore: store,
    embedder: new FakeEmbedder(),
  });
  return { app, store };
}

describe("knowledge-base REST API", () => {
  it("imports notes and exposes stats", async () => {
    const { app } = createApp();
    const importRes = await app.request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        notes: [
          {
            title: "Daily Digest Memory - 2026-03-17",
            contentText: "AI digest with policy summary",
            tags: ["Daily-Digest-Prompt", "daily-digest"],
            summary: "Digest summary",
            kind: "digest",
            importance: 0.8,
          },
        ],
      }),
    });
    expect(importRes.status).toBe(200);
    const importJson = await importRes.json();
    expect(importJson.result.imported).toBe(1);

    const statsRes = await app.request("/api/stats");
    const statsJson = await statsRes.json();
    expect(statsJson.totalNotes).toBe(1);
    expect(statsJson.topTags[0].tag).toBe("Daily-Digest-Prompt");
  });

  it("supports hybrid and retrieve queries for digest memory", async () => {
    const { app } = createApp();
    await app.request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        notes: [
          {
            title: "Daily Digest Memory - 2026-03-17",
            contentText: "AI digest with policy summary and context budget note",
            tags: ["daily-digest", "AI"],
            summary: "AI digest",
            kind: "digest",
          },
          {
            title: "Reference Memory",
            contentText: "Long-term policy reference",
            tags: ["policy"],
            summary: "Policy note",
            kind: "semantic",
          },
        ],
      }),
    });

    const hybridRes = await app.request("/api/search/hybrid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "AI digest", topK: 2 }),
    });
    const hybridJson = await hybridRes.json();
    expect(hybridJson.items).toHaveLength(2);
    expect(hybridJson.items[0].metadata.title).toContain("Daily Digest Memory");

    const retrieveRes = await app.request("/api/search/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "policy summary", topK: 2 }),
    });
    const retrieveJson = await retrieveRes.json();
    expect(retrieveJson.formattedContext).toContain("摘要");
    expect(retrieveJson.items.length).toBeGreaterThan(0);
  });

  it("supports topic, layer, and time filters", async () => {
    const { app } = createApp();
    await app.request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        notes: [
          {
            title: "Daily Digest Memory - 2026-03-17",
            contentText: "AI digest context",
            tags: ["daily-digest", "AI"],
            topic: "AI",
            digestDate: "2026-03-17",
            memoryLayer: "recent",
            kind: "digest",
          },
          {
            title: "Daily Digest Memory - 2026-02-01",
            contentText: "policy digest context",
            tags: ["daily-digest", "policy"],
            topic: "policy",
            digestDate: "2026-02-01",
            memoryLayer: "archive",
            kind: "digest",
          },
        ],
      }),
    });

    const notesRes = await app.request(
      "/api/notes?limit=10&topic=policy&memoryLayer=archive&startDate=2026-02-01&endDate=2026-02-28"
    );
    const notesJson = await notesRes.json();
    expect(notesJson.notes).toHaveLength(1);
    expect(notesJson.notes[0].topic).toBe("policy");

    const searchRes = await app.request("/api/search/hybrid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: "digest",
        topic: "AI",
        memoryLayer: "recent",
        topK: 5,
      }),
    });
    const searchJson = await searchRes.json();
    expect(searchJson.items).toHaveLength(1);
    expect(searchJson.items[0].metadata.memoryLayer).toBe("recent");
  });

  it("accepts task-type boost parameters for digest retrieval", async () => {
    const { app } = createApp();
    await app.request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        notes: [
          {
            title: "Daily Digest Memory - 2026-03-17",
            contentText: "AI system development digest context",
            tags: ["daily-digest", "AI", "系統開發"],
            topic: "AI",
            taskType: "ai_sysdev",
            digestDate: "2026-03-17",
            kind: "digest",
          },
        ],
      }),
    });

    const retrieveRes = await app.request("/api/search/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: "AI digest",
        taskType: "ai_sysdev",
        taskTags: ["AI", "系統開發"],
        recencyHalfLifeDays: 45,
        topK: 3,
      }),
    });
    const retrieveJson = await retrieveRes.json();

    expect(retrieveJson.items).toHaveLength(1);
    expect(retrieveJson.formattedContext).toContain("任務類型：ai_sysdev");
  });
});
