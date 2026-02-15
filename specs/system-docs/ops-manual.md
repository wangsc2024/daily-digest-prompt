# 每日摘要 Agent 系統 — 操作手冊

> **文件版本**：1.0
> **最後更新**：2026-02-15
> **系統版本**：Daily Digest Prompt v3（Agent Team 架構）

---

## 目錄

- [1. 文件資訊](#1-文件資訊)
- [2. 系統概覽](#2-系統概覽)
- [3. 環境準備](#3-環境準備)
- [4. 排程管理](#4-排程管理)
- [5. 日常操作](#5-日常操作)
- [6. 配置調整](#6-配置調整)
- [7. 監控與告警](#7-監控與告警)
- [8. 故障排除](#8-故障排除)
- [9. 維護程序](#9-維護程序)
- [10. 附錄](#10-附錄)

---

## 1. 文件資訊

### 1.1 文件目的

本手冊為「每日摘要 Agent 系統」的完整操作指南，涵蓋日常運維、配置變更、監控告警、故障排除及維護程序。所有操作均附有可直接執行的完整指令與預期輸出範例。

### 1.2 適用對象

| 角色 | 使用範圍 |
|------|---------|
| 維運人員 | 排程管理、日常監控、故障排除、日誌查詢 |
| 系統管理者 | 環境部署、配置調整、排程遷移、Token 輪換 |

**前提假設**：讀者具備 PowerShell 7 和 CLI 操作經驗，但不需熟悉專案內部架構。

### 1.3 參考文件

| 文件 | 路徑 | 說明 |
|------|------|------|
| 系統需求文件（SRD） | `specs/system-docs/srd.md` | 功能需求與非功能需求定義（REQ-FUNC-xxx / REQ-NFR-xxx） |
| 系統設計文件（SSD） | `specs/system-docs/ssd.md` | 架構設計與元件定義（COMP-xxx / IF-xxx / DS-xxx） |
| 專案指引 | `CLAUDE.md` | 專案慣例、架構說明、常用指令 |
| 排程定義 | `HEARTBEAT.md` | 宣告式排程元資料 |
| Skill 索引 | `skills/SKILL_INDEX.md` | 13 個 Skill 的速查表與路由引擎 |

---

## 2. 系統概覽

### 2.1 系統功能摘要

每日摘要 Agent 系統是一個透過 Windows 排程器定時執行 Claude Code CLI 的自動化系統。它的核心功能為：

1. **自動彙整**：每日 08:00 自動收集 Todoist 待辦事項、屏東在地新聞（含政策解讀）、AI 技術動態、知識庫回顧、習慣/學習提示及佛學禪語
2. **推播通知**：將結構化摘要透過 ntfy.sh 推送到行動裝置
3. **任務規劃**：每小時（02:00-23:00）自動查詢 Todoist 待辦並執行可由 Agent 處理的任務（單一/團隊雙軌模式，整點與半點交替）
4. **智慧降級**：外部 API 失敗時自動使用快取降級，確保摘要不中斷
5. **行為強制**：Hooks 機器強制層在 runtime 攔截違規操作，自動記錄結構化日誌

**一句話總結**：Windows Scheduler 定時觸發 PowerShell 腳本 -> PowerShell 啟動 Claude Code Agent -> Agent 依 Skill 驅動收集資料 -> 組裝摘要 -> ntfy 推播通知。

### 2.2 外部服務角色速查表

| 服務 | 做什麼 | 需要什麼 | 壞了會怎樣 |
|------|--------|---------|-----------|
| Claude Code CLI | 執行 Agent 邏輯 | `claude` CLI 已安裝（npm） | 完全無法執行，腳本直接失敗 |
| Windows Scheduler | 定時觸發排程 | `schtasks` 已配置 | 不自動執行，需手動觸發 |
| Todoist API | 讀取今日待辦事項 | `TODOIST_API_TOKEN` 環境變數 | 降級使用 `cache/todoist.json`（30 分鐘 TTL） |
| ntfy.sh | 推播摘要通知 | 網路連線 | 無通知但不影響摘要產出 |
| RAG 知識庫 | 知識持久化與查詢 | `localhost:3000` 服務運行 | 跳過知識庫區塊，不影響其他區塊 |
| Cloudflare MCP | 屏東新聞資料 | 網路連線 | 降級使用 `cache/pingtung-news.json`（6 小時 TTL） |
| HN Firebase | AI 技術新聞 | 網路連線 | 降級使用 `cache/hackernews.json`（2 小時 TTL） |
| Gmail API | 郵件讀取（團隊模式） | OAuth 憑證（credentials.json + token.json） | 跳過郵件區塊 |
| GitHub | 版本控制與自動推送 | `git` 已安裝 | 自動推送任務失敗，不影響摘要 |
| Cisco AI Defense | Skills 安全掃描 | `skill-scanner` 已安裝 | 跳過安全審查區塊 |

> **設計原則**（對應 SRD REQ-NFR-001）：除 Claude Code 外，任何單一外部服務故障都不會導致整體系統無法執行。

### 2.3 執行模式說明

本系統提供四種執行模式：

| 模式 | 腳本 | 耗時 | 說明 |
|------|------|------|------|
| 每日摘要（單一模式） | `run-agent.ps1` | 3-4 分鐘 | 單一 Agent 循序執行所有步驟，含自動重試 1 次 |
| **每日摘要（團隊模式）** | `run-agent-team.ps1` | **約 1 分鐘** | **推薦**。Phase 1 並行 5 個 Agent 擷取資料 + Phase 2 組裝 |
| Todoist 任務規劃（單一模式） | `run-todoist-agent.ps1` | 視任務而定 | 30 分鐘超時保護，執行後自動清理 |
| **Todoist 任務規劃（團隊模式）** | `run-todoist-agent-team.ps1` | 視任務而定 | **推薦**。並行模式處理 Todoist 任務 |

**單一模式 vs 團隊模式比較**：

| 面向 | 單一模式 | 團隊模式 |
|------|---------|---------|
| 速度 | 循序執行，較慢 | 並行擷取，快 3-4 倍 |
| 資源消耗 | 1 個 Claude 程序 | Phase 1 最多 5 個 + Phase 2 1 個 |
| 可靠性 | 任何步驟失敗後重試整體 | Phase 1 各自獨立，個別失敗不影響其他 |
| 除錯 | 日誌集中、易追蹤 | 日誌分散（加 `team_` 前綴區分） |
| 推薦場景 | 開發測試、除錯 | **日常排程（預設使用）** |

### 2.4 關鍵路徑與檔案地圖

#### 配置檔案（改了下次排程自動生效）

| 檔案 | 用途 | 對應元件 |
|------|------|---------|
| `config/pipeline.yaml` | 每日摘要管線步驟定義 | COMP-CFG-001 |
| `config/routing.yaml` | Todoist 三層路由規則 | COMP-CFG-002 |
| `config/cache-policy.yaml` | API 快取 TTL 與降級策略 | COMP-CFG-003 |
| `config/frequency-limits.yaml` | 自動任務頻率限制 | COMP-CFG-004 |
| `config/scoring.yaml` | TaskSense 優先級計分 | COMP-CFG-005 |
| `config/notification.yaml` | ntfy 通知配置 | COMP-CFG-006 |
| `config/digest-format.md` | 摘要輸出排版模板 | COMP-CFG-007 |
| `templates/shared/preamble.md` | 共用前言（禁令 + Skill-First） | COMP-TPL-001 |

#### 持久化資料（需備份）

| 檔案 | 用途 | 寫入者 |
|------|------|--------|
| `context/digest-memory.json` | 摘要記憶（連續天數、統計） | Agent |
| `state/scheduler-state.json` | 排程執行記錄（最近 200 筆） | **PowerShell 腳本**（Agent 只讀） |
| `state/todoist-history.json` | Todoist 自動任務歷史 | Agent |
| `context/auto-tasks-today.json` | 自動任務當日頻率追蹤 | Agent |

#### 快取檔案（可安全刪除）

| 檔案 | TTL | 說明 |
|------|-----|------|
| `cache/todoist.json` | 30 分鐘 | Todoist Agent 不使用快取，僅 daily-digest 使用 |
| `cache/pingtung-news.json` | 360 分鐘（6 小時） | 屏東新聞快取 |
| `cache/hackernews.json` | 120 分鐘（2 小時） | HN AI 新聞快取 |
| `cache/knowledge.json` | 60 分鐘（1 小時） | 知識庫查詢快取 |
| `cache/gmail.json` | 30 分鐘 | Gmail 郵件快取 |

#### 日誌檔案（自動清理 7 天）

| 目錄/檔案 | 格式 | 說明 |
|-----------|------|------|
| `logs/*.log` | 純文字 | PowerShell 腳本執行日誌 |
| `logs/team_*.log` | 純文字 | 團隊模式執行日誌 |
| `logs/todoist_*.log` | 純文字 | Todoist Agent 執行日誌 |
| `logs/structured/*.jsonl` | JSONL | Hooks 結構化日誌（自動標籤） |
| `logs/structured/session-summary.jsonl` | JSONL | Session 結束健康摘要 |

---

## 3. 環境準備

### 3.1 前置需求

#### PowerShell 7 (pwsh)

本系統所有腳本均要求 PowerShell 7，不相容 PowerShell 5.1（Start-Job 缺少 `-WorkingDirectory`、`$OutputEncoding` 預設 ASCII）。

**安裝**：
```powershell
winget install Microsoft.PowerShell
```

**驗證**：
```powershell
pwsh --version
```

**預期輸出**：
```
PowerShell 7.4.x
```

#### Claude Code CLI

**安裝**：
```powershell
npm install -g @anthropic-ai/claude-code
```

**驗證**：
```powershell
claude --version
```

**預期輸出**：
```
claude x.x.x
```

#### Python 3.8+

Hooks 系統使用 Python 解析 JSON。

> **重要**：Windows 環境必須使用 `python`（非 `python3`）。Windows Store 安裝的 `python3` 是空殼程式（exit code 49），會導致所有 Hooks 靜默失敗。

**安裝**：從 https://www.python.org/downloads/ 下載安裝，確保勾選「Add to PATH」。

**驗證**：
```powershell
python --version
```

**預期輸出**：
```
Python 3.11.x
```

**驗證非空殼**：
```powershell
python -c "print('OK')"
```

**預期輸出**：
```
OK
```

若輸出為空或 exit code 為 49，代表是 Windows Store 空殼，需移除或重新安裝。

#### curl

Windows 10/11 內建 curl，通常無需額外安裝。

**驗證**：
```powershell
curl --version
```

**預期輸出**（節錄）：
```
curl 8.x.x (Windows) ...
```

### 3.2 環境變數設定

#### TODOIST_API_TOKEN

1. 前往 https://app.todoist.com/app/settings/integrations/developer 取得 API Token
2. 設定環境變數：

```powershell
# 當前 session（臨時）
$env:TODOIST_API_TOKEN = "你的_token_值"

# 永久設定（系統級）
[System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", "你的_token_值", "User")
```

3. 驗證：
```powershell
$env:TODOIST_API_TOKEN.Substring(0, 8) + "..."
```

**預期輸出**：
```
abcdef01...
```

> **注意**（對應 MEMORY.md）：Todoist API 已於 2026-02 遷移至 v1（`/api/v1/`），REST API v2（`/rest/v2/`）回傳 410 Gone。篩選端點為 `/api/v1/tasks/filter?query=`。

#### Gmail OAuth 憑證

1. 在 Google Cloud Console 建立 OAuth 2.0 憑證
2. 下載 `credentials.json` 放至專案 skills/gmail/ 目錄
3. 首次執行授權流程：

```powershell
python skills/gmail/scripts/gmail.py search "newer_than:1d"
```

4. 瀏覽器會開啟授權頁面，完成後自動產生 `token.json`

> **安全提示**：`credentials.json` 和 `token.json` 已被 Hooks 的 `pre_write_guard.py` 列為敏感檔案，Agent 無法覆寫。

### 3.3 外部服務連通性驗證

執行以下指令驗證所有外部服務連通性：

#### Todoist API

```powershell
curl -s -H "Authorization: Bearer $env:TODOIST_API_TOKEN" "https://api.todoist.com/api/v1/tasks/filter?query=today"
```

**預期輸出**（正常）：
```json
{"results":[...],"next_cursor":null}
```

**異常輸出**：
- `{"error":"Forbidden"}` -> Token 無效或過期
- `410 Gone` -> 使用了舊版 v2 端點

#### 知識庫（RAG）

```powershell
curl -s http://localhost:3000/api/health
```

**預期輸出**：
```json
{"status":"ok"}
```

**異常**：連線拒絕 -> 知識庫服務未啟動

#### ntfy 推播

```powershell
curl -d "ops-manual connectivity test" ntfy.sh/wangsc2025
```

**預期輸出**：
```json
{"id":"xxx","time":...,"event":"message",...}
```

手機應收到測試通知。

#### 屏東新聞 MCP

```powershell
curl -s -X POST https://ptnews-mcp.pages.dev/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pingtung_news_latest","arguments":{"count":1}}}'
```

**預期輸出**（正常）：
```json
{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"..."}]}}
```

**異常**：HTTP 521 -> Cloudflare 後端暫時不可用

#### HN Firebase

```powershell
curl -s "https://hacker-news.firebaseio.com/v0/topstories.json?limitToFirst=1&orderBy=%22%24key%22"
```

**預期輸出**：
```json
[12345678]
```

#### Gmail

```powershell
python skills/gmail/scripts/gmail.py search "newer_than:1d"
```

**預期輸出**：
```
Found N messages ...
```

### 3.4 目錄結構初始化

執行腳本時會自動建立必要目錄，但若需手動初始化：

```powershell
$base = "D:\Source\daily-digest-prompt"
@("logs", "logs\structured", "state", "context", "cache", "results") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path "$base\$_" | Out-Null
    Write-Host "OK: $base\$_"
}
```

**預期輸出**：
```
OK: D:\Source\daily-digest-prompt\logs
OK: D:\Source\daily-digest-prompt\logs\structured
OK: D:\Source\daily-digest-prompt\state
OK: D:\Source\daily-digest-prompt\context
OK: D:\Source\daily-digest-prompt\cache
OK: D:\Source\daily-digest-prompt\results
```

### 3.5 Hooks 驗證

Hooks 設定在 `.claude/settings.json`，需驗證四個 Hook 均正常運作。

**驗證 Hook 檔案存在**：
```powershell
@("hooks\pre_bash_guard.py", "hooks\pre_write_guard.py", "hooks\post_tool_logger.py", "hooks\on_stop_alert.py") | ForEach-Object {
    $path = "D:\Source\daily-digest-prompt\$_"
    if (Test-Path $path) { Write-Host "OK: $_" -ForegroundColor Green }
    else { Write-Host "MISSING: $_" -ForegroundColor Red }
}
```

**驗證 Python 可解析 Hook**：
```powershell
python -c "import json, sys; print('Python JSON OK')"
```

**預期輸出**：
```
OK: hooks\pre_bash_guard.py
OK: hooks\pre_write_guard.py
OK: hooks\post_tool_logger.py
OK: hooks\on_stop_alert.py
Python JSON OK
```

**驗證設定檔結構**：
```powershell
Get-Content "D:\Source\daily-digest-prompt\.claude\settings.json" | python -m json.tool
```

若輸出格式化 JSON 即表示設定檔語法正確。若報錯，需檢查 JSON 語法。

---

## 4. 排程管理

### 4.1 Heartbeat 排程總覽

本系統採用**宣告式排程管理**。所有排程定義集中在 `HEARTBEAT.md` 的 YAML frontmatter 中，而非直接操作 Windows Task Scheduler。

**設計理念**：
- 排程定義納入版本控制（Git 追蹤）
- `setup-scheduler.ps1 -FromHeartbeat` 讀取 YAML 並轉換為 Windows 排程任務
- 調整排程時間只需修改 `HEARTBEAT.md`，再重新執行設定工具

**目前排程**（定義於 `HEARTBEAT.md`，對應 SRD §3.6）：

| 排程名稱 | 觸發時間 | 腳本 | 超時 | 重試 | 說明 |
|---------|---------|------|------|------|------|
| `Claude_daily-digest-am` | 每日 08:00 | `run-agent-team.ps1` | 300s | 1 次 | 每日摘要 - 早 |
| `Claude_daily-digest-mid` | 每日 11:15 | `run-agent-team.ps1` | 300s | 1 次 | 每日摘要 - 午 |
| `Claude_daily-digest-pm` | 每日 21:15 | `run-agent-team.ps1` | 300s | 1 次 | 每日摘要 - 晚 |
| `Claude_todoist-single` | 每小時整點 02:00-23:00 | `run-todoist-agent.ps1` | 1800s | 0 次 | Todoist 單一模式 |
| `Claude_todoist-team` | 每小時半點 02:30-23:30 | `run-todoist-agent-team.ps1` | 1200s | 0 次 | Todoist 團隊模式 |

> **雙軌比較**：兩種 Todoist 模式時間錯開 30 分鐘，比較效能與成功率。
> - **single-mode**：一個 claude 完成查詢+執行+通知，CLI 啟動快（~20s）
> - **team-mode**：Phase 1 查詢 → Phase 2 並行執行 → Phase 3 組裝，適合多任務

**YAML 與 Windows Task 的轉換**：

```yaml
# HEARTBEAT.md 定義範例
todoist-single:
    cron: "0 2-23 * * *"       # -> -Daily -At 02:00 + RepetitionInterval 60m
    interval: 60m               # -> RepetitionDuration 21 hours (2-23)
    script: run-todoist-agent.ps1
    timeout: 1800
```

### 4.2 建立排程

#### 從 HEARTBEAT.md 批次建立（推薦）

```powershell
# 需要系統管理員權限
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\setup-scheduler.ps1 -FromHeartbeat
```

**預期輸出**：
```
從 HEARTBEAT.md 讀取到 5 個排程：
  - Claude_daily-digest-am | 08:00 | run-agent-team.ps1 | 每日摘要 - 早
    OK 已建立
  - Claude_daily-digest-mid | 11:15 | run-agent-team.ps1 | 每日摘要 - 午
    OK 已建立
  - Claude_daily-digest-pm | 21:15 | run-agent-team.ps1 | 每日摘要 - 晚
    OK 已建立
  - Claude_todoist-single | 02:00 | run-todoist-agent.ps1 | Todoist 單一模式
    間隔模式：每 60 分鐘，持續 21 小時
    OK 已建立
  - Claude_todoist-team | 02:30 | run-todoist-agent-team.ps1 | Todoist 團隊模式
    間隔模式：每 60 分鐘，持續 21 小時
    OK 已建立

全部完成！
```

#### 手動指定單一排程

```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\setup-scheduler.ps1 -Time "08:00" -TaskName "ClaudeDailyDigest" -Script "run-agent-team.ps1"
```

**預期輸出**：
```
OK 排程建立成功！
   名稱: ClaudeDailyDigest
   時間: 每天 08:00
   腳本: D:\Source\daily-digest-prompt\run-agent-team.ps1
```

### 4.3 查看、修改、刪除排程

**查看所有 Claude 排程**：
```powershell
schtasks /query /tn Claude* /v /fo list
```

**預期輸出**（節錄）：
```
HostName:      DESKTOP-XXXX
TaskName:      \Claude_daily-digest
Status:        Ready
Trigger:       每日 08:00
Next Run Time: 2026-02-16 08:00:00
Last Run Time: 2026-02-15 08:00:00
Last Result:   0
```

**手動觸發排程（測試用）**：
```powershell
schtasks /run /tn Claude_daily-digest
```

**刪除排程**：
```powershell
schtasks /delete /tn Claude_daily-digest /f
```

**修改排程時間**：無法直接修改，需先刪除再重建，或修改 `HEARTBEAT.md` 後重新執行 `-FromHeartbeat`。

### 4.4 排程時間調整建議

| 排程 | 建議時間 | 理由 |
|------|---------|------|
| daily-digest-am | 07:30-08:30 | 早晨起床前完成，開啟一天時收到通知 |
| daily-digest-mid | 11:00-12:00 | 午間更新，掌握上午新變化 |
| daily-digest-pm | 21:00-22:00 | 晚間回顧，總結當日資訊 |
| todoist-single | 02:00-23:00 整點 | 全天覆蓋，單一模式穩定性高 |
| todoist-team | 02:30-23:30 半點 | 與單一模式錯開，團隊模式適合多任務 |

**雙軌策略**：兩種 Todoist 模式錯開 30 分鐘並行運行，可比較效能與成功率。

> **注意**：排程設定包含 `-StartWhenAvailable`，若電腦關機期間錯過排程，開機後會自動補執行。

---

## 5. 日常操作

### 5.1 手動執行每日摘要

#### 團隊並行模式（推薦）

```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\run-agent-team.ps1
```

**預期輸出**：
```
=== Agent Team start: 2026-02-15 08:00:01 ===
Mode: parallel (Phase 1 x5 + Phase 2 x1)

=== Phase 1: Parallel fetch start ===
[Phase1] Started: todoist (Job 1)
[Phase1] Started: news (Job 2)
[Phase1] Started: hackernews (Job 3)
[Phase1] Started: gmail (Job 4)
[Phase1] Started: security (Job 5)
[Phase1] Waiting for 5 agents (timeout: 180s)...
[Phase1] todoist OK: status=success, source=api
[Phase1] news OK: status=success, source=api
[Phase1] hackernews OK: status=success, source=api
[Phase1] gmail OK: status=success, source=api
[Phase1] security OK: status=success, source=scan

=== Phase 1 complete (45s) ===
Results: todoist=success | news=success | hackernews=success | gmail=success | security=success

=== Phase 2: Assembly start ===
[Phase2] Running assembly agent (attempt 1)...
  [assemble] ... (Agent 輸出)
[Phase2] Assembly completed (30s)

=== Agent Team done (success): 2026-02-15 08:01:16 ===
Total: 75s (Phase1: 45s)
```

#### 單一模式（備用）

```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\run-agent.ps1
```

**預期輸出**：
```
=== Claude Agent start: 2026-02-15 08:00:01 ===
--- calling Claude Code (attempt 1) ---
... (Agent 循序執行各步驟)
=== done (success): 2026-02-15 08:03:45 ===
```

### 5.2 手動執行 Todoist 任務規劃

#### 團隊模式（推薦）

```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\run-todoist-agent-team.ps1
```

#### 單一模式

```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\run-todoist-agent.ps1
```

**預期輸出**：
```
=== Todoist Agent start: 2026-02-15 09:00:01 ===
--- calling Claude Code (timeout: 1800s) ---
... (Agent 查詢 Todoist、路由任務、執行任務)
=== done (success): 2026-02-15 09:05:30 ===
```

**注意事項**：
- Todoist Agent 有 30 分鐘超時保護（`$MaxDurationSeconds = 1800`）
- 超時後會強制終止並記錄 `timeout` 狀態
- 每次最多執行 2 項任務（定義在 `config/scoring.yaml` 的 `max_tasks_per_run: 2`）

### 5.3 健康狀態檢查

```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\check-health.ps1
```

**預期輸出**：
```
========================================
  Claude Agent Health Report
  2026-02-15 10:00:00
========================================

[排程狀態]
  近 7 天執行次數: 42
  成功率: 95.2%
  平均耗時: 85 秒
  最近失敗: 無
  上次執行: 2026-02-15T00:01:30 (success)

  [近期執行記錄]
  時間                  | 狀態    | 耗時   | 錯誤
  ----------------------|---------|--------|------
  2026-02-15T00:01:30   | success | 75s    | -
  2026-02-14T22:00:30   | success | 120s   | -
  ...

[記憶狀態]
  連續執行: 15 次
  上次執行: 2026-02-15
  習慣提示連續: 15 天
  學習技巧連續: 15 天

[快取狀態]
  todoist.json: 2.1KB, 120 分鐘前更新 (有效)
  pingtung-news.json: 15.3KB, 45 分鐘前更新 (新鮮)
  hackernews.json: 8.7KB, 90 分鐘前更新 (有效)
  knowledge.json: 3.2KB, 30 分鐘前更新 (新鮮)

[日誌分析]
  近 7 天日誌數量: 42
  問題統計: 無問題發現

========================================
```

**指標解讀**：

| 指標 | 正常 | 注意 | 異常 |
|------|------|------|------|
| 成功率 | >= 90%（綠色） | 70-90%（黃色） | < 70%（紅色） |
| 平均耗時 | < 120s | 120-300s | > 300s |
| 快取狀態 | 新鮮/有效 | - | 過期（紅色） |
| 問題統計 | 無問題 | WARN > 0 | ERROR > 0 |

### 5.4 執行成果查詢

`query-logs.ps1` 提供五種查詢模式：

#### 近 7 天摘要（預設）

```powershell
.\query-logs.ps1
```

**預期輸出**：
```
========================================
  排程執行成果摘要（近 7 天）
========================================

[總覽]
  執行次數: 42
  成功率:   95.2%
  平均耗時: 85 秒

[按 Agent 分類]
  Agent               | 執行 | 成功 | 失敗 | 成功率 | 平均耗時
  --------------------|------|------|------|--------|--------
  daily-digest-team   | 7    | 7    | 0    | 100%   | 75s
  todoist             | 35   | 33   | 2    | 94.3%  | 88s
```

#### 按 Agent 篩選

```powershell
.\query-logs.ps1 -Days 3 -Agent todoist
```

#### 特定日期詳情

```powershell
.\query-logs.ps1 -Mode detail -Date 2026-02-12
```

**預期輸出**：
```
========================================
  執行詳情: 2026-02-12
========================================

[時間線]
  08:00 daily-digest-team     success  75s    todoist=ok news=ok hackernews=ok gmail=ok security=ok
  09:00 todoist                success  120s
  10:00 todoist                success  95s
  ...
```

#### 錯誤彙總

```powershell
.\query-logs.ps1 -Mode errors
```

#### Todoist 自動任務歷史

```powershell
.\query-logs.ps1 -Mode todoist
```

**預期輸出**：
```
========================================
  Todoist Agent 執行歷史（近 7 天）
========================================

[執行統計]
  執行次數: 35 | 成功: 33 | 成功率: 94.3%

[自動任務明細]
  楞嚴經研究: 15 次（成功 14）
  系統 Log 審查: 5 次（成功 5）
  Git Push: 8 次（成功 7）

  研究主題:
    - 五十陰魔 (3 次)
    - 楞嚴咒功德 (2 次)
    ...

[每日摘要]
  日期       | 楞嚴經 | Log審查 | Git Push | 完成任務 | 執行次數
  -----------|--------|---------|----------|----------|--------
  2026-02-15 | 2/3    | 1/1     | 1/2      | 3        | 8
  2026-02-14 | 3/3    | 1/1     | 2/2      | 5        | 14
  ...
```

#### 趨勢分析

```powershell
.\query-logs.ps1 -Mode trend -Days 14
```

#### JSON 輸出（供程式處理）

```powershell
.\query-logs.ps1 -Mode summary -Format json
```

### 5.5 結構化日誌查詢

Hooks 產生的 JSONL 日誌提供更細粒度的分析：

```bash
# 今日摘要
python hooks/query_logs.py

# 近 7 天
python hooks/query_logs.py --days 7

# 僅攔截事件
python hooks/query_logs.py --blocked

# 僅錯誤事件
python hooks/query_logs.py --errors

# 快取使用審計
python hooks/query_logs.py --cache-audit

# Session 健康摘要
python hooks/query_logs.py --sessions --days 7

# JSON 輸出
python hooks/query_logs.py --format json
```

**快取審計輸出範例**：
```
  [快取審計]
    來源              API呼叫   快取讀取   快取寫入     狀態
    --------------- -------- -------- -------- --------
    todoist                1        1        1     正常
    pingtung-news          1        1        1     正常
    hackernews             1        1        1     正常
    knowledge              2        2        0     正常
    gmail                  1        0        0     繞過!
```

> **「繞過!」**表示 API 呼叫前未先查快取，違反 Skill-First 原則（對應 SRD REQ-NFR-003）。

### 5.6 Skills 安全掃描

```powershell
# 快速總覽（預設）
.\scan-skills.ps1

# 完整 Markdown 報告 + 行為分析
.\scan-skills.ps1 -Format markdown -UseBehavioral

# JSON 輸出
.\scan-skills.ps1 -Format json

# 掃描單一 Skill
.\scan-skills.ps1 -SkillName todoist

# CI 模式（有風險則失敗）
.\scan-skills.ps1 -FailOnFindings
```

**預期輸出**（正常）：
```
========================================
  Skill Security Scanner Report
  2026-02-15 10:00:00
========================================

[Scanning all skills] D:\Source\daily-digest-prompt\skills
... (掃描結果)

========================================
  Result: ALL CLEAR
========================================
```

**前提**：需安裝 `skill-scanner`：
```powershell
uv pip install cisco-ai-skill-scanner --python D:/Python311/python.exe
```

---

## 6. 配置調整

### 6.1 配置變更總覽 — 文件中心制的實務意義

本系統採用**文件驅動架構**。核心原則：

> **改配置不改 Prompt**：所有可變邏輯都抽入結構化配置文件（YAML/Markdown），Prompt 只是薄層調度器。

**實務意義**：
- 修改配置後**無需重啟、無需部署**，下次排程觸發時自動載入新配置
- 配置文件由 Agent 在執行時動態讀取（`Read` 工具）
- 多人協作時，配置變更可透過 Git PR 審核

**配置文件速查表**：

| 配置文件 | 修改目的 | 引用者 | 對應 SSD |
|---------|---------|--------|---------|
| `config/pipeline.yaml` | 調整摘要步驟順序/新增步驟 | daily-digest-prompt.md | COMP-CFG-001 |
| `config/routing.yaml` | 調整任務路由規則/新增標籤 | hour-todoist-prompt.md | COMP-CFG-002 |
| `config/cache-policy.yaml` | 調整快取 TTL/降級策略 | 所有使用 API 的 Agent | COMP-CFG-003 |
| `config/frequency-limits.yaml` | 調整自動任務每日上限 | hour-todoist-prompt.md | COMP-CFG-004 |
| `config/scoring.yaml` | 調整任務優先級計分/每次上限 | hour-todoist-prompt.md | COMP-CFG-005 |
| `config/notification.yaml` | 調整通知 topic/tags/模板 | 所有有通知需求的 Agent | COMP-CFG-006 |
| `config/digest-format.md` | 調整摘要排版格式 | daily-digest-prompt.md, assemble-digest.md | COMP-CFG-007 |

### 6.2 管線配置（pipeline.yaml）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\pipeline.yaml`

**可調整欄位**：

| 欄位 | 說明 | 範例 |
|------|------|------|
| `steps[].id` | 步驟識別碼 | `todoist`, `news`, `hackernews` |
| `steps[].name` | 步驟描述（Agent 參考用） | `"查詢 Todoist 今日待辦"` |
| `steps[].skills` | 該步驟使用的 Skill | `[todoist, api-cache]` |
| `steps[].cache_key` | 快取鍵名（對應 cache-policy.yaml） | `todoist` |
| `steps[].required` | 是否必要（true 表示不可跳過） | `true` |
| `finalize[].action` | 收尾動作 | `compile_digest`, `send_notification` |

**修改範例：新增一個步驟**

修改前：
```yaml
steps:
  - id: zen
    name: "生成佛學禪語"
    skills: []
    output_section: "佛學禪語"
```

修改後（在 zen 後面新增天氣步驟）：
```yaml
steps:
  - id: zen
    name: "生成佛學禪語"
    skills: []
    output_section: "佛學禪語"

  - id: weather
    name: "查詢屏東天氣"
    skills: [api-cache]
    cache_key: weather
    output_section: "今日天氣"
```

**注意事項**：
- 新增步驟需在 `config/cache-policy.yaml` 同步新增對應的快取設定
- 步驟順序即執行順序，可透過調整 YAML 順序來改變
- `required: true` 的步驟失敗會影響整體驗證

### 6.3 路由配置（routing.yaml）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\routing.yaml`

**三層路由架構**：

| 層級 | 信心度 | 觸發條件 | 說明 |
|------|--------|---------|------|
| Tier 1：標籤路由 | 100% | Todoist 標籤（@code, @research 等） | 最高優先，直接映射 Skill |
| Tier 2：關鍵字路由 | 80% | 任務內容含特定關鍵字 | 比對 SKILL_INDEX 觸發詞 |
| Tier 3：語義路由 | 60% | LLM 分析任務描述 | 最低優先，兜底處理 |

**修改範例：新增標籤路由**

修改前：
```yaml
label_routing:
  mappings:
    "@code":
      skills: ["程式開發（Plan-Then-Execute）"]
      allowed_tools: "Read,Bash,Write,Edit,Glob,Grep"
      template: "templates/sub-agent/code-task.md"
```

修改後（新增 @learn 標籤）：
```yaml
label_routing:
  mappings:
    "@code":
      skills: ["程式開發（Plan-Then-Execute）"]
      allowed_tools: "Read,Bash,Write,Edit,Glob,Grep"
      template: "templates/sub-agent/code-task.md"
    "@learn":
      skills: ["learning-mastery", "knowledge-query"]
      allowed_tools: "Read,Bash,Write,WebSearch,WebFetch"
      template: "templates/sub-agent/research-task.md"
```

**注意事項**：
- `pre_filter.exclude_categories` 定義的類型（實體行動、人際互動等）優先於所有路由層
- 新增標籤後需在 Todoist 中對應設定
- `template` 路徑指向 `templates/sub-agent/` 下的模板檔案

### 6.4 快取策略（cache-policy.yaml）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\cache-policy.yaml`

**可調整欄位**：

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `sources.<name>.ttl_minutes` | 快取有效期（分鐘） | 依來源不同 |
| `degradation_max_age_hours` | 降級使用過期快取的最大時效 | 24 小時 |

**修改範例：延長屏東新聞快取 TTL**

修改前：
```yaml
sources:
  pingtung-news:
    file: "cache/pingtung-news.json"
    ttl_minutes: 360  # 6 小時
```

修改後：
```yaml
sources:
  pingtung-news:
    file: "cache/pingtung-news.json"
    ttl_minutes: 720  # 12 小時
```

**注意事項**：
- TTL 過短會增加 API 呼叫次數，過長會導致資料陳舊
- `degradation_max_age_hours: 24` 表示 API 故障時最多使用 24 小時前的快取
- Todoist Agent 不使用快取（需即時資料），僅 daily-digest 使用

### 6.5 自動任務頻率限制（frequency-limits.yaml）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\frequency-limits.yaml`

**可調整欄位**：

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `tasks.shurangama.daily_limit` | 楞嚴經研究每日上限 | 3 |
| `tasks.log_audit.daily_limit` | 系統 Log 審查每日上限 | 1 |
| `tasks.git_push.daily_limit` | Git Push 每日上限 | 2 |
| `history.max_auto_tasks` | 歷史記錄陣列上限 | 200 |

**修改範例：增加楞嚴經研究上限**

修改前：
```yaml
tasks:
  shurangama:
    name: "楞嚴經研究"
    daily_limit: 3
```

修改後：
```yaml
tasks:
  shurangama:
    name: "楞嚴經研究"
    daily_limit: 5
```

**注意事項**：
- 頻率追蹤檔 `context/auto-tasks-today.json` 每日自動歸零
- 全部達上限時直接跳到通知步驟
- 歸零邏輯：`date` 欄位不等於今天時自動重置所有計數

### 6.6 優先級計分（scoring.yaml）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\scoring.yaml`

**計分公式**：`綜合分數 = Todoist 優先級分 * 信心度乘數 * 描述加成`

**可調整欄位**：

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `max_tasks_per_run` | 每次最多執行任務數 | 2 |
| `priority_scores` | Todoist 優先級對應分數 | p1=4, p2=3, p3=2, p4=1 |
| `confidence_multipliers` | 路由層級信心度乘數 | tier1=1.0, tier2=0.8, tier3=0.6 |
| `description_bonus` | 有描述欄位的加成 | 有=1.2, 無=1.0 |

**修改範例：每次最多處理 3 項任務**

修改前：
```yaml
max_tasks_per_run: 2
```

修改後：
```yaml
max_tasks_per_run: 3
```

**注意事項**：
- 增加 `max_tasks_per_run` 會延長 Agent 單次執行時間，注意 Todoist Agent 有 30 分鐘超時
- 計分結果決定任務執行順序，高分優先

### 6.7 通知配置（notification.yaml）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\notification.yaml`

**可調整欄位**：

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `default_topic` | ntfy 推播目標 | `wangsc2025` |
| `service_url` | ntfy 服務 URL | `https://ntfy.sh` |
| `max_message_length` | 訊息最大長度 | 500 |
| `tag_mappings` | 各場景的通知標籤 | 見配置檔案 |

**修改範例：變更推播目標**

修改前：
```yaml
default_topic: "wangsc2025"
```

修改後：
```yaml
default_topic: "my-new-topic"
```

**注意事項**：
- Windows 環境必須用 JSON 檔案方式發送通知，不可用 inline JSON 字串（會亂碼）
- 必須加 `charset=utf-8` header
- 修改 topic 後，Hooks 的 `on_stop_alert.py` 中的 `NTFY_TOPIC` 也需同步修改（硬編碼）

### 6.8 摘要格式（digest-format.md）

**檔案路徑**：`D:\Source\daily-digest-prompt\config\digest-format.md`

此檔案定義摘要的各區塊排版模板，Agent 依此格式組裝最終輸出。

**可調整內容**：
- 區塊順序（對應 pipeline.yaml 的步驟）
- 區塊標題和圖示
- 各區塊的顯示欄位

**修改範例：調整區塊順序**

將「今日待辦」移到「AI 技術動態」之後：只需調整 Markdown 中區塊的排列順序即可。

**注意事項**：
- 此檔案僅影響輸出排版，不影響資料擷取邏輯
- Agent 讀取此檔案後會將實際資料替換描述文字

---

## 7. 監控與告警

### 7.1 Harness 自動告警機制

系統透過 `hooks/on_stop_alert.py` 在每個 Agent session 結束時自動執行健康檢查。此機制屬於 Harness 強制層（對應 SSD COMP-HOOK-004），不依賴 Agent 自律。

**運作流程**：

```
Agent session 結束
    |
    v
on_stop_alert.py 啟動
    |
    v
讀取今日結構化日誌（logs/structured/YYYY-MM-DD.jsonl）
    |-- 使用 offset 追蹤，僅分析本次 session 新增的日誌
    |
    v
分析項目：
    |-- 統計 blocked 事件（違規攔截）
    |-- 統計 error 事件（工具錯誤）
    |-- 偵測 cache bypass（API 呼叫未先查快取）
    |
    v
判定嚴重度
    |-- critical: blocked >= 3 OR errors >= 5
    |-- warning:  blocked 1-2 OR errors 1-4 OR cache bypass
    |-- info:     全部正常（不告警）
    |
    v
若 warning/critical -> 發送 ntfy 告警
    |
    v
寫入 session-summary.jsonl
```

**告警嚴重度判定**：

| 條件 | 嚴重度 | ntfy 優先級 | 標籤 |
|------|--------|-----------|------|
| blocked 事件 >= 3 | critical | 5（最高） | rotating_light, shield |
| errors >= 5 | critical | 5 | rotating_light, shield |
| blocked 事件 1-2 | warning | 4 | warning, shield |
| errors 1-4 | warning | 4 | warning, shield |
| cache bypass 偵測到 | warning | 4 | warning, shield |
| 全部正常 | info（不告警） | - | - |

**告警內容格式範例**：

```
標題: Harness 嚴重警告
內容:
工具呼叫: 45 | API: 5 | 快取讀取: 3 | 錯誤: 6 | 攔截: 2

攔截 2 次違規操作:
  - 禁止 nul 重導向（會建立 nul 實體檔案）。請改用 > /dev/null 2>&1 (x1)
  - 禁止 Agent 寫入 scheduler-state.json（此檔案由 PowerShell 腳本維護） (x1)

偵測到 6 次工具錯誤:
  - Bash (x4)
  - Read (x2)

快取繞過警告 (未先查快取): gmail
```

### 7.2 監控指標

| 指標 | 正常範圍 | 注意範圍 | 異常範圍 | 查看方式 |
|------|---------|---------|---------|---------|
| 成功率 | > 90% | 70-90% | < 70% | `check-health.ps1` |
| 平均耗時 | < 120s | 120-300s | > 300s | `check-health.ps1` |
| 快取命中率 | > 50% | 20-50% | < 20% | `python hooks/query_logs.py --cache-audit` |
| 攔截次數 | 0 | 1-2 | >= 3 | `python hooks/query_logs.py --blocked` |
| 錯誤事件 | 0 | 1-4 | >= 5 | `python hooks/query_logs.py --errors` |
| 連續執行天數 | 持續增加 | - | 突然歸零 | `check-health.ps1`（記憶狀態） |
| 日誌量 | 穩定 | - | 突增（可能迴圈） | `python hooks/query_logs.py --days 7` |

### 7.3 告警處理 SOP

#### Critical 告警回應流程

1. **確認告警內容**：檢視 ntfy 通知中的攔截詳情與錯誤摘要
2. **查看結構化日誌**：
   ```bash
   python hooks/query_logs.py --blocked
   python hooks/query_logs.py --errors
   ```
3. **判斷影響範圍**：
   - blocked 事件：Agent 嘗試了什麼違規操作？是否影響資料完整性？
   - errors >= 5：哪些工具失敗？是否為外部服務問題？
4. **執行修復**：
   - 外部服務問題 -> 參照 [8.2 外部服務連線問題](#82-外部服務連線問題)
   - Agent 行為異常 -> 檢查對應 Prompt 和 SKILL.md 是否被修改
5. **驗證修復**：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File check-health.ps1
   ```
6. **手動重跑**（如有必要）：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1
   ```

#### Warning 告警回應流程

1. **確認告警類型**：cache bypass 通常為最常見的 warning
2. **查看快取審計**：
   ```bash
   python hooks/query_logs.py --cache-audit
   ```
3. **評估嚴重度**：
   - 偶發一次 cache bypass -> 記錄觀察，無需立即處理
   - 連續多次 -> 檢查對應 SKILL.md 是否遺漏快取流程
4. **下次巡檢時追蹤**

### 7.4 主動巡檢清單

#### 每日巡檢（建議 09:00 後）

- [ ] 執行 `check-health.ps1` 確認成功率和最近失敗
- [ ] 檢查手機是否收到今日摘要通知
- [ ] 若有失敗記錄，查看對應日誌：
  ```powershell
  Get-Content (Get-ChildItem D:\Source\daily-digest-prompt\logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
  ```
- [ ] 檢查是否有 `nul` 檔案產生：
  ```powershell
  Get-ChildItem D:\Source\daily-digest-prompt -Filter "nul" -Recurse -ErrorAction SilentlyContinue
  ```

#### 每週巡檢（建議週一）

- [ ] 趨勢分析：
  ```powershell
  .\query-logs.ps1 -Mode trend -Days 14
  ```
- [ ] Skills 安全掃描：
  ```powershell
  .\scan-skills.ps1 -Format markdown -UseBehavioral
  ```
- [ ] 快取審計：
  ```bash
  python hooks/query_logs.py --cache-audit --days 7
  ```
- [ ] Session 健康摘要：
  ```bash
  python hooks/query_logs.py --sessions --days 7
  ```
- [ ] 確認日誌自動清理正常（logs/ 目錄不應有 7 天前的 .log 檔案）：
  ```powershell
  Get-ChildItem D:\Source\daily-digest-prompt\logs\*.log | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
  ```
  預期輸出應為空。

---

## 8. 故障排除

### 8.1 Agent 執行失敗

#### 問題：claude not found

- **可能原因**：Claude Code CLI 未安裝或未加入 PATH
- **排查步驟**：
  1. 確認安裝狀態：
     ```powershell
     npm list -g @anthropic-ai/claude-code
     ```
  2. 確認 PATH：
     ```powershell
     Get-Command claude -ErrorAction SilentlyContinue
     ```
- **解決方案**：
  ```powershell
  npm install -g @anthropic-ai/claude-code
  ```
- **預防措施**：將 npm global bin 目錄加入系統 PATH

#### 問題：prompt file not found

- **可能原因**：Prompt 檔案被移動或重新命名
- **排查步驟**：
  1. 確認檔案存在：
     ```powershell
     Test-Path D:\Source\daily-digest-prompt\daily-digest-prompt.md
     Test-Path D:\Source\daily-digest-prompt\hour-todoist-prompt.md
     ```
  2. 檢查腳本中的路徑設定是否正確
- **解決方案**：還原檔案或修正腳本中的 `$PromptFile` 路徑
- **預防措施**：Prompt 檔案重新命名後同步更新對應的 .ps1 腳本

#### 問題：exit code 非 0

- **可能原因**：Agent 內部錯誤（API 呼叫失敗、Skill 讀取失敗等）
- **排查步驟**：
  1. 查看最近日誌：
     ```powershell
     Get-Content (Get-ChildItem D:\Source\daily-digest-prompt\logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | Select-String "ERROR|WARN|FAIL"
     ```
  2. 查看結構化日誌中的錯誤：
     ```bash
     python hooks/query_logs.py --errors
     ```
  3. 確認外部服務連通性（參照 [3.3 外部服務連通性驗證](#33-外部服務連通性驗證)）
- **解決方案**：根據錯誤類型修復（外部服務問題/配置錯誤/Skill 問題）
- **預防措施**：定期執行健康檢查

#### 問題：timeout（超過 30 分鐘）

- **可能原因**：Agent 陷入迴圈或外部 API 極慢回應
- **排查步驟**：
  1. 查看日誌中的超時記錄：
     ```powershell
     .\query-logs.ps1 -Mode errors
     ```
  2. 確認 `state/scheduler-state.json` 中是否有 `"status": "timeout"` 記錄
  3. 查看結構化日誌中的工具呼叫數量（判斷是否迴圈）：
     ```bash
     python hooks/query_logs.py
     ```
- **解決方案**：
  - 外部 API 慢 -> 快取降級會自動處理
  - Agent 迴圈 -> 檢查對應 Prompt 邏輯是否有遞迴
  - 超時保護已內建於 `run-todoist-agent.ps1`（`$MaxDurationSeconds = 1800`）
- **預防措施**：監控趨勢分析中的平均耗時，異常升高時主動排查

### 8.2 外部服務連線問題

#### 8.2.1 Todoist 401 Unauthorized / 410 Gone / 429 Rate Limit

##### 問題：401 Unauthorized

- **可能原因**：TODOIST_API_TOKEN 無效或過期
- **排查步驟**：
  1. 驗證 Token：
     ```powershell
     curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $env:TODOIST_API_TOKEN" "https://api.todoist.com/api/v1/tasks/filter?query=today"
     ```
  2. 預期回傳 `200`，若為 `401` 表示 Token 無效
- **解決方案**：前往 Todoist Settings > Integrations > Developer 重新取得 Token，更新環境變數
- **預防措施**：Token 設定在系統級環境變數中，避免 session 遺失

##### 問題：410 Gone

- **可能原因**：使用了已棄用的 REST API v2 端點
- **排查步驟**：
  1. 確認 Skill 中使用的端點：
     ```bash
     python hooks/query_logs.py --tag todoist
     ```
  2. 搜尋日誌中是否有 `/rest/v2/` 呼叫
- **解決方案**：
  - 正確端點：`https://api.todoist.com/api/v1/tasks/filter?query=today`
  - 錯誤端點：`https://api.todoist.com/rest/v2/tasks?filter=today`（已棄用）
  - 更新 `skills/todoist/SKILL.md` 中的端點
- **預防措施**：SKILL.md 已更新為 v1 端點。若手動修改請確認使用 `/api/v1/`

##### 問題：429 Rate Limit

- **可能原因**：短時間內呼叫次數過多
- **排查步驟**：
  ```bash
  python hooks/query_logs.py --tag todoist --days 1
  ```
- **解決方案**：等待限速解除（通常 1 分鐘），快取機制會自動降級
- **預防措施**：確保 `config/cache-policy.yaml` 中 Todoist TTL 設定合理（預設 30 分鐘）

#### 8.2.2 屏東新聞 MCP 521 Web Server Down

- **可能原因**：Cloudflare Workers 後端暫時不可用
- **排查步驟**：
  1. 手動測試：
     ```powershell
     curl -s -o /dev/null -w "%{http_code}" -X POST https://ptnews-mcp.pages.dev/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pingtung_news_latest","arguments":{"count":1}}}'
     ```
  2. 預期 `200`，若為 `521` 表示後端不可用
- **解決方案**：
  - 系統自動降級使用 `cache/pingtung-news.json`（6 小時 TTL）
  - 若快取也過期（超過 24 小時），該區塊會被跳過
  - 通常等待 5-30 分鐘後恢復
- **預防措施**：確保快取 TTL 足夠覆蓋服務中斷時間

#### 8.2.3 知識庫 localhost:3000 無回應

- **可能原因**：知識庫服務未啟動
- **排查步驟**：
  1. 測試連通性：
     ```powershell
     curl -s http://localhost:3000/api/health
     ```
  2. 檢查服務是否運行（依知識庫部署方式確認程序是否存在）
- **解決方案**：
  - 啟動知識庫服務
  - 若短時間無法恢復，系統會自動跳過知識庫相關區塊
- **預防措施**：將知識庫設為開機自動啟動服務

#### 8.2.4 ntfy 推播失敗

##### 中文亂碼

- **可能原因**：未使用 JSON 檔案方式發送或缺少 `charset=utf-8`
- **排查步驟**：
  1. 檢查日誌中 ntfy 相關操作：
     ```bash
     python hooks/query_logs.py --tag ntfy
     ```
  2. 確認是否使用 `@file.json` 方式發送
- **解決方案**（正確的發送流程）：
  1. 用 Write 工具建立 `ntfy_temp.json`（確保 UTF-8 編碼）
  2. 用 `curl -H "Content-Type: application/json; charset=utf-8" -d @ntfy_temp.json https://ntfy.sh` 發送
  3. 發送後刪除暫存檔
- **預防措施**：此流程定義在 `config/notification.yaml` 的 `send_steps`，Agent 依此執行

##### 網路問題

- **可能原因**：無法連線到 ntfy.sh
- **排查步驟**：
  ```powershell
  curl -s -o /dev/null -w "%{http_code}" https://ntfy.sh
  ```
- **解決方案**：ntfy 失敗不影響摘要產出，等待網路恢復即可
- **預防措施**：無（ntfy 為外部服務，設計為可容忍失敗）

#### 8.2.5 Gmail 認證過期

- **可能原因**：OAuth token 過期（通常 7 天）
- **排查步驟**：
  ```powershell
  python skills/gmail/scripts/gmail.py search "newer_than:1d"
  ```
  若出現 `Token has been expired or revoked` 錯誤
- **解決方案**：
  1. 刪除 `token.json`
  2. 重新執行授權流程：
     ```powershell
     python skills/gmail/scripts/gmail.py search "newer_than:1d"
     ```
  3. 在瀏覽器完成 OAuth 授權
- **預防措施**：token.json 有 refresh_token 會自動更新，若仍過期表示 refresh_token 也失效

#### 8.2.6 HN Firebase API 異常

- **可能原因**：Firebase API 暫時不可用或回應格式變更
- **排查步驟**：
  ```powershell
  curl -s "https://hacker-news.firebaseio.com/v0/topstories.json?limitToFirst=5&orderBy=%22%24key%22"
  ```
- **解決方案**：系統自動降級使用 `cache/hackernews.json`（2 小時 TTL）
- **預防措施**：確保快取 TTL 設定合理

### 8.3 編碼問題

#### 問題：ntfy 中文亂碼

- **可能原因**：直接用 Bash echo 或 inline JSON 傳送中文字串
- **排查步驟**：
  1. 查看日誌中 ntfy 呼叫是否使用 `@file.json`：
     ```bash
     python hooks/query_logs.py --tag ntfy
     ```
- **解決方案**：
  - 必須用 Write 工具建立 JSON 檔案（自動 UTF-8 編碼）
  - 必須加 `charset=utf-8` header
  - 此規則定義在 `config/notification.yaml` 的 `send_steps`
- **預防措施**：SKILL.md 和配置檔案已明確定義正確流程

#### 問題：python3 空殼問題

- **可能原因**：Windows Store 安裝的 `python3` 是空殼（exit code 49）
- **排查步驟**：
  ```powershell
  python3 -c "print('test')"
  # 若無輸出或 exit code 49 -> 空殼

  python -c "print('test')"
  # 應輸出 "test" -> 正常
  ```
- **解決方案**：
  - `.claude/settings.json` 中的 Hooks 指令已改用 `python`（非 `python3`）
  - 若仍有問題，在「設定 > 應用程式 > 應用程式執行別名」中停用 `python3.exe`
- **預防措施**：所有 Hook 設定統一使用 `python`

#### 問題：PowerShell 5.1 Start-Job 缺陷

- **可能原因**：使用 PowerShell 5.1 而非 7，Start-Job 缺少 `-WorkingDirectory` 參數
- **排查步驟**：
  ```powershell
  $PSVersionTable.PSVersion
  ```
  若 Major < 7 -> 不相容
- **解決方案**：升級到 PowerShell 7：
  ```powershell
  winget install Microsoft.PowerShell
  ```
- **預防措施**：
  - 排程設定使用 `pwsh.exe`（非 `powershell.exe`）
  - `setup-scheduler.ps1` 已將 `-Execute` 設為 `pwsh.exe`

### 8.4 nul 檔案問題

#### 問題：發現 nul 檔案

- **可能原因**：在 Bash 中使用了 `> nul`（cmd 語法，在 bash 環境會建立實體檔案）
- **排查步驟**：
  ```powershell
  # 搜尋 nul 檔案
  Get-ChildItem D:\Source\daily-digest-prompt -Filter "nul" -Recurse -ErrorAction SilentlyContinue

  # 檢查結構化日誌中的攔截記錄
  python hooks/query_logs.py --blocked
  ```
- **解決方案**：
  ```powershell
  # 刪除 nul 檔案（Windows 特殊處理）
  Remove-Item "D:\Source\daily-digest-prompt\nul" -Force -ErrorAction SilentlyContinue

  # 或使用 bash
  rm -f "D:/Source/daily-digest-prompt/nul"
  ```
- **預防措施**：
  - `pre_bash_guard.py` 已在 runtime 攔截 `> nul` 指令
  - `pre_write_guard.py` 已攔截 `file_path` 為 `nul` 的 Write 操作
  - 兩道 Hook 提供機器級強制，不依賴 Agent 自律
  - 正確用法：`> /dev/null 2>&1`（bash）或 `| Out-Null`（PowerShell）

### 8.5 快取問題

#### 問題：快取一直未命中

- **可能原因**：快取檔案不存在、TTL 設定過短、或 Agent 未遵循快取流程
- **排查步驟**：
  1. 檢查快取檔案是否存在：
     ```powershell
     Get-ChildItem D:\Source\daily-digest-prompt\cache\
     ```
  2. 檢查快取時間戳：
     ```powershell
     Get-ChildItem D:\Source\daily-digest-prompt\cache\*.json | ForEach-Object { "$($_.Name): $($_.LastWriteTime)" }
     ```
  3. 快取審計：
     ```bash
     python hooks/query_logs.py --cache-audit
     ```
- **解決方案**：
  - 快取不存在 -> 首次執行後會自動建立
  - TTL 過短 -> 調整 `config/cache-policy.yaml`
  - 未遵循流程 -> 檢查 SKILL.md 中的快取操作指示
- **預防措施**：快取審計會在 session 結束時自動偵測 bypass

#### 問題：降級使用過期資料

- **可能原因**：API 呼叫失敗且快取在 `degradation_max_age_hours`（24 小時）內
- **排查步驟**：
  1. 摘要通知中會包含降級標記：`"資料來自快取（{time}）"`
  2. 確認對應的 API 是否恢復：
     ```powershell
     # 以 Todoist 為例
     curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $env:TODOIST_API_TOKEN" "https://api.todoist.com/api/v1/tasks/filter?query=today"
     ```
- **解決方案**：API 恢復後，下次執行會自動更新快取
- **預防措施**：降級是設計行為（對應 SRD REQ-NFR-001），確保資料可用性

#### 問題：快取檔案損壞

- **可能原因**：寫入時中斷（如斷電、程序異常終止）
- **排查步驟**：
  ```powershell
  # 嘗試解析快取檔案
  Get-Content D:\Source\daily-digest-prompt\cache\todoist.json | python -m json.tool
  ```
  若報 JSON 解析錯誤 -> 已損壞
- **解決方案**：
  ```powershell
  # 直接刪除損壞的快取檔案（可安全刪除）
  Remove-Item D:\Source\daily-digest-prompt\cache\todoist.json
  ```
  下次執行會重新從 API 取得資料並寫入快取
- **預防措施**：快取設計為可隨時刪除，不影響系統功能

### 8.6 記憶檔案問題

#### 問題：digest-memory.json 損壞

- **可能原因**：寫入時中斷或格式錯誤
- **排查步驟**：
  ```powershell
  Get-Content D:\Source\daily-digest-prompt\context\digest-memory.json | python -m json.tool
  ```
- **解決方案**：
  ```powershell
  # 備份損壞檔案
  Copy-Item D:\Source\daily-digest-prompt\context\digest-memory.json D:\Source\daily-digest-prompt\context\digest-memory.json.bak

  # 刪除損壞檔案（Agent 會在下次執行時視為首次運行並重建）
  Remove-Item D:\Source\daily-digest-prompt\context\digest-memory.json
  ```
- **預防措施**：
  - `digest-memory.json` 由 Agent 獨佔寫入（`schema_version=2`）
  - 損壞時連續天數會重置為 1

#### 問題：連續天數異常重置

- **可能原因**：同日多次執行不應遞增；JSON 損壞導致重置
- **排查步驟**：
  1. 確認記憶檔案中的 `last_run` 日期
  2. 比對 `state/scheduler-state.json` 中的執行記錄
- **解決方案**：
  - 同日多次是正常行為（設計為不重複遞增）
  - JSON 損壞 -> 參照上方解決方案
  - 若需手動修正天數，可直接編輯 `context/digest-memory.json` 的 `run_count` 欄位
- **預防措施**：連續天數計算以本地日期（+08:00）為準

#### 問題：scheduler-state.json 損壞

- **可能原因**：PowerShell 寫入時中斷
- **排查步驟**：
  ```powershell
  Get-Content D:\Source\daily-digest-prompt\state\scheduler-state.json | python -m json.tool
  ```
- **解決方案**：
  ```powershell
  # 備份
  Copy-Item D:\Source\daily-digest-prompt\state\scheduler-state.json D:\Source\daily-digest-prompt\state\scheduler-state.json.bak

  # 重建空狀態（PowerShell 腳本下次執行時會自動寫入）
  '{"runs":[]}' | Set-Content D:\Source\daily-digest-prompt\state\scheduler-state.json -Encoding UTF8
  ```
- **預防措施**：
  - 此檔案由 PowerShell 腳本獨佔寫入
  - Agent 對此檔案僅有讀取權限（Hooks 強制）
  - 保留最近 200 筆記錄，超出自動移除最舊的

### 8.7 排程問題

#### 問題：排程未觸發

- **可能原因**：排程未建立、排程停用、或使用者未登入
- **排查步驟**：
  1. 確認排程狀態：
     ```powershell
     schtasks /query /tn Claude* /v /fo list
     ```
  2. 確認 `Status` 為 `Ready`，`Next Run Time` 正確
  3. 確認 `Last Result` 為 `0`（成功）
- **解決方案**：
  - 排程不存在 -> 重新建立：
    ```powershell
    pwsh -ExecutionPolicy Bypass -File setup-scheduler.ps1 -FromHeartbeat
    ```
  - 排程停用 -> 啟用：
    ```powershell
    schtasks /change /tn Claude_daily-digest /enable
    ```
- **預防措施**：排程設定包含 `-StartWhenAvailable`，錯過的排程開機後會補執行

#### 問題：排程重複執行

- **可能原因**：建立了多個相同排程
- **排查步驟**：
  ```powershell
  schtasks /query /tn Claude* /fo list
  ```
  確認是否有重複名稱
- **解決方案**：刪除重複的排程：
  ```powershell
  schtasks /delete /tn "重複的排程名" /f
  ```
  使用 `-FromHeartbeat` 重新建立（會自動移除舊排程）
- **預防措施**：`setup-scheduler.ps1` 在建立前會先檢查並移除同名排程

#### 問題：開機後補執行未啟動

- **可能原因**：排程設定未包含 `-StartWhenAvailable`
- **排查步驟**：
  ```powershell
  schtasks /query /tn Claude_daily-digest /v /fo list | Select-String "StartWhenAvailable"
  ```
- **解決方案**：重新建立排程（`setup-scheduler.ps1` 已包含此設定）
- **預防措施**：使用 `-FromHeartbeat` 統一建立，確保設定一致

### 8.8 團隊模式問題

#### 問題：Phase 1 agent timeout

- **可能原因**：某個 fetch agent 卡住或外部 API 極慢
- **排查步驟**：
  1. 查看日誌中的 Phase 1 結果：
     ```powershell
     Get-Content (Get-ChildItem D:\Source\daily-digest-prompt\logs\team_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | Select-String "Phase1"
     ```
  2. 確認哪個 agent 超時（`TIMEOUT` 標記）
- **解決方案**：
  - Phase 1 超時的 agent 會被強制終止，其 `sections` 狀態標記為 `failed`
  - Phase 2 組裝時會跳過失敗的區塊
  - 下次執行通常自動恢復
- **預防措施**：Phase 1 超時設為 180 秒（`$Phase1TimeoutSeconds = 180`），可在 `run-agent-team.ps1` 中調整

#### 問題：results/*.json 未建立

- **可能原因**：fetch agent 執行失敗，未產出結果檔案
- **排查步驟**：
  ```powershell
  Get-ChildItem D:\Source\daily-digest-prompt\results\
  ```
  確認哪些結果檔案遺失
- **解決方案**：
  - PowerShell 腳本會自動偵測遺失的結果檔案並標記為 `failed`
  - Phase 2 組裝 agent 會處理遺失的資料（跳過或降級）
- **預防措施**：results/ 目錄由腳本自動建立，無需手動維護

#### 問題：Phase 2 組裝失敗

- **可能原因**：組裝 Prompt 檔案遺失或 Agent 內部錯誤
- **排查步驟**：
  1. 確認組裝 Prompt 存在：
     ```powershell
     Test-Path D:\Source\daily-digest-prompt\prompts\team\assemble-digest.md
     ```
  2. 查看日誌中的 Phase 2 輸出：
     ```powershell
     Get-Content (Get-ChildItem D:\Source\daily-digest-prompt\logs\team_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | Select-String "Phase2|assemble"
     ```
- **解決方案**：
  - Phase 2 內建重試 1 次（間隔 60 秒）
  - 若重試仍失敗，整體狀態記為 `failed`
  - 可手動重跑：
    ```powershell
    pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1
    ```
- **預防措施**：確保 `prompts/team/assemble-digest.md` 不被意外修改

---

## 9. 維護程序

### 9.1 日誌清理

日誌自動清理已內建於各執行腳本中，每次執行結束時自動刪除 7 天前的日誌。

**手動清理**：
```powershell
# 清理 7 天前的執行日誌
Get-ChildItem D:\Source\daily-digest-prompt\logs\*.log |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force -Verbose

# 清理結構化日誌（視需要）
Get-ChildItem D:\Source\daily-digest-prompt\logs\structured\*.jsonl |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -Verbose
```

> **注意**：結構化日誌（JSONL）不在自動清理範圍內，建議保留 30 天以上供分析。

### 9.2 快取清理

快取檔案可安全刪除，下次執行時自動重建。

```powershell
# 清除所有快取
Remove-Item D:\Source\daily-digest-prompt\cache\*.json -Force -Verbose

# 清除特定來源快取
Remove-Item D:\Source\daily-digest-prompt\cache\todoist.json -Force
```

**場景**：快取資料陳舊或損壞時執行。

### 9.3 狀態檔案備份與還原

**備份**：
```powershell
$backupDir = "D:\Backup\daily-digest-$(Get-Date -Format 'yyyyMMdd')"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Copy-Item D:\Source\daily-digest-prompt\context\digest-memory.json "$backupDir\" -Force
Copy-Item D:\Source\daily-digest-prompt\state\scheduler-state.json "$backupDir\" -Force
Copy-Item D:\Source\daily-digest-prompt\state\todoist-history.json "$backupDir\" -Force -ErrorAction SilentlyContinue
Copy-Item D:\Source\daily-digest-prompt\context\auto-tasks-today.json "$backupDir\" -Force -ErrorAction SilentlyContinue

Write-Host "備份完成: $backupDir"
```

**還原**：
```powershell
$backupDir = "D:\Backup\daily-digest-20260215"  # 指定備份日期

Copy-Item "$backupDir\digest-memory.json" D:\Source\daily-digest-prompt\context\ -Force
Copy-Item "$backupDir\scheduler-state.json" D:\Source\daily-digest-prompt\state\ -Force
Copy-Item "$backupDir\todoist-history.json" D:\Source\daily-digest-prompt\state\ -Force -ErrorAction SilentlyContinue

Write-Host "還原完成"
```

### 9.4 Skills 更新

Skills 來源為 `D:\Source\skills\`，複製到專案內確保自包含。

**同步流程**：
```powershell
$source = "D:\Source\skills"
$target = "D:\Source\daily-digest-prompt\skills"

# 列出需更新的 Skill
$skills = @("todoist", "pingtung-news", "pingtung-policy-expert", "hackernews-ai-digest",
            "atomic-habits", "learning-mastery", "knowledge-query", "ntfy-notify",
            "digest-memory", "api-cache", "scheduler-state", "gmail", "skill-scanner")

foreach ($skill in $skills) {
    if (Test-Path "$source\$skill\SKILL.md") {
        Copy-Item "$source\$skill\SKILL.md" "$target\$skill\SKILL.md" -Force
        Write-Host "Updated: $skill" -ForegroundColor Green
    }
    else {
        Write-Host "Skipped (not found in source): $skill" -ForegroundColor Yellow
    }
}
```

**更新後驗證**：
```powershell
.\scan-skills.ps1
```

### 9.5 Hooks 更新與測試

**更新 Hook 檔案後的測試流程**：

1. 語法檢查：
   ```powershell
   python -m py_compile hooks/pre_bash_guard.py
   python -m py_compile hooks/pre_write_guard.py
   python -m py_compile hooks/post_tool_logger.py
   python -m py_compile hooks/on_stop_alert.py
   ```
   無輸出即表示語法正確。

2. 驗證設定檔案引用正確：
   ```powershell
   Get-Content D:\Source\daily-digest-prompt\.claude\settings.json | python -m json.tool
   ```

3. 執行一次 Agent 後檢查結構化日誌：
   ```bash
   python hooks/query_logs.py
   ```
   確認有新的日誌記錄產生。

### 9.6 排程遷移（換機器）

**匯出步驟**：

1. 備份整個專案目錄：
   ```powershell
   Copy-Item D:\Source\daily-digest-prompt D:\Backup\daily-digest-prompt -Recurse
   ```

2. 記錄環境變數：
   ```powershell
   $env:TODOIST_API_TOKEN | Set-Content D:\Backup\todoist-token.txt
   ```

3. 匯出排程設定（參考用）：
   ```powershell
   schtasks /query /tn Claude* /v /fo csv > D:\Backup\schedules.csv
   ```

**匯入步驟（新機器）**：

1. 安裝前置需求（PowerShell 7、Claude Code CLI、Python 3.8+、curl）
2. 還原專案目錄到 `D:\Source\daily-digest-prompt`
3. 設定環境變數：
   ```powershell
   [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", "你的_token", "User")
   ```
4. 重建排程：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\setup-scheduler.ps1 -FromHeartbeat
   ```
5. 驗證連通性（參照 [3.3 外部服務連通性驗證](#33-外部服務連通性驗證)）
6. 手動執行一次驗證：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\run-agent-team.ps1
   ```

> **注意**：`D:\Source\daily-digest-prompt` 為硬編碼路徑，若需變更須同步修改所有 `.ps1` 腳本中的 `$AgentDir` 變數。

### 9.7 API Token 輪換

#### Todoist API Token

1. 前往 https://app.todoist.com/app/settings/integrations/developer
2. 重新產生 Token（舊 Token 會立即失效）
3. 更新環境變數：
   ```powershell
   [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", "新的_token", "User")
   ```
4. **重啟 PowerShell session**（環境變數生效需要新 session）
5. 驗證：
   ```powershell
   curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $env:TODOIST_API_TOKEN" "https://api.todoist.com/api/v1/tasks/filter?query=today"
   ```
   預期回傳 `200`。

#### Gmail OAuth Token

1. 刪除過期的 token.json
2. 重新授權（參照 [3.2 環境變數設定 > Gmail OAuth](#32-環境變數設定)）

#### ntfy Topic 變更

1. 修改 `config/notification.yaml` 中的 `default_topic`
2. 修改 `hooks/on_stop_alert.py` 中的 `NTFY_TOPIC` 常數
3. 測試：
   ```powershell
   curl -d "token rotation test" ntfy.sh/新的topic名
   ```

---

## 10. 附錄

### 10.1 完整指令速查表

#### 執行指令

| 指令 | 說明 |
|------|------|
| `pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1` | 每日摘要（團隊模式，推薦） |
| `pwsh -ExecutionPolicy Bypass -File run-agent.ps1` | 每日摘要（單一模式） |
| `pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1` | Todoist 任務規劃（團隊模式，推薦） |
| `pwsh -ExecutionPolicy Bypass -File run-todoist-agent.ps1` | Todoist 任務規劃（單一模式） |

#### 排程管理

| 指令 | 說明 |
|------|------|
| `.\setup-scheduler.ps1 -FromHeartbeat` | 從 HEARTBEAT.md 批次建立排程 |
| `.\setup-scheduler.ps1 -Time "08:00" -Script "run-agent-team.ps1"` | 手動建立單一排程 |
| `schtasks /query /tn Claude* /v` | 查看所有 Claude 排程 |
| `schtasks /run /tn Claude_daily-digest` | 手動觸發排程 |
| `schtasks /delete /tn Claude_daily-digest /f` | 刪除排程 |

#### 監控查詢

| 指令 | 說明 |
|------|------|
| `pwsh -ExecutionPolicy Bypass -File check-health.ps1` | 健康狀態報告 |
| `.\query-logs.ps1` | 近 7 天摘要 |
| `.\query-logs.ps1 -Days 3 -Agent todoist` | 近 3 天 Todoist |
| `.\query-logs.ps1 -Mode detail -Date 2026-02-12` | 特定日期詳情 |
| `.\query-logs.ps1 -Mode errors` | 錯誤彙總 |
| `.\query-logs.ps1 -Mode todoist` | 自動任務歷史 |
| `.\query-logs.ps1 -Mode trend -Days 14` | 趨勢分析 |
| `.\query-logs.ps1 -Mode summary -Format json` | JSON 輸出 |

#### 結構化日誌

| 指令 | 說明 |
|------|------|
| `python hooks/query_logs.py` | 今日摘要 |
| `python hooks/query_logs.py --days 7` | 近 7 天 |
| `python hooks/query_logs.py --blocked` | 攔截事件 |
| `python hooks/query_logs.py --errors` | 錯誤事件 |
| `python hooks/query_logs.py --cache-audit` | 快取審計 |
| `python hooks/query_logs.py --sessions --days 7` | Session 健康 |
| `python hooks/query_logs.py --format json` | JSON 輸出 |

#### Skills 安全掃描

| 指令 | 說明 |
|------|------|
| `.\scan-skills.ps1` | 快速掃描 |
| `.\scan-skills.ps1 -Format markdown -UseBehavioral` | 完整報告 + 行為分析 |
| `.\scan-skills.ps1 -Format json` | JSON 輸出 |
| `.\scan-skills.ps1 -SkillName todoist` | 掃描單一 Skill |

#### 維護指令

| 指令 | 說明 |
|------|------|
| `Remove-Item cache\*.json -Force` | 清除所有快取 |
| `Remove-Item context\digest-memory.json` | 重置記憶（連續天數歸零） |
| `Get-ChildItem logs\*.log | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force` | 手動清理舊日誌 |
| `Get-ChildItem -Filter "nul" -Recurse` | 搜尋 nul 檔案 |

### 10.2 配置檔案速查表

| 路徑 | 用途 | 引用者 | 修改後生效方式 |
|------|------|--------|-------------|
| `config/pipeline.yaml` | 摘要管線步驟 | daily-digest-prompt.md | 下次排程自動生效 |
| `config/routing.yaml` | 任務路由規則 | hour-todoist-prompt.md | 下次排程自動生效 |
| `config/cache-policy.yaml` | 快取 TTL 策略 | 所有 Agent | 下次排程自動生效 |
| `config/frequency-limits.yaml` | 自動任務頻率 | hour-todoist-prompt.md | 下次排程自動生效 |
| `config/scoring.yaml` | 優先級計分 | hour-todoist-prompt.md | 下次排程自動生效 |
| `config/notification.yaml` | 通知配置 | 所有有通知的 Agent | 下次排程自動生效 |
| `config/digest-format.md` | 摘要排版 | daily-digest-prompt.md, assemble-digest.md | 下次排程自動生效 |
| `templates/shared/preamble.md` | 共用前言 | 所有 prompt | 下次排程自動生效 |
| `HEARTBEAT.md` | 排程定義 | setup-scheduler.ps1 | 需重新執行 `-FromHeartbeat` |
| `.claude/settings.json` | Hooks 設定 | Claude Code runtime | 下次 Agent 啟動生效 |

### 10.3 外部服務端點速查表

| 服務 | 端點 URL | 認證方式 | 快取 TTL | 對應 Skill |
|------|---------|---------|---------|-----------|
| Todoist | `api.todoist.com/api/v1` | Bearer Token | 30 分鐘 | todoist |
| 屏東新聞 | `ptnews-mcp.pages.dev/mcp` | 無 | 360 分鐘 | pingtung-news |
| HN Firebase | `hacker-news.firebaseio.com/v0` | 無 | 120 分鐘 | hackernews-ai-digest |
| 知識庫 | `localhost:3000` | 無 | 60 分鐘 | knowledge-query |
| ntfy | `ntfy.sh` | 無 | 不快取 | ntfy-notify |
| Gmail | `gmail.googleapis.com/gmail/v1` | OAuth 2.0 | 30 分鐘 | gmail |

> **重要**：Todoist 的篩選端點為 `/api/v1/tasks/filter?query=today`，不是 `/api/v1/tasks?filter=today`（後者的 `filter` 參數會被靜默忽略）。

### 10.4 錯誤碼對照表

#### PowerShell 腳本 Exit Code

| Exit Code | 含義 | 處理方式 |
|-----------|------|---------|
| 0 | 成功 | 無需處理 |
| 1 | 腳本錯誤（prompt 不存在、claude 未安裝） | 查看日誌中的 `[ERROR]` 訊息 |

#### scheduler-state.json 狀態值

| 狀態 | 含義 | 處理方式 |
|------|------|---------|
| `success` | 執行成功 | 無需處理 |
| `failed` | 執行失敗（含重試後仍失敗） | 查看 `error` 欄位和對應日誌 |
| `timeout` | 超時被強制終止 | 查看 Agent 是否陷入迴圈 |

#### HTTP 狀態碼（外部 API）

| 狀態碼 | 含義 | 處理方式 |
|--------|------|---------|
| 200 | 成功 | 無需處理 |
| 401 | 認證失敗 | 檢查 Token/憑證 |
| 403 | 禁止存取 | 檢查 Token 權限 |
| 410 | 端點已棄用 | 更新為正確端點版本 |
| 429 | 請求過多 | 等待限速解除，依賴快取降級 |
| 500/502/503 | 伺服器錯誤 | 等待恢復，依賴快取降級 |
| 521 | 後端不可用（Cloudflare） | 等待恢復，依賴快取降級 |

#### Hooks 攔截原因

| 原因 | Hook | 觸發條件 |
|------|------|---------|
| `禁止 nul 重導向` | pre_bash_guard.py | Bash 指令含 `> nul` |
| `禁止 Agent 寫入 scheduler-state.json` | pre_bash_guard.py / pre_write_guard.py | 對 scheduler-state.json 的寫入操作 |
| `禁止刪除根目錄` | pre_bash_guard.py | `rm -rf /` |
| `禁止 force push` | pre_bash_guard.py | `git push --force` 到 main/master |
| `禁止寫入 nul 檔案` | pre_write_guard.py | Write 工具的 file_path 為 nul |
| `禁止寫入敏感檔案` | pre_write_guard.py | 寫入 .env/credentials.json/token.json |

### 10.5 緊急復原程序

**場景**：系統完全無法運作（排程不觸發、Agent 無法啟動、所有服務不可用）。

#### 逐步復原指南

**第 1 步：確認基礎環境**
```powershell
# 確認 PowerShell 7
pwsh --version
# 預期: PowerShell 7.x

# 確認 Claude Code
claude --version
# 預期: claude x.x.x

# 確認 Python
python --version
# 預期: Python 3.x

# 確認工作目錄完整
Test-Path D:\Source\daily-digest-prompt\daily-digest-prompt.md
Test-Path D:\Source\daily-digest-prompt\hour-todoist-prompt.md
Test-Path D:\Source\daily-digest-prompt\run-agent-team.ps1
# 預期: 全部 True
```

**第 2 步：初始化目錄**
```powershell
$base = "D:\Source\daily-digest-prompt"
@("logs", "logs\structured", "state", "context", "cache", "results") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path "$base\$_" | Out-Null
}
```

**第 3 步：設定環境變數**
```powershell
# 確認 Todoist Token
if (-not $env:TODOIST_API_TOKEN) {
    Write-Host "WARNING: TODOIST_API_TOKEN not set" -ForegroundColor Red
    # 設定 Token
    [System.Environment]::SetEnvironmentVariable("TODOIST_API_TOKEN", "你的_token", "User")
}
```

**第 4 步：驗證外部服務（依重要性排序）**
```powershell
# 1. Claude Code（必要）
claude --version

# 2. ntfy（通知）
curl -d "recovery test" ntfy.sh/wangsc2025

# 3. Todoist（待辦）
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $env:TODOIST_API_TOKEN" "https://api.todoist.com/api/v1/tasks/filter?query=today"
```

**第 5 步：手動執行驗證**
```powershell
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\run-agent-team.ps1
```

**第 6 步：重建排程**
```powershell
# 需要系統管理員權限
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\setup-scheduler.ps1 -FromHeartbeat
```

**第 7 步：確認恢復**
```powershell
# 健康檢查
pwsh -ExecutionPolicy Bypass -File D:\Source\daily-digest-prompt\check-health.ps1

# 確認排程
schtasks /query /tn Claude* /v /fo list
```

**若狀態檔案遺失或損壞**：
```powershell
# 重置記憶（連續天數歸零，但不影響功能）
Remove-Item D:\Source\daily-digest-prompt\context\digest-memory.json -Force -ErrorAction SilentlyContinue

# 重置排程狀態
'{"runs":[]}' | Set-Content D:\Source\daily-digest-prompt\state\scheduler-state.json -Encoding UTF8

# 清除快取（強制從 API 重新取得）
Remove-Item D:\Source\daily-digest-prompt\cache\*.json -Force -ErrorAction SilentlyContinue
```

---

> **文件維護**：本手冊應隨系統變更同步更新。重大配置變更、新增外部服務、或新發現的故障模式，均應補充至對應章節。
