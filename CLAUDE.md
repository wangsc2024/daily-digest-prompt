# Daily Digest Prompt - 專案指引

## 專案概述
每日摘要 Agent：透過 Windows 排程器定時執行 Claude Code，自動彙整待辦事項、在地新聞與禪語，並推播通知。
具備跨次記憶、API 快取降級、排程狀態追蹤等機制（靈感來自 NanoClaw 架構）。

## ⚡ Skill-First 策略（最高原則）

本專案的 Agent 是 **Skill 驅動型**，所有行為都由 Skill 指引。

### 核心規則
1. **先讀 `skills/SKILL_INDEX.md`**：Agent 啟動的第一個動作就是載入 Skill 索引
2. **能用 Skill 就用 Skill**：禁止自行拼湊已有 Skill 覆蓋的邏輯
3. **先讀 SKILL.md 再動手**：每個步驟都必須先讀取對應的 SKILL.md
4. **Skill 鏈式組合**：積極串聯多個 Skill 實現更高價值
5. **Skill 匹配篩選**：Todoist Agent 篩選任務時，主動比對 SKILL_INDEX 觸發關鍵字

### Skill 使用強度
- **必用**：todoist、pingtung-news、pingtung-policy-expert、hackernews-ai-digest、atomic-habits、learning-mastery、ntfy-notify、digest-memory、api-cache、scheduler-state
- **積極用**：knowledge-query、gmail
- **搭配用**：pingtung-policy-expert 必搭 pingtung-news、api-cache 必搭任何 API 呼叫、groq 搭配 hackernews-ai-digest（批次翻譯）+ pingtung-news（快速摘要）

詳細路由邏輯見 `docs/skill-routing-guide.md`；完整索引見 `skills/SKILL_INDEX.md`。

## 🤝 Agent Team & 子 Agent 策略（積極並行）

### 核心原則
1. **團隊模式優先**：有 `*-team.ps1` 時，一律優先使用
2. **主動拆分並行**：≥2 個獨立任務就用子 Agent 並行
3. **保護主 Context Window**：研究/分析委派給子 Agent
4. **子 Agent 專責分工**：每個子 Agent 只做一件事，結果透過 `results/*.json` 交接

### 何時啟動子 Agent
| 情境 | 做法 |
|------|------|
| 多個 API 呼叫互不依賴 | 並行啟動多個子 Agent 同時呼叫 |
| 研究 / 探索任務 | 用 `subagent_type=Explore` 深度搜尋 |
| 耗時操作（build / lint） | 用 `run_in_background=true` 背景執行 |

### 何時用 Agent Team（TeamCreate）
| 情境 | 做法 |
|------|------|
| 複雜多步驟任務（3+ 步驟且有依賴） | 建立 Team，用任務清單協調分工 |
| 前端 + 後端 / 研究 + 實作 同步進行 | 不同 Agent 各司其職，Team Lead 統籌 |

### 禁止行為
- 禁止串行處理可並行的獨立任務
- 禁止主 Agent 獨攬所有工作
- 禁止忽略 background 模式（耗時 >30 秒考慮背景執行）

## 文件驅動架構設計原則

| 原則 | 說明 |
|------|------|
| **Prompt 是薄層調度器** | 只含角色宣告、步驟骨架、容錯語義；數據型邏輯全部外部化 |
| **配置用 YAML、模板用 Markdown** | YAML 支援注釋、層級清晰；Markdown 是 LLM 最自然的理解格式 |
| **按需載入** | 子 Agent 模板、自動任務 prompt 只在觸發時才 Read，不預載 |
| **單一定義處** | nul 禁令、Skill-First 規則只在 `templates/shared/preamble.md` 定義一次 |
| **改配置不改 prompt** | 調 TTL → 改 `config/cache-policy.yaml`；調路由 → 改 `config/routing.yaml` |

### 配置文件速查

| 文件 | 用途 | 引用者 |
|------|------|--------|
| `config/pipeline.yaml` | 每日摘要管線步驟 | daily-digest-prompt.md |
| `config/routing.yaml` | Todoist 三層路由規則 | hour-todoist-prompt.md |
| `config/cache-policy.yaml` | 各 API 快取 TTL | daily-digest-prompt.md |
| `config/frequency-limits.yaml` | 自動任務頻率限制 | hour-todoist-prompt.md |
| `config/scoring.yaml` | TaskSense 優先級計分 | hour-todoist-prompt.md |
| `config/notification.yaml` | ntfy 通知配置 | hour-todoist-prompt.md、assemble-digest.md |
| `config/digest-format.md` | 摘要輸出排版模板 | daily-digest-prompt.md、assemble-digest.md |
| `config/dedup-policy.yaml` | 研究去重策略 | 所有研究模板 |
| `config/audit-scoring.yaml` | 系統審查 7 維度計分規則 | system-audit Skill |
| `config/benchmark.yaml` | 系統效能基準線 | system-insight Skill |
| `config/health-scoring.yaml` | 健康評分 6 維度權重 | query-logs.ps1 -Mode health-score |
| `config/hook-rules.yaml` | Hooks 規則外部化 | pre_bash_guard.py、pre_write_guard.py |
| `config/llm-router.yaml` | LLM 路由規則（Groq vs Claude） | skills/groq/SKILL.md |
| `config/timeouts.yaml` | 各 Agent 超時配置 | run-todoist-agent-team.ps1 |
| `config/topic-rotation.yaml` | 主題輪替演算法（LRU + 同日去重） | 研究任務模板 |
| `templates/shared/preamble.md` | 共用前言（nul 禁令 + Skill-First） | 所有 prompt |

## 架構

完整目錄結構見 `docs/ARCHITECTURE.md`。
本專案採用文件驅動架構：Prompt 薄層 + YAML 外部配置 + Markdown 模板按需載入。
快取狀態由 PowerShell Phase 0 預計算寫入 `cache/status.json`，LLM 直接讀 `valid` 欄位，無需自行計算時間差。

## 執行流程摘要

詳細步驟見 `docs/OPERATIONS.md`。

| 流程 | 腳本 | 模式 | 預期耗時 |
|------|------|------|---------|
| 每日摘要 | run-agent-team.ps1 | Phase 0→1→2 | ~1-2 分鐘 |
| Todoist 任務 | run-todoist-agent-team.ps1 | Phase 1→2→3 | 依任務而異 |
| 系統審查 | run-system-audit-team.ps1 | Phase 0→1→2 | 15-20 分鐘 |
| Gmail | run-gmail-agent.ps1 | 單一 | ~5 分鐘 |

## 技術棧
- **執行環境**: PowerShell 7 (pwsh)
- **排程**: Windows Task Scheduler
- **Agent**: Claude Code CLI（`claude -p`）
- **通知**: ntfy.sh（topic: `wangsc2025`）
- **Python**: uv 管理（`uv sync`），pyproject.toml 定義依賴

## Hooks 機器強制層（摘要）

`.claude/settings.json` — Hook 命令格式：`uv run --project D:/Source/daily-digest-prompt python D:/...`

| Hook | 類型 | 用途 |
|------|------|------|
| `pre_bash_guard.py` | PreToolUse:Bash | nul重導向、危險操作攔截 |
| `pre_write_guard.py` | PreToolUse:Write/Edit | nul寫入、敏感檔案、路徑遍歷攔截 |
| `pre_read_guard.py` | PreToolUse:Read | 敏感路徑讀取攔截 |
| `post_tool_logger.py` | PostToolUse:* | 結構化 JSONL 日誌（自動標籤 + 50MB 輪轉） |
| `cjk_guard.py` | PostToolUse:Write/Edit | CJK 字元守衛（日文變體修正） |
| `on_stop_alert.py` | Stop | Session 結束健康檢查 + ntfy 告警 |

詳細規則、日誌格式、查詢指令見 `docs/OPERATIONS.md`。

## NanoClaw 啟發的優化機制
1. **跨次記憶**：`context/digest-memory.json`，追蹤連續天數、待辦完成率
2. **HTTP 快取**：PS 預計算 `cache/status.json`，Phase 1 Agent 讀 valid 欄位判斷是否命中
3. **排程狀態**：`state/scheduler-state.json`（PS 獨佔寫入），失敗自動重試一次
4. **自動任務輪轉**：19 個任務，47 次/日上限，round-robin 確保公平輪轉

## 架構決策索引（ADR 速查）

> 完整 ADR 詳情由 `arch-evolution` Skill 維護於 `context/adr-registry.json`。

| ADR | 決策標題 | 狀態 |
|-----|---------|------|
| ADR-001 | **Skill-First 策略**：必用先查 SKILL_INDEX | ✅ Accepted |
| ADR-002 | **文件驅動架構**：Prompt 薄層 + YAML 外部配置 | ✅ Accepted |
| ADR-003 | **PowerShell 7 (pwsh)** 作為執行環境 | ✅ Accepted |
| ADR-004 | **Team 並行模式優先**於單一模式 | ✅ Accepted |
| ADR-005 | **Hook 機器強制層**取代 Prompt 自律 | ✅ Accepted |
| ADR-006 | **scheduler-state.json 由 PowerShell 獨佔寫入** | ✅ Accepted |
| ADR-007 | **研究去重三層防護**（registry + KB + 冷卻） | ✅ Accepted |
| ADR-008 | **OODA 閉環架構**（system-insight→audit→arch-evolution→self-heal） | ✅ Accepted |

> **如何新增 ADR**：執行 `arch-evolution 模組 A`，自動從 `context/improvement-backlog.json` 轉化為 ADR。

## Skills（專案 26 個 + 全域 54 個）

- **專案 Skills**（26 個）：完整清單見 `skills/SKILL_INDEX.md`（19 核心 + 7 工具）
- **全域 Cursor Skills**（54 個）：完整清單見 `C:\Users\user\.cursor\skills\SKILLS_INDEX.md`
- **全域 Claude Skills**（56 個）：位於 `C:\Users\user\.claude\skills\`（含 code-assistant、issue-resolver-skill、knowledge-query、pingtung-news 等專屬 skills）
- Skills 來源：`D:\Source\skills\`，複製到專案內確保自包含

## ntfy 通知注意事項
- Windows 環境必須用 JSON 檔案方式發送，不可用 inline JSON 字串（會亂碼）
- 必須加 `charset=utf-8` header：`curl -H "Content-Type: application/json; charset=utf-8" -d @file.json https://ntfy.sh`
- 用 Write 工具建立 JSON 檔確保 UTF-8 編碼，不可用 Bash echo 建檔
- 發送後刪除暫存 JSON 檔

## 慣例
- 全程使用正體中文；日誌檔名：`yyyyMMdd_HHmmss.log`；保留 7 天自動清理
- 所有 .ps1 腳本使用 PowerShell 7 (`pwsh`)；`.ps1` 建議 UTF-8 with BOM
- Python 依賴由 uv 管理，使用 `uv run python` 執行（非裸 `python`）
- **計畫檔存放**：一律放在 `docs/plans/` 目錄下（格式：`{feature}-plan.md`），禁止存放至專案目錄外（pre_write_guard.py 會攔截路徑遍歷）

### 自動任務命名規範（嚴禁使用連字號）

> **背景**：連字號（`-`）vs 底線（`_`）命名不一致已多次導致「Phase 2 未產出結果檔案」靜默錯誤。

| 項目 | 規範 | 反例 |
|------|------|------|
| **task_key**（frequency-limits.yaml 定義） | `ai_github_research` | ~~`ai-github-research`~~ |
| **Prompt 檔名** | `todoist-auto-{task_key}.md` | 連字號 task_key 部分禁用 |
| **結果 JSON 檔名** | `results/todoist-auto-{task_key}.json` | ~~`todoist-auto-ai-github.json`~~ |
| **結果 JSON `agent` 欄位** | `"agent": "todoist-auto-{task_key}"` | ~~`"agent": "todoist-auto-ai-github"`~~ |

**黃金規則**：`frequency-limits.yaml` 的 key 是**唯一真相來源**，prompt 檔名、結果 JSON 檔名、`agent` 欄位三者必須完全一致（含底線）。

**新增自動任務 checklist**：
1. `config/frequency-limits.yaml` 加入 task_key（底線）
2. `prompts/team/todoist-auto-{task_key}.md`（底線）
3. Prompt 內 `results/todoist-auto-{task_key}.json`（底線）
4. Prompt 內 `"agent": "todoist-auto-{task_key}"`（底線）
5. `run-todoist-agent-team.ps1` 的 `$AutoTaskTimeoutOverride`（底線）
6. `config/timeouts.yaml` 的 `phase2_timeout_by_task`（底線）

### 嚴禁產生 nul 檔案（最高優先級 — Hook 機器強制）
- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`（cmd 語法，在 bash 中會建立實體檔案）
- 禁止使用 Write 工具寫入任何名為 `nul` 的檔案路徑
- 要抑制輸出：`| Out-Null`（PowerShell）或 `> /dev/null`（bash）

> **機器強制**：`hooks/pre_bash_guard.py` 和 `hooks/pre_write_guard.py` 在 runtime 攔截。

## 排程配置

| 排程 | 觸發時間 | 腳本 | 模式 |
|------|---------|------|------|
| system-audit | 每日 00:40 | run-system-audit-team.ps1 | 團隊並行審查 |
| daily-digest-am | 每日 08:00 | run-agent-team.ps1 | 團隊並行 |
| daily-digest-mid | 每日 11:15 | run-agent-team.ps1 | 團隊並行 |
| daily-digest-pm | 每日 21:15 | run-agent-team.ps1 | 團隊並行 |
| todoist-single | 每小時整點 02-23 | run-todoist-agent.ps1 | 單一 |
| todoist-team | 每小時半點 02-23 | run-todoist-agent-team.ps1 | 3 階段並行 |

詳細排程 cron 定義在 `HEARTBEAT.md`；timeout 設定在 `config/timeouts.yaml`。

## 常用操作
```powershell
# 每日系統審查（推薦）
pwsh -ExecutionPolicy Bypass -File run-system-audit-team.ps1

# 每日摘要（推薦）
pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1

# Todoist 任務規劃（推薦）
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1

# 從 HEARTBEAT.md 批次建立排程（需管理員權限）
.\setup-scheduler.ps1 -FromHeartbeat

# 查看系統健康度
pwsh -ExecutionPolicy Bypass -File check-health.ps1

# 查詢執行成果
.\query-logs.ps1                              # 近 7 天摘要
.\query-logs.ps1 -Days 3 -Agent todoist       # 近 3 天 Todoist
.\query-logs.ps1 -Mode errors                  # 錯誤彙總
.\query-logs.ps1 -Mode trend -Days 14          # 趨勢分析

# 配置膨脹度量
.\analyze-config.ps1                           # 目前度量值
.\analyze-config.ps1 -Trend                   # 7 天趨勢

# Hook 結構化日誌查詢（詳細指令見 docs/OPERATIONS.md）
uv run python hooks/query_logs.py              # 今日摘要
uv run python hooks/query_logs.py --days 7    # 近 7 天
uv run python hooks/query_logs.py --blocked   # 攔截事件
```
