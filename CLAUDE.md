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
- 13 個 Skill 的速查表（名稱、觸發關鍵字、用途）
- 路由決策樹（任務 → Skill 匹配邏輯）
- 鏈式組合模式（如：新聞 → 政策解讀 → 知識庫匯入 → 通知）
- 能力矩陣（依任務類型、依外部服務查找 Skill）
- 禁止行為清單

### Skill 使用強度
- **必用**（每次必定使用）：todoist、pingtung-news、pingtung-policy-expert、hackernews-ai-digest、atomic-habits、learning-mastery、ntfy-notify、digest-memory、api-cache、scheduler-state
- **積極用**（有機會就用）：knowledge-query、gmail
- **搭配用**：pingtung-policy-expert 必搭 pingtung-news、api-cache 必搭任何 API 呼叫、skill-scanner 搭配 Log 審查或新增 Skill 時

## 架構

```
daily-digest-prompt/
  daily-digest-prompt.md          # 每日摘要 Agent prompt（核心指令）
  hour-todoist-prompt.md          # Todoist 任務規劃 Agent prompt
  run-agent.ps1                   # 每日摘要執行腳本（單一模式，含重試）
  run-agent-team.ps1              # 每日摘要執行腳本（團隊並行模式）
  run-todoist-agent.ps1           # Todoist 任務規劃執行腳本
  setup-scheduler.ps1             # 排程設定工具
  check-health.ps1                # 健康檢查報告工具（快速一覽）
  scan-skills.ps1                 # 技能安全掃描工具（Cisco AI Defense）
  query-logs.ps1                  # 執行成果查詢工具（5 種模式）
  .claude/
    settings.json                 # Hooks 設定（PreToolUse/PostToolUse/Stop）
  hooks/                          # Claude Code Hooks（機器強制層）
    pre_bash_guard.py             # PreToolUse:Bash - 攔截 nul 重導向、危險操作
    pre_write_guard.py            # PreToolUse:Write/Edit - 攔截 nul 寫入、敏感檔案
    post_tool_logger.py           # PostToolUse:* - 結構化 JSONL 日誌（自動標籤）
    on_stop_alert.py              # Stop - Session 結束時健康檢查 + ntfy 自動告警
    query_logs.py                 # 結構化日誌查詢工具（CLI）
  prompts/team/                   # 團隊模式 Agent prompts
    fetch-todoist.md              # Phase 1: Todoist 資料擷取
    fetch-news.md                 # Phase 1: 屏東新聞資料擷取
    fetch-hackernews.md           # Phase 1: HN AI 新聞資料擷取
    assemble-digest.md            # Phase 2: 摘要組裝 + 通知 + 狀態
  results/                        # 團隊模式 Phase 1 結果（Phase 2 清理）
  context/                        # 跨次記憶（持久化）
    digest-memory.json            # 摘要記憶（連續天數、待辦統計等）
    auto-tasks-today.json         # 自動任務頻率追蹤（每日歸零）
  cache/                          # API 回應快取
    todoist.json                  # Todoist 快取（TTL: 30 分鐘）
    pingtung-news.json            # 屏東新聞快取（TTL: 6 小時）
    hackernews.json               # HN 快取（TTL: 2 小時）
    knowledge.json                # 知識庫快取（TTL: 1 小時）
    gmail.json                    # Gmail 快取（TTL: 30 分鐘）
  state/                          # 排程執行狀態
    scheduler-state.json          # 執行記錄（最近 200 筆，含 log_file）
    todoist-history.json          # Todoist 自動任務歷史（楞嚴經/Log審查/Git push）
  skills/                         # 專案內 skill 指引（自包含）
    SKILL_INDEX.md                # Skill 索引與路由引擎（Agent 首先載入）
    todoist/SKILL.md              # Todoist API 查詢今日待辦
    pingtung-news/SKILL.md        # 屏東新聞 MCP 查詢
    hackernews-ai-digest/SKILL.md # HN AI 新聞摘要（curl 簡化版）
    atomic-habits/SKILL.md        # 原子習慣每日提示
    learning-mastery/SKILL.md     # 深度學習技術每日技巧
    pingtung-policy-expert/SKILL.md # 屏東新聞政策背景解讀
    knowledge-query/SKILL.md      # 個人知識庫查詢（可選）
    ntfy-notify/SKILL.md          # ntfy 通知發送
    digest-memory/SKILL.md        # 摘要記憶持久化
    api-cache/SKILL.md            # HTTP 回應快取
    scheduler-state/SKILL.md      # 排程狀態管理
    gmail/SKILL.md                # Gmail 郵件讀取（OAuth2）
    skill-scanner/SKILL.md        # AI 技能安全掃描（Cisco AI Defense）
  logs/                           # 執行日誌（自動清理 7 天）
    structured/                   # 結構化 JSONL 日誌（hooks 自動產生）
      YYYY-MM-DD.jsonl            # 每日工具呼叫記錄（自動標籤）
      session-summary.jsonl       # Session 健康摘要（Stop hook 產生）
```

## 執行流程

### 每日摘要（daily-digest-prompt.md）
1. Windows Task Scheduler 觸發 `run-agent.ps1`
2. 腳本自動建立 context/、cache/、state/ 目錄
3. 腳本讀取 `daily-digest-prompt.md` 作為 prompt
4. 透過 `claude -p --allowedTools "Read,Bash,Write"` 執行
5. **Agent 首先載入 `skills/SKILL_INDEX.md`（Skill-First）**
6. 載入記憶（digest-memory）與快取機制（api-cache）
7. 依序執行各步驟，每步嚴格依照對應 SKILL.md 操作
8. 主動觸發 Skill 鏈式組合（如：新聞 → 政策解讀 → 知識庫匯入）
9. 整理摘要（含連續報到、健康度、Skill 使用報告）→ ntfy 推播 → 寫入記憶（Agent）；狀態由 PowerShell 腳本寫入
10. 若執行失敗，腳本自動重試一次（間隔 2 分鐘）

### 每日摘要 - 團隊並行模式（run-agent-team.ps1）
1. Windows Task Scheduler 觸發 `run-agent-team.ps1`
2. **Phase 1**：用 `Start-Job` 同時啟動 3 個 `claude -p`（Todoist + 新聞 + HN）
3. 各 Agent 獨立執行快取檢查 + API 呼叫，結果寫入 `results/*.json`
4. 等待全部完成（timeout 180s），收集各 Agent 狀態
5. **Phase 2**：啟動組裝 Agent 讀取 `results/*.json`
6. 組裝 Agent 加上政策解讀、習慣提示、學習技巧、知識庫查詢、禪語
7. 整理完整摘要 → ntfy 推播 → 更新記憶/狀態 → 清理 results/
8. Phase 2 失敗可自動重試一次（間隔 60 秒）
9. 預期耗時約 1 分鐘（單一模式約 3-4 分鐘）

### Todoist 任務規劃（hour-todoist-prompt.md）
1. Windows Task Scheduler 或手動觸發 `run-todoist-agent.ps1`
2. 腳本讀取 `hour-todoist-prompt.md` 作為 prompt
3. 透過 `claude -p --allowedTools "Read,Bash,Write"` 執行
4. **Agent 首先載入 `skills/SKILL_INDEX.md`（Skill-First）**
5. 查詢 Todoist → 用 SKILL_INDEX 觸發關鍵字比對任務 → 匹配 Skill 納入執行方案
6. 生成子 Agent prompt（含 SKILL.md 路徑引用）→ 執行 → 關閉任務 → ntfy 通知
7. **無可處理項目時**（含頻率限制，每日自動歸零）：
   - 楞嚴經研究（每日最多 **3 次**），將成果寫入 RAG 知識庫
   - 系統 Log 深度審查（每日最多 **1 次**），找出改善/優化項目並執行修正
   - 專案推送 GitHub（每日最多 **2 次**），自動 commit + push 變更至 GitHub
   - 頻率追蹤：`context/auto-tasks-today.json`（跨日自動歸零）
8. **研究任務 KB 去重機制**：所有研究類任務（楞嚴經、AI、Claude Code、GitHub、邏輯思維）的子 Agent 在研究前必須先查詢知識庫已有筆記（用 `/api/notes?limit=100` + tag/title 本地篩選），根據已有內容自主選擇未涵蓋的主題，避免重複研究

## 技術棧
- **執行環境**: Windows PowerShell
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
| `pre_bash_guard.py` | PreToolUse | Bash | 攔截 nul 重導向、scheduler-state 寫入、危險刪除、force push |
| `pre_write_guard.py` | PreToolUse | Write, Edit | 攔截 nul 檔案建立、scheduler-state 寫入、敏感檔案寫入 |
| `post_tool_logger.py` | PostToolUse | *（所有工具） | 結構化 JSONL 日誌，自動標籤分類 |
| `on_stop_alert.py` | Stop | — | Session 結束時分析日誌，異常時自動 ntfy 告警 |

### 強制規則對照表（Prompt 自律 → Hook 強制）

| 規則 | 之前（Prompt 宣告） | 之後（Hook 攔截） |
|------|-------------------|------------------|
| 禁止 `> nul` 重導向 | Prompt 寫「禁止」，Agent 自律 | `pre_bash_guard.py` 在執行前攔截，回傳 block reason |
| 禁止寫入 `nul` 檔案 | Prompt 寫「禁止」，Agent 自律 | `pre_write_guard.py` 攔截 file_path 為 nul 的 Write |
| scheduler-state.json 只讀 | Prompt 寫「Agent 只讀」 | Hook 攔截所有對此檔案的寫入/編輯/重導向 |
| 敏感檔案保護 | .gitignore 排除 | Hook 攔截 .env/credentials/token 的寫入 |
| force push 保護 | 開發者口頭約定 | Hook 攔截 `git push --force` 到 main/master |

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
| 快取繞過 | API 呼叫無對應 cache-read | warning |
| 全部正常 | 無上述問題 | 不告警（靜默記錄 session-summary） |

告警透過 ntfy 推送到 `wangsc2025`，含：呼叫統計、攔截詳情、錯誤摘要、快取繞過來源。

### 查詢結構化日誌

```bash
# 今日摘要
python3 hooks/query_logs.py

# 近 7 天
python3 hooks/query_logs.py --days 7

# 僅攔截事件
python3 hooks/query_logs.py --blocked

# 僅錯誤
python3 hooks/query_logs.py --errors

# 快取使用審計
python3 hooks/query_logs.py --cache-audit

# Session 摘要
python3 hooks/query_logs.py --sessions --days 7

# JSON 輸出（供程式處理）
python3 hooks/query_logs.py --format json
```

### 前置需求
- Python 3.8+（hooks 用 Python 解析 JSON，跨平台相容）
- Windows 環境需安裝 Git Bash 或確保 `python3` 可用（或改為 `python`）

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
- `run-agent.ps1` 記錄每次執行狀態到 `state/scheduler-state.json`
- 失敗時自動重試一次（間隔 2 分鐘）
- `check-health.ps1` 提供近 7 天健康度報告

## 使用的 Skills（專案內自包含）
- `skills/SKILL_INDEX.md` - **Skill 索引與路由引擎**（Agent 啟動首先載入）
- `skills/todoist/SKILL.md` - Todoist REST API 查詢今日待辦
- `skills/pingtung-news/SKILL.md` - MCP 服務查詢屏東縣政府新聞
- `skills/hackernews-ai-digest/SKILL.md` - Hacker News API 篩選 AI 新聞（curl 簡化版）
- `skills/atomic-habits/SKILL.md` - 《原子習慣》每日提示（依星期輪替）
- `skills/learning-mastery/SKILL.md` - 《深度學習的技術》每日學習技巧（依星期輪替）
- `skills/pingtung-policy-expert/SKILL.md` - 屏東施政背景解讀（強化新聞區塊）
- `skills/knowledge-query/SKILL.md` - 個人知識庫查詢（localhost:3000，可選）
- `skills/ntfy-notify/SKILL.md` - ntfy 推播通知（Write 建 UTF-8 JSON + curl 發送）
- `skills/digest-memory/SKILL.md` - 摘要記憶持久化（跨次追蹤）
- `skills/api-cache/SKILL.md` - HTTP 回應快取（降級保護）
- `skills/scheduler-state/SKILL.md` - 排程狀態管理（執行記錄）
- `skills/gmail/SKILL.md` - Gmail 郵件讀取（OAuth2 認證，可選）
- `skills/skill-scanner/SKILL.md` - Cisco AI Defense Skill Scanner（技能安全掃描）

> Skills 來源：`D:\Source\skills\`，複製到專案內確保自包含，不依賴外部路徑。

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
- Windows 環境需設定 `chcp 65001` 確保 UTF-8 編碼
- `.ps1` 檔案必須使用 UTF-8 with BOM 編碼（PowerShell 5.1 無 BOM 會用系統預設編碼讀取，中文會亂碼）

### 嚴禁產生 nul 檔案（最高優先級 — Hook 機器強制）
以下行為全部禁止，違反將產生名為 `nul` 的垃圾檔案：
- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`（這是 cmd 語法，在 bash 中會建立實體檔案）
- 禁止使用 Write 工具寫入任何名為 `nul` 的檔案路徑
- 禁止在任何指令中將 `nul` 作為輸出目標
- 要抑制輸出請改用：`| Out-Null`（PowerShell）或 `> /dev/null`（bash）或直接不重導向
- 要丟棄 stderr 請用 `2>/dev/null`（bash）或 `2>$null`（PowerShell）

> **機器強制**：此規則已由 `hooks/pre_bash_guard.py` 和 `hooks/pre_write_guard.py` 在 runtime 攔截。
> Agent 即使違反，工具呼叫也會被 block，並記錄到結構化日誌。

## 常用操作
```powershell
# 手動執行每日摘要（單一模式）
powershell -ExecutionPolicy Bypass -File run-agent.ps1

# 手動執行每日摘要（團隊並行模式，推薦）
powershell -ExecutionPolicy Bypass -File run-agent-team.ps1

# 手動執行 Todoist 任務規劃
powershell -ExecutionPolicy Bypass -File run-todoist-agent.ps1

# 設定排程（可自訂時間）
.\setup-scheduler.ps1 -Time "08:00"

# 查看排程狀態
schtasks /query /tn ClaudeDailyDigest /v

# 查看系統健康度（快速一覽）
powershell -ExecutionPolicy Bypass -File check-health.ps1

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
python3 hooks/query_logs.py                     # 今日摘要
python3 hooks/query_logs.py --days 7             # 近 7 天
python3 hooks/query_logs.py --blocked            # 攔截事件
python3 hooks/query_logs.py --errors             # 錯誤事件
python3 hooks/query_logs.py --cache-audit        # 快取使用審計
python3 hooks/query_logs.py --sessions --days 7  # Session 健康摘要
```
