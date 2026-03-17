import Mistral from "@mistralai/mistralai";
import type { Document } from "./types.js";
import { InMemoryVectorStore } from "./vector-store.js";

const EMBED_MODEL = "mistral-embed";

export async function searchRelevantDocs(
  query: string,
  vectorStore: InMemoryVectorStore,
  mistralClient: Mistral,
  topK = 5
): Promise<Document[]> {
  const embedRes = await mistralClient.embeddings.create({
    model: EMBED_MODEL,
    inputs: [query],
  });
  const queryEmbedding = embedRes.data[0]?.embedding;
  if (!queryEmbedding) {
    throw new Error("Failed to get query embedding");
  }
  return vectorStore.searchByVector(queryEmbedding, topK);
}
