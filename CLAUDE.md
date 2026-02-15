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

### Skill 索引
`skills/SKILL_INDEX.md` 包含：
- 14 個 Skill 速查表（13 核心 + 1 工具，名稱、觸發關鍵字、用途）
- 路由決策樹（任務 → Skill 匹配邏輯）
- 鏈式組合模式（如：新聞 → 政策解讀 → 知識庫匯入 → 通知）
- 能力矩陣（依任務類型、依外部服務查找 Skill）
- 禁止行為清單

### Skill 使用強度
- **必用**（每次必定使用）：todoist、pingtung-news、pingtung-policy-expert、hackernews-ai-digest、atomic-habits、learning-mastery、ntfy-notify、digest-memory、api-cache、scheduler-state
- **積極用**（有機會就用）：knowledge-query、gmail
- **搭配用**：pingtung-policy-expert 必搭 pingtung-news、api-cache 必搭任何 API 呼叫、skill-scanner 搭配 Log 審查或新增 Skill 時

## 文件驅動架構設計原則

| 原則 | 說明 |
|------|------|
| **Prompt 是薄層調度器** | Prompt 只含角色宣告、步驟骨架、容錯語義；數據型邏輯全部外部化 |
| **配置用 YAML、模板用 Markdown** | YAML 支援注釋、層級清晰；Markdown 是 LLM 最自然的理解格式 |
| **按需載入** | 子 Agent 模板、自動任務 prompt 只在觸發時才 Read，不預載進 context window |
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
| `config/dedup-policy.yaml` | 研究去重策略（冷卻天數、飽和閾值） | 所有研究模板 |
| `templates/shared/preamble.md` | 共用前言（nul 禁令 + Skill-First） | 所有 prompt |

## 架構

本專案採用**文件驅動架構**：Prompt 是薄層調度器，所有可變邏輯抽入結構化配置文件與模板，按需載入。

```
daily-digest-prompt/
  # Prompt 層（薄層調度器，讀配置 → 按管線執行）
  daily-digest-prompt.md          # 每日摘要 Agent（~80 行，引用 config/ + templates/）
  hour-todoist-prompt.md          # Todoist 任務規劃 Agent（~140 行，引用 config/ + templates/）
  daily-gmail-prompt.md           # Gmail Agent（獨立排程）
  HEARTBEAT.md                    # 排程元資料（cron 定義，供 setup-scheduler.ps1 讀取）

  # 配置層（數據型配置，修改無需動 prompt）
  config/
    pipeline.yaml                 # 每日摘要管線：步驟順序、Skill 依賴、後處理
    routing.yaml                  # Todoist 三層路由：標籤映射、關鍵字映射、排除清單
    cache-policy.yaml             # 快取策略：各 API 的 TTL、降級時限
    frequency-limits.yaml         # 自動任務頻率限制（14 個任務，38 次/日上限）
    scoring.yaml                  # TaskSense 優先級計分規則
    notification.yaml             # ntfy 通知配置（topic、標籤、模板）
    dedup-policy.yaml             # 研究去重策略（冷卻天數、飽和閾值、跨任務去重）
    digest-format.md              # 摘要輸出排版模板

  # 模板層（按需載入，不預載進 context window）
  templates/
    shared/
      preamble.md                 # 共用前言（nul 禁令 + Skill-First，一處定義）
      done-cert.md                # DONE_CERT 格式定義
      quality-gate.md             # 驗證閘門規則（迭代精修）
    sub-agent/                    # 子 Agent 任務模板（Todoist 路由後按需載入）
      skill-task.md               # 模板 A：有 Skill 匹配的任務
      research-task.md            # 模板 B：知識庫研究任務（含 KB 去重）
      code-task.md                # 模板 D：@code 任務（Plan-Then-Execute）
      game-task.md                # 模板 E：遊戲設計任務（品質分析→修改）
      general-task.md             # 模板 C：無 Skill 匹配的一般任務
      refinement.md               # 品質閘門精修 prompt
    auto-tasks/                   # 自動任務 prompt（無可處理項目或全部完成時按需載入）
      # 佛學研究（12 次/日）
      shurangama-research.md      # 楞嚴經研究（4 步驟含 KB 去重）
      buddhist-research.md        # 通用佛學模板（教觀綱宗/法華經/淨土宗共用）
      # AI/技術研究（17 次/日）
      tech-research.md            # 每日任務技術研究（分析已完成任務所需技術）
      ai-deep-research.md         # AI 深度研究計畫（4 階段）
      unsloth-research.md         # Unsloth LLM fine-tuning 研究
      ai-github-research.md       # AI GitHub 熱門專案研究
      ai-smart-city-research.md   # AI 智慧城市研究
      ai-sysdev-research.md       # AI 系統開發研究
      # 系統優化（2 次/日）
      skill-audit.md              # Skill 品質審查 + 優化
      # 系統維護（5 次/日）
      log-audit.md                # 系統 Log 審查（8 步驟含修正）
      git-push.md                 # GitHub 推送流程
      # 遊戲創意（2 次/日）
      creative-game-optimize.md   # 創意遊戲優化（D:\Source\game 目錄）

  # 執行腳本
  run-agent.ps1                   # 每日摘要執行腳本（單一模式，含重試）
  run-agent-team.ps1              # 每日摘要執行腳本（團隊並行模式，推薦）
  run-todoist-agent.ps1           # Todoist 任務規劃執行腳本（單一模式）
  run-todoist-agent-team.ps1      # Todoist 任務規劃執行腳本（3 階段並行，推薦）
  run-gmail-agent.ps1             # Gmail Agent 執行腳本
  setup-scheduler.ps1             # 排程設定工具（支援 HEARTBEAT.md 批次建立）
  check-health.ps1                # 健康檢查報告工具（快速一覽）
  scan-skills.ps1                 # 技能安全掃描工具（Cisco AI Defense）
  query-logs.ps1                  # 執行成果查詢工具（5 種模式）

  # Hooks 機器強制層
  .claude/
    settings.json                 # Hooks 設定（PreToolUse/PostToolUse/Stop）
  hooks/
    pre_bash_guard.py             # PreToolUse:Bash - 攔截 nul 重導向、危險操作
    pre_write_guard.py            # PreToolUse:Write/Edit - 攔截 nul 寫入、敏感檔案
    post_tool_logger.py           # PostToolUse:* - 結構化 JSONL 日誌（自動標籤）
    on_stop_alert.py              # Stop - Session 結束時健康檢查 + ntfy 自動告警
    query_logs.py                 # 結構化日誌查詢工具（CLI）

  # 團隊模式 Agent prompts
  prompts/team/
    # 每日摘要團隊模式（Phase 1 → Phase 2）
    fetch-todoist.md              # Phase 1: Todoist 資料擷取
    fetch-news.md                 # Phase 1: 屏東新聞資料擷取
    fetch-hackernews.md           # Phase 1: HN AI 新聞資料擷取
    fetch-gmail.md                # Phase 1: Gmail 郵件擷取
    fetch-security.md             # Phase 1: Cisco AI Defense 安全審查
    assemble-digest.md            # Phase 2: 摘要組裝 + 通知 + 狀態
    # Todoist 團隊模式（Phase 1 → Phase 2 → Phase 3）
    todoist-query.md              # Phase 1: Todoist 查詢 + 路由 + 計分 + 規劃
    todoist-assemble.md           # Phase 3: 組裝結果 + 關閉任務 + 通知
    todoist-auto-shurangama.md    # Phase 2: 自動楞嚴經研究
    todoist-auto-logaudit.md      # Phase 2: 自動 Log 審查
    todoist-auto-gitpush.md       # Phase 2: 自動 Git 推送
  results/                        # 團隊模式中間結果（完成後清理）

  # 持久化資料
  context/
    digest-memory.json            # 摘要記憶（連續天數、待辦統計等）
    auto-tasks-today.json         # 自動任務頻率追蹤（每日歸零）
    research-registry.json        # 研究主題註冊表（跨任務去重，7 天滾動）
  cache/                          # API 回應快取（TTL 定義在 config/cache-policy.yaml）
    todoist.json / pingtung-news.json / hackernews.json / gmail.json
  state/
    scheduler-state.json          # 執行記錄（最近 200 筆，PowerShell 獨佔寫入）
    todoist-history.json          # Todoist 自動任務歷史

  # Skills（行為指引，自包含）
  skills/
    SKILL_INDEX.md                # Skill 索引與路由引擎（Agent 首先載入）
    todoist/ pingtung-news/ hackernews-ai-digest/ atomic-habits/
    learning-mastery/ pingtung-policy-expert/ knowledge-query/
    ntfy-notify/ digest-memory/ api-cache/ scheduler-state/
    gmail/ skill-scanner/
    game-design/                  # 共 14 個 Skill（13 核心 + 1 工具，各含 SKILL.md）

  # 規格與文件
  specs/system-docs/              # 系統文件（SRD/SSD/ops-manual）
  docs/                           # 研究文件與優化計畫
  tests/                          # 測試套件（Todoist API/Gmail 格式測試）

  # 日誌
  logs/
    structured/                   # 結構化 JSONL 日誌（hooks 自動產生）
```

## 執行流程

### 每日摘要（daily-digest-prompt.md）
1. Windows Task Scheduler 觸發 `run-agent.ps1`
2. 腳本自動建立 context/、cache/、state/ 目錄
3. 腳本讀取 `daily-digest-prompt.md` 作為 prompt（~80 行薄層調度器）
4. 透過 `claude -p --allowedTools "Read,Bash,Write"` 執行
5. Agent 載入共用前言（`templates/shared/preamble.md`）+ Skill 索引
6. 讀取 `config/pipeline.yaml` 取得管線定義 + `config/cache-policy.yaml` 取得快取 TTL
7. 依 pipeline.yaml 的 `init` → `steps` → `finalize` 順序執行，每步依對應 SKILL.md 操作
8. 摘要格式依 `config/digest-format.md` 排版 → ntfy 推播 → 寫入記憶
9. 若執行失敗，腳本自動重試一次（間隔 2 分鐘）

### 每日摘要 - 團隊並行模式（run-agent-team.ps1）
1. Windows Task Scheduler 觸發 `run-agent-team.ps1`
2. **Phase 1**：用 `Start-Job` 同時啟動 5 個 `claude -p`（Todoist + 新聞 + HN + Gmail + 安全審查）
3. 各 Agent 獨立執行快取檢查 + API 呼叫，結果寫入 `results/*.json`
4. 等待全部完成（timeout 300s），收集各 Agent 狀態
5. **Phase 2**：啟動組裝 Agent 讀取 `results/*.json`（timeout 420s）
6. 組裝 Agent 加上政策解讀、習慣提示、學習技巧、知識庫查詢、禪語
7. 整理完整摘要 → ntfy 推播 → 更新記憶/狀態 → 清理 results/
8. Phase 2 失敗可自動重試一次（間隔 60 秒）
9. 預期耗時約 1 分鐘（單一模式約 3-4 分鐘）

### Todoist 任務規劃 - 單一模式（run-todoist-agent.ps1）
1. Windows Task Scheduler 觸發 `run-todoist-agent.ps1`（timeout 2100s）
2. Agent 載入共用前言 + Skill 索引（~140 行薄層調度器）
3. 讀取 `config/routing.yaml` 取得三層路由規則 + `config/frequency-limits.yaml` 取得頻率限制
4. 查詢 Todoist → 依 routing.yaml 路由 → 按 `config/scoring.yaml` 計分排序
5. 子 Agent 模板從 `templates/sub-agent/` 按需載入（不預載）
6. 無可處理項目或全部完成時，自動任務 prompt 從 `templates/auto-tasks/` 按需載入
7. 品質驗證依 `templates/shared/quality-gate.md` + `templates/shared/done-cert.md`
8. 通知格式依 `config/notification.yaml`
9. **自動任務頻率限制**（定義在 config/frequency-limits.yaml）：14 個任務，合計 38 次/日上限，round-robin 輪轉
10. **研究任務 KB 去重**（定義在 templates/sub-agent/research-task.md）：研究前先查詢知識庫避免重複

### Todoist 任務規劃 - 團隊並行模式（run-todoist-agent-team.ps1，推薦）
1. Windows Task Scheduler 觸發 `run-todoist-agent-team.ps1`
2. **Phase 1**：1 個查詢 Agent（Todoist 查詢 + 過濾 + 路由 + 規劃，timeout 300s）
3. 輸出計畫類型：`tasks`（有待辦）/ `auto`（觸發自動任務）/ `idle`（跳過）
4. **Phase 2**：N 個並行執行 Agent（依計畫分配，動態 timeout 按任務類型計算）
   - research: 600s、code: 900s、skill/general: 300s、auto: 600s、gitpush: 180s
5. **Phase 3**：1 個組裝 Agent（關閉任務 + 更新狀態 + 推播通知，timeout 180s）
6. Phase 3 失敗可自動重試一次（間隔 60 秒）

## 技術棧
- **執行環境**: PowerShell 7 (pwsh)
- **排程**: Windows Task Scheduler
- **Agent**: Claude Code CLI（`claude -p`）
- **通知**: ntfy.sh（topic: `wangsc2025`）

## Hooks 機器強制層（Harness Enforcement）

從「Agent 自律」升級到「機器強制」。透過 Claude Code Hooks 在 runtime 攔截工具呼叫，違規操作在執行前就被阻斷。

### 設定檔
`.claude/settings.json`（專案級，commit 到 repo，所有開發者共享）

### Hook 清單

| Hook | 類型 | Matcher | 用途 |
|------|------|---------|------|
| `pre_bash_guard.py` | PreToolUse | Bash | 攔截 nul 重導向、scheduler-state 寫入、危險刪除、force push、敏感環境變數讀取、機密外洩 |
| `pre_write_guard.py` | PreToolUse | Write, Edit | 攔截 nul 檔案建立、scheduler-state 寫入、敏感檔案寫入、路徑遍歷攻擊 |
| `post_tool_logger.py` | PostToolUse | *（所有工具） | 結構化 JSONL 日誌，自動標籤分類 |
| `on_stop_alert.py` | Stop | — | Session 結束時分析日誌，異常時自動 ntfy 告警（使用安全暫存檔） |

### 強制規則對照表（Prompt 自律 → Hook 強制）

| 規則 | 之前（Prompt 宣告） | 之後（Hook 攔截） |
|------|-------------------|------------------|
| 禁止 `> nul` 重導向 | Prompt 寫「禁止」，Agent 自律 | `pre_bash_guard.py` 在執行前攔截，回傳 block reason |
| 禁止寫入 `nul` 檔案 | Prompt 寫「禁止」，Agent 自律 | `pre_write_guard.py` 攔截 file_path 為 nul 的 Write |
| scheduler-state.json 只讀 | Prompt 寫「Agent 只讀」 | Hook 攔截所有對此檔案的寫入/編輯/重導向 |
| 敏感檔案保護 | .gitignore 排除 | Hook 攔截 .env/credentials/token/secrets/.htpasswd 的寫入 |
| force push 保護 | 開發者口頭約定 | Hook 攔截 `git push --force` 到 main/master |
| 路徑遍歷防護 | 無 | `pre_write_guard.py` 攔截 `../` 逃逸專案目錄的路徑 |
| 敏感環境變數保護 | 無 | `pre_bash_guard.py` 攔截 echo/printenv/env 讀取 TOKEN/SECRET/KEY/PASSWORD |
| 機密外洩防護 | 無 | `pre_bash_guard.py` 攔截 curl/wget 傳送敏感變數 |

### 結構化日誌系統

`post_tool_logger.py` 對每個工具呼叫自動產生 JSONL 記錄，含：

**自動標籤分類**：
| 標籤 | 觸發條件 | 用途 |
|------|---------|------|
| `api-call` | Bash 指令含 `curl` | API 呼叫追蹤 |
| `todoist` / `pingtung-news` / `hackernews` / `knowledge` / `gmail` | URL 模式匹配 | API 來源識別 |
| `cache-read` / `cache-write` | 讀寫 `cache/*.json` | 快取操作追蹤 |
| `skill-read` / `skill-index` | 讀取 `SKILL.md` / `SKILL_INDEX.md` | Skill 使用追蹤 |
| `memory-read` / `memory-write` | 讀寫 `digest-memory.json` | 記憶操作追蹤 |
| `sub-agent` | Bash 指令含 `claude -p` | 子 Agent 追蹤 |
| `blocked` | PreToolUse hook 攔截 | 違規操作記錄 |
| `error` | 工具輸出含錯誤關鍵字 | 錯誤追蹤 |

**JSONL 格式**：
```json
{"ts":"2026-02-14T08:01:30+08:00","sid":"abc123","tool":"Bash","event":"post","summary":"curl -s https://api.todoist.com/...","output_len":1234,"has_error":false,"tags":["api-call","todoist"]}
```

### 自動告警機制

`on_stop_alert.py` 在 Agent session 結束時自動分析：

| 檢查項 | 條件 | 告警等級 |
|--------|------|---------|
| 違規攔截 | blocked > 0 | warning（≥3 則 critical） |
| 工具錯誤 | errors ≥ 1 | warning（≥5 則 critical） |
| 全部正常 | 無上述問題 | 不告警（靜默記錄 session-summary） |

告警透過 ntfy 推送到 `wangsc2025`，含：呼叫統計、攔截詳情、錯誤摘要。

### 查詢結構化日誌

```bash
# 今日摘要
python hooks/query_logs.py

# 近 7 天
python hooks/query_logs.py --days 7

# 僅攔截事件
python hooks/query_logs.py --blocked

# 僅錯誤
python hooks/query_logs.py --errors

# 快取使用審計
python hooks/query_logs.py --cache-audit

# Session 摘要
python hooks/query_logs.py --sessions --days 7

# JSON 輸出（供程式處理）
python hooks/query_logs.py --format json
```

### 前置需求
- Python 3.8+（hooks 用 Python 解析 JSON，跨平台相容）
- Windows 環境使用 `python`（非 `python3`，因 Windows Store 的 `python3` 空殼會靜默失敗）

## NanoClaw 啟發的優化機制

### 1. 跨次記憶持久化
- 每次執行讀取/更新 `context/digest-memory.json`
- 追蹤：連續執行天數、待辦完成率、習慣/學習連續天數
- 摘要開頭顯示「連續報到第 N 天」

### 2. HTTP 回應快取
- API 成功回應存入 `cache/*.json`（含時間戳與 TTL）
- 每次 API 呼叫前先檢查快取有效性
- API 故障時自動降級使用過期快取（24 小時內）

### 3. 排程狀態管理
- 各 `run-*.ps1` 腳本記錄每次執行狀態到 `state/scheduler-state.json`
- 失敗時自動重試一次（間隔依腳本不同：60s～120s）
- `check-health.ps1` 提供近 7 天健康度報告

### 4. 自動任務輪轉（round-robin）
- 14 個自動任務定義在 `config/frequency-limits.yaml`，合計 38 次/日上限
- 5 大群組：佛學研究(12)、AI/技術研究(17)、系統優化(2)、系統維護(5)、遊戲創意(2)
- 維護 `next_execution_order` 指針（跨日保留），確保所有任務公平輪轉
- 觸發條件：無可處理 Todoist 項目 **或** 今日任務全部完成

## Skills（專案內自包含，共 14 個）

完整清單見 `skills/SKILL_INDEX.md`。Skills 來源：`D:\Source\skills\`，複製到專案內確保自包含。

## ntfy 通知注意事項
- Windows 環境必須用 JSON 檔案方式發送，不可用 inline JSON 字串（會亂碼）
- 必須加 `charset=utf-8` header：`curl -H "Content-Type: application/json; charset=utf-8" -d @file.json https://ntfy.sh`
- 用 Write 工具建立 JSON 檔確保 UTF-8 編碼，不可用 Bash echo 建檔
- 發送後刪除暫存 JSON 檔

## 慣例
- 全程使用正體中文
- 日誌檔名格式：`yyyyMMdd_HHmmss.log`
- 日誌保留 7 天，自動清理
- prompt 內容修改後無需重新部署，下次排程自動生效
- 所有 .ps1 腳本使用 PowerShell 7 (`pwsh`) 執行，UTF-8 為預設編碼
- `.ps1` 檔案建議使用 UTF-8 with BOM 編碼（向下相容 PowerShell 5.1）

### 嚴禁產生 nul 檔案（最高優先級 — Hook 機器強制）
以下行為全部禁止，違反將產生名為 `nul` 的垃圾檔案：
- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`（這是 cmd 語法，在 bash 中會建立實體檔案）
- 禁止使用 Write 工具寫入任何名為 `nul` 的檔案路徑
- 禁止在任何指令中將 `nul` 作為輸出目標
- 要抑制輸出請改用：`| Out-Null`（PowerShell）或 `> /dev/null`（bash）或直接不重導向
- 要丟棄 stderr 請用 `2>/dev/null`（bash）或 `2>$null`（PowerShell）

> **機器強制**：此規則已由 `hooks/pre_bash_guard.py` 和 `hooks/pre_write_guard.py` 在 runtime 攔截。
> Agent 即使違反，工具呼叫也會被 block，並記錄到結構化日誌。

## 排程配置

排程定義集中在 `HEARTBEAT.md`，支援批次建立：

| 排程 | 觸發時間 | 腳本 | 模式 |
|------|---------|------|------|
| daily-digest-am | 每日 08:00 | run-agent-team.ps1 | 團隊並行 |
| daily-digest-mid | 每日 11:15 | run-agent-team.ps1 | 團隊並行 |
| daily-digest-pm | 每日 21:15 | run-agent-team.ps1 | 團隊並行 |
| todoist-single | 每小時整點 02-23 | run-todoist-agent.ps1 | 單一 |
| todoist-team | 每小時半點 02-23 | run-todoist-agent-team.ps1 | 3 階段並行 |

## 常用操作
```powershell
# 手動執行每日摘要（團隊並行模式，推薦）
pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1

# 手動執行每日摘要（單一模式，備用）
pwsh -ExecutionPolicy Bypass -File run-agent.ps1

# 手動執行 Todoist 任務規劃（團隊並行模式，推薦）
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1

# 手動執行 Todoist 任務規劃（單一模式，備用）
pwsh -ExecutionPolicy Bypass -File run-todoist-agent.ps1

# 從 HEARTBEAT.md 批次建立排程
.\setup-scheduler.ps1 -FromHeartbeat

# 設定排程（傳統方式）
.\setup-scheduler.ps1 -Time "08:00" -Script "run-agent-team.ps1"

# 查看排程狀態
schtasks /query /tn ClaudeDailyDigest /v

# 查看系統健康度（快速一覽）
pwsh -ExecutionPolicy Bypass -File check-health.ps1

# 查詢執行成果（靈活查詢）
.\query-logs.ps1                              # 近 7 天摘要
.\query-logs.ps1 -Days 3 -Agent todoist       # 近 3 天 Todoist
.\query-logs.ps1 -Mode detail -Date 2026-02-12 # 特定日期詳情
.\query-logs.ps1 -Mode errors                  # 錯誤彙總
.\query-logs.ps1 -Mode todoist                 # 自動任務歷史
.\query-logs.ps1 -Mode trend -Days 14          # 趨勢分析
.\query-logs.ps1 -Mode summary -Format json    # JSON 輸出

# 掃描 Skills 安全性
.\scan-skills.ps1
.\scan-skills.ps1 -Format markdown -UseBehavioral

# 查看最新日誌
Get-Content (Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1)

# Hook 結構化日誌查詢
python hooks/query_logs.py                     # 今日摘要
python hooks/query_logs.py --days 7             # 近 7 天
python hooks/query_logs.py --blocked            # 攔截事件
python hooks/query_logs.py --errors             # 錯誤事件
python hooks/query_logs.py --cache-audit        # 快取使用審計
python hooks/query_logs.py --sessions --days 7  # Session 健康摘要
```
