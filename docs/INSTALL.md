# 安裝指南

## 前置條件

| 軟體 | 版本 | 用途 |
|------|------|------|
| Windows 11 | 10.0+ | 作業系統 |
| PowerShell 7 (pwsh) | 7.x | 排程腳本執行環境 |
| [uv](https://docs.astral.sh/uv/) | 最新版 | Python 套件管理 |
| [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) | 最新版 | AI Agent 執行引擎 |
| Git | 2.x+ | 版本控制 |

## 安裝步驟

### 1. 取得原始碼

```bash
git clone <repo-url> D:\Source\daily-digest-prompt
cd D:\Source\daily-digest-prompt
```

### 2. 安裝 Python 依賴

```bash
uv sync
```

此命令依據 `pyproject.toml` 與 `uv.lock` 安裝所有依賴，確保可重現的環境。

### 3. 設定環境變數

複製範本檔並填入實際值：

```bash
cp .env.example .env
```

必要環境變數（詳見 `.env.example`）：
- `TODOIST_API_TOKEN` — Todoist API 金鑰
- `ANTHROPIC_API_KEY` — Claude API 金鑰（若使用 Claude API）

> 注意：`.env` 已加入 `.gitignore`，不會被提交。

### 4. 驗證安裝

```powershell
pwsh -ExecutionPolicy Bypass -File check-health.ps1
```

應看到各項檢查通過的輸出。

## 排程設定

本專案透過 Windows Task Scheduler 定期執行 Agent。

### 自動建立排程（推薦）

以**管理員權限**開啟 PowerShell 7，執行：

```powershell
.\setup-scheduler.ps1 -FromHeartbeat
```

此命令讀取 `HEARTBEAT.md` 中的排程定義，批次建立 Windows 排程任務。

### 排程總覽

| 排程名稱 | 觸發時間 | 執行腳本 |
|---------|---------|---------|
| system-audit | 每日 00:40 | `run-system-audit-team.ps1` |
| daily-digest-am | 每日 08:00 | `run-agent-team.ps1` |
| daily-digest-mid | 每日 11:15 | `run-agent-team.ps1` |
| daily-digest-pm | 每日 21:15 | `run-agent-team.ps1` |
| todoist-single | 每小時整點 02-23 | `run-todoist-agent.ps1` |
| todoist-team | 每小時半點 02-23 | `run-todoist-agent-team.ps1` |

完整排程 cron 定義見 `HEARTBEAT.md`，timeout 設定見 `config/timeouts.yaml`。

## ntfy 通知訂閱

本專案使用 [ntfy.sh](https://ntfy.sh) 推播通知。

### 訂閱方式

1. 安裝 ntfy App（[Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347)）
2. 訂閱 topic：`wangsc2025`
3. 或使用網頁版：https://ntfy.sh/wangsc2025

### 通知類型

| 通知 | 來源 | 說明 |
|------|------|------|
| 每日摘要 | `run-agent-team.ps1` | 待辦事項 + 新聞 + 禪語 |
| 任務執行結果 | `run-todoist-agent-team.ps1` | Todoist 任務處理報告 |
| 系統審查 | `run-system-audit-team.ps1` | 系統健康評分與改善建議 |
| 自癒報告 | self-heal 自動任務 | 修復行為通知 |

## 驗證步驟

安裝完成後，依序驗證：

```powershell
# 1. 健康檢查（確認所有組件正常）
pwsh -ExecutionPolicy Bypass -File check-health.ps1

# 2. 手動執行一次每日摘要（確認 Agent 可運作）
pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1

# 3. 查詢執行成果
.\query-logs.ps1

# 4. 確認排程已建立
Get-ScheduledTask | Where-Object { $_.TaskName -like "daily-digest*" -or $_.TaskName -like "todoist*" -or $_.TaskName -like "system-audit*" }
```

若所有步驟均成功，系統已可自動運行。
