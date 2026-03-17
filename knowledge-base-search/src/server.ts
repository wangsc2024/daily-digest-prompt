/**
 * Knowledge Base Search API
 * Hono + Mistral 3.2 small / mistral-small + function calling
 */
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
import type { QueryResponse, FunctionCallRecord } from "./types.js";
import type { Document } from "./types.js";

const CHAT_MODEL = process.env.MISTRAL_MODEL ?? "mistral-small-latest";
const PORT = Number(process.env.PORT) || 3000;
const MAX_TOOL_ITERATIONS = 5;

const log = pino({
  level: process.env.LOG_LEVEL ?? "info",
  transport:
    process.env.NODE_ENV !== "production"
      ? { target: "pino-pretty", options: { colorize: true } }
      : undefined,
});

const SAMPLE_DOCS: Omit<Document, "embedding">[] = [
  {
    id: "doc-1",
    content:
      "Retrieval-Augmented Generation (RAG) 是一種結合檢索與生成的 AI 技術。系統先從向量資料庫檢索相關文件，再將檢索結果注入提示詞傳給 LLM 產出答案。",
    metadata: { topic: "RAG", source: "manual" },
  },
  {
    id: "doc-2",
    content:
      "Mistral AI 提供 mistral-small、mistral-large 等模型，支援 function calling 與 embeddings。mistral-embed 可用於文字向量化。",
    metadata: { topic: "Mistral", source: "manual" },
  },
  {
    id: "doc-3",
    content:
      "Hono 是輕量級 TypeScript/JavaScript HTTP 框架，支援 Node.js、Deno、Bun、Cloudflare Workers 等多種運行環境。",
    metadata: { topic: "Hono", source: "manual" },
  },
  {
    id: "doc-4",
    content:
      "Function calling 允許 LLM 決定何時呼叫外部工具，例如查詢 API、搜尋資料庫。模型會回傳函式名稱與參數，由應用程式執行並將結果回饋模型。",
    metadata: { topic: "function-calling", source: "manual" },
  },
  {
    id: "doc-5",
    content:
      "向量資料庫儲存文件的 embedding 向量，透過餘弦相似度或近似最近鄰搜尋找出與查詢最相關的文件片段。常見選擇包含 Pinecone、Weaviate、Chroma。",
    metadata: { topic: "vector-db", source: "manual" },
  },
];

async function seedIfEmpty(
  store: InMemoryVectorStore,
  mistralClient: Mistral
): Promise<void> {
  if (store.getDocCount() > 0) return;

  log.info("Vector store empty, seeding sample documents...");
  for (const doc of SAMPLE_DOCS) {
    const res = await mistralClient.embeddings.create({
      model: "mistral-embed",
      inputs: [doc.content],
    });
    const embedding = res.data[0]?.embedding;
    if (!embedding) {
      log.warn(`Failed to embed doc ${doc.id}`);
      continue;
    }
    await store.addDocuments([{ ...doc, embedding }]);
  }
  log.info(`Seeded ${SAMPLE_DOCS.length} documents`);
}

function buildSystemPrompt(contextDocs: Document[]): string {
  const contextText =
    contextDocs.length > 0
      ? contextDocs
          .map(
            (d) => `[${d.id}]\n${d.content}`
          )
          .join("\n\n")
      : "（無相關知識庫內容）";

  return `你是一個知識庫助手。請根據以下從向量檢索取得的上下文回答使用者問題。若上下文不足以回答，可透過工具搜尋更多內容或呼叫外部 API 取得即時資料。回答請簡潔且基於事實。

## 檢索到的上下文
${contextText}`;
}

const app = new Hono();

app.use("*", logger());
app.use("*", cors());

app.get("/health", (c) => {
  return c.json({ status: "ok", timestamp: new Date().toISOString() });
});

app.post("/query", async (c) => {
  const mistralClient = c.get("mistral") as Mistral;
  const vectorStore = c.get("vectorStore") as InMemoryVectorStore;
  const executorCtx = { vectorStore, mistralClient };

  let body: { query?: string; topK?: number };
  try {
    body = await c.req.json();
  } catch {
    log.warn("Invalid JSON body");
    return c.json(
      { error: "Invalid JSON", status: "error" },
      400
    );
  }

  const query = body?.query;
  if (typeof query !== "string" || !query.trim()) {
    return c.json(
      { error: "Missing or invalid 'query' field", status: "error" },
      400
    );
  }

  const topK = Math.min(10, Math.max(1, Number(body?.topK) || 5));

  log.info({ query, topK }, "Query received");

  const functionCalls: FunctionCallRecord[] = [];
  let answer = "";
  let status: QueryResponse["status"] = "success";

  try {
    // 1. Vector retrieval
    const contextDocs = await searchRelevantDocs(
      query,
      vectorStore,
      mistralClient,
      topK
    );
    log.debug({ count: contextDocs.length }, "Retrieved docs");

    const systemPrompt = buildSystemPrompt(contextDocs);
    type Message =
      | { role: "system"; content: string }
      | { role: "user"; content: string }
      | { role: "assistant"; content?: string; toolCalls?: Array<{ id?: string; function?: { name?: string; arguments?: string } }> }
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

      const choice = chatRes.choices?.[0];
      const msg = choice?.message;

      if (!msg) {
        log.warn("No message in chat response");
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

      // Mistral expects assistant message with tool_calls, then tool messages
      messages.push({
        role: "assistant",
        content: content || undefined,
        toolCalls,
      });

      for (const tc of toolCalls) {
        const name = tc.function?.name ?? "unknown";
        const toolCallId = tc.id ?? `tc-${iterations}-${name}`;
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(tc.function?.arguments ?? "{}");
        } catch {
          log.warn({ name }, "Failed to parse tool arguments");
        }

        log.info({ name, args }, "Executing tool");
        const { result, record } = await executeFunction(name, args, executorCtx);
        functionCalls.push(record);

        messages.push({
          role: "tool",
          content: typeof result === "string" ? result : JSON.stringify(result),
          tool_call_id: toolCallId,
        } as Message);
      }
    }

    if (iterations >= MAX_TOOL_ITERATIONS && !answer) {
      answer = lastContent || "達到工具呼叫上限，請簡化查詢後重試。";
      status = "partial";
    }

    const response: QueryResponse = {
      answer: answer || "無回應。",
      functionCalls: functionCalls.length > 0 ? functionCalls : undefined,
      status,
      sources: contextDocs.map((d) => ({
        id: d.id,
        content: d.content,
      })),
    };

    log.info({ status, fcCount: functionCalls.length }, "Query completed");
    return c.json(response);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log.error({ err, query }, "Query failed");
    return c.json(
      {
        answer: "",
        status: "error" as const,
        error: message,
      },
      500
    );
  }
});

async function main() {
  const apiKey = process.env.MISTRAL_API_KEY;
  if (!apiKey) {
    log.error("MISTRAL_API_KEY is required");
    process.exit(1);
  }

  const mistralClient = new Mistral({ apiKey });
  const vectorStore = new InMemoryVectorStore();

  await seedIfEmpty(vectorStore, mistralClient);

  app.use("*", async (c, next) => {
    c.set("mistral", mistralClient);
    c.set("vectorStore", vectorStore);
    await next();
  });

  const port = PORT;
  log.info({ port, model: CHAT_MODEL }, "Server starting");

  const { serve } = await import("hono/node-server");
  serve(app, (info) => {
    log.info({ port: info.port }, "Listening");
  });
}

main().catch((e) => {
  log.fatal(e);
  process.exit(1);
});

export default app;
