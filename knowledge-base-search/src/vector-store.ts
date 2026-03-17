import type { Document } from "./types.js";

function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) return 0;
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!;
    normA += a[i]! * a[i]!;
    normB += b[i]! * b[i]!;
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

export class InMemoryVectorStore {
  private docs: Document[] = [];

  async addDocuments(documents: Document[]): Promise<void> {
    this.docs.push(...documents);
  }

  getDocCount(): number {
    return this.docs.length;
  }

  async searchByVector(queryEmbedding: number[], topK = 5): Promise<Document[]> {
    if (this.docs.length === 0) return [];
    const scored = this.docs
      .filter((d) => d.embedding && d.embedding.length > 0)
      .map((doc) => ({
        doc,
        score: cosineSimilarity(queryEmbedding, doc.embedding!),
      }))
      .sort((a, b) => b.score - a.score);
    return scored.slice(0, topK).map((s) => s.doc);
  }
}
