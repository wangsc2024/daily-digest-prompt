export interface MemoryMetadata {
  title?: string;
  summary?: string;
  tags?: string[];
  source?: string;
  kind?: "digest" | "episodic" | "semantic" | "reference";
  topic?: string;
  taskType?: string;
  retrievalHints?: string[];
  memoryLayer?: "recent" | "archive";
  createdAt?: string;
  updatedAt?: string;
  lastAccessedAt?: string;
  accessCount?: number;
  importance?: number;
  expiresAt?: string | null;
  digestDate?: string;
  [key: string]: unknown;
}

export interface Document {
  id: string;
  content: string;
  metadata?: MemoryMetadata;
  embedding?: number[];
}

export interface QueryRequest {
  query: string;
  topK?: number;
}

export interface FunctionCallRecord {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
}

export interface QueryResponse {
  answer: string;
  functionCalls?: FunctionCallRecord[];
  status: "success" | "partial" | "error";
  sources?: Array<{ id: string; content: string; score?: number }>;
}

export interface ImportNote {
  id?: string;
  title: string;
  contentText: string;
  tags?: string[];
  source?: string;
  summary?: string;
  topic?: string;
  taskType?: string;
  retrievalHints?: string[];
  createdAt?: string;
  updatedAt?: string;
  expiresAt?: string | null;
  importance?: number;
  kind?: MemoryMetadata["kind"];
  digestDate?: string;
  memoryLayer?: MemoryMetadata["memoryLayer"];
}

export interface StoredNote {
  id: string;
  title: string;
  contentText: string;
  tags: string[];
  source: string;
  summary: string;
  topic?: string;
  taskType?: string;
  retrievalHints: string[];
  createdAt: string;
  updatedAt: string;
  lastAccessedAt: string;
  accessCount: number;
  importance: number;
  expiresAt: string | null;
  kind: NonNullable<MemoryMetadata["kind"]>;
  digestDate?: string;
  memoryLayer: NonNullable<MemoryMetadata["memoryLayer"]>;
  embedding?: number[];
}
