# 共用前言（所有 Agent prompt 引用此文件）

## 語言
全程使用正體中文。

## Agent 角色聲明（改善日誌可讀性）

執行前，在輸出的第一行加入角色聲明：
```
[FETCH] 我的角色：fetcher（API 呼叫與資料抓取）
```
將 `[FETCH]` 替換為 `config/agent-roles.yaml` 中對應角色的 `log_prefix`（fetcher/analyst/assembler/auditor）。
若不確定角色或任務跨角色，略過此步驟，不影響執行。

## Skill-First 核心規則
1. **先讀索引**：執行前必須先讀取 `skills/SKILL_INDEX.md`，建立完整的 Skill 認知地圖
2. **先讀 SKILL.md 再動手**：每個步驟都必須先讀取對應的 SKILL.md，嚴格依指示操作
3. **能用 Skill 就用 Skill**：禁止自行拼湊 API 呼叫或邏輯
4. **Skill 鏈式組合**：積極串聯多個 Skill（如：todoist → knowledge-query → ntfy-notify）
5. **所有外部 API 必經 api-cache**：任何 curl 呼叫前，必須先走快取流程

## Workflow 自動引用規則

若你是 `todoist-auto-*` 自動任務，在執行主要步驟**之前**：
1. 讀取 `workflows/index.yaml`（不存在則略過）
2. 找出 `task_types` 包含你的 task_key 或 `"all"` 的 entries
3. 用 Read 工具讀取匹配的 workflow 文件，遵守其規範
4. 無匹配或 index 不存在 → 略過，繼續主任務

## 禁止行為
- 不讀 SKILL.md 就直接呼叫 API
- 自行拼 curl 指令而不參考 SKILL.md 中的正確格式
- 跳過 api-cache 直接呼叫外部服務
- 執行結束不更新記憶和狀態

## ⚡ Shell 執行強制規則（所有 todoist-auto-*.md 適用）

> **任何 Shell 命令都必須用 Bash tool 實際執行，不得只輸出命令文字。**

| 命令類型 | 強制事項 |
|---------|---------|
| `curl` / `pwsh` / `git` / `uv run` / `python` | 必須用 Bash tool 執行，不得只描述 |
| `cat task_prompt.md \| claude -p` | 必須用 Bash tool 執行；先用 Write 工具建立 task_prompt.md，再 Bash 執行 claude -p |
| 每個關鍵 Shell 步驟 | 執行後立即確認輸出（ls / grep / echo 確認） |
| `status: "success"` | 只能在確認實際輸出存在後才能寫入 |

**違反症狀**：Agent 輸出「建議步驟」文字、「以下命令可執行...」等描述性語言，而未看到 Bash tool 的呼叫紀錄。

## 結果檔案寫入前驗證

寫入 `results/` JSON 前，建議呼叫 middleware 驗證確保必填欄位（task_type/task_key/status/summary）完整。缺失欄位可由 auto_fix_tier1() 自動補上。

## 知識庫寫入確認規則

所有 `POST /api/import` 或 `POST /api/notes` 執行後，**必須**確認寫入成功：

```bash
# 儲存回應到暫存檔後確認
curl -s -X POST "http://localhost:3000/api/import" \
  -H "Content-Type: application/json" \
  -d @note.json > /tmp/kb-import-result.json

# 確認回應含 id 欄位
grep -q '"id"' /tmp/kb-import-result.json && echo "✅ KB 寫入成功" || echo "❌ KB 寫入失敗"
```

- 回應含 `"id"` → 記錄 note_id，繼續
- 回應不含 `"id"` 或 curl 失敗 → 結果 JSON 的 `status` 改為 `"partial"`，記錄錯誤原因

## Context 保護：重量操作委派子 Agent

當任務需要**讀取 5 個以上檔案**或**執行耗時搜尋**時，必須用 Agent 工具委派子 Agent，主 Agent 只接收摘要 JSON：

| 操作類型 | 委派方式 |
|---------|---------|
| 讀取多個 SKILL.md / log 檔案 | `subagent_type=Explore`，指定搜尋範圍 |
| 複雜分析（log 審查、狀態比對） | `subagent_type=general-purpose`，傳回結構化結果 |
| 研究 / WebFetch 多篇 | `subagent_type=general-purpose`，傳回摘要 |

> **禁止**：主 Agent 直接累積大量檔案內容後再分析（OOM 風險）。
> **正確**：子 Agent 分析後傳回 ≤ 200 行 JSON 摘要，主 Agent 根據摘要決策。

## 自動任務連續記憶規則（所有 todoist-auto-*.md 適用）

若你是一個自動任務（結果寫入 `results/todoist-auto-{task_key}.json`），必須遵守以下連續記憶協議：

### 任務開始前：讀取歷史執行記錄
在執行主要任務**之前**（第一個實質步驟之前），執行：
```
Read context/continuity/auto-task-{task_key}.json
```
（不存在則略過）

從 `runs[]` 最近 5 筆中提取：
- **上次研究的 topic** → 本次選擇不同角度或繼續深化
- **key_findings** → 避免重複已知結論，從上次的基礎繼續推進
- **next_suggested_angle** → 若有此欄位，優先考慮此方向
- **kb_note_ids** → 本次研究應排除（已整合到知識庫的筆記）

### 任務完成後（包含失敗路徑）：寫入本次執行記錄
在寫入最終結果檔 `results/todoist-auto-{task_key}.json` **之後**（無論 status 為 success、failed 或 partial）、結束之前，執行：
> **失敗路徑也必須寫入**：若任務因錯誤提早終止，仍需嘗試寫入 continuity（`status: "failed"`），確保下次執行能感知到失敗歷史。

1. Read `context/continuity/auto-task-{task_key}.json`（不存在則初始化 `{"task_key":"<key>","schema_version":1,"max_runs":5,"runs":[]}`）
2. 在 `runs[]` **開頭**插入本次記錄：
```json
{
  "executed_at": "<ISO 8601>",
  "topic": "<本次研究/處理的核心主題（10-20 字）>",
  "status": "<completed|failed|partial>",
  "key_findings": "<2-3 句：本次最重要的發現或成果>",
  "kb_note_ids": ["<匯入知識庫的 note_id>"],
  "next_suggested_angle": "<下次可以繼續探索的方向（10-20 字），若無則留空>"
}
```
3. 若 `runs` 超過 `max_runs`（5）則移除最舊的
4. 用 Write 工具完整覆寫 `context/continuity/auto-task-{task_key}.json`

> **重要**：`{task_key}` 為此 prompt 對應的任務鍵（與 `results/todoist-auto-{task_key}.json` 相同）。

---

## Context 壓縮感知（ADR-036）

在每個主要步驟開始前，檢查是否存在 `state/context-compression-hint-{SESSION_ID前8字}.txt`：
- 若存在且非空：讀取並按指示壓縮工作記憶，然後刪除此檔案繼續執行
- 若不存在：正常執行

此機制由 Hook 系統（post_tool_logger.py）自動觸發，無需手動管理。
壓縮策略：65-80% 使用率 → BufferWindow（保留最近 5 次關鍵結果）；> 80% → Summary（強制壓縮）。

---

## 重要禁令：禁止產生 nul 檔案
- 絕對禁止在 Bash 指令中使用 `> nul`、`2>nul`、`> NUL`，這會在 Windows 上產生名為 nul 的實體檔案
- 絕對禁止用 Write 工具建立名為 nul 的檔案
- 需要抑制輸出時改用 `> /dev/null 2>&1`
- 刪除暫存檔時直接用 `rm filename`，不要重導向到 nul
