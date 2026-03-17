import "dotenv/config";
import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import Mistral from "@mistralai/mistralai";
import pino from "pino";
import { InMemoryVectorStore } from "./vector-store.js";
import { searchRelevantDocs } from "./retriever.js";
import { TOOLS } from "./tools.js";
import { executeFunction } from "./function-executor.js";
import type {
  Document,
  FunctionCallRecord,
  ImportNote,
  MemoryMetadata,
  QueryResponse,
} from "./types.js";
import type { SearchFilters } from "./vector-store.js";

const CHAT_MODEL = process.env.MISTRAL_MODEL ?? "mistral-small-latest";
const PORT = Number(process.env.PORT) || 3000;
const MAX_TOOL_ITERATIONS = 5;
const STORE_PATH = process.env.KB_STORE_PATH ?? "data/long_term_memory.json";

const log = pino({
  level: process.env.LOG_LEVEL ?? "info",
  transport:
    process.env.NODE_ENV !== "production"
      ? { target: "pino-pretty", options: { colorize: true } }
      : undefined,
});

const SAMPLE_DOCS: Array<ImportNote & { id: string }> = [
  {
    id: "doc-1",
    title: "RAG",
    contentText:
      "Retrieval-Augmented Generation (RAG) 是一種結合檢索與生成的 AI 技術。系統先從向量資料庫檢索相關文件，再將檢索結果注入提示詞傳給 LLM 產出答案。",
    tags: ["RAG", "AI"],
    source: "manual",
    kind: "reference",
    summary: "RAG 結合檢索與生成，先取回上下文再交給模型回答。",
    importance: 0.7,
  },
  {
    id: "doc-2",
    title: "向量資料庫",
    contentText:
      "向量資料庫儲存文件的 embedding 向量，透過餘弦相似度或近似最近鄰搜尋找出與查詢最相關的文件片段。常見選擇包含 Pinecone、Weaviate、Chroma。",
    tags: ["vector-db"],
    source: "manual",
    kind: "reference",
    summary: "向量資料庫用 embedding 做相似度搜尋。",
    importance: 0.7,
  },
];

type Embedder = {
  embed(input: string): Promise<number[]>;
};

class MistralEmbedder implements Embedder {
  constructor(private readonly client: Mistral) {}

  async embed(input: string): Promise<number[]> {
    const res = await this.client.embeddings.create({
      model: "mistral-embed",
      inputs: [input],
    });
    const embedding = res.data[0]?.embedding;
    if (!embedding) throw new Error("Failed to get embedding");
    return embedding;
  }
}

function buildSystemPrompt(contextDocs: Array<Document & { score?: number }>): string {
  const contextText =
    contextDocs.length > 0
      ? contextDocs.map((d) => {
          const title = String(d.metadata?.title ?? d.id);
          const summary = String(d.metadata?.summary ?? "");
          return `[${title}]\n摘要：${summary}\n內容：${d.content}`;
        }).join("\n\n")
      : "（無相關知識庫內容）";

  return `你是一個知識庫助手。請根據以下上下文回答使用者問題。若上下文不足，可呼叫工具補查，但回答仍需明確標出依據。回答請簡潔、具體。 \n\n## 檢索上下文\n${contextText}`;
}

async function seedIfEmpty(store: InMemoryVectorStore, embedder: Embedder): Promise<void> {
  if (store.getDocCount() > 0) return;
  for (const note of SAMPLE_DOCS) {
    const embedding = await embedder.embed(note.contentText);
    store.upsertNote(note, embedding);
  }
}

function buildApp(deps: {
  mistralClient: Mistral;
  vectorStore: InMemoryVectorStore;
  embedder: Embedder;
}): Hono {
  const app = new Hono();

  function parseFilters(payload: Record<string, unknown>): SearchFilters {
    const tags =
      Array.isArray(payload.tags) && payload.tags.length > 0
        ? payload.tags.map((tag) => String(tag))
        : undefined;
    const asString = (value: unknown): string | undefined =>
      typeof value === "string" && value.trim() ? value.trim() : undefined;
    return {
      topic: asString(payload.topic),
      taskType: asString(payload.taskType),
      taskTags:
        Array.isArray(payload.taskTags) && payload.taskTags.length > 0
          ? payload.taskTags.map((tag) => String(tag))
          : undefined,
      keyword: asString(payload.keyword),
      tags,
      kind: asString(payload.kind) as MemoryMetadata["kind"] | undefined,
      memoryLayer: asString(payload.memoryLayer) as MemoryMetadata["memoryLayer"] | undefined,
      startDate: asString(payload.startDate),
      endDate: asString(payload.endDate),
      recencyHalfLifeDays:
        typeof payload.recencyHalfLifeDays === "number"
          ? payload.recencyHalfLifeDays
          : typeof payload.recencyHalfLifeDays === "string" && payload.recencyHalfLifeDays.trim()
            ? Number(payload.recencyHalfLifeDays)
            : undefined,
    };
  }

  app.use("*", logger());
  app.use("*", cors());
  app.use("*", async (c, next) => {
    c.set("mistral", deps.mistralClient);
    c.set("vectorStore", deps.vectorStore);
    c.set("embedder", deps.embedder);
    await next();
  });

  app.get("/health", (c) =>
    c.json({
      status: "ok",
      timestamp: new Date().toISOString(),
      storage: STORE_PATH,
      notes: deps.vectorStore.getDocCount(),
    })
  );

  app.get("/api/health", (c) => c.json({ status: "ok", timestamp: new Date().toISOString() }));

  app.get("/api/notes", (c) => {
    const limit = Math.min(100, Math.max(1, Number(c.req.query("limit") ?? 20)));
    const filters = parseFilters({
      topic: c.req.query("topic"),
      taskType: c.req.query("taskType"),
      taskTags: c.req.query("taskTags")?.split(",").map((tag) => tag.trim()).filter(Boolean),
      keyword: c.req.query("keyword"),
      kind: c.req.query("kind"),
      memoryLayer: c.req.query("memoryLayer"),
      startDate: c.req.query("startDate"),
      endDate: c.req.query("endDate"),
      recencyHalfLifeDays: c.req.query("recencyHalfLifeDays"),
      tags: c.req.query("tags")?.split(",").map((tag) => tag.trim()).filter(Boolean),
    });
    return c.json({ notes: deps.vectorStore.listNotes(limit, filters) });
  });

  app.get("/api/notes/tags", (c) => c.json({ tags: deps.vectorStore.listTags() }));

  app.get("/api/stats", (c) => c.json(deps.vectorStore.stats()));

  app.post("/api/import", async (c) => {
    const body = (await c.req.json()) as { notes?: ImportNote[] };
    const notes = body.notes ?? [];
    const importedIds: string[] = [];
    for (const note of notes) {
      const embedding = await deps.embedder.embed(note.contentText);
      const stored = deps.vectorStore.upsertNote(note, embedding);
      importedIds.push(stored.id);
    }
    const evicted = deps.vectorStore.evictExpired();
    return c.json({
      message: `Imported ${importedIds.length} notes, 0 failed`,
      result: {
        success: true,
        imported: importedIds.length,
        failed: 0,
        errors: [],
        noteIds: importedIds,
        evicted,
      },
    });
  });

  app.post("/api/search/semantic", async (c) => {
    const body = (await c.req.json()) as {
      query?: string;
      topK?: number;
      minScore?: number;
      topic?: string;
      taskType?: string;
      taskTags?: string[];
      keyword?: string;
      tags?: string[];
      kind?: string;
      memoryLayer?: string;
      startDate?: string;
      endDate?: string;
      recencyHalfLifeDays?: number;
    };
    const query = body.query?.trim() ?? "";
    if (!query) return c.json({ error: "Missing query" }, 400);
    const topK = Math.min(50, Math.max(1, Number(body.topK ?? 5)));
    const minScore = Number(body.minScore ?? 0);
    const embedding = await deps.embedder.embed(query);
    const items = (await deps.vectorStore.searchByVector(embedding, topK, parseFilters(body))).filter(
      (item) => item.score >= minScore
    );
    return c.json({ items });
  });

  app.post("/api/search/keyword", async (c) => {
    const body = (await c.req.json()) as {
      query?: string;
      topK?: number;
      topic?: string;
      taskType?: string;
      taskTags?: string[];
      keyword?: string;
      tags?: string[];
      kind?: string;
      memoryLayer?: string;
      startDate?: string;
      endDate?: string;
      recencyHalfLifeDays?: number;
    };
    const query = body.query?.trim() ?? "";
    if (!query) return c.json({ error: "Missing query" }, 400);
    const topK = Math.min(50, Math.max(1, Number(body.topK ?? 5)));
    return c.json({ items: deps.vectorStore.keywordSearch(query, topK, parseFilters(body)) });
  });

  app.post("/api/search/hybrid", async (c) => {
    const body = (await c.req.json()) as {
      query?: string;
      topK?: number;
      topic?: string;
      taskType?: string;
      taskTags?: string[];
      keyword?: string;
      tags?: string[];
      kind?: string;
      memoryLayer?: string;
      startDate?: string;
      endDate?: string;
      recencyHalfLifeDays?: number;
    };
    const query = body.query?.trim() ?? "";
    if (!query) return c.json({ error: "Missing query" }, 400);
    const topK = Math.min(50, Math.max(1, Number(body.topK ?? 5)));
    const embedding = await deps.embedder.embed(query);
    return c.json({ items: deps.vectorStore.hybridSearch(query, embedding, topK, parseFilters(body)) });
  });

  app.post("/api/search/retrieve", async (c) => {
    const body = (await c.req.json()) as {
      query?: string;
      topK?: number;
      topic?: string;
      taskType?: string;
      taskTags?: string[];
      keyword?: string;
      tags?: string[];
      kind?: string;
      memoryLayer?: string;
      startDate?: string;
      endDate?: string;
      recencyHalfLifeDays?: number;
    };
    const query = body.query?.trim() ?? "";
    if (!query) return c.json({ error: "Missing query" }, 400);
    const topK = Math.min(50, Math.max(1, Number(body.topK ?? 5)));
    const embedding = await deps.embedder.embed(query);
    return c.json(deps.vectorStore.retrieveContext(query, embedding, topK, parseFilters(body)));
  });

  app.post("/query", async (c) => {
    const mistralClient = c.get("mistral") as Mistral;
    const vectorStore = c.get("vectorStore") as InMemoryVectorStore;
    const executorCtx = { vectorStore, mistralClient };

    const body = (await c.req.json()) as { query?: string; topK?: number };
    const query = body?.query;
    if (typeof query !== "string" || !query.trim()) {
      return c.json({ error: "Missing or invalid 'query' field", status: "error" }, 400);
    }

    const topK = Math.min(10, Math.max(1, Number(body?.topK) || 5));
    const functionCalls: FunctionCallRecord[] = [];
    let answer = "";
    let status: QueryResponse["status"] = "success";

    try {
      const contextDocs = await searchRelevantDocs(query, vectorStore, mistralClient, topK);
      const systemPrompt = buildSystemPrompt(contextDocs);

      type Message =
        | { role: "system"; content: string }
        | { role: "user"; content: string }
        | {
            role: "assistant";
            content?: string;
            toolCalls?: Array<{ id?: string; function?: { name?: string; arguments?: string } }>;
          }
        | { role: "tool"; content: string; tool_call_id: string };

      const messages: Message[] = [
        { role: "system", content: systemPrompt },
        { role: "user", content: query },
      ];

      let iterations = 0;
      let lastContent = "";

      while (iterations < MAX_TOOL_ITERATIONS) {
        iterations++;
        const chatRes = await mistralClient.chat.complete({
          model: CHAT_MODEL,
          messages,
          tools: TOOLS,
          toolChoice: "auto",
        });

        const msg = chatRes.choices?.[0]?.message;
        if (!msg) {
          status = "partial";
          answer = lastContent || "無法產生回應。";
          break;
        }

        const content = msg.content ?? "";
        if (content) lastContent = content;
        const toolCalls = msg.toolCalls;
        if (!toolCalls || toolCalls.length === 0) {
          answer = content || lastContent || "無回應內容。";
          break;
        }

        messages.push({ role: "assistant", content: content || undefined, toolCalls });
        for (const tc of toolCalls) {
          const name = tc.function?.name ?? "unknown";
          const toolCallId = tc.id ?? `tc-${iterations}-${name}`;
          let args: Record<string, unknown> = {};
          try {
            args = JSON.parse(tc.function?.arguments ?? "{}");
          } catch {
            log.warn({ name }, "Failed to parse tool arguments");
          }
          const { result, record } = await executeFunction(name, args, executorCtx);
          functionCalls.push(record);
          messages.push({
            role: "tool",
            content: typeof result === "string" ? result : JSON.stringify(result),
            tool_call_id: toolCallId,
          });
        }
      }

      if (iterations >= MAX_TOOL_ITERATIONS && !answer) {
        answer = lastContent || "達到工具呼叫上限，請簡化查詢後重試。";
        status = "partial";
      }

      return c.json({
        answer: answer || "無回應。",
        functionCalls: functionCalls.length > 0 ? functionCalls : undefined,
        status,
        sources: contextDocs.map((d) => ({ id: d.id, content: d.content, score: d.score })),
      } satisfies QueryResponse);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      log.error({ err, query }, "Query failed");
      return c.json({ answer: "", status: "error" as const, error: message }, 500);
    }
  });

  return app;
}

async function main() {
  const apiKey = process.env.MISTRAL_API_KEY;
  if (!apiKey) {
    log.error("MISTRAL_API_KEY is required");
    process.exit(1);
  }

  const mistralClient = new Mistral({ apiKey });
  const vectorStore = new InMemoryVectorStore(STORE_PATH);
  const embedder = new MistralEmbedder(mistralClient);
  await seedIfEmpty(vectorStore, embedder);

  const app = buildApp({ mistralClient, vectorStore, embedder });
  log.info({ port: PORT, model: CHAT_MODEL }, "Server starting");

  const { serve } = await import("hono/node-server");
  serve({ fetch: app.fetch, port: PORT }, (info) => {
    log.info({ port: info.port }, "Listening");
  });
}

if (process.env.VITEST !== "true") {
  main().catch((e) => {
    log.fatal(e);
    process.exit(1);
  });
}

export { buildApp, MistralEmbedder };
export default buildApp;
