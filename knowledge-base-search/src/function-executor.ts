import type Mistral from "@mistralai/mistralai";
import type { Document } from "./types.js";
import { searchRelevantDocs } from "./retriever.js";
import type { InMemoryVectorStore } from "./vector-store.js";
import type { FunctionCallRecord } from "./types.js";

const MAX_FETCH_BODY = 100_000;
const FETCH_TIMEOUT_MS = 10_000;

export interface ExecutorContext {
  vectorStore: InMemoryVectorStore;
  mistralClient: Mistral;
}

export async function executeFunction(
  name: string,
  args: Record<string, unknown>,
  ctx: ExecutorContext
): Promise<{ result: unknown; record: FunctionCallRecord }> {
  const record: FunctionCallRecord = { name, arguments: args };

  try {
    if (name === "fetch_external_data") {
      const endpoint = String(args.endpoint ?? "");
      if (!endpoint || !endpoint.startsWith("http")) {
        throw new Error("Invalid endpoint: must be a valid HTTP URL");
      }
      const payload = args.payload as Record<string, unknown> | undefined;
      const res = await fetch(endpoint, {
        method: payload ? "POST" : "GET",
        headers: { "Content-Type": "application/json" },
        body: payload ? JSON.stringify(payload) : undefined,
        signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      });
      const text = await res.text();
      if (text.length > MAX_FETCH_BODY) {
        record.result = { truncated: true, length: text.length, preview: text.slice(0, 500) };
      } else {
        try {
          record.result = JSON.parse(text);
        } catch {
          record.result = text;
        }
      }
    } else if (name === "search_knowledge_base") {
      const query = String(args.query ?? "");
      const topK = Math.min(10, Math.max(1, Number(args.topK) || 3));
      const docs = await searchRelevantDocs(
        query,
        ctx.vectorStore,
        ctx.mistralClient,
        topK
      );
      record.result = docs.map((d) => ({ id: d.id, content: d.content }));
    } else {
      record.result = { error: `Unknown function: ${name}` };
    }
    return { result: record.result, record };
  } catch (err) {
    record.result = { error: String(err) };
    return { result: record.result, record };
  }
}
