你是 Todoist 結果組裝 Agent，全程使用正體中文。
你的任務是讀取所有 Phase 1+2 結果，關閉已完成的 Todoist 任務，更新頻率計數與歷史追蹤，最後發送 ntfy 通知。
不要重新查詢 Todoist API、不要重新執行任務。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

必須先讀取以下 SKILL.md：
- `skills/todoist/SKILL.md`（關閉任務、新增評論）
- `skills/ntfy-notify/SKILL.md`（發送通知）

---

## 步驟 1：讀取所有結果

### 1.1 讀取計畫
用 Read 讀取 `results/todoist-plan.json`，了解 `plan_type`。

### 1.2 讀取 Phase 2 結果
根據 plan_type 讀取對應結果檔案：

**plan_type = "tasks"**：
- 讀取所有 `results/todoist-result-*.json`（可能 1-3 個）
- 若檔案不存在 → 該任務標記為 failed

**plan_type = "auto"**：
- 讀取所有 `results/todoist-auto-*.json`（自動任務結果，可能有多種類型）
- 結果檔案命名格式：`todoist-auto-{task_key}.json`（如 `todoist-auto-shurangama.json`）

**plan_type = "idle"**：
- 無 Phase 2 結果

---

## 步驟 1.5：快取狀態確認（Harness 合規）

用 Read 讀取 `cache/todoist.json`：
- 存在 → 記錄 `cached_at`，供後續步驟參考
- 不存在 → 略過，繼續步驟 2

> 此步驟確保 session 內有 `cache-read` + `todoist` 標籤，避免 Harness 快取繞過警告。

---

## 步驟 1.6：更新 API 健康狀態（Circuit Breaker）

此步驟讀取 Phase 1 的結構化日誌，統計 Todoist API 呼叫結果，並更新 `state/api-health.json`。

**執行方式**（使用內嵌 Python 腳本）：
```bash
TODAY=$(date +%Y-%m-%d)
cat "logs/structured/$TODAY.jsonl" 2>/dev/null | python -c "
import json
import sys
sys.path.insert(0, 'hooks')
from agent_guardian import CircuitBreaker

api_results = []
for line in sys.stdin:
    if not line.strip():
        continue
    try:
        record = json.loads(line)
        tags = record.get('tags', [])
        error_category = record.get('error_category')
        if 'todoist' in tags and 'api-call' in tags:
            is_failure = error_category in ['server_error', 'network_error']
            api_results.append(not is_failure)
    except:
        pass

if api_results:
    breaker = CircuitBreaker('state/api-health.json')
    breaker.record_result('todoist', success=api_results[-1])
    print(f'Updated todoist circuit breaker: {api_results[-1]}')
"
```

---

## 步驟 2：關閉 Todoist 任務（僅 plan_type = "tasks" 時）

對每個 Phase 2 結果中 status = "success" 的任務：

### 2.1 關閉任務
```bash
curl -s -X POST "https://api.todoist.com/api/v1/tasks/TASK_ID/close" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

### 2.2 記錄已關閉 ID
讀取 `context/auto-tasks-today.json`，將 TASK_ID 加入 `closed_task_ids`，用 Write 覆寫。

### 2.3 附加成功評論
用 Write 建立 `comment.json`：
```json
{
  "task_id": "TASK_ID",
  "content": "✅ Claude Code 自動完成（團隊模式）\n- 品質分: N/5\n- 產出: [摘要]\n- 驗證: 通過"
}
```
```bash
curl -s -X POST "https://api.todoist.com/api/v1/comments" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @comment.json
rm comment.json
```

### 2.4 失敗任務處理
對 status ≠ "success" 的任務：
- 不關閉
- 降低優先級（若 priority > 1）
- 用 Write 建立 `update.json`：`{"priority": N-1, "due_string": "tomorrow"}`
- `curl -s -X POST "https://api.todoist.com/api/v1/tasks/TASK_ID" -H "Authorization: Bearer $TODOIST_API_TOKEN" -H "Content-Type: application/json; charset=utf-8" -d @update.json`
- `rm update.json`
- 附加失敗評論

---

## 步驟 2.5：完成後自動任務觸發判斷

**僅在 plan_type = "tasks" 且至少有 1 個 Phase 2 結果 status = "success" 時執行。**

1. 重新查詢 Todoist 今日待辦：
```bash
curl -s "https://api.todoist.com/api/v1/tasks/filter?query=today" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```
2. 對結果執行截止日期過濾 + 已關閉 ID 過濾（含本次步驟 2 剛關閉的 ID）
3. 用前置過濾（排除實體行動等）+ Tier 1/2/3 路由判斷可處理項目
4. 若可處理項目 = 0 且自動任務未達上限：
   - 讀取 `context/auto-tasks-today.json` 檢查頻率
   - 依 config/frequency-limits.yaml 輸出可執行的自動任務
   - 記錄到通知中：`🔄 今日任務全部完成，建議下次執行自動任務：[任務名稱]`
   - **注意**：團隊模式下，自動任務不在此步驟執行，僅記錄建議（下次排程執行）
5. 若仍有可處理項目 → 輸出「仍有 N 筆可處理待辦，不觸發自動任務」

---

## 步驟 3：更新頻率計數（僅 plan_type = "auto" 時）

讀取 `context/auto-tasks-today.json`，根據 Phase 2 結果更新：

對每個存在的 `results/todoist-auto-*.json` 結果檔案：
1. 從結果 JSON 中讀取 `type` 欄位（如 `shurangama`、`tech_research`）
2. 查找 `config/frequency-limits.yaml` 中對應的 `counter_field`
3. 將該欄位 +1

用 Write 覆寫整個 JSON。

---

## 步驟 4：更新歷史追蹤

用 Read 讀取 `state/todoist-history.json`（不存在則初始化 `{"auto_tasks":[],"daily_summary":[]}`）。

### 4.1 auto_tasks（plan_type = "auto" 時）
對每個 Phase 2 結果，在 `auto_tasks` 末尾加入：
```json
{
  "date": "今天日期",
  "timestamp": "ISO 8601",
  "type": "任務類型（如 shurangama, tech_research, ai_deep_research 等）",
  "topic": "研究主題（若適用）或 null",
  "findings": "審查發現數（Log/Skill 審查）或 null",
  "fixes": "修正數或 null",
  "commit_hash": "commit hash（Git push）或 null",
  "note_id": "知識庫筆記 ID（研究類）或 null",
  "status": "success 或 failed 或 no_changes"
}
```

### 4.2 daily_summary
查找今天日期條目：
- 存在 → 更新計數
- 不存在 → 新增
```json
{
  "date": "今天日期",
  "auto_task_counts": "從 auto-tasks-today.json 複製所有 *_count 欄位",
  "todoist_completed": "本次完成數",
  "total_executions": "累計或 1"
}
```

保留最近 200 條 auto_tasks、30 條 daily_summary。用 Write 覆寫。

---

## 步驟 5：發送 ntfy 通知
**使用 Skill**：`ntfy-notify`

讀取 `skills/ntfy-notify/SKILL.md`。

### 通知內容

**plan_type = "tasks"**：
```
📋 Todoist 自動執行報告（團隊模式）

📊 統計
- 待辦總數：N 項 | 已執行：N 項（成功 N / 失敗 N）
- 已跳過：N 項

✅ 已完成
1. [任務名稱] — Tier N | Skill: [...] | 品質: N/5

❌ 失敗（如有）
1. [任務名稱] — 殘留: [...]

⏭️ 已跳過（如有）

🔧 Skill 使用
- 路由：標籤 N / 關鍵字 N / 語義 N
- ⚡ 團隊並行模式
```

**plan_type = "auto"**：
```
📋 Todoist 自動任務報告（團隊模式）

🔧 自動任務
- [任務名稱]：[主題/結果摘要] / 成功/失敗
 （依實際執行的自動任務類型列出）

📊 今日自動任務進度：已用 N / 上限 38

⚡ 團隊並行模式
```

**plan_type = "idle"**：
```
📋 Todoist 報告
- 無可處理待辦
- 今日自動任務已達上限
```

### Skill 同步警告（附加於通知末尾）
讀取 plan JSON 的 `sync_warnings`，若 `unmatched_labels` 非空，在通知末尾加入：
```
⚠️ Skill 同步提醒
- 未匹配標籤：[列表]
```

### 發送步驟
1. 用 Write 建立 `ntfy_temp.json`（UTF-8）
2. `curl -H "Content-Type: application/json; charset=utf-8" -d @ntfy_temp.json https://ntfy.sh`
3. `rm ntfy_temp.json`

### ntfy tags
- tasks 成功 → `["white_check_mark"]`
- tasks 有失敗 → `["warning"]`
- auto 成功 → `["books", "wrench"]`
- idle → `["information_source"]`

---

## 步驟 6：清理 results/

```bash
rm -f results/todoist-plan.json results/todoist-task-*.md results/todoist-result-*.json
rm -f results/todoist-auto-*.json
```

---

## 完成
所有步驟已完成，任務結束。
