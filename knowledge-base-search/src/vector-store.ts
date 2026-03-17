import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import type { Document, ImportNote, StoredNote } from "./types.js";

export interface SearchFilters {
  topic?: string;
  taskType?: string;
  taskTags?: string[];
  keyword?: string;
  tags?: string[];
  kind?: StoredNote["kind"];
  memoryLayer?: StoredNote["memoryLayer"];
  startDate?: string;
  endDate?: string;
  recencyHalfLifeDays?: number;
}

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

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .map((token) => token.trim())
    .filter(Boolean);
}

function keywordScore(note: StoredNote, query: string): number {
  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) return 0;
  const haystack = tokenize(
    `${note.title} ${note.summary} ${note.tags.join(" ")} ${note.contentText}`
  );
  if (haystack.length === 0) return 0;
  const counts = new Map<string, number>();
  for (const token of haystack) {
    counts.set(token, (counts.get(token) ?? 0) + 1);
  }
  let score = 0;
  for (const token of queryTokens) {
    score += counts.get(token) ?? 0;
  }
  return score / queryTokens.length;
}

function toDoc(note: StoredNote): Document {
  return {
    id: note.id,
    content: note.contentText,
    embedding: note.embedding,
    metadata: {
      title: note.title,
      summary: note.summary,
      tags: note.tags,
      source: note.source,
      kind: note.kind,
      topic: note.topic,
      taskType: note.taskType,
      retrievalHints: note.retrievalHints,
      memoryLayer: note.memoryLayer,
      createdAt: note.createdAt,
      updatedAt: note.updatedAt,
      lastAccessedAt: note.lastAccessedAt,
      accessCount: note.accessCount,
      importance: note.importance,
      expiresAt: note.expiresAt,
      digestDate: note.digestDate,
    },
  };
}

function parseDate(value?: string | null): number | null {
  if (!value) return null;
  const ts = Date.parse(value);
  return Number.isNaN(ts) ? null : ts;
}

function deriveMemoryLayer(note: Pick<ImportNote, "memoryLayer" | "digestDate" | "updatedAt" | "createdAt">): StoredNote["memoryLayer"] {
  if (note.memoryLayer) return note.memoryLayer;
  const anchor = parseDate(note.digestDate) ?? parseDate(note.updatedAt) ?? parseDate(note.createdAt);
  if (anchor === null) return "recent";
  const days = (Date.now() - anchor) / (1000 * 60 * 60 * 24);
  return days <= 7 ? "recent" : "archive";
}

function normalizeMemoryLayer(note: StoredNote): StoredNote["memoryLayer"] {
  return deriveMemoryLayer({
    digestDate: note.digestDate,
    updatedAt: note.updatedAt,
    createdAt: note.createdAt,
  });
}

export class InMemoryVectorStore {
  private notes = new Map<string, StoredNote>();

  constructor(private readonly persistPath?: string) {
    this.loadFromDisk();
  }

  private loadFromDisk(): void {
    if (!this.persistPath) return;
    try {
      const raw = readFileSync(this.persistPath, "utf8");
      const parsed = JSON.parse(raw) as { notes?: StoredNote[] };
      for (const note of parsed.notes ?? []) {
        note.memoryLayer = normalizeMemoryLayer(note);
        this.notes.set(note.id, note);
      }
    } catch {
      // Ignore missing/corrupt persistence file and rebuild from runtime state.
    }
  }

  private persist(): void {
    if (!this.persistPath) return;
    mkdirSync(dirname(this.persistPath), { recursive: true });
    writeFileSync(
      this.persistPath,
      JSON.stringify({ notes: this.getAllNotes() }, null, 2),
      "utf8"
    );
  }

  private touch(note: StoredNote): StoredNote {
    const now = new Date().toISOString();
    note.lastAccessedAt = now;
    note.accessCount += 1;
    note.memoryLayer = normalizeMemoryLayer(note);
    this.notes.set(note.id, note);
    return note;
  }

  addDocuments(documents: Document[]): Promise<void> {
    const now = new Date().toISOString();
    for (const doc of documents) {
      const metadata = doc.metadata ?? {};
      const note: StoredNote = {
        id: doc.id,
        title: String(metadata.title ?? doc.id),
        contentText: doc.content,
        tags: Array.isArray(metadata.tags) ? metadata.tags.map(String) : [],
        source: String(metadata.source ?? "manual"),
        summary: String(metadata.summary ?? doc.content.slice(0, 200)),
        topic: typeof metadata.topic === "string" ? metadata.topic : undefined,
        taskType: typeof metadata.taskType === "string" ? metadata.taskType : undefined,
        retrievalHints: Array.isArray(metadata.retrievalHints)
          ? metadata.retrievalHints.map(String)
          : [],
        createdAt: String(metadata.createdAt ?? now),
        updatedAt: String(metadata.updatedAt ?? now),
        lastAccessedAt: String(metadata.lastAccessedAt ?? now),
        accessCount: Number(metadata.accessCount ?? 0),
        importance: Number(metadata.importance ?? 0.5),
        expiresAt:
          metadata.expiresAt === undefined ? null : (metadata.expiresAt as string | null),
        kind: (metadata.kind as StoredNote["kind"] | undefined) ?? "reference",
        digestDate: metadata.digestDate as string | undefined,
        memoryLayer:
          (metadata.memoryLayer as StoredNote["memoryLayer"] | undefined) ??
          deriveMemoryLayer({
            digestDate: metadata.digestDate as string | undefined,
            updatedAt: metadata.updatedAt as string | undefined,
            createdAt: metadata.createdAt as string | undefined,
          }),
        embedding: doc.embedding,
      };
      note.memoryLayer = normalizeMemoryLayer(note);
      this.notes.set(note.id, note);
    }
    this.persist();
    return Promise.resolve();
  }

  upsertNote(note: ImportNote, embedding?: number[]): StoredNote {
    const existing = note.id ? this.notes.get(note.id) : undefined;
    const now = new Date().toISOString();
    const stored: StoredNote = {
      id: note.id ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      title: note.title,
      contentText: note.contentText,
      tags: note.tags ?? existing?.tags ?? [],
      source: note.source ?? existing?.source ?? "import",
      summary:
        note.summary ?? existing?.summary ?? note.contentText.replace(/\s+/g, " ").slice(0, 200),
      topic: note.topic ?? existing?.topic,
      taskType: note.taskType ?? existing?.taskType,
      retrievalHints: note.retrievalHints ?? existing?.retrievalHints ?? [],
      createdAt: existing?.createdAt ?? note.createdAt ?? now,
      updatedAt: note.updatedAt ?? now,
      lastAccessedAt: existing?.lastAccessedAt ?? now,
      accessCount: existing?.accessCount ?? 0,
      importance: note.importance ?? existing?.importance ?? 0.5,
      expiresAt:
        note.expiresAt !== undefined ? note.expiresAt : (existing?.expiresAt ?? null),
      kind: note.kind ?? existing?.kind ?? "reference",
      digestDate: note.digestDate ?? existing?.digestDate,
      memoryLayer:
        note.memoryLayer ??
        existing?.memoryLayer ??
        deriveMemoryLayer({
          digestDate: note.digestDate,
          updatedAt: note.updatedAt ?? existing?.updatedAt,
          createdAt: note.createdAt ?? existing?.createdAt,
        }),
      embedding: embedding ?? existing?.embedding,
    };
    stored.memoryLayer = normalizeMemoryLayer(stored);
    this.notes.set(stored.id, stored);
    this.persist();
    return stored;
  }

  getDocCount(): number {
    return this.getActiveNotes().length;
  }

  getAllNotes(): StoredNote[] {
    return Array.from(this.notes.values()).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }

  getActiveNotes(now = new Date()): StoredNote[] {
    const active: StoredNote[] = [];
    for (const note of this.notes.values()) {
      note.memoryLayer = normalizeMemoryLayer(note);
      if (note.expiresAt && new Date(note.expiresAt) < now) continue;
      active.push(note);
    }
    return active;
  }

  private matchesFilters(note: StoredNote, filters?: SearchFilters): boolean {
    if (!filters) return true;
    if (filters.kind && note.kind !== filters.kind) return false;
    if (filters.memoryLayer && note.memoryLayer !== filters.memoryLayer) return false;
    if (filters.topic) {
      const topic = filters.topic.toLowerCase();
      const haystack = `${note.topic ?? ""} ${note.title} ${note.summary}`.toLowerCase();
      if (!haystack.includes(topic)) return false;
    }
    if (filters.taskType) {
      const taskType = filters.taskType.toLowerCase();
      const haystack = `${note.taskType ?? ""} ${note.tags.join(" ")}`.toLowerCase();
      if (!haystack.includes(taskType)) return false;
    }
    if (filters.keyword) {
      const keyword = filters.keyword.toLowerCase();
      const haystack = `${note.title} ${note.summary} ${note.contentText} ${note.tags.join(" ")}`.toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    if (filters.tags && filters.tags.length > 0) {
      const noteTags = new Set(note.tags.map((tag) => tag.toLowerCase()));
      const expected = filters.tags.map((tag) => tag.toLowerCase());
      if (!expected.every((tag) => noteTags.has(tag))) return false;
    }
    const noteTime =
      parseDate(note.digestDate) ?? parseDate(note.updatedAt) ?? parseDate(note.createdAt);
    const start = parseDate(filters.startDate);
    const end = parseDate(filters.endDate);
    if (start !== null && noteTime !== null && noteTime < start) return false;
    if (end !== null && noteTime !== null && noteTime > end) return false;
    return true;
  }

  private getFilteredNotes(filters?: SearchFilters): StoredNote[] {
    return this.getActiveNotes().filter((note) => this.matchesFilters(note, filters));
  }

  evictExpired(now = new Date()): number {
    let removed = 0;
    for (const [id, note] of this.notes.entries()) {
      if (note.expiresAt && new Date(note.expiresAt) < now) {
        this.notes.delete(id);
        removed += 1;
      }
    }
    if (removed > 0) this.persist();
    return removed;
  }

  async searchByVector(
    queryEmbedding: number[],
    topK = 5,
    filters?: SearchFilters
  ): Promise<Array<Document & { score: number }>> {
    const scored = this.getFilteredNotes(filters)
      .filter((d) => d.embedding && d.embedding.length > 0)
      .map((doc) => ({
        note: doc,
        score: cosineSimilarity(queryEmbedding, doc.embedding!),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .map(({ note, score }) => ({ ...toDoc(this.touch(note)), score }));
    this.persist();
    return scored;
  }

  keywordSearch(query: string, topK = 5, filters?: SearchFilters): Array<Document & { score: number }> {
    const scored = this.getFilteredNotes(filters)
      .map((note) => ({ note, score: keywordScore(note, query) }))
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .map(({ note, score }) => ({ ...toDoc(this.touch(note)), score }));
    this.persist();
    return scored;
  }

  hybridSearch(
    query: string,
    queryEmbedding: number[],
    topK = 5,
    filters?: SearchFilters
  ): Array<Document & { score: number }> {
    const vectorScores = new Map<string, number>();
    for (const entry of this.getFilteredNotes(filters)) {
      if (entry.embedding && entry.embedding.length > 0) {
        vectorScores.set(entry.id, cosineSimilarity(queryEmbedding, entry.embedding));
      }
    }

    const scored = this.getFilteredNotes(filters)
      .map((note) => {
        const semantic = vectorScores.get(note.id) ?? 0;
        const lexical = keywordScore(note, query);
        const freshnessDays = Math.max(
          0,
          (Date.now() - new Date(note.updatedAt).getTime()) / (1000 * 60 * 60 * 24)
        );
        const halfLifeDays = Math.max(1, filters?.recencyHalfLifeDays ?? 60);
        const freshnessBoost = Math.exp(-freshnessDays / halfLifeDays);
        const taskTags = filters?.taskTags ?? [];
        const tagOverlap =
          taskTags.length > 0
            ? taskTags.filter((tag) =>
                note.tags.some((noteTag) => noteTag.toLowerCase() === tag.toLowerCase())
              ).length
            : 0;
        const taskBoost = 1 + 0.2 * tagOverlap;
        const score =
          (
            semantic * 0.55 +
            Math.min(lexical / 3, 1) * 0.25 +
            Math.min(note.importance, 1) * 0.1 +
            freshnessBoost * 0.1
          ) * taskBoost;
        return { note, score };
      })
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .map(({ note, score }) => ({ ...toDoc(this.touch(note)), score }));
    this.persist();
    return scored;
  }

  retrieveContext(
    query: string,
    queryEmbedding: number[],
    topK = 5,
    filters?: SearchFilters
  ): { items: Array<Document & { score: number }>; formattedContext: string } {
    const items = this.hybridSearch(query, queryEmbedding, topK, filters);
    const formattedContext = items
      .map((item, index) => {
        const metadata = item.metadata ?? {};
        const title = String(metadata.title ?? item.id);
        const summary = String(metadata.summary ?? "");
        const tags = Array.isArray(metadata.tags) ? metadata.tags.join(", ") : "";
        const topic = metadata.topic ? `\n主題：${String(metadata.topic)}` : "";
        const taskType = metadata.taskType ? `\n任務類型：${String(metadata.taskType)}` : "";
        const layer = metadata.memoryLayer ? `\n記憶層：${String(metadata.memoryLayer)}` : "";
        const digestDate = metadata.digestDate ? `\n日期：${String(metadata.digestDate)}` : "";
        return `#${index + 1} ${title}\n摘要：${summary}${topic}${taskType}${layer}${digestDate}\n標籤：${tags}\n內容：${item.content}`;
      })
      .join("\n\n");
    return { items, formattedContext };
  }

  listNotes(limit = 20, filters?: SearchFilters): StoredNote[] {
    return this.getFilteredNotes(filters)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, limit);
  }

  stats(): {
    totalNotes: number;
    topTags: Array<{ tag: string; count: number }>;
    layerCounts: Record<StoredNote["memoryLayer"], number>;
  } {
    const tagCounts = new Map<string, number>();
    const layerCounts: Record<StoredNote["memoryLayer"], number> = { recent: 0, archive: 0 };
    for (const note of this.getActiveNotes()) {
      layerCounts[note.memoryLayer] += 1;
      for (const tag of note.tags) {
        tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
      }
    }
    const topTags = Array.from(tagCounts.entries())
      .map(([tag, count]) => ({ tag, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
    return { totalNotes: this.getDocCount(), topTags, layerCounts };
  }

  listTags(): string[] {
    return Array.from(
      new Set(this.getActiveNotes().flatMap((note) => note.tags))
    ).sort((a, b) => a.localeCompare(b));
  }
}
