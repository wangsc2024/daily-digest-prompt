---
name: workflow-forge
version: "1.0.0"
description: |
  Workflow 鑄造廠。運用流程標準化提升系統品質與輸出內容穩定度，避免輸出格式錯誤，優化系統一致性。
  分析 config/*.yaml、prompts、results 輸出規範，識別格式與一致性缺口，產出或更新工作流定義、輸出 Schema、驗證規則，並整合至專案配置。
  Use when: 排程自動流程標準化、輸出格式規範化、工作流定義補齊、系統一致性優化。
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "workflow-forge"
  - "workflow 鑄造"
  - "流程標準化"
  - "輸出格式規範"
  - "工作流定義"
  - "系統一致性"
  - "格式驗證"
  - "結果 Schema"
  - "輸出標準化"
  - "工作流 YAML"
  - "驗證清單"
depends-on:
  - knowledge-query
  - system-insight
  - ntfy-notify
  - config/dependencies.yaml
---

# Workflow Forge — 流程標準化與輸出穩定度鑄造廠

> **端點來源**：`config/dependencies.yaml`（ADR-001 Phase 3）— 請讀取 YAML 取得對應 base_url（deps key: ntfy_notify）。

## 設計目標

- **流程標準化**：將反覆執行的步驟固化成可驗證的 YAML/配置，減少人為歧異。
- **輸出穩定度**：為關鍵輸出（如 `results/todoist-auto-*.json`）訂定 Schema 或必填欄位，避免格式錯誤。
- **系統一致性**：對齊 config、prompts、templates 的命名與結構，優化跨模組一致。

執行鏈：
```
觀測（config + prompts + 失敗案例）→ 識別（格式/一致性缺口）→ 設計（工作流或 Schema）
→ 生成（YAML/JSON Schema）→ 驗證（格式 + 必填）→ 整合（config 或 workflows/）→ 通知
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立現有 Skill 地圖）
3. 讀取 `docs/ARCHITECTURE.md` 或 `CLAUDE.md` 中與「文件驅動」「配置」相關段落，掌握 config 與 prompt 的職責邊界

---

## 步驟 1：工作流與輸出現況掃描

並行讀取以下來源，建立「現況清單」：

**1a. 配置類**
- `config/pipeline.yaml`：管線步驟與 output_section
- `config/routing.yaml`：路由規則與 max_tasks_per_run
- `config/cache-policy.yaml`：TTL 與 cache_key 對應
- `config/ooda-workflow.yaml`：OODA 狀態與 state_file
- `config/frequency-limits.yaml`：tasks 的 template、result_suffix、timeout_seconds

**1b. 輸出規範**
- 以 Grep 搜尋 `results/todoist-auto-*.json` 的產出處（prompts/team/todoist-auto-*.md 內 "Write.*results/"）
- 彙整各任務的結果 JSON 必填欄位（如 agent、status、task_key）與常見選填欄位
- 讀取 `context/system-insight.json` 的 `alerts`、`recommendations`，篩選與「格式」「一致性」「輸出錯誤」相關的項目

**1c. 失敗或告警信號**
- 讀取 `state/failed-auto-tasks.json`（若存在）：記錄哪些任務常因 result 格式缺失失敗
- 讀取 `context/improvement-backlog.json`：篩選與「流程」「格式」「標準化」相關的項目

**輸出**：產生「缺口清單」（每項含：類型=格式/一致性/缺失、來源檔案、建議產物、優先級 P0/P1/P2）

---

## 步驟 2：優先級與可執行性篩選

對缺口清單評分（滿分 100），選出**本次執行 1 項**：

- **影響範圍（0–40）**：影響多個自動任務或每日摘要 → 高分；僅單一腳本 → 低分
- **可執行性（0–35）**：僅需新增/修改 YAML 或 JSON Schema、不需改動程式碼 → 高分；需改 PowerShell 核心邏輯 → 低分
- **信號強度（0–25）**：來自 failed-auto-tasks 或 system-insight critical → 高分；來自 improvement-backlog P2 → 低分

**開創性門檻**：本次產物是否為「新」工作流定義或「新」輸出 Schema（非僅重複既有檔案內容）？若否，選次高缺口。

**輸出**：選定 1 個缺口，明確「產物類型」（workflow YAML / output schema / 驗證清單）與「產物路徑」。

---

## 步驟 3：設計產物規格

依選定缺口類型撰寫規格（不產出檔案，僅規格）：

- **若為 workflow YAML**：步驟順序、每步輸入/輸出、對應 config 鍵、與現有 pipeline/routing 的對齊方式
- **若為 output schema**：必填欄位（agent、status、task_key 等）、選填欄位、型別與範例值，對應 `results/todoist-auto-{key}.json`
- **若為驗證清單**：檢查項目（如「所有 todoist-auto-*.md 內結果 JSON 含 agent 欄位」）、檢查方式（Grep / 小腳本）

將規格寫入 `context/workflow_forge_spec.json`（用 Write），供步驟 4 依此生成。

---

## 步驟 4：生成產物

依 `context/workflow_forge_spec.json` 的規格產出實體檔案：

- **Workflow YAML**：寫入 `workflows/`（新檔）或 `config/`（若為配置擴充），符合專案 YAML 風格（注釋、鍵名與 config 一致）
- **Output Schema**：寫入 `config/schemas/`（JSON Schema 格式）或 `workflows/`（Markdown 規格檔）
- **驗證清單**：寫入 `workflows/`（如 `workflows/validation-checklist.md`）

**約束**：不修改 `state/scheduler-state.json`、`config/frequency-limits.yaml` 的 tasks 區塊（僅可新增獨立檔案或 config 內新鍵）；不刪除既有 config 鍵。

**產出後必須執行（步驟 4 結束前）**：

1. 讀取 `workflows/index.yaml`（不存在則用以下結構初始化）：
   ```yaml
   version: "1.0.0"
   updated_at: ""
   description: "workflow-forge 產出物索引，Agent 執行前依 task_type 篩選適用 workflow"
   entries: []
   ```
2. 在 `entries[]` **開頭**插入新 entry：
   ```yaml
   - id: "wf-{YYYYMMDD}-{artifact_slug}"
     path: "{artifact_path}"           # 統一使用 workflows/ 前綴
     type: "{workflow_yaml|output_schema|validation_checklist|report|code|config|documentation}"
     title: "{產物標題（10-20 字）}"
     version: "1.0.0"
     created_at: "{YYYY-MM-DD}"
     task_types:
       - "{適用 task_key 或 all}"
     priority: "{P0|P1|P2}"
     summary: "{缺口描述（30-50 字）}"
     read_when: "{always|producing_results_json|developing_or_reviewing_prompt}"
   ```
3. 更新頂層 `updated_at` 為今日日期（YYYY-MM-DD）
4. 用 Write 工具完整覆寫 `workflows/index.yaml`
5. **所有新產出的 workflow 檔案一律寫入 `workflows/`**（不再寫 `docs/workflows/`）

---

## 步驟 5：格式驗證

- **YAML**：`uv run python -c "import yaml; yaml.safe_load(open('...'))"` 確認可解析
- **JSON Schema**：若有 JSON Schema 檔，以 `jsonschema` 或簡短 Python 驗證其為合法 Schema
- **必填欄位對齊**：若產物為 schema，以 Grep 抽樣 2～3 個 `prompts/team/todoist-auto-*.md` 確認所述必填欄位與 schema 一致

若驗證失敗，用 Edit 修正，最多 **2 輪**。2 輪後仍失敗 → 結果 JSON 設 `status: "format_failed"`，跳至步驟 8。

---

## 步驟 6：整合與登記

- 若產物為新檔：在 `docs/ARCHITECTURE.md` 或 `config/README.md` 中新增一筆說明（標題 + 路徑 + 一句用途），或更新 `config/README.md` 的配置速查表
- 若產物為擴充既有 config：在該 YAML 頂部注釋或 README 中註明本次新增鍵的用途
- 將本次產物路徑、缺口類型、優先級寫入 `context/workflow-forge-registry.json`（若不存在則建立；格式：`{"entries": [{"date": "YYYY-MM-DD", "artifact_path": "...", "gap_type": "...", "priority": "P1"}]}`），供日後去重與追蹤

**步驟 6 結束前必須執行：同步更新 `config/agent-extra-reads.yaml`**

讀取 `config/agent-extra-reads.yaml`，在 `task_type_mapping` 下新增或更新 entry：
- 若產物的 `task_types` **包含特定 task_key**（非 `"all"`），新增對應映射：
  ```yaml
  {task_key}:
    reads:
      - path: "{artifact_path}"
        purpose: "{summary 前 30 字}"
        when: "always"
    enabled: true
  ```
- 若 `task_type_mapping` 下已存在該 task_key，在其 `reads[]` 末尾 **append** 新項目（不替換）
- 若產物 `task_types` 僅含 `"all"`，跳過此步驟（全局 workflow 由 preamble 統一處理）
- 用 Write 工具完整覆寫 `config/agent-extra-reads.yaml`（保留原有頂層結構和其他 task_key）

---

## 步驟 7：匯入知識庫（可選）

讀取 `skills/knowledge-query/SKILL.md`，將本次「工作流鑄造報告」匯入 KB（title 含 "workflow-forge"，tags 含 "workflow-forge", "流程標準化"）。若 KB 不可用，記錄 `kb_imported: false`，不影響 status。

---

## 步驟 8：通知與結果 JSON

### 8a. ntfy 通知

依 `status` 用 Write 建立 `ntfy_workflow_forge.json` 再 curl POST 至 `https://ntfy.sh`（Content-Type: application/json; charset=utf-8，-d @ntfy_workflow_forge.json）：

| status           | title                          | priority |
|------------------|--------------------------------|----------|
| success / partial | 🔧 workflow-forge：{產物名稱} 已產出 | 3        |
| format_failed    | ❌ workflow-forge：格式驗證失敗   | 4        |

### 8b. 結果 JSON

用 Write 建立 `results/todoist-auto-workflow_forge.json`：

```json
{
  "agent": "todoist-auto-workflow_forge",
  "task_key": "workflow_forge",
  "status": "success",
  "artifact": {
    "path": "產物路徑",
    "type": "workflow_yaml | output_schema | validation_checklist",
    "gap_addressed": "缺口簡述"
  },
  "integration_status": "integrated",
  "kb_imported": true
}
```

`status` 取值：`success`、`partial`（KB 未匯入但產物已整合）、`format_failed`。

---

## 降級處理

- **缺口清單為空**：從 improvement-backlog 選一項與「流程/格式」最相關者，產出對應的驗證清單或小改動建議，仍寫入結果 JSON，status 設為 `partial`，message 註明「無高優先級缺口，已產出建議清單」。
- **步驟 4 無法在不改核心 config 前提下產出**：改為產出 `workflows/` 下「建議變更」Markdown，不直接改 config，integration_status 設為 `proposed`。
