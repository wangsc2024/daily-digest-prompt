export interface Document {
  id: string;
  content: string;
  metadata?: Record<string, unknown>;
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
