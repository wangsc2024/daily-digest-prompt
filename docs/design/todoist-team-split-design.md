# run-todoist-agent-team.ps1 執行步驟與分拆設計

> 本文檔說明現有腳本的詳細執行流程、分拆策略，以及執行器（claude/codex/groq/openrouter）的決策邏輯。

---

## 一、現有執行步驟（run-todoist-agent-team.ps1）

### 整體架構

```
Phase 0 (預檢查) → Phase 1 (查詢+規劃) → Phase 2 (並行執行) → Phase 3 (組裝+通知)
```

---

### Phase 0：前置準備與 Circuit Breaker（約 1–5 秒）

| 步驟 | 說明 | 產出 |
|------|------|------|
| 0.1 | 設定 UTF-8 編碼、路徑變數、日誌檔名 | `$LogFile`, `$Timestamp` |
| 0.2 | 載入 `.env`（TODOIST_API_TOKEN, BOT_API_SECRET） | 環境變數 |
| 0.3 | 設定 HOOK_SECURITY_PRESET（預設 strict） | 安全策略 |
| 0.4 | 產生 Trace ID | `$traceId` |
| 0.5 | 檢查 `claude` 是否已安裝 | 未安裝則 exit 1 |
| 0.6 | 載入 `circuit-breaker-utils.ps1` | - |
| 0.7 | 呼叫 `Test-CircuitBreaker "todoist"` | CLOSED / HALF_OPEN / OPEN |
| 0.8 | 若 OPEN → 跳過執行、更新狀態、exit 0 | - |

**可抽離**：0.1–0.5 為通用初始化；0.6–0.8 為 Todoist 專用預檢查。

---

### Phase 1：查詢 + 過濾 + 路由 + 規劃（約 180–420 秒）

| 步驟 | 說明 | 工具 | 產出 |
|------|------|------|------|
| 1.1 | 讀取 `prompts/team/todoist-query.md` | Read | `$queryContent` |
| 1.2 | 啟動 **todoist-query** Job（`claude -p`） | claude | - |
| 1.3 | （可選）並行啟動 **chatroom-query** Job | claude | `chatroom-plan.json` |
| 1.4 | 等待 query Job（timeout 420s，最多重試 1 次） | - | - |
| 1.5 | 若超時：檢查 `todoist-plan.json` 是否已寫入（fallback） | - | - |
| 1.6 | 更新 Circuit Breaker（成功/失敗） | - | - |
| 1.7 | 解析 `results/todoist-plan.json` | Read | `$plan` |
| 1.8 | 依 `plan_type` 計算 Phase 2 動態 timeout | - | `$Phase2TimeoutSeconds` |

**Phase 1 內部（todoist-query Agent）**：

- 查 Todoist API / 快取
- 過濾（時間、已關閉 ID、安全檢查）
- 查 bot.js chatroom pending
- 路由（三層規則）
- 檢查自動任務頻率
- 寫入 `results/todoist-plan.json`、`results/task_prompt_*.md`

**可抽離**：Phase 1 的「誰來執行」可替換為不同執行器（claude / codex / groq / openrouter）。

---

### Phase 2：並行執行（依 plan_type 而定）

#### 2A：plan_type = "tasks"（Todoist 任務）

| 步驟 | 說明 | 工具 | 產出 |
|------|------|------|------|
| 2A.1 | 遍歷 `plan.tasks` | - | - |
| 2A.2 | 讀取 `task.prompt_file`（如 `results/task_prompt_1.md`） | Read | `$taskPrompt` |
| 2A.3 | 依 `task.allowed_tools` 啟動 N 個 Job | claude | N 個 Job |
| 2A.4 | 每個 Job：`$prompt \| claude -p --allowedTools $tools` | claude | 各任務結果 |

#### 2B：plan_type = "auto"（自動任務）

| 步驟 | 說明 | 工具 | 產出 |
|------|------|------|------|
| 2B.1 | 掃描 `prompts/team/todoist-auto-*.md` | Glob | `$dedicatedPrompts` |
| 2B.2 | 遍歷 `plan.auto_tasks.selected_tasks` | - | - |
| 2B.3 | Key 正規化（連字號→底線、別名對照） | - | `$normalizedKey` |
| 2B.4 | 讀取對應 prompt，若有 `prompt_content` 則前置注入 | Read | `$promptContent` |
| 2B.5 | 啟動 N 個 Job（`claude -p`，全工具） | claude | N 個 Job |

#### 2C：plan_type = "idle"

- 不啟動 Phase 2 Job，直接進入 Phase 3。

#### Phase 2 收尾

| 步驟 | 說明 |
|------|------|
| 2.6 | `Wait-Job -Timeout $Phase2TimeoutSeconds` |
| 2.7 | 收集結果、更新 `$sections`、記錄 timeout/failed |
| 2.8 | 清理 stderr 檔、寫入 spans |

**可抽離**：Phase 2 的「誰來執行」同樣可替換為不同執行器。

---

### Phase 3：組裝 + 關閉 + 通知（約 60–180 秒）

| 步驟 | 說明 | 工具 | 產出 |
|------|------|------|------|
| 3.1 | 讀取 `prompts/team/todoist-assemble.md` | Read | `$assembleContent` |
| 3.2 | 主流程執行（非 Job）：`$assembleContent \| claude -p --allowedTools "Read,Bash,Write"` | claude | - |
| 3.3 | 最多重試 1 次（指數退避） | - | - |
| 3.4 | 更新 FSM、寫入 spans | - | - |

**Phase 3 內部（todoist-assemble Agent）**：

- 讀取 Phase 2 結果
- 關閉 Todoist 任務
- 更新 auto-tasks-today.json
- 發送 ntfy 通知

**可抽離**：Phase 3 的執行器亦可替換。

---

### 收尾

| 步驟 | 說明 |
|------|------|
| F.1 | 計算 `$totalDuration`、`$phaseBreakdown` |
| F.2 | 更新 `scheduler-state.json`（success/failed） |
| F.3 | 清理 7 天前的 log、spans |

---

## 二、分拆策略

### 2.1 分拆成兩個腳本

| 腳本 | 職責 | 輸入 | 輸出 |
|------|------|------|------|
| **select-todoist-model.ps1** | 用 Groq 從模型清單選出本次使用的執行器 | 執行上下文（時間、token 用量、plan_type 等） | `results/model-selection.json` |
| **run-todoist-executor-{backend}.ps1** | 依選定執行器執行 Phase 1–3 | `model-selection.json` 或 `-Backend` 參數 | 與現有腳本相同（plan、狀態、通知） |

### 2.2 分拆後的流程

```
run-todoist-agent-team.ps1（協調器）
  │
  ├─ Phase 0：Circuit Breaker（共用，不變）
  │
  ├─ 呼叫 select-todoist-model.ps1
  │     └─ 輸出：results/model-selection.json
  │           { "backend": "claude" | "codex" | "groq" | "openrouter", "reason": "..." }
  │
  └─ 依 backend 呼叫對應執行器：
        run-todoist-executor-claude.ps1   ← 現有邏輯（Phase 1–3）
        run-todoist-executor-codex.ps1
        run-todoist-executor-groq.ps1
        run-todoist-executor-openrouter.ps1
```

### 2.3 共用模組抽離

將重複邏輯抽到 `todoist-team-utils.ps1`：

- `Write-Log`
- `Update-State`
- `Update-FailureStats`
- `Send-FailureAlert`
- `Set-FsmState`
- `Write-Span`
- `Remove-StderrIfBenign`
- 路徑變數、timeout 預算、key 別名表

各執行器腳本僅負責：**呼叫對應 CLI/API**，其餘流程共用。

---

## 三、執行器決策邏輯（依任務性質 + 模型額度）

### 3.1 核心原則

> **每次排程可能執行數個任務，應依任務的性質及模型的額度來決定採用何項模型。**

- **Per-task 選擇**：每個任務獨立決定使用哪個執行器，非整次 run 共用一個 backend
- **任務性質**：research / code / skill / auto 等類型，影響模型能力匹配
- **模型額度**：各模型（claude、codex、groq、openrouter）的剩餘配額，影響是否可選

### 3.2 決策時機

| 階段 | 決策對象 | 說明 |
|------|----------|------|
| **Phase 1** | 單一 query agent | 可固定用 claude（規劃需穩定），或依額度選 groq/openrouter |
| **Phase 2** | **每個 task 獨立** | 依任務性質 + 各模型剩餘額度，為每個 task 指派 backend |
| **Phase 3** | 單一 assemble agent | 可固定用 claude，或依額度選 |

重點：**Phase 2 的 N 個任務可分散到不同執行器**，以平衡負載與額度。

### 3.3 決策輸入

#### 任務性質（來自 plan）

| 來源 | 欄位 | 任務類型推斷 |
|------|------|--------------|
| `plan.tasks` | `allowed_tools` | 含 WebSearch/WebFetch → research；含 Edit/Glob/Grep → code；否則 → skill |
| `plan.auto_tasks.selected_tasks` | `key` | tech_research → research；log_audit、qa_optimize → code；shurangama、github_scout → research；git_push → general |

#### 模型額度（需追蹤）

| 模型 | 額度來源 | 說明 |
|------|----------|------|
| claude | `state/token-usage.json` 或 Anthropic 用量 | 每日/每月 token 上限 |
| codex | OpenAI 用量或自訂配額 | 每日請求數或 token |
| groq | 免費 5 req/min；付費可調 | `config/llm-router.yaml` rate_limit |
| openrouter | openrouter/free 無硬限 | 可用請求數或成本預算 |

**建議**：新增 `state/model-quotas.json` 追蹤各模型今日已用額度，供選擇器參考。

```json
{
  "date": "2026-03-08",
  "claude": { "used_tokens": 85000, "daily_limit": 200000 },
  "codex": { "used_requests": 3, "daily_limit": 50 },
  "groq": { "used_requests": 12, "rate_limit_per_min": 5 },
  "openrouter": { "used_requests": 0, "daily_budget": 100 }
}
```

### 3.4 決策流程：Per-Task 指派

```
Phase 1 完成 → 取得 plan.tasks 或 plan.auto_tasks.selected_tasks
                    │
                    ▼
        ┌───────────────────────────────┐
        │ 讀取 state/model-quotas.json   │
        │ 讀取 config/executor-routing  │
        └───────────────┬───────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ 對每個 task：                   │
        │   1. 推斷任務性質 (research/   │
        │      code/skill/auto)         │
        │   2. 篩選「額度足夠」的模型     │
        │   3. 依性質匹配能力排序         │
        │   4. 選最高分且額度足夠者       │
        └───────────────┬───────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ 輸出 results/task-assignments  │
        │ .json                          │
        │ { "task-1": "claude",           │
        │   "task-2": "groq",             │
        │   "auto-tech_research": "codex" }│
        └───────────────────────────────┘
```

### 3.5 任務性質 → 模型匹配矩陣

| 任務性質 | 建議優先順序 | 理由 |
|----------|--------------|------|
| **research** | claude ≥ codex > openrouter > groq | 需 WebSearch/WebFetch，推理深度高 |
| **code** | claude ≥ codex > groq > openrouter | 需 Edit/Glob/Grep，程式碼理解 |
| **skill** | groq ≥ openrouter > codex > claude | 輕量、結構化，可省 Claude 額度 |
| **auto**（混合） | 依 key 細分：tech_research→claude；log_audit→codex；shurangama→openrouter | 依子任務特性 |

### 3.6 額度優先規則

1. **額度不足則跳過**：若某模型今日額度已用完，不納入候選
2. **額度預留**：Phase 3 預留 claude 或 codex 額度（組裝需穩定）
3. **輪替分散**：同性質多任務時，盡量輪流使用不同模型，避免單一模型爆量

### 3.7 決策實作：Groq 批次選擇

**select-todoist-model.ps1** 在 Phase 1 完成後、Phase 2 啟動前執行：

1. 輸入：`plan` + `state/model-quotas.json` + `config/executor-routing.yaml`
2. 組裝 prompt 給 Groq：
   - 任務清單（含性質推斷）
   - 各模型剩餘額度
   - 匹配矩陣（可從 config 讀入）
3. 要求回傳 JSON：`{ "assignments": { "task-1": "claude", "task-2": "groq", ... }, "reasoning": "..." }`
4. 寫入 `results/task-assignments.json`

### 3.8 決策實作：規則引擎（備援）

若 Groq 不可用，用規則引擎做 per-task 指派：

```yaml
# config/executor-routing.yaml
task_nature_mapping:
  research: [claude, codex, openrouter, groq]
  code:     [claude, codex, groq, openrouter]
  skill:    [groq, openrouter, codex, claude]
  auto:     [claude, codex, openrouter, groq]

quota_rules:
  claude_daily_limit: 200000
  groq_rate_per_min: 5
  reserve_for_phase3: claude  # Phase 3 預留

selection: pick_first_available  # 依序取第一個額度足夠者
```

### 3.9 執行器能力對照

| 執行器 | 類型 | 工具支援 | 額度特性 |
|--------|------|----------|----------|
| **claude** | CLI | 全工具 | Token 計費，易達上限 |
| **codex** | CLI | sandbox 執行 | 請求數/Token 計費 |
| **groq** | API | tool calling | 5 req/min（免費） |
| **openrouter** | API | tool calling | openrouter/free 無硬限 |

### 3.10 Phase 2 執行流程（Per-Task 指派後）

```
foreach task in plan.tasks / plan.auto_tasks.selected_tasks:
    backend = task-assignments[task.id]
    case backend:
        claude   → Start-Job { $prompt | claude -p ... }
        codex    → Start-Job { codex exec "..." ... }
        groq     → Start-Job { node agentic-executor.js --api groq ... }
        openrouter → Start-Job { node agentic-executor.js --api openrouter ... }
```

---

---

## 四、新流程：先整理任務，再啟動 JOB

### 4.1 核心變更

> **應改變原有的流程，先整理出此次排程需要執行的任務，再啟動 JOB。**

| 原流程 | 新流程 |
|--------|--------|
| Phase 1 啟動 query Job（claude -p）→ 產出 plan | Phase 1 **僅整理任務**，不啟動任何執行 Job |
| Phase 2 直接啟動 N 個 task Job | Phase 2 **模型指派** → Phase 3 **才啟動** N 個 Job |

### 4.2 新流程架構

```
Phase 0: Circuit Breaker
    │
Phase 1: 任務整理（無 Job）
    │   ├─ 查 Todoist API / 快取
    │   ├─ 過濾（時間、已關閉、安全）
    │   ├─ 查 chatroom pending
    │   ├─ 路由 + 頻率檢查
    │   └─ 產出：results/todoist-plan.json（完整任務清單）
    │
Phase 2: 模型指派（無 Job）
    │   ├─ 讀取 plan + model-quotas
    │   ├─ 依任務性質 + 額度為每個 task 指派 backend
    │   └─ 產出：results/task-assignments.json
    │
Phase 3: 啟動 JOB（並行執行）
    │   ├─ 依 assignments 為每個 task 啟動對應執行器 Job
    │   └─ Wait-Job → 收集結果
    │
Phase 4: 組裝 + 通知
    └─ 關閉任務、更新狀態、ntfy
```

### 4.3 關鍵分界

| 階段 | 是否啟動執行 Job | 產出 |
|------|------------------|------|
| Phase 1 | **否** | `todoist-plan.json`（任務清單） |
| Phase 2 | **否** | `task-assignments.json`（task → backend） |
| Phase 3 | **是** | N 個 Job 並行執行 |
| Phase 4 | 主流程 1 個 | 組裝 Agent |

### 4.4 Phase 1 任務整理的實作選項

| 選項 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **A. 規則 + API** | PowerShell/Python：Todoist API + config/routing.yaml + frequency-limits.yaml，純規則產出 plan | 無 LLM、省 token、快 | 路由邏輯需完整遷移 |
| **B. Groq 輕量** | Groq 做路由決策，API 查詢由腳本完成 | 省 Claude、較快 | Groq 需理解路由規則 |
| **C. Claude 規劃專用** | 保留現有 todoist-query，但明確為「規劃 only」，不混入執行 | 邏輯不變、改動小 | 仍耗 Claude token |

**建議**：短期採 **C**（改動最小）；中期評估 **A**（完全省 Phase 1 的 LLM）。

### 4.5 流程對照

```
【原流程】
Phase 1: Start-Job(claude -p query) → plan
Phase 2: foreach task → Start-Job(claude -p task)  ← 規劃與執行交錯感

【新流程】
Phase 1: 整理任務（可為 API+規則 或 單一 query Job）→ plan（完整清單）
Phase 2: 模型指派 → assignments
Phase 3: foreach task → Start-Job(對應執行器)     ← 任務清單已確定，再啟動
Phase 4: 組裝
```

---

## 五、小結

| 項目 | 說明 |
|------|------|
| **流程變更** | 先整理任務（Phase 1）→ 模型指派（Phase 2）→ 再啟動 JOB（Phase 3） |
| **決策** | Per-task，依任務性質 + 模型額度 |
| **分拆** | select-todoist-model.ps1、todoist-team-utils.ps1、run-todoist-executor-{backend}.ps1 |
| **Phase 1 選項** | 規則+API（省 token）／Groq／Claude 規劃專用 |
