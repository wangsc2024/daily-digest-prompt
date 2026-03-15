---
name: cursor-cli
version: "1.0.0"
description: |
  以 Cursor CLI 的 agent -p（非互動模式）作為專案另一執行任務工具。適用腳本、排程、單次程式碼任務、
  重構、審查、腳本化 AI 流程；與既有 Todoist Agent / run-agent-team 管線並行，不取代 Phase 1/2/3。
  Use when: 用終端機跑 Cursor Agent、agent -p、CLI 任務、非互動 Agent、腳本化 Cursor、排程呼叫 Agent。
allowed-tools: Bash, Read, Write
cache-ttl: N/A
triggers:
  - "cursor cli"
  - "cursor CLI"
  - "agent -p"
  - "agent --print"
  - "Cursor Agent 終端"
  - "CLI 任務"
  - "非互動 Agent"
  - "腳本化 Cursor"
  - "排程呼叫 Agent"
  - "cursor-cli"
---

# Cursor CLI — 專案另一執行任務工具

以 **Cursor CLI** 的 `agent -p`（非互動模式）在終端機執行 AI 任務，可寫入檔案與執行 shell，適合腳本、CI、排程。

> **知識庫**：完整參數與規則見 `docs/research/研究報告_cursor-cli-agent-print_20260314.md`。執行前建議先讀該文件。

---

## 1. 前置條件

| 項目 | 說明 |
|------|------|
| 安裝 | 已執行 `irm 'https://cursor.com/install?win32=true' \| iex`（PowerShell） |
| 認證 | 已執行 `agent login` 或設定 `CURSOR_API_KEY` |
| 環境 | 本專案以 **PowerShell 7 (pwsh)** 為主，與 run-todoist-agent-team.ps1、run-agent-team.ps1 一致 |

檢查登入狀態：`agent status` 或 `agent about`。

---

## 2. agent -p 核心規則（必守）

| 規則 | 說明 |
|------|------|
| **-p 即非互動** | `-p` 或 `--print` 表示非互動：回應印到 stdout，**具備完整工具權限**（write、shell），無需逐筆批准 |
| **output-format 僅搭配 -p** | `--output-format` **僅在與 `-p` 一起使用時有效**；可選 `text`（預設）、`json`、`stream-json` |
| **唯讀用 ask** | 若只要分析、不修改檔案，請用 `--mode=ask` 或在 prompt 聲明「do not write any code」 |
| **專案規則會載入** | CLI 會讀專案根目錄 `AGENTS.md`、`CLAUDE.md`、`.cursor/rules/`，本專案 Skill-First、nul 禁令等會生效 |
| **任務檔先行** | 使用 cursor-cli 時**須先依任務內容建立任務專用任務檔**（Markdown，可置於 `temp/` 或 `docs/plans/`），再以 Cursor CLI 參照該檔執行。任務檔應含：任務目標、步驟（含採用之 Skill）、最後回報格式；範例見 `temp/cursor-cli-task-weishi-bashi.md`。 |
| **積極採用 Skill** | 執行任務時**應積極採用**專案內與任務相關的 Skill（先讀 `skills/SKILL_INDEX.md` 或對應 SKILL.md），以提升功能完整性與執行品質；例如知識庫用 knowledge-query、通知用 ntfy-notify、API 用 api-cache、研究用 web-research 等，避免重複造輪或偏離專案既有最佳實踐。 |
| **外部功能與 Skill 先於 CLI 內執行** | 凡任務涉及外部功能或**透過 Skill 調用的操作**（如 knowledge-query 匯入、ntfy-notify 通知、Podcast 腳本、API 呼叫等），**必須先在 CLI 內實際執行**（依對應 Skill 指示執行 curl、pwsh、Invoke-RestMethod 等），不得預先略過或改為「請手動執行」說明。僅當**實際執行後**發生錯誤（連線失敗、逾時、腳本回傳非零等）時，才在輸出中註明 fallback 與手動做法。 |

---

## 3. 本專案推薦用法（Windows PowerShell）

### 3.0 標準流程：建立任務檔後執行（必循）

使用 cursor-cli 時應依下列順序進行：

1. **依任務內容建立任務專用任務檔**（Markdown）  
   - 建議路徑：`temp/cursor-cli-task-<任務簡稱>.md` 或 `docs/plans/<任務簡稱>.md`  
   - 內容需含：任務目標、步驟（可引用 Skill）、最後回報格式；必要時註明「外部功能與 Skill 先於 CLI 內執行、僅失敗時 fallback」  
   - 範例：`temp/cursor-cli-task-weishi-bashi.md`

2. **以 Cursor CLI 參照該任務檔執行**  
   - 例：`agent -p "依 temp/cursor-cli-task-xxx.md 執行任務" --workspace "D:\Source\daily-digest-prompt"`  
   - 或先 Read 該檔，再以「請依下列任務說明執行：…」為 prompt 呼叫 `agent -p`

### 3.1 單次任務（純文字輸出）

```powershell
agent -p "找出並修復此專案中的效能問題"
```

### 3.2 指定工作區與模型

```powershell
agent -p "重構 config 目錄下的 YAML 命名一致" --workspace "D:\Source\daily-digest-prompt" --model composer-1.5
```

### 3.3 腳本可解析（JSON）

```powershell
agent -p "列出未完成的 TODO 並輸出 JSON 清單" --output-format json --workspace "D:\Source\daily-digest-prompt"
```

### 3.4 唯讀分析（不寫檔）

```powershell
agent -p "分析 docs/ 目錄結構並產出摘要，不要修改任何檔案" --mode=ask --workspace "D:\Source\daily-digest-prompt"
```

### 3.5 先規劃再執行（Plan 模式）

```powershell
agent -p "設計並實作一個新的自動任務從 frequency-limits 讀取並驗證" --plan --workspace "D:\Source\daily-digest-prompt"
```

### 3.6 排程 / 無頭（信任工作區）

```powershell
agent -p "執行今日的知識庫摘要任務" --workspace "D:\Source\daily-digest-prompt" --trust
```

---

## 4. 參數速查（-p 情境常用）

| 參數 | 說明 |
|------|------|
| `-p`, `--print` | 非互動，輸出到 stdout，完整工具權限 |
| `--output-format text\|json\|stream-json` | 僅與 -p 有效；預設 text |
| `--stream-partial-output` | 僅與 -p + stream-json 有效 |
| `--model <id>` | 例：composer-1.5；可用 `agent models` 列出 |
| `--mode plan\|ask` | plan=先釐清再執行；ask=唯讀 |
| `--workspace <path>` | 工作區目錄（建議本專案用絕對路徑） |
| `--trust` | 無頭時信任工作區不再次詢問 |
| `-f`, `--force`, `--yolo` | 強制允許指令（慎用） |
| `--sandbox enabled\|disabled` | 沙箱開關 |

---

## 5. 與專案既有流程的關係

| 情境 | 建議 |
|------|------|
| 每日摘要 / Todoist 三階段 | 仍以 **run-agent-team.ps1**、**run-todoist-agent-team.ps1** 為主 |
| 單次程式碼任務、重構、審查 | 使用 **cursor-cli**（agent -p） |
| 任務涉及知識庫 / 通知 / API / 研究等 | **積極採用對應 Skill**（見 SKILL_INDEX.md），在 CLI 內依 Skill 指示執行，以提升功能與一致性 |
| 需與 MCP / 專案規則一致 | CLI 會讀 `.cursor/mcp.json`、`CLAUDE.md`、`.cursor/rules/`，無需重複配置 |
| 排程內呼叫 Agent | 可用 pwsh 執行 `agent -p "任務" --workspace ... --trust`，注意 -p 具完整寫入權限，建議限定 workspace |

---

## 6. 禁止與注意

- **禁止** 在未先建立任務專用任務檔的情況下，直接以游離 prompt 執行具結構的 cursor-cli 任務；須先寫好任務檔再以 CLI 參照執行。
- **禁止** 在未指定 `--workspace` 的排程中執行會寫入檔案的 `agent -p`，以免寫錯目錄。
- **禁止** 在未實際執行前就略過外部功能或 Skill 調用並改為「請手動執行」；須先於 CLI 內嘗試（含依 Skill 指示的步驟），僅在執行失敗時才 fallback 成手動說明。
- **注意** `-p` 下 Cursor 有完整 write/shell 權限，敏感或共用環境避免 `--force`/`--yolo`。
- **建議** 唯讀類任務明確使用 `--mode=ask` 或於 prompt 聲明不寫入。

---

## 7. 參考

- 知識庫：`docs/research/研究報告_cursor-cli-agent-print_20260314.md`
- 官方：[Cursor CLI Overview](https://cursor.com/docs/cli/overview)、[Parameters](https://cursor.com/docs/cli/reference/parameters)
