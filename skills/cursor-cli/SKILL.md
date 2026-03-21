---
name: cursor-cli
version: "1.2.0"
description: |
  以 Cursor CLI 的 agent -p（非互動模式）作為專案另一執行任務工具。適用腳本、排程、單次程式碼任務、
  重構、審查、腳本化 AI 流程；與既有 Todoist Agent / run-agent-team 管線並行，不取代 Phase 1/2/3。
  Use when: 用終端機跑 Cursor Agent、agent -p、CLI 任務、非互動 Agent、腳本化 Cursor、排程呼叫 Agent。
allowed-tools: Bash, Read, Write
cache-ttl: N/A
triggers:
  - "cursor cli"
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

## ⛔ 執行前強制核查清單（必全部勾選才可執行）

> 每次使用 cursor-cli 前，**逐項確認**。任何一項未完成，禁止繼續。

```
□ 1. 已確認任務目標明確（非游離想法）
□ 2. 已建立任務檔 temp/cursor-cli-task-<名稱>.md（含目標、步驟、回報格式）
□ 3. 已查閱 skills/SKILL_INDEX.md，確認任務涉及的 Skill 並列入任務檔步驟
□ 4. 任務涉及外部功能（knowledge-query/ntfy/API/Podcast 等）→ 已在任務檔中明確要求「先在 CLI 內執行，失敗才 fallback」
□ 5. 已在 agent -p 指令加上 --workspace "D:\Source\daily-digest-prompt"（寫入型任務必填）
□ 6. 唯讀類任務 → 已確認指令含 --mode=ask 或 prompt 含「不寫入」聲明
```

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

| 優先級 | 規則 | 說明 |
|--------|------|------|
| 🔴 P0 | **任務檔先行** | 禁止以游離 prompt 執行有結構的任務。**必須先建立任務檔**（`temp/cursor-cli-task-<名稱>.md`），再以 CLI 參照執行。 |
| 🔴 P0 | **外部功能先執行** | 凡任務涉及外部功能（knowledge-query、ntfy-notify、API 呼叫、Podcast 腳本等），**必須先在 CLI 內實際執行**，僅在執行失敗後才 fallback 成手動說明。 |
| 🔴 P0 | **--workspace 必填（寫入型）** | 排程或會寫入檔案的 `agent -p`，必須加 `--workspace` 限定範圍，避免寫入錯誤目錄。 |
| 🟡 P1 | **積極採用 Skill** | 執行前先查 `skills/SKILL_INDEX.md`，有對應 Skill 就採用，不重複造輪。 |
| 🟡 P1 | **-p 即非互動** | `-p` 具備完整工具權限（write、shell），無需逐筆批准，排程與 CI 中注意安全。 |
| 🟡 P1 | **output-format 僅搭配 -p** | `--output-format` 僅在與 `-p` 一起使用時有效；可選 `text`（預設）、`json`、`stream-json`。 |
| 🟢 P2 | **唯讀用 ask** | 只要分析不修改，用 `--mode=ask` 或在 prompt 聲明「do not write any code」。 |
| 🟢 P2 | **專案規則會載入** | CLI 會讀 `CLAUDE.md`、`.cursor/rules/`，Skill-First、nul 禁令等會自動生效。 |

**預設推薦 LLM**：`--model composer-2-fast`（[Composer 2 說明](https://cursor.com/zh-Hant/blog/composer-2)）。若需較省輸出成本可改 `--model composer-2`。

---

## 3. 規則遵守決策樹

### 3.1 任務檔決策

```
收到任務請求
    │
    ▼
是否已有任務檔？
    ├─ 否 → 先建立 temp/cursor-cli-task-<名稱>.md（見 §5 模板）
    │         → 再繼續
    └─ 是 → 確認任務檔含：目標、步驟、Skill 引用、回報格式
              → 繼續執行
```

### 3.2 外部功能先行決策

```
任務步驟涉及外部功能（API/ntfy/KB/Podcast）？
    │
    ▼
    是 → 在任務檔中明確寫：「此步驟必須在 CLI 內執行（curl/pwsh/Invoke-RestMethod）」
          └─ CLI 執行中 → 執行成功？
                ├─ 是 → 繼續下一步
                └─ 否（連線失敗/逾時/非零回傳） → 輸出 fallback + 手動說明
    │
    否 → 直接執行（不需特殊處理）
```

---

## 4. 正確 vs 錯誤範例

### ✗ 錯誤做法 1：游離 prompt 直接執行

```powershell
# 錯誤：無任務檔、無 --workspace，prompt 游離
agent -p "幫我整理 config 目錄"
```

### ✓ 正確做法 1：建立任務檔再執行

```powershell
# Step 1: 建立任務檔
# temp/cursor-cli-task-config-cleanup.md（見 §5 模板）

# Step 2: 參照任務檔執行
agent -p "依 temp/cursor-cli-task-config-cleanup.md 執行任務" `
  --workspace "D:\Source\daily-digest-prompt" `
  --model composer-2-fast
```

---

### ✗ 錯誤做法 2：外部功能改為「請手動執行」

```markdown
# 任務檔（錯誤）
## 步驟 3：匯入知識庫
請手動執行 knowledge-query 匯入。（CLI 不執行）
```

### ✓ 正確做法 2：先在 CLI 內執行，失敗才 fallback

```markdown
# 任務檔（正確）
## 步驟 3：匯入知識庫
依 skills/knowledge-query/SKILL.md 執行 Invoke-RestMethod 匯入。
若連線失敗（HTTP 非 2xx 或逾時），記錄錯誤並輸出手動步驟。
```

---

### ✗ 錯誤做法 3：排程任務漏加 --workspace

```powershell
# 錯誤：寫入型任務未限定工作區
agent -p "更新 state/run-fsm.json" --trust
```

### ✓ 正確做法 3：明確指定 workspace

```powershell
agent -p "依 temp/cursor-cli-task-fsm-update.md 執行任務" `
  --workspace "D:\Source\daily-digest-prompt" `
  --model composer-2-fast `
  --trust
```

---

## 5. 任務檔標準模板

建立路徑：`temp/cursor-cli-task-<任務簡稱>.md`

```markdown
# Cursor CLI 任務：<任務簡稱>

## 任務目標
<一句話描述目標>

## 前置確認
- [ ] 已查閱 skills/SKILL_INDEX.md，確認使用 Skill：<列出 Skill 名稱>
- [ ] 外部功能先行執行規則已列入各相關步驟

## 執行步驟
1. <步驟一>（若涉及外部 API/Skill，明確標注：「必須在 CLI 內執行，失敗才 fallback」）
2. <步驟二>
3. ...

## 使用 Skill
- <Skill 名稱>：<用途>（讀取路徑：skills/<skill-name>/SKILL.md）

## 回報格式
任務完成後輸出：
- 執行結果摘要
- 變更的檔案清單（若有）
- 外部功能執行狀態（成功/fallback）
- 下一步建議（若有）
```

---

## 6. 本專案推薦用法（Windows PowerShell）

### 6.1 標準流程：建立任務檔後執行（必循）

```powershell
# Step 1: 建立任務檔（用 Write 工具或手動）
# temp/cursor-cli-task-<名稱>.md

# Step 2: 執行（參照任務檔）
agent -p "依 temp/cursor-cli-task-<名稱>.md 執行任務" `
  --workspace "D:\Source\daily-digest-prompt" `
  --model composer-2-fast
```

### 6.2 常用指令速查

```powershell
# 單次任務（純文字輸出）
agent -p "依 temp/cursor-cli-task-xxx.md 執行任務" --workspace "D:\Source\daily-digest-prompt"

# 腳本可解析（JSON）
agent -p "依 temp/cursor-cli-task-xxx.md 執行任務" --output-format json --workspace "D:\Source\daily-digest-prompt"

# 唯讀分析（不寫檔）
agent -p "依 temp/cursor-cli-task-xxx.md 執行任務" --mode=ask --workspace "D:\Source\daily-digest-prompt"

# 先規劃再執行（Plan 模式）
agent -p "依 temp/cursor-cli-task-xxx.md 執行任務" --plan --workspace "D:\Source\daily-digest-prompt"

# 排程 / 無頭（信任工作區）
agent -p "依 temp/cursor-cli-task-xxx.md 執行任務" --workspace "D:\Source\daily-digest-prompt" --trust
```

---

## 7. 參數速查（-p 情境常用）

| 參數 | 說明 |
|------|------|
| `-p`, `--print` | 非互動，輸出到 stdout，完整工具權限 |
| `--output-format text\|json\|stream-json` | 僅與 -p 有效；預設 text |
| `--stream-partial-output` | 僅與 -p + stream-json 有效 |
| `--model <id>` | 本 Skill 預設推薦：`composer-2-fast`；另可 `composer-2`、`composer-1.5` 等；`agent models` 列出 |
| `--mode plan\|ask` | plan=先釐清再執行；ask=唯讀 |
| `--workspace <path>` | 工作區目錄（建議本專案用絕對路徑）**寫入型任務必填** |
| `--trust` | 無頭時信任工作區不再次詢問 |
| `-f`, `--force`, `--yolo` | 強制允許指令（慎用） |
| `--sandbox enabled\|disabled` | 沙箱開關 |

---

## 8. 與專案既有流程的關係

| 情境 | 建議 |
|------|------|
| 每日摘要 / Todoist 三階段 | 仍以 **run-agent-team.ps1**、**run-todoist-agent-team.ps1** 為主 |
| 單次程式碼任務、重構、審查 | 使用 **cursor-cli**（agent -p） |
| 任務涉及知識庫 / 通知 / API / 研究等 | **積極採用對應 Skill**，在 CLI 內依 Skill 指示執行，以提升功能與一致性 |
| 需與 MCP / 專案規則一致 | CLI 會讀 `.cursor/mcp.json`、`CLAUDE.md`、`.cursor/rules/`，無需重複配置 |
| 排程內呼叫 Agent | 用 pwsh 執行 + `--workspace` + `--trust`，注意 -p 具完整寫入權限 |

---

## 9. 禁止事項（違者視為規則違反）

| 禁止行為 | 原因 |
|----------|------|
| 未建立任務檔即以游離 prompt 執行具結構的任務 | 無法追蹤、審計困難、步驟易遺漏 |
| 未指定 `--workspace` 的排程中執行寫入型 `agent -p` | 可能寫入錯誤目錄 |
| 實際執行前跳過外部功能，改為「請手動執行」 | 違反外部功能先行原則，降低自動化效能 |
| 使用 `--force`/`--yolo` 於敏感或共用環境 | 安全風險 |
| 任務涉及 Skill 但未查閱 SKILL_INDEX.md | 重複造輪，偏離專案最佳實踐 |

---

## 10. 參考

- 知識庫：`docs/research/研究報告_cursor-cli-agent-print_20260314.md`
- 模型：[推出 Composer 2](https://cursor.com/zh-Hant/blog/composer-2)（`composer-2-fast` / `composer-2`）
- 官方：[Cursor CLI Overview](https://cursor.com/docs/cli/overview)、[Parameters](https://cursor.com/docs/cli/reference/parameters)
