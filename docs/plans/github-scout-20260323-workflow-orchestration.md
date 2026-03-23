# GitHub Scout 落實計畫：Workflow Orchestration 強化

> **建立日期**：2026-03-23
> **來源**：GitHub Scout 靈感蒐集（n8n, Dify, LangGraph）
> **狀態**：待人工審核
> **優先級**：P0/P1（4 個方案）

---

## 背景

基於對 3 個高 stars Workflow 引擎專案的分析（n8n 181K、Dify 134K、LangGraph 27.2K），產出 6 個改進建議。其中 1 個低風險方案已落實（自動失敗恢復），本計畫涵蓋剩餘 4 個方案。

---

## 方案 2：API-first 架構與統一 API 層（P0 - Medium 風險）

### 來源專案
- **Dify** (https://github.com/langgenius/dify)
- **借鑑模式**：API-first 架構、統一 API 閘道

### 目標

建立統一 API 閘道層（`api/unified_gateway.py`），整合現有散落的外部 API 呼叫（Todoist、Gmail、Pingtung News），提供一致介面、統一快取、預算管理、錯誤處理。

### 詳細步驟

#### 階段 1：基礎 Gateway（1-2 天）

1. **建立專案結構**
   ```
   api/
   ├── __init__.py
   ├── unified_gateway.py  # FastAPI app
   ├── routes/
   │   ├── todoist.py      # Todoist 端點
   │   ├── gmail.py        # Gmail 端點
   │   └── news.py         # News 端點
   └── middleware/
       ├── cache.py        # 快取中介軟體
       └── budget.py       # 預算中介軟體
   ```

2. **實作 FastAPI Gateway**
   - 使用 FastAPI（已在 pyproject.toml 中，輕量且快速）
   - 端點定義：
     - `GET /api/todoist/tasks?filter=today`
     - `POST /api/todoist/tasks`
     - `PATCH /api/todoist/tasks/{id}`
     - `GET /api/gmail/messages`
     - `POST /api/gmail/send`
     - `GET /api/news/latest?count=10`
     - `GET /api/news/search?keyword={keyword}`

3. **統一錯誤處理**
   - 422 Unprocessable Entity（參數錯誤）
   - 500 Internal Server Error（後端錯誤）
   - 503 Service Unavailable（外部 API 失敗）
   - 自動重試（exponential backoff，最多 3 次）

4. **請求日誌**
   - 寫入 `logs/api-gateway.jsonl`
   - 格式：`{timestamp, endpoint, method, status_code, latency_ms, cache_hit}`

#### 階段 2：整合現有機制（2-3 天）

1. **整合 api-cache Skill**
   - 每個 GET 端點自動套用快取
   - 使用 `cache/status.json` 判斷 valid
   - 快取命中時直接回傳，無需呼叫外部 API

2. **整合 llm-router**（簡化版）
   - 需要 LLM 的端點（如摘要、分類）路由到 Groq/Claude
   - 使用 `tools/llm_router.py` 的 routing 邏輯

3. **整合 budget_guard**
   - Middleware 在每次 LLM 呼叫前檢查預算
   - 超額時回傳 429 Too Many Requests

#### 階段 3：bot/routes.js 整合（1 天）

1. **修改 bot/routes.js**
   - 原：直接 curl Todoist API
   - 改：curl http://localhost:8000/api/todoist/tasks

2. **向後相容**
   - 若 gateway 未啟動（port 8000 無回應），退回直接呼叫原 API
   - 環境變數 `USE_API_GATEWAY=true/false` 控制

#### 階段 4：部署與監控（1 天）

1. **啟動腳本**
   ```powershell
   # start-api-gateway.ps1
   uv run uvicorn api.unified_gateway:app --port 8000 --log-level info
   ```

2. **健康檢查整合**
   - `check-health.ps1` 新增 `[API Gateway 健康度]` 區塊
   - 檢查 http://localhost:8000/health

3. **監控指標**
   - 每日請求數
   - 快取命中率
   - 平均 latency
   - 錯誤率（>5% 告警）

### 風險評估

- **技術風險**：Medium
  - FastAPI 穩定，但需新增依賴（uvicorn）
  - bot/routes.js 修改需謹慎測試

- **相依性風險**：Medium
  - 依賴 api-cache、llm-router、budget_guard
  - 建議階段 1 先不整合，獨立驗證 gateway 可用性

### Rollback 方案

1. 停止 uvicorn 服務
2. bot/routes.js 設定 `USE_API_GATEWAY=false`
3. 系統退回直接呼叫原 API（無需刪除程式碼）

### 驗證清單

- [ ] uvicorn 啟動成功（http://localhost:8000/health 回傳 ok）
- [ ] curl http://localhost:8000/api/todoist/tasks?filter=today 正常回傳
- [ ] 第二次請求快取命中（latency 明顯降低）
- [ ] logs/api-gateway.jsonl 有請求記錄
- [ ] 模擬 Todoist API 失敗，gateway 自動重試 3 次
- [ ] bot/routes.js 改用 gateway，Todoist 任務查詢仍正常

---

## 方案 3：Monorepo + Workspace 架構（P1 - High 風險）

### 來源專案
- **n8n** (https://github.com/n8n-io/n8n)
- **借鑑模式**：pnpm workspace、monorepo 架構

### 目標

將平面專案結構（27 skills、13 tools、8 hooks 混雜根目錄）重組為 monorepo，強制模組邊界、清晰依賴。

### 為何標記為 High 風險

1. **影響範圍極廣**
   - 需移動數百個檔案
   - 所有 import 路徑需更新（Python、Node.js）
   - 所有 .ps1 腳本路徑需更新
   - .claude/settings.json 的 hook 路徑需更新

2. **Rollback 成本高**
   - 無法簡單的「刪除檔案」rollback
   - 需完整 git revert

3. **工具鏈成熟度未知**
   - uv workspace 功能在 2026-03 可能尚未成熟
   - pnpm workspace（Node.js）需與 uv（Python）混用

### 建議執行方式

**階段 0：調研與驗證**（建議先執行，1-2 天）
1. 建立測試分支 `monorepo-poc`
2. 小規模測試：只移動 1 個 skill + 1 個 tool
3. 驗證 uv workspace 是否支援
4. 驗證 import 路徑更新策略
5. 驗證 .ps1 腳本路徑更新策略

**若階段 0 通過，再進入完整遷移**（3-5 天）

### 詳細步驟（完整遷移）

1. **建立 workspace 結構**
   ```
   packages/
   ├── core/          # tools/, config/, state/
   ├── skills/        # skills/*/
   ├── hooks/         # hooks/, .claude/settings.json
   └── bot/           # bot/, index.js, groq-relay.js
   ```

2. **移動檔案**
   ```powershell
   mv tools/ packages/core/
   mv skills/ packages/skills/
   mv hooks/ packages/hooks/
   mv bot/ packages/bot/
   ```

3. **更新 pyproject.toml**（workspace root）
   ```toml
   [tool.uv.workspace]
   members = ["packages/core", "packages/skills", "packages/hooks"]
   ```

4. **更新所有 import**（Python）
   - 使用 sed/awk 批次替換
   - `from tools.llm_router` → `from core.tools.llm_router`
   - `from skills.todoist.SKILL` → `from skills.todoist.SKILL`

5. **更新所有路徑**（PowerShell）
   - 所有 .ps1 腳本的路徑引用
   - `.claude/settings.json` 的 hook 路徑

6. **驗證**
   - uv sync（確認依賴解析）
   - uv run pytest（856 個測試通過）
   - 執行 run-agent-team.ps1（主流程正常）

### 驗證清單

- [ ] uv sync 成功
- [ ] pytest 通過（856 個測試）
- [ ] run-agent-team.ps1 執行成功
- [ ] run-todoist-agent-team.ps1 執行成功
- [ ] check-health.ps1 通過
- [ ] Hooks 正常觸發（.claude/settings.json 路徑正確）

### 建議

**暫緩執行**，先完成其他低/中風險方案，累積經驗後再評估是否需要 monorepo。

**替代方案**：
- 使用 `CODEOWNERS` 檔案定義模組邊界
- 使用 `pre-commit` hook 驗證 import 規則
- 保持平面結構，但強化文件與命名規範

---

## 方案 4：Graph-based Workflow Orchestration（P1 - Medium 風險）

### 來源專案
- **LangGraph** (https://github.com/langchain-ai/langgraph)
- **借鑑模式**：Graph-based orchestration、stateful workflow

### 目標

引入圖式編排機制，取代目前線性 Phase 0→1→2 管線，支援條件分支、並行任務、動態路由。

### 詳細步驟

#### 階段 1：Workflow Graph 定義（1-2 天）

1. **建立 workflow-graph.yaml**
   ```yaml
   version: 1
   workflow_id: "daily-digest"
   nodes:
     - id: "fetch_todoist"
       type: "skill"
       executor: "todoist"
       output: "todoist.json"

     - id: "fetch_news"
       type: "skill"
       executor: "pingtung-news"
       output: "news.json"

     - id: "analyze"
       type: "agent"
       executor: "claude"
       input: ["todoist.json", "news.json"]
       output: "analysis.json"

     - id: "assemble"
       type: "agent"
       executor: "claude"
       input: ["analysis.json"]
       output: "digest.json"

   edges:
     - from: "fetch_todoist"
       to: "analyze"
       condition: "todoist.count > 0"

     - from: "fetch_news"
       to: "analyze"
       # 無條件，總是執行

     - from: "analyze"
       to: "assemble"

   # 並行執行組
   parallel_groups:
     - ["fetch_todoist", "fetch_news"]
   ```

2. **實作 workflow_executor.py**
   - `WorkflowGraph.load_from_yaml()`：解析 YAML
   - `WorkflowGraph.validate()`：檢查圖合法性（無環、節點存在）
   - `WorkflowGraph.execute()`：執行圖
     - 使用 topological sort 排序節點
     - 支援條件分支（eval condition）
     - 支援並行執行（ThreadPoolExecutor）

#### 階段 2：整合現有流程（1-2 天）

1. **修改 run-agent-team.ps1**
   ```powershell
   # 檢查是否有 workflow-graph.yaml
   if (Test-Path "config/workflow-graph.yaml") {
       # 使用 graph 模式
       uv run python tools/workflow_executor.py --graph config/workflow-graph.yaml
   } else {
       # 退回線性模式（向後相容）
       # ... 原有 Phase 0→1→2 邏輯
   }
   ```

2. **錯誤處理**
   - 節點執行失敗 → 記錄錯誤，繼續執行不依賴此節點的其他節點
   - 整個 graph 失敗 → 寫入錯誤日誌，退出

#### 階段 3：進階功能（可選，2-3 天）

1. **Human-in-the-loop**
   - 節點類型 `type: "approval"`
   - 執行到此節點時暫停，等待批准（寫入 state/approval-pending.json）
   - 批准後繼續執行

2. **Subgraphs**
   - 節點類型 `type: "subgraph"`
   - 執行另一個 workflow-graph YAML

3. **Dynamic routing**
   - 根據前一節點的輸出動態選擇下一節點
   - 條件可使用 Python expr（安全的 eval）

### 風險評估

- **技術風險**：Medium
  - Graph 解析與執行邏輯複雜
  - 並行執行需謹慎處理狀態

- **相依性風險**：Low
  - 獨立於現有 Skills，只是編排層

### Rollback 方案

1. 刪除或重命名 `config/workflow-graph.yaml`
2. run-agent-team.ps1 自動退回線性 Phase 執行
3. workflow_executor.py 保留但不呼叫

### 驗證清單

- [ ] workflow_executor.py --graph config/workflow-graph.yaml --dry-run 成功
- [ ] 實際執行 graph，節點依序執行
- [ ] 測試條件分支（todoist.count == 0 → 跳過 analyze）
- [ ] 測試並行執行（fetch_todoist + fetch_news 同時執行）
- [ ] 測試錯誤處理（某節點失敗，其他節點繼續）

---

## 方案 5：聲明式 Workflow 定義（P1 - Low 風險）

### 來源專案
- **Dify** (https://github.com/langgenius/dify)
- **借鑑模式**：Declarative workflow model

### 目標

將複雜任務編排從 prompt 中抽離到 YAML 配置，簡化 prompt 維護，提升 workflow 可讀性與版本控制。

### 詳細步驟

#### 階段 1：Workflow YAML 定義（1 天）

1. **建立 templates/workflows/ 目錄**

2. **定義 research-workflow.yaml**
   ```yaml
   workflow_id: "research"
   version: 1
   steps:
     - name: "load_registry"
       action: "read_file"
       params:
         file: "context/research-registry.json"
       output: "registry"

     - name: "filter_topics"
       action: "python_expr"
       params:
         expr: "[t for t in topics if t not in registry['topics_index']]"
         variables:
           topics: ["AI Agent", "Workflow", "LLM"]
       output: "available_topics"

     - name: "select_topic"
       action: "python_expr"
       params:
         expr: "available_topics[0] if available_topics else 'fallback'"
         variables:
           available_topics: "$available_topics"
       output: "selected_topic"

     - name: "web_search"
       action: "web_search"
       params:
         query: "$selected_topic GitHub 2026"
       output: "search_results"
       error_handling:
         on_error: "retry"
         max_retries: 3

     - name: "write_results"
       action: "write_file"
       params:
         file: "tmp/research-results.json"
         content: "$search_results"
   ```

3. **擴展 workflow_executor.py**
   - 新增 action types：
     - `read_file`、`write_file`
     - `bash`（執行 shell 命令）
     - `web_search`（呼叫 WebSearch tool）
     - `python_expr`（安全的 Python 表達式）
     - `llm_call`（呼叫 LLM）
   - 變數替換：`$variable_name` 替換為前面步驟的輸出
   - 錯誤處理：`on_error: retry/skip/fail`

#### 階段 2：Prompt 簡化（1-2 天）

1. **修改 todoist-auto-*.md**
   - 原：包含大量 if/else、迴圈邏輯
   - 改：
     ```markdown
     ## 執行流程
     讀取 `templates/workflows/{task_key}-workflow.yaml`，用 Bash 執行：
     ```bash
     uv run python tools/workflow_executor.py --workflow templates/workflows/{task_key}-workflow.yaml
     ```

     取得輸出後組裝最終結果 JSON。
     ```

2. **保留原 prompt**（向後相容）
   - 新 workflow YAML 僅作為選用功能
   - 若 workflow 檔案不存在，執行原邏輯

#### 階段 3：進階功能（可選，1-2 天）

1. **條件判斷**
   ```yaml
   - name: "check_count"
     action: "python_expr"
     expr: "len(tasks) > 0"
     output: "has_tasks"

   - name: "process_tasks"
     action: "llm_call"
     condition: "$has_tasks == true"  # 只在有任務時執行
     params:
       prompt: "分析任務..."
   ```

2. **迴圈**
   ```yaml
   - name: "process_each_task"
     action: "loop"
     params:
       items: "$tasks"
       steps:
         - name: "analyze_task"
           action: "llm_call"
           params:
             prompt: "分析任務 $item ..."
   ```

### 風險評估

- **技術風險**：Low
  - YAML 解析簡單
  - 向後相容（不影響現有 prompt）

- **相依性風險**：Low
  - 可與方案 4（Graph Orchestration）整合，但也可獨立運作

### Rollback 方案

1. 保留原 todoist-auto-*.md，不修改
2. 刪除 templates/workflows/ 即可退回

### 驗證清單

- [ ] workflow_executor.py --workflow templates/workflows/research-workflow.yaml 成功
- [ ] 每個步驟依序執行、輸出正確
- [ ] 測試條件判斷（if has_tasks then process）
- [ ] 測試迴圈（for task in tasks: analyze(task)）
- [ ] 測試錯誤處理（web_search 失敗 → retry 3 次）

---

## 總結

| 方案 | 風險 | 建議執行順序 | 預估工時 |
|------|------|-------------|---------|
| 1. 自動失敗恢復 | Low | ✅ 已完成 | - |
| 2. API-first 架構 | Medium | 第 2 順位 | 5-7 天 |
| 3. Monorepo | **High** | **暫緩**（先 POC） | 3-5 天（完整遷移） |
| 4. Graph Orchestration | Medium | 第 3 順位 | 3-5 天 |
| 5. 聲明式 Workflow | Low | 第 1 順位 | 2-4 天 |

### 推薦執行路徑

1. **方案 5（聲明式 Workflow）** - 風險低、獨立性高、立即可用
2. **方案 2（API Gateway）** - 統一介面層，後續整合更容易
3. **方案 4（Graph Orchestration）** - 可與方案 5 整合，提供更強大編排能力
4. **方案 3（Monorepo）** - 暫緩，先執行階段 0 POC，驗證可行性後再決定

---

**建立者**: todoist-auto-github_scout
**最後更新**: 2026-03-23T12:00:00+08:00
