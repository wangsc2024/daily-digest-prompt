/**
 * Function calling schema definitions for Mistral.
 * Mistral 3.2 small / mistral-small-latest supports tools with JSON schema.
 */

export const TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "fetch_external_data",
      description: "根據提供的參數呼叫外部 API 取得即時資料。當知識庫中無相關資訊或需要最新數據時使用。",
      parameters: {
        type: "object" as const,
        properties: {
          endpoint: {
            type: "string",
            description: "API 的完整 URL 端點",
          },
          payload: {
            type: "object",
            description: "POST 請求的 JSON 資料（可選）",
          },
        },
        required: ["endpoint"] as const,
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "search_knowledge_base",
      description: "在知識庫中搜尋更多相關內容。當需要額外上下文或使用者問了進階問題時使用。",
      parameters: {
        type: "object" as const,
        properties: {
          query: {
            type: "string",
            description: "搜尋的關鍵字或問題",
          },
          topK: {
            type: "number",
            description: "回傳的結果數量，預設 3",
          },
        },
        required: ["query"] as const,
      },
    },
  },
];

export type ToolName = "fetch_external_data" | "search_knowledge_base";
