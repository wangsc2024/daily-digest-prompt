# Cursor CLI agent -p 非互動模式研究與規則整理

## 執行摘要

- **研究日期**：2026-03-14
- **來源**：Cursor 官方文件（cli/overview、cli/using、cli/reference/parameters）
- **用途**：作為專案「另一執行任務工具」的知識庫與 cursor-cli Skill 依據
- **核心**：`agent -p`（或 `--print`）為非互動模式，可寫入檔案與執行 shell，適合腳本、CI、排程任務

---

## 1. agent -p / --print 定義與行為

| 項目 | 說明 |
|------|------|
| **選項** | `-p` 或 `--print` |
| **效果** | 以非互動模式執行 Agent，將回應印到終端（stdout） |
| **工具權限** | **具備完整工具權限**：file write、shell 等，無需人工逐筆批准 |
| **適用場景** | 腳本、CI/CD、排程、PowerShell 管線、一次性任務 |

官方原文：
> Print responses to console (for scripts or non-interactive use). **Has access to all tools, including write and shell.**

> With non-interactive mode, you can invoke Agent in a non-interactive way. This allows you to integrate it in scripts, CI pipelines, etc. **Cursor has full write access in non-interactive mode.**

---

## 2. 與 --output-format 的搭配規則

| 規則 | 說明 |
|------|------|
| **僅與 -p 生效** | `--output-format` **僅在與 `--print` 一起使用時有效**，互動模式會忽略 |
| **可選值** | `text`（預設）、`json`、`stream-json` |
| **text** | 純文字輸出 agent 的最終回應，適合人類閱讀與簡單日誌 |
| **json** | 結構化輸出，方便腳本解析（如 jq、PowerShell ConvertFrom-Json） |
| **stream-json** | 以 JSON 串流輸出部分結果；可搭配 `--stream-partial-output` |

官方參數表：
> `--output-format <value>` — Output format (**only works with `--print`**): `text`, `json`, or `stream-json` (default: `text`)

> `--stream-partial-output` — Stream partial output as individual text deltas (**only works with `--print` and `stream-json` format**)

---

## 3. 常用參數組合（-p 情境）

| 用途 | 範例 |
|------|------|
| 單次任務、純文字 | `agent -p "找出並修復效能問題"` |
| 指定模型 | `agent -p "任務描述" --model composer-1.5` |
| 腳本可解析輸出 | `agent -p "列出未完成 TODO" --output-format json` |
| 串流 JSON（長任務） | `agent -p "重構模組" --output-format stream-json --stream-partial-output` |
| 唯讀探索（不寫檔） | `agent -p "分析專案結構，不要改任何檔案" --mode=ask` |
| 先規劃再執行 | `agent -p "設計並實作登入 API" --plan` |
| 指定工作區 | `agent -p "任務" --workspace D:/Source/daily-digest-prompt` |
| 無頭/CI 信任工作區 | `agent -p "任務" --trust` |
| 強制允許指令 | `agent -p "任務" --force` 或 `--yolo` |

---

## 4. 模式（--mode）在 -p 下的影響

| 模式 | 旗標 | 在 -p 下的行為 |
|------|------|----------------|
| Agent | 預設 | 可讀寫檔案、執行 shell，完整工具權限 |
| Plan | `--plan` / `--mode=plan` | 先釐清與規劃，再執行；適合複雜任務 |
| Ask | `--mode=ask` | 唯讀：搜尋與回答，不編輯檔案、不執行寫入/Shell |

在非互動模式下，若希望「只分析不修改」，應明確使用 `--mode=ask` 或在 prompt 中聲明「do not write any code」「僅分析不修改」。

---

## 5. 認證與環境

| 項目 | 說明 |
|------|------|
| 登入 | `agent login`（需先完成，-p 才會正常呼叫後端） |
| API Key | 可用 `--api-key <key>` 或環境變數 `CURSOR_API_KEY` |
| 狀態檢查 | `agent status` 或 `agent about` |

---

## 6. 沙箱與安全（-p 時特別注意）

| 選項 | 說明 |
|------|------|
| `--sandbox enabled` | 預設；限制指令執行環境 |
| `--sandbox disabled` | 關閉沙箱，權限較大 |
| `--trust` | 僅在 headless/非互動時有效；信任工作區不再次詢問 |
| `-f` / `--force` / `--yolo` | 強制允許原本會被拒絕的指令（慎用） |

因 `-p` 具備完整寫入與 shell 權限，在排程或 CI 中建議：
- 明確指定 `--workspace` 限制範圍
- 需要時用 `--mode=ask` 做唯讀任務
- 敏感環境避免使用 `--force`/`--yolo`

---

## 7. 與本專案整合要點

- **執行環境**：Windows PowerShell 7（pwsh），與現有 run-todoist-agent-team.ps1、run-agent-team.ps1 一致。
- **專案規則**：CLI 會讀取專案根目錄 `AGENTS.md`、`CLAUDE.md` 及 `.cursor/rules/`，與編輯器相同；本專案有 CLAUDE.md（Skill-First、nul 禁令等），agent -p 會遵守。
- **MCP**：會讀取 `.cursor/mcp.json`（或 Cursor 的 mcp 配置），可與現有 MCP 工具鏈整合。
- **用途定位**：作為「另一執行任務工具」——可與 Todoist Agent、排程腳本並行，用於單次程式碼任務、重構、審查、腳本化 AI 流程，而不取代既有 Phase 1/2/3 管線。

---

## 8. 參考連結

- [Cursor CLI Overview](https://cursor.com/docs/cli/overview)
- [Using Agent in CLI](https://cursor.com/docs/cli/using)
- [Parameters (reference)](https://cursor.com/docs/cli/reference/parameters)
