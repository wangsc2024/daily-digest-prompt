# Chat 對話系統規劃報告：具備 Function Calling 與工具調用能力的完整方案

> **版本**: v1.1（自審優化版）
> **日期**: 2026-03-17
> **狀態**: 規劃中（待確認後實作）
> **Todoist Task**: 6g3Q4V4crqCxX7HX

---

## 一、專案目標與範圍

### 1.1 核心目標

在現有 `my-gun-relay` 基礎上，建構一個具備 **Function Calling（工具調用）** 能力的 Chat 對話系統，讓使用者透過自然語言與 LLM 對話，LLM 可自主決定呼叫後端工具並將結果整合回覆。

### 1.2 設計原則

| 原則 | 說明 |
|------|------|
| **漸進式升級** | 在現有 Gun.js 加密聊天基礎上疊加，不重寫 |
| **Skill-First** | 工具系統直接復用 daily-digest-prompt 的 Skills 生態 |
| **SSE + WebSocket 混合** | LLM Streaming 用 SSE，即時聊天用 WebSocket（現有 Gun.js） |
| **Human-in-the-Loop** | 敏感工具呼叫需使用者確認 |
| **本地優先** | 不依賴外部 SaaS，所有元件本地部署 |

### 1.3 範圍界定

| 範圍內 | 範圍外 |
|--------|--------|
| 單一使用者對話（個人助手） | 多租戶/多使用者管理 |
| Function Calling（工具調用） | 語音輸入/輸出 |
| LLM Token Streaming | 圖片/檔案上傳處理 |
| 對話歷史持久化 | 複雜的 RAG Pipeline |
| 工具註冊與動態發現 | 付費計費系統 |
| 基本安全防護 | 企業級 SSO/LDAP |

---

## 二、系統架構

### 2.1 整體架構圖

```
┌─────────────────────────────────────────────────────┐
│                  前端 (React SPA)                     │
│  ┌───────────┐  ┌───────────┐  ┌──────────────────┐ │
│  │ Chat Panel │  │ Tool Panel│  │ Settings Panel   │ │
│  │ (對話介面) │  │ (工具狀態)│  │ (模型/工具配置)  │ │
│  └─────┬─────┘  └─────┬─────┘  └──────────────────┘ │
│        │ SSE(Streaming) │ REST                        │
└────────┼───────────────┼────────────────────────────┘
         │               │
┌────────▼───────────────▼────────────────────────────┐
│              後端 API (FastAPI)                       │
│  ┌──────────────────────────────────────────────┐   │
│  │              路由層 (Router)                   │   │
│  │  /api/chat    /api/tools   /api/conversations │   │
│  └──────────────────┬───────────────────────────┘   │
│  ┌──────────────────▼───────────────────────────┐   │
│  │           對話引擎 (Chat Engine)              │   │
│  │  ┌────────────┐  ┌─────────────────────────┐ │   │
│  │  │ LLM Client │  │ Tool Orchestrator       │ │   │
│  │  │ (Groq/     │  │ (工具註冊/發現/執行/    │ │   │
│  │  │  Claude)   │  │  結果回傳)              │ │   │
│  │  └────────────┘  └─────────────────────────┘ │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │           工具層 (Tool Registry)              │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌───────┐ │   │
│  │  │知識庫  │ │Todoist │ │屏東新聞│ │自訂.. │ │   │
│  │  │查詢    │ │任務    │ │查詢    │ │工具   │ │   │
│  │  └────────┘ └────────┘ └────────┘ └───────┘ │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │           資料層 (Storage)                    │   │
│  │  SQLite (對話歷史) + JSON (工具配置)          │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────┐
│              現有整合層                               │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Gun.js   │  │ KB API   │  │ Todoist API       │  │
│  │ Relay    │  │ :3000    │  │                   │  │
│  │ :3001    │  │          │  │                   │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 2.2 技術棧選擇

| 層級 | 技術 | 理由 |
|------|------|------|
| **後端框架** | FastAPI (Python) | 原生 async、SSE StreamingResponse、自動 OpenAPI 文件 |
| **前端框架** | React + Vite + TypeScript | 元件化、HMR、生態豐富 |
| **前端樣式** | Tailwind CSS | 與現有 index.html 風格一致（dark navy + indigo accent） |
| **LLM 呼叫** | Groq SDK（主） + Claude API（備） | Groq 低延遲；Claude 複雜推理 |
| **LLM Streaming** | SSE (Server-Sent Events) | 80% 場景 SSE 就夠，比 WebSocket 簡單可靠 |
| **即時聊天** | 保留 Gun.js WebSocket | 現有 E2E 加密通道不動 |
| **資料庫** | SQLite (aiosqlite) | 輕量、零配置、適合單用戶 |
| **Python 管理** | uv | 專案慣例 |
| **部署** | 本地 (localhost) | 不使用 Docker（專案規範） |

### 2.3 埠號規劃

| 服務 | 埠號 | 說明 |
|------|------|------|
| FastAPI 後端 | 8000 | Chat API + 前端靜態檔託管 |
| Gun.js Relay | 8765 | 現有（index.js） |
| Bot API | 3001 | 現有（bot.js） |
| 知識庫 API | 3000 | 現有 |
| Groq Relay | 3002 | 現有（bot/groq-relay.js） |

---

## 三、API 架構設計

### 3.1 RESTful API 端點

#### 對話管理

| 方法 | 路由 | 說明 |
|------|------|------|
| POST | `/api/chat` | 發送訊息並取得 LLM 回應（SSE Streaming） |
| GET | `/api/conversations` | 列出對話紀錄 |
| GET | `/api/conversations/{id}` | 取得單一對話完整歷史 |
| DELETE | `/api/conversations/{id}` | 刪除對話 |
| POST | `/api/conversations` | 建立新對話 |

#### 工具管理

| 方法 | 路由 | 說明 |
|------|------|------|
| GET | `/api/tools` | 列出所有已註冊工具 |
| GET | `/api/tools/{name}` | 取得單一工具詳情 |
| POST | `/api/tools/{name}/execute` | 手動執行工具（測試用） |
| PUT | `/api/tools/{name}/toggle` | 啟用/停用工具 |

#### 系統

| 方法 | 路由 | 說明 |
|------|------|------|
| GET | `/api/health` | 健康檢查 |
| GET | `/api/config` | 取得前端需要的配置 |

### 3.2 核心 API：`POST /api/chat`（SSE Streaming）

**請求格式**：

```json
{
  "conversation_id": "uuid-or-null",
  "message": "幫我查詢知識庫中關於 React Hooks 的筆記",
  "model": "groq-llama-3.3-70b",
  "tool_choice": "auto",
  "max_tool_iterations": 5
}
```

**SSE 回應事件流**：

```
event: conversation_created
data: {"conversation_id": "abc123"}

event: message_saved
data: {"message_id": "msg_001"}

event: thinking
data: {"content": "分析使用者意圖..."}

event: tool_call
data: {"tool_name": "knowledge_query", "arguments": {"query": "React Hooks", "method": "hybrid", "topK": 5}, "requires_confirmation": false}

event: tool_result
data: {"tool_name": "knowledge_query", "success": true, "result_preview": "找到 3 篇相關筆記..."}

event: token
data: {"content": "根"}

event: token
data: {"content": "據"}

event: token
data: {"content": "知識庫"}

event: usage
data: {"input_tokens": 1250, "output_tokens": 380, "model": "llama-3.3-70b-versatile"}

event: done
data: {"message_id": "msg_002", "tool_calls_count": 1}
```

**事件類型定義**：

| 事件 | 用途 | 前端處理 |
|------|------|---------|
| `conversation_created` | 新對話建立 | 更新 URL/側邊欄 |
| `message_saved` | 使用者訊息已存入 DB | 確認送達 |
| `thinking` | LLM 推理過程（可選） | 顯示思考動畫 |
| `tool_call` | LLM 決定呼叫工具 | 顯示工具呼叫卡片 |
| `tool_confirmation_required` | 敏感工具需確認 | 彈出確認對話框 |
| `tool_result` | 工具執行結果 | 更新工具卡片狀態 |
| `token` | LLM 輸出 Token | 逐字渲染 |
| `usage` | Token 使用統計 | 顯示用量 |
| `error` | 錯誤 | 顯示錯誤訊息 |
| `done` | 完成 | 關閉 SSE 連線 |

### 3.3 工具確認機制（Human-in-the-Loop）

當工具被標記為 `requires_confirmation: true` 時：

```
event: tool_confirmation_required
data: {
  "request_id": "req_001",
  "tool_name": "todoist_create_task",
  "arguments": {"content": "研究 React 19 新特性", "priority": 3},
  "description": "即將在 Todoist 建立新任務"
}
```

前端顯示確認對話框，使用者選擇後：

```
POST /api/chat/confirm
{
  "request_id": "req_001",
  "approved": true
}
```

---

## 四、Function Calling 與工具系統設計

### 4.1 工具定義格式（JSON Schema）

每個工具遵循統一的定義格式（相容 OpenAI Function Calling 規範）：

```python
class ToolDefinition:
    name: str              # snake_case，如 "knowledge_query"
    description: str       # 自然語言描述，供 LLM 判斷何時使用
    parameters: dict       # JSON Schema，定義輸入參數
    requires_confirmation: bool  # 是否需要人類確認
    category: str          # 分類（query/action/system）
    timeout_seconds: int   # 執行超時
```

### 4.2 內建工具清單（第一階段）

| 工具名稱 | 分類 | 描述 | 確認 |
|----------|------|------|------|
| `knowledge_query` | query | 查詢知識庫筆記（hybrid/semantic/keyword） | 否 |
| `knowledge_import` | action | 將內容匯入知識庫 | 是 |
| `todoist_list_tasks` | query | 列出 Todoist 待辦事項 | 否 |
| `todoist_create_task` | action | 建立新的 Todoist 任務 | 是 |
| `todoist_complete_task` | action | 完成 Todoist 任務 | 是 |
| `pingtung_news` | query | 查詢屏東縣政府新聞 | 否 |
| `web_search` | query | 網路搜尋（整合 Groq） | 否 |
| `get_current_time` | system | 取得目前時間與日期 | 否 |
| `calculate` | system | 數學計算 | 否 |

### 4.3 工具執行流程

```
使用者訊息
    │
    ▼
LLM 推理（含 tools 定義）
    │
    ├─ finish_reason: "stop" → 直接回覆
    │
    └─ finish_reason: "tool_calls" → 工具調用流程
         │
         ▼
    解析 tool_calls[]（可能多個並行）
         │
         ├─ requires_confirmation = false
         │   └─ 直接執行 → 取得結果
         │
         └─ requires_confirmation = true
             └─ SSE 推送確認請求 → 等待使用者回應
                 ├─ approved → 執行
                 └─ rejected → 告知 LLM「使用者拒絕」
         │
         ▼
    將所有工具結果回傳 LLM（tool role messages）
         │
         ▼
    LLM 再次推理
         │
         ├─ 更多工具調用 → 遞迴（上限 max_tool_iterations）
         └─ 最終回覆 → SSE token streaming → done
```

### 4.4 工具註冊機制（Plugin 式）

```python
# tools/registry.py
class ToolRegistry:
    """工具註冊表 — 支援動態註冊與發現"""

    def __init__(self):
        self._tools: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: Callable):
        """註冊工具"""
        self._tools[definition.name] = ToolHandler(definition, handler)

    def list_tools(self) -> list[dict]:
        """列出所有啟用工具（供 LLM tools 參數使用）"""
        return [t.to_openai_format() for t in self._tools.values() if t.enabled]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """執行工具並回傳結果"""
        handler = self._tools.get(name)
        if not handler:
            return ToolResult(success=False, error=f"工具 {name} 不存在")
        try:
            result = await asyncio.wait_for(
                handler.execute(arguments),
                timeout=handler.definition.timeout_seconds
            )
            return ToolResult(success=True, data=result)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"工具 {name} 執行超時")
```

### 4.5 工具實作範例：knowledge_query

```python
# tools/builtin/knowledge_query.py

DEFINITION = ToolDefinition(
    name="knowledge_query",
    description="查詢個人知識庫中的筆記。支援混合搜尋（語義+關鍵字）、語義搜尋、關鍵字搜尋。適用於回答使用者關於筆記內容、學習記錄、研究成果的問題。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜尋關鍵字或自然語言問句"
            },
            "method": {
                "type": "string",
                "enum": ["hybrid", "semantic", "keyword"],
                "description": "搜尋方法：hybrid（推薦）、semantic（概念性）、keyword（精確詞）",
                "default": "hybrid"
            },
            "topK": {
                "type": "integer",
                "description": "回傳結果數量",
                "default": 5,
                "minimum": 1,
                "maximum": 20
            }
        },
        "required": ["query"]
    },
    requires_confirmation=False,
    category="query",
    timeout_seconds=10
)

async def handler(arguments: dict) -> dict:
    """執行知識庫查詢"""
    method = arguments.get("method", "hybrid")
    url = f"http://localhost:3000/api/search/{method}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "query": arguments["query"],
            "topK": arguments.get("topK", 5)
        })
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return {
            "total": len(results),
            "notes": [
                {
                    "title": r["title"],
                    "content_preview": r.get("content", "")[:500],
                    "score": r.get("score", 0),
                    "tags": r.get("tags", [])
                }
                for r in results
            ]
        }
```

---

## 五、前端介面設計

### 5.1 頁面佈局

```
┌──────────────────────────────────────────────────┐
│  Sidebar (240px)    │    Main Area               │
│  ┌──────────────┐   │    ┌─────────────────────┐ │
│  │ + 新對話      │   │    │    對話標題          │ │
│  │              │   │    ├─────────────────────┤ │
│  │ 今天         │   │    │                     │ │
│  │  ├ 對話 1    │   │    │   訊息流            │ │
│  │  └ 對話 2    │   │    │   (Messages)        │ │
│  │              │   │    │                     │ │
│  │ 昨天         │   │    │  [User] 查詢...     │ │
│  │  └ 對話 3    │   │    │                     │ │
│  │              │   │    │  [Tool] 🔧 呼叫     │ │
│  │ 本週         │   │    │  knowledge_query    │ │
│  │  └ 對話 4    │   │    │  ✅ 找到 3 篇筆記   │ │
│  │              │   │    │                     │ │
│  │──────────────│   │    │  [Assistant] 根據... │ │
│  │ ⚙ 設定      │   │    │                     │ │
│  │ 🔧 工具管理  │   │    ├─────────────────────┤ │
│  └──────────────┘   │    │ [輸入框]     [送出] │ │
│                     │    └─────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### 5.2 訊息類型與渲染

| 訊息類型 | 視覺呈現 | 說明 |
|----------|---------|------|
| **使用者訊息** | 右側、深灰背景 | Markdown 渲染 |
| **助手回覆** | 左側、透明背景 | Markdown + 程式碼高亮 |
| **工具呼叫** | 左側、可摺疊卡片 | 顯示工具名稱、參數、結果 |
| **確認請求** | 左側、黃色邊框卡片 | 含「允許」「拒絕」按鈕 |
| **錯誤訊息** | 左側、紅色邊框 | 含重試按鈕 |
| **系統訊息** | 置中、灰色小字 | 如「新對話已建立」 |

### 5.3 工具呼叫卡片（Tool Call Card）

```
┌─────────────────────────────────┐
│ 🔧 knowledge_query              │ ← 工具名稱
│ ──────────────────────────────── │
│ 查詢: "React Hooks 最佳實踐"    │ ← 參數摘要
│ 方法: hybrid | 數量: 5          │
│ ──────────────────────────────── │
│ ✅ 找到 3 篇相關筆記             │ ← 結果摘要
│ ▸ 展開完整結果                   │ ← 可摺疊
└─────────────────────────────────┘
```

### 5.4 設計風格

延續現有 `index.html` 的 **Glassmorphism** 風格：

- **配色**：Deep navy (#06080d) + Indigo accent (#818cf8) + Emerald (#34d399)
- **字體**：Space Grotesk（標題）+ JetBrains Mono（程式碼）+ Noto Sans TC（中文）
- **效果**：backdrop-filter: blur、rgba 半透明背景、光暈效果
- **響應式**：768px 斷點，行動裝置隱藏 sidebar

---

## 六、LLM 整合策略

### 6.1 雙模型路由

根據現有 `config/llm-router.yaml` 的 mapping 格式：

| 場景 | 模型 | 理由 |
|------|------|------|
| 一般對話 | Groq llama-3.3-70b | 低延遲、免費額度充足 |
| 複雜推理/多步工具調用 | Claude claude-sonnet-4-6 | 推理能力強、Tool Use 原生支援 |
| 快速分類/意圖識別 | Groq llama-3.1-8b | 超低延遲、輕量 |

### 6.2 對話上下文管理

```python
class ConversationManager:
    """對話上下文管理 — 滑動窗口 + 摘要壓縮"""

    MAX_MESSAGES = 50          # 對話窗口上限
    SUMMARIZE_THRESHOLD = 30   # 觸發摘要壓縮的訊息數

    async def get_context(self, conversation_id: str) -> list[dict]:
        messages = await self.db.get_messages(conversation_id)
        if len(messages) > self.SUMMARIZE_THRESHOLD:
            # 將前 N-10 條摘要化，保留最近 10 條完整
            summary = await self.summarize(messages[:-10])
            return [{"role": "system", "content": summary}] + messages[-10:]
        return messages
```

### 6.3 System Prompt 設計

```markdown
你是一個智慧個人助手，具備以下工具可供使用：
- knowledge_query：查詢個人知識庫
- todoist_list_tasks：列出待辦事項
- todoist_create_task：建立新任務
- pingtung_news：查詢屏東新聞
- web_search：網路搜尋
- calculate：數學計算
- get_current_time：取得目前時間

使用規則：
1. 先判斷是否需要使用工具，若不需要則直接回答
2. 使用者提到「筆記」「知識庫」「我之前寫的」→ 優先 knowledge_query
3. 使用者提到「任務」「待辦」「要做」→ 優先 todoist 相關工具
4. 使用者提到「屏東」「新聞」「縣政」→ 優先 pingtung_news
5. 工具回傳結果後，整合為自然語言回覆，不要直接貼 JSON
6. 全程使用正體中文回答
```

---

## 七、資料模型

### 7.1 SQLite Schema

```sql
-- 對話
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,            -- UUID
    title TEXT,                     -- 對話標題（自動生成）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    model TEXT DEFAULT 'groq-llama-3.3-70b',
    metadata TEXT                   -- JSON，可選配置
);

-- 訊息
CREATE TABLE messages (
    id TEXT PRIMARY KEY,            -- UUID
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,             -- user/assistant/tool/system
    content TEXT,                   -- 文字內容
    tool_calls TEXT,               -- JSON，LLM 的工具調用請求
    tool_call_id TEXT,             -- 工具結果對應的 call ID
    tool_name TEXT,                -- 工具名稱（role=tool 時）
    tokens_input INTEGER,
    tokens_output INTEGER,
    model TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- 工具執行日誌
CREATE TABLE tool_executions (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    tool_name TEXT NOT NULL,
    arguments TEXT,                 -- JSON
    result TEXT,                   -- JSON
    success BOOLEAN,
    duration_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- 索引
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_tool_executions_tool ON tool_executions(tool_name, created_at);
```

### 7.2 對話標題自動生成

首次收到使用者訊息後，用 LLM 生成 ≤20 字的對話標題：

```python
async def generate_title(first_message: str) -> str:
    """用 Groq 快速生成對話標題"""
    resp = await groq.chat(
        model="llama-3.1-8b-instant",
        messages=[{
            "role": "user",
            "content": f"用正體中文為以下對話生成一個簡短標題（20字以內）：\n{first_message}"
        }],
        max_tokens=30
    )
    return resp.choices[0].message.content.strip()
```

---

## 八、安全設計

### 8.1 威脅模型

| 威脅 | 風險等級 | 緩解措施 |
|------|---------|---------|
| **Prompt Injection** | 高 | 工具輸入驗證、結果截斷、System Prompt 強化 |
| **工具濫用** | 高 | requires_confirmation + 頻率限制 + 最大迭代上限 |
| **XSS** | 中 | DOMPurify 消毒所有 Markdown 渲染輸出 |
| **API 金鑰洩露** | 中 | 環境變數儲存、不回傳前端、.env 排除 git |
| **過量 Token 消耗** | 中 | 對話長度上限 + Token 預算 + budget_guard 整合 |
| **SSRF（工具發起內網請求）** | 中 | 工具 URL 白名單、禁止任意 HTTP 請求 |

### 8.2 具體防護措施

```python
# 1. 工具輸入驗證（JSON Schema 強制）
def validate_tool_input(tool_name: str, arguments: dict) -> bool:
    schema = registry.get_schema(tool_name)
    # 使用 Pydantic 或 jsonschema 驗證
    validate(arguments, schema)

# 2. 結果大小限制
MAX_TOOL_RESULT_CHARS = 4000
def truncate_result(result: str) -> str:
    if len(result) > MAX_TOOL_RESULT_CHARS:
        return result[:MAX_TOOL_RESULT_CHARS] + "\n...(結果已截斷)"
    return result

# 3. 工具調用頻率限制
RATE_LIMITS = {
    "knowledge_query": {"max_per_minute": 30},
    "todoist_create_task": {"max_per_minute": 5},
    "web_search": {"max_per_minute": 10},
}

# 4. 最大工具迭代上限
MAX_TOOL_ITERATIONS = 5  # 預設，API 可覆寫（上限 10）
```

### 8.3 認證

第一階段採用簡單方案（單一使用者）：

- **API 層**：Bearer Token（環境變數 `CHAT_API_SECRET`）
- **前端**：Token 存於 `sessionStorage`（頁籤關閉自動清除）
- **CORS**：僅允許 `localhost` 來源

---

## 九、目錄結構

```
D:\Source\chat-system/              # 新專案目錄
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI 入口
│   │   ├── config.py              # 配置管理
│   │   ├── models/
│   │   │   ├── conversation.py    # 對話 Pydantic Model
│   │   │   └── tool.py            # 工具 Pydantic Model
│   │   ├── routers/
│   │   │   ├── chat.py            # /api/chat（SSE Streaming）
│   │   │   ├── conversations.py   # /api/conversations CRUD
│   │   │   ├── tools.py           # /api/tools 管理
│   │   │   └── health.py          # /api/health
│   │   ├── services/
│   │   │   ├── chat_engine.py     # 對話引擎（LLM 調用 + 工具編排）
│   │   │   ├── llm_client.py      # LLM 呼叫抽象層（Groq/Claude）
│   │   │   └── conversation_manager.py  # 對話上下文管理
│   │   ├── tools/
│   │   │   ├── registry.py        # 工具註冊表
│   │   │   ├── base.py            # 工具基礎類別
│   │   │   └── builtin/
│   │   │       ├── knowledge_query.py
│   │   │       ├── todoist.py
│   │   │       ├── pingtung_news.py
│   │   │       ├── web_search.py
│   │   │       └── utilities.py   # 時間、計算等
│   │   └── db/
│   │       ├── database.py        # SQLite 連線管理
│   │       └── migrations.py      # Schema 初始化
│   ├── pyproject.toml
│   └── tests/
│       ├── test_chat_engine.py
│       ├── test_tool_registry.py
│       └── test_tools/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx      # 對話面板
│   │   │   ├── MessageBubble.tsx  # 訊息氣泡
│   │   │   ├── ToolCallCard.tsx   # 工具呼叫卡片
│   │   │   ├── Sidebar.tsx        # 側邊欄
│   │   │   ├── InputBar.tsx       # 輸入列
│   │   │   └── ConfirmDialog.tsx  # 工具確認對話框
│   │   ├── hooks/
│   │   │   ├── useChat.ts         # SSE 連線管理
│   │   │   └── useConversations.ts
│   │   ├── services/
│   │   │   └── api.ts             # API Client
│   │   └── types/
│   │       └── index.ts           # TypeScript 型別定義
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
└── README.md
```

---

## 十、實作階段規劃

### Phase 1：最小可行產品（MVP）— 預估 2-3 天

- FastAPI 後端骨架 + SQLite 資料庫
- `POST /api/chat` SSE Streaming（Groq）
- 2 個內建工具：`knowledge_query` + `get_current_time`
- 極簡 React 前端（單一對話、訊息流、工具呼叫卡片）
- 無認證（localhost 限定）

### Phase 2：核心功能完善 — 預估 2-3 天

- 對話歷史 CRUD（多對話切換）
- 完整工具集（5+ 工具）
- Human-in-the-Loop 確認機制
- 雙模型路由（Groq + Claude）
- Bearer Token 認證

### Phase 3：體驗優化 — 預估 1-2 天

- 對話標題自動生成
- 對話搜尋
- 工具管理面板（啟用/停用）
- Token 用量統計
- 響應式行動裝置支援

### Phase 4：進階整合（可選）— 預估 2-3 天

- 與現有 Gun.js 聊天室橋接
- MCP 協議支援（將工具封裝為 MCP Server）
- 自訂工具上傳（用戶自定義 JSON Schema + Python handler）
- 語音輸入（Groq Whisper）

---

## 十一、與現有系統整合點

| 整合 | 方式 | 說明 |
|------|------|------|
| **知識庫 (:3000)** | HTTP Client | knowledge_query 工具直接呼叫 KB API |
| **Bot.js (:3001)** | HTTP Client | 可選：將聊天室任務橋接為工具 |
| **Groq Relay (:3002)** | HTTP Client | LLM 推理路由 |
| **Todoist API** | HTTP Client | todoist_* 工具組 |
| **屏東新聞 MCP** | HTTP Client | pingtung_news 工具 |
| **ntfy** | HTTP Client | 完成通知推播 |
| **daily-digest-prompt** | 共用配置 | 可讀取 config/*.yaml |

---

## 十二、風險與緩解

| 風險 | 影響 | 緩解 |
|------|------|------|
| Groq API 頻率限制 | 高頻使用時被限流 | Claude 備援 + 本地快取 |
| 工具執行失敗 | 對話中斷 | 優雅降級：告知 LLM 工具失敗，改以知識回答 |
| Token 超支 | 月度成本超標 | budget_guard.py 整合 + 每日上限 |
| Gun.js 與新系統衝突 | 埠號/資源競爭 | 獨立埠號 + 獨立程序 |
| SQLite 並行寫入 | 資料損壞 | WAL mode + 單一寫入者 |

---

## 十三、品質保證

| 面向 | 標準 |
|------|------|
| **單元測試** | 覆蓋率 ≥ 80%（後端） |
| **API 測試** | 所有端點 happy path + error path |
| **工具測試** | 每個工具 mock + integration test |
| **前端測試** | 關鍵元件 Vitest + React Testing Library |
| **安全測試** | Prompt Injection 測試案例、XSS 測試 |
| **效能基線** | 首 Token 延遲 < 500ms（Groq）、工具執行 < 5s |

---

## 十四、附錄

### A. 相關知識庫筆記

1. **Chat 對話系統設計：Function Calling 與工具調用架構全解析** (noteId: 5b7875b4)
2. **2025-2026 年 Chat 對話系統主流架構模式完整研究** (noteId: 26b9306c)

### B. 參考架構

- OpenAI Function Calling API
- Anthropic Claude Tool Use
- MCP (Model Context Protocol)
- FastAPI StreamingResponse
- Gun.js SEA Encryption

### C. 決策記錄

| 決策 | 選項 | 選擇 | 理由 |
|------|------|------|------|
| 後端框架 | FastAPI vs Express | FastAPI | 專案慣例 Python + 原生 SSE + 自動文件 |
| LLM Streaming | SSE vs WebSocket | SSE | 單向即可、更簡單可靠、CDN 友好 |
| 資料庫 | SQLite vs PostgreSQL | SQLite | 單用戶、零配置、輕量 |
| 工具格式 | OpenAI 格式 vs MCP | OpenAI 格式 | 更多 LLM 支援、簡單直接 |
| 前端 | React vs Vue vs 純 HTML | React + Vite | 元件化、TypeScript、生態豐富 |
| 認證 | JWT vs Bearer Token | Bearer Token | 單用戶場景夠用、MVP 簡單 |

---

## 十五、補充設計（自審第 1 輪新增）

### 15.1 錯誤碼定義

| HTTP 狀態碼 | 錯誤碼 | 說明 |
|-------------|--------|------|
| 400 | `INVALID_MESSAGE` | 訊息內容為空或格式錯誤 |
| 400 | `INVALID_TOOL_ARGS` | 工具參數不符合 JSON Schema |
| 401 | `UNAUTHORIZED` | Bearer Token 缺失或無效 |
| 404 | `CONVERSATION_NOT_FOUND` | 對話 ID 不存在 |
| 404 | `TOOL_NOT_FOUND` | 工具名稱不存在 |
| 408 | `TOOL_TIMEOUT` | 工具執行超時 |
| 429 | `RATE_LIMITED` | 工具呼叫頻率超限 |
| 429 | `TOKEN_BUDGET_EXCEEDED` | Token 預算超限 |
| 500 | `LLM_ERROR` | LLM API 呼叫失敗 |
| 502 | `TOOL_EXECUTION_ERROR` | 工具執行內部錯誤 |
| 503 | `SERVICE_UNAVAILABLE` | 依賴服務不可用（KB/Todoist） |

### 15.2 可觀測性設計

**結構化日誌**（與現有 `hooks/post_tool_logger.py` 格式一致）：

```jsonl
{"ts":"2026-03-17T08:00:00","level":"info","component":"chat_engine","event":"chat_request","conversation_id":"abc","model":"groq","message_length":45}
{"ts":"2026-03-17T08:00:01","level":"info","component":"tool_executor","event":"tool_call","tool":"knowledge_query","duration_ms":230,"success":true}
{"ts":"2026-03-17T08:00:02","level":"info","component":"chat_engine","event":"chat_response","tokens_in":1250,"tokens_out":380,"tool_calls":1,"total_ms":1850}
```

**健康檢查端點** `GET /api/health`：

```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "dependencies": {
    "knowledge_base": {"status": "ok", "latency_ms": 15},
    "groq_api": {"status": "ok", "latency_ms": 120},
    "sqlite": {"status": "ok"}
  },
  "stats": {
    "total_conversations": 42,
    "total_messages": 580,
    "total_tool_calls": 156,
    "tokens_used_today": 45000
  }
}
```

**日誌檔案**：`logs/chat-system/yyyyMMdd.jsonl`（7 天保留）。

### 15.3 快取策略

| 資源 | 快取位置 | TTL | 說明 |
|------|---------|-----|------|
| 工具定義清單 | 記憶體 | 啟動時載入 | 工具不頻繁變動 |
| 知識庫搜尋結果 | 記憶體 (LRU) | 5 分鐘 | 相同查詢短期內不重查 |
| LLM 回應 | 不快取 | - | 每次回應應反映最新上下文 |
| 對話歷史 | SQLite + 記憶體 | Session | 活躍對話保持在記憶體 |
| 工具執行結果 | 不快取 | - | 工具結果具時效性 |

```python
from functools import lru_cache
from cachetools import TTLCache

# 知識庫搜尋結果快取
_search_cache = TTLCache(maxsize=100, ttl=300)  # 5 min

async def cached_kb_search(query: str, method: str, topK: int):
    key = f"{method}:{query}:{topK}"
    if key in _search_cache:
        return _search_cache[key]
    result = await _raw_kb_search(query, method, topK)
    _search_cache[key] = result
    return result
```

### 15.4 鍵盤快捷鍵

| 快捷鍵 | 功能 |
|--------|------|
| `Enter` | 送出訊息 |
| `Shift+Enter` | 換行 |
| `Ctrl+N` | 新對話 |
| `Ctrl+K` | 搜尋對話 |
| `Escape` | 關閉確認對話框 / 取消搜尋 |
| `Ctrl+/` | 顯示快捷鍵清單 |

### 15.5 Token 成本估算

| 模型 | 定價（每 1M token） | 估計日用量 | 日成本 |
|------|---------------------|-----------|--------|
| Groq llama-3.3-70b | 免費（限額 14.4K req/day） | ~100 對話 × 2K token = 200K | $0 |
| Groq llama-3.1-8b | 免費 | ~100 標題生成 × 100 token = 10K | $0 |
| Claude Sonnet 4.6 | $3/$15 (in/out) | ~10 複雜對話 × 5K token = 50K | ~$0.5 |
| **合計** | | | **~$0.5/天** |

> 日常使用以 Groq 免費額度為主，僅複雜推理 fallback 至 Claude，月成本約 $15。

### 15.6 Gun.js 橋接設計（Phase 4 詳述）

```
Gun.js 聊天室         Chat System
 (index.html)          (React SPA)
     │                     │
     │  訊息               │  訊息
     ▼                     ▼
 Gun.js Relay ──bridge──► FastAPI
  (E2E 加密)     REST     (明文+LLM)
     │                     │
     └──── 共用 ──────────┘
        Bot API (:3001)
```

**橋接方式**：FastAPI 定時輪詢 Bot API 取得新的 pending 任務，處理後回寫結果。不修改現有 Gun.js 加密通道。

### 15.7 CSRF 防護

由於 API 是無狀態 REST（Bearer Token 認證），且不使用 Cookie-based session，CSRF 攻擊面較小。額外措施：

- 所有狀態修改操作（POST/PUT/DELETE）必須帶 `Authorization` header
- CORS 嚴格限制 `allow_origins`
- 敏感工具操作額外要求 `X-Confirm-Token`（前端在確認對話框中生成的一次性 token）
