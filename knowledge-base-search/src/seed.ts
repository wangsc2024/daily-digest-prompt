/**
 * Seed the vector store with sample documents.
 * Run: npm run seed (requires MISTRAL_API_KEY)
 */
import "dotenv/config";
import Mistral from "@mistralai/mistralai";
import { InMemoryVectorStore } from "./vector-store.js";
import type { Document } from "./types.js";

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

async function main() {
  const apiKey = process.env.MISTRAL_API_KEY;
  if (!apiKey) {
    console.error("MISTRAL_API_KEY is required. Set it in .env");
    process.exit(1);
  }

  const client = new Mistral({ apiKey });
  const store = new InMemoryVectorStore();

  console.log("Embedding sample documents...");
  for (const doc of SAMPLE_DOCS) {
    const res = await client.embeddings.create({
      model: "mistral-embed",
      inputs: [doc.content],
    });
    const embedding = res.data[0]?.embedding;
    if (!embedding) {
      console.error(`Failed to embed doc ${doc.id}`);
      continue;
    }
    store.addDocuments([{ ...doc, embedding }]);
  }

  console.log(`Seeded ${SAMPLE_DOCS.length} documents.`);
  console.log("Note: In-memory store resets on restart. For persistence, use Pinecone/Weaviate.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
