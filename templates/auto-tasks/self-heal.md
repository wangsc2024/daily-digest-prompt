---
name: "self-heal"
template_type: "auto_task_template"
version: "1.0.0"
released_at: "2026-03-20"
---
# 自動任務：自癒迴圈

> 由 round-robin 自動觸發，每日最多 1 次（`config/frequency-limits.yaml` daily_limit: 1）

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則。

## 前置檢查（降級機制）
用 Read 讀取 `context/system-insight.json`：
- 若不存在或修改時間超過 24 小時 → 跳過步驟 1 的資料分析，僅執行步驟 2 中不依賴該檔案的修復項（b/c/d/e/g）
- 在報告中標註「system-insight 資料不可用，部分檢查已跳過」

## 自癒流程

### 步驟 1：分析系統健康（需 system-insight.json）
讀取 `context/system-insight.json`（由 system-insight Skill 產生）：
- 分析 alerts 中是否有 critical 等級
- 識別 high_failure_hours（高失敗率時段）
- 檢查 skill_usage_coverage 是否偏低

### 步驟 2：識別並修復可自動修復的問題

#### a. [需 system-insight] 高失敗率 API 快取清除
- 若某 API 來源失敗率 > 30% → 刪除對應 `cache/*.json` 強制下次重抓
- 支援的快取：todoist.json, pingtung-news.json, hackernews.json, gmail.json

#### b. research-registry.json 過期清理
- 讀取 `context/research-registry.json`
- 移除 entries 中日期超過 7 天的條目，欄位讀取優先序：
  1. `entry["date"]`（YYYY-MM-DD 字串，用 `datetime.date.fromisoformat()` 解析）← **主要欄位**
  2. `entry["timestamp"]`（ISO 8601，`datetime.datetime.fromisoformat()` 後取 `.date()`）← 備援
  3. 兩個欄位**都不存在**→ **保留**該條目，記錄 `"skip(no date field)"` 到日誌，不拋出 KeyError
- 保持 `version` 欄位不變

#### c. auto-tasks-today.json 跨日歸零
- 讀取 `context/auto-tasks-today.json`
- 若 date 欄位 ≠ 今天 → 重置所有計數為 0，保留 `next_execution_order`

#### d. logs/structured/ 單檔大小檢查
- 用 Bash 檢查 `logs/structured/` 下所有 .jsonl 檔案大小
- 若任何檔案 > 50MB → 輪轉（重命名為 .rotated，僅保留最新 1 個）

#### e. run-once-*.ps1 殘留清理
- 掃描專案根目錄的 `run-once-*.ps1` 和 `task_prompt_once*.md`
- 對每個檔案，檢查對應 Windows 排程是否存在
- 若排程不存在 → 安全刪除殘留檔案

#### f. Chatroom 整合健康檢查（G28）
用 Read 讀取 `state/api-health.json`：
- 找出 `gun-bot` 的 circuit_breaker 狀態
- 若 state="open"（API 連續失敗）→ 刪除 `cache/chatroom.json`（強制下次重抓）+ 記錄到 alerts

用 Bash 檢查 `cache/chatroom.json` 修改時間：
```bash
uv run --project D:/Source/daily-digest-prompt python -c "
import json, os, datetime
path = 'cache/chatroom.json'
if os.path.exists(path):
    age = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(path))
    print(f'age_minutes:{int(age.total_seconds()/60)}')
    with open(path) as f:
        data = json.load(f)
    print(f'source:{data.get(\"source\",\"unknown\")}')
else:
    print('age_minutes:-1')
"
```
- 若 age_minutes > 120 且 source != "api" → 刪除 `cache/chatroom.json`（過期降級快取清理）
- 若 age_minutes = -1（不存在）→ 正常，無需處理

#### g. done-certs 過期清理（P5-A）
掃描 `state/done-certs/` 目錄，刪除超過 24 小時的舊憑證檔案：
```bash
uv run --project D:/Source/daily-digest-prompt python -c "
from tools.agent_pool.done_cert import cleanup_stale_certs
result = cleanup_stale_certs(max_age_hours=24)
print(f'done-certs 清理：移除 {result[\"removed\"]} 個過期憑證')
"
```
- 若 `state/done-certs/` 不存在 → 跳過（正常，代表 P5-A 尚未啟用）
- 記錄清理數量到日誌

#### h. arch-decision.json 架構決策修復（來自 arch-evolution）

先讀取 `context/workflow-state.json`（用於判斷 OODA 狀態），再依以下四分支處理 `context/arch-decision.json`：

**分支 1**：`arch-decision.json` 存在 且 `generated_at` 距今 ≤ 48 小時
→ 正常執行（見下方執行邏輯）

**分支 2**：`arch-decision.json` 存在 但 `generated_at` 距今 > 48 小時
→ 跳過此步驟 + 發送 warning 通知（priority: 3）：「arch-decision.json 已過期（>48h），等待下次 arch-evolution 更新」

**分支 3**：`arch-decision.json` 不存在 且 `workflow-state.json` 的 `history` 中有 `step=decide` 的 completed 記錄
→ 發送 critical 通知（priority: 4）：「arch-decision.json 遺失，但 decide 步驟已執行，請確認檔案是否被意外刪除」
→ 跳過此步驟

**分支 4**：`arch-decision.json` 不存在 且 `workflow-state.json` 無 decide completed 記錄
→ 記錄 info（priority: 2）：「OODA 尚未執行到 Decide 步驟，屬正常狀態」
→ 跳過此步驟

**分支 1 的執行邏輯**（`execution_status` 狀態機）：
**篩選條件**（必須**同時**滿足，才列入可執行清單）：
- `action === "immediate_fix"`（僅執行架構決策標記為 immediate_fix 的項目）
- `execution_status === "pending"` 或（`execution_status === "failed_retry"` 且 `retry_count < 3`）

依上條件篩選後，取前 3 項（每次最多執行 3 項，避免單次修復過多）。若篩選結果為 0 項，必須在報告中明確寫出：「arch-decision 可執行 0 項（原因：無 action=immediate_fix 且 execution_status=pending 的條目）」，方便事後查 log 與 schema 是否一致。

**【動手前 git 備份】**（可執行清單 > 0 項時必須執行）：

收集所有待執行項目的 `related_files` 聯集（去重），執行：
```bash
cd D:/Source/daily-digest-prompt && git add {related_files 清單} && git commit -m "backup: self-heal 執行前備份（{N} 個 immediate_fix 待執行：{ADR-ID 清單}）"
```
- 若 `related_files` 為空，則 `git add -A`，備份整體狀態
- 若 git commit 失敗（例如無變更），記錄 `"git backup: no changes to commit"` 並繼續執行（不中止）
- 備份完成後，記錄 commit hash 供後續 ntfy 通知使用

對每個可執行的 immediate_fix 項目：
1. 閱讀 `fix_instructions`，確認操作安全性（必須是可用 Read/Write/Edit/Bash 安全完成的操作）
2. 依 `fix_instructions` 逐步執行修復
3. 執行後依 `verification` 欄位描述的方式驗證修復結果
4. 在 `context/arch-decision.json` 對應條目中更新執行狀態（**必須立即寫回，不等所有項目完成**）：

   **執行成功**：
   ```json
   {
     "execution_status": "success",
     "executed_at": "ISO 8601 時間戳",
     "execution_result": "success",
     "execution_note": "一句話說明修復結果"
   }
   ```

   **執行失敗（retry_count < 2）**：
   ```json
   {
     "execution_status": "failed_retry",
     "retry_count": retry_count + 1,
     "execution_result": "failed",
     "execution_note": "失敗原因（供下次重試參考）"
   }
   ```

   **執行失敗（retry_count >= 2，已達上限）**：
   ```json
   {
     "execution_status": "failed_max_retry",
     "executed_at": "ISO 8601 時間戳",
     "execution_result": "failed",
     "execution_note": "失敗原因；已達最大重試次數 3，不再重試"
   }
   ```
   → `failed_max_retry` 項目發送 warning 通知：「{backlog_id} 修復失敗達 3 次，需人工介入」

**安全中止條件**：若某項修復執行失敗，記錄錯誤後繼續下一項，不中止整個步驟。

**步驟 h 備援來源（adr-registry）**：當 arch-decision 無可執行的 immediate_fix（篩選後 0 項）或 arch-decision 不存在/過期時，再讀取 `context/adr-registry.json`：
- 篩出 `implementation_status === "immediate_fix"` 的 ADR
- 對每個該 ADR，檢查 arch-decision 的 `decisions` 中是否已有對應 `backlog_id === adr.id` 且 `execution_status === "success"` 的條目；若**無**則視為「尚未執行」
- 對尚未執行的 immediate_fix ADR，從其 `decision` 與 `related_files` 推導可執行的 fix_instructions（限 Read/Write/Edit/Bash 安全操作），**最多執行 1 項**（避免單次過多），執行後在報告中註明「來自 adr-registry 備援 1 項」
- 若推導不出安全步驟或無此類 ADR → 報告「adr-registry 備援：0 項」

#### i. 自動任務失敗追蹤處理（failed-auto-tasks.json）

用 Read 讀取 `state/failed-auto-tasks.json`（不存在則跳過此步驟）。

若 `entries` 陣列為空或不存在 → 跳過。

對每個 entry，依 `consecutive_count` 分兩層處理：

**Layer 1（consecutive_count >= 1，首次失敗以上）— 告警**：
- 發送 ntfy 通知（priority: 3）：
  ```
  ⚠️ 自動任務失敗追蹤：{task_key}
  連續失敗 {consecutive_count} 次 | 原因：{reason}
  最後失敗：{last_failed_at}
  ```
- 記錄到修復報告：「[alert] {task_key} 連續失敗 {consecutive_count} 次」

**Layer 2（consecutive_count >= 2，持續失敗）— 重置計數器**：
1. 用 Read 讀取 `config/frequency-limits.yaml`，取得該任務的 `counter_field` 和 `daily_limit`
2. 用 Read 讀取 `context/auto-tasks-today.json`
3. 若 `{counter_field}` 值 >= `daily_limit`（已耗盡今日配額）：
   - 將該欄位重置為 0（允許下次 round-robin 重跑）
   - 用 Write 覆寫 `context/auto-tasks-today.json`
   - 在 `state/failed-auto-tasks.json` 對應 entry 更新 `reset_count` +1
   - 記錄：「[fix] {task_key} counter reset to 0 (reset #{reset_count})」
4. 若計數器仍為 0（任務原本就有資格，未達上限）：
   - 不重置（無需操作）
   - 記錄：「[skip] {task_key} counter=0 已可在下次 round-robin 執行」

**安全邊界**：
- 每個 task_key 同一天最多重置 1 次（防止無限循環）
- `reset_count` 累積超過 5 次的 entry → 發送 priority=4 告警：「{task_key} 已重置 5 次，需人工檢查 prompt/config」

### 步驟 3：記錄修復行為
每項修復動作記錄到結構化日誌（透過工具呼叫自動被 post_tool_logger.py 記錄）。

### 步驟 4：驗證修復結果
- 對每項修復重新檢查，確認已修復
- 統計：修復嘗試 N 項（含步驟 a–g 的常規修復 + 步驟 h 的 arch-decision 修復），成功 M 項
- **步驟 h 報告**：必須明確列出「arch-decision 執行 K 項」（K = 本次實際執行的 immediate_fix 數量）；若 K = 0，寫「arch-decision 可執行 0 項（原因：無 action=immediate_fix 且 execution_status=pending 的條目 / 或 arch-decision 不存在/過期）」
- **步驟 h 通知措辭規範**：若所有條目均為 `action=skip`，通知中不得只寫「2 done, 3 partial」而不說明這是 ADR 背景狀態。正確格式：「arch-decision 可執行 0 項（5 項均已有對應 ADR：其中 done=2, partial=3，均跳過）」，避免用戶誤解為本次執行了 5 項。

### 步驟 5：發送修復報告（必發，依結果分級）

依 `skills/ntfy-notify/SKILL.md` 發送通知（**無論是否有修復動作，均發送**）。

> **JSON 建立規則**：用 Write 工具建立 JSON 檔時，`message` 欄位的換行**必須**用 `\n` 轉義序列（不得寫成實際換行符號，會讓 JSON 無效）。

**訊息段落建構方式**（先組段落字串，再合入 JSON `message`）：

```
段落 1（摘要行）：  {M}/{N} 項成功 | arch {arch_success} 項 | {YYYY-MM-DD HH:mm}
段落 2（成功清單，僅當 arch_success>0）：
  ✅ 已執行：\n• {ADR-ID}：{backlog_pattern}\n  → {execution_note}
段落 3（失敗清單，僅當有失敗項目）：
  ❌ 失敗：\n• {步驟名稱/ADR-ID}：{失敗原因}（retry: {retry_count}）
段落 4（修改檔案）：
  📁 {related_files 用逗號分隔，無則省略}
段落 5（備份 commit）：
  🔒 {git_commit_hash 或 "備份：無變更"}
段落 6（步驟 i 告警，僅當 alert_count>0）：
  ⚠️ 另有 {alert_count} 個任務失敗告警（見個別通知）
```

各段落之間用 `\n\n` 分隔；各段落內部用 `\n` 分隔。

> **注意（步驟 i 告警計數）**：步驟 i 的告警是獨立通知，但最終報告需帶入 `alert_count`。

---

**case A｜有修復且全部成功（M = N）**：
```json
{
  "topic": "wangsc2025",
  "title": "✅ 自癒完成 | {M}/{N} 成功",
  "message": "<依上方段落建構，段落 1+2+4+5+6>",
  "priority": 2,
  "tags": ["white_check_mark"]
}
```

**case B｜部分失敗（M < N）**：
```json
{
  "topic": "wangsc2025",
  "title": "⚠️ 自癒部分失敗 | {M}/{N} 成功",
  "message": "<依上方段落建構，段落 1+2+3+4+5+6>",
  "priority": 3,
  "tags": ["warning"]
}
```

**case C｜無修復項目 且 alert_count = 0（系統健康）**：
```json
{
  "topic": "wangsc2025",
  "title": "🔧 自癒：系統健康",
  "message": "無需修復項目，系統運行正常 | {YYYY-MM-DD HH:mm}",
  "priority": 2,
  "tags": ["white_check_mark"]
}
```

**case D｜無修復項目 但步驟 i 有告警**：
```json
{
  "topic": "wangsc2025",
  "title": "🔧 自癒：無修復（{alert_count} 告警）",
  "message": "步驟 a-h 無需修復 | ⚠️ {alert_count} 個任務失敗告警已另行通知 | {YYYY-MM-DD HH:mm}",
  "priority": 2,
  "tags": ["white_check_mark", "warning"]
}
```

### 步驟 5c：記錄 Act 完成（OODA 日誌）

用 Read 讀取 `context/workflow-state.json`，在 `history` 陣列末尾追加 act 完成條目：
```json
{
  "status": "completed",
  "step": "act",
  "ts": "ISO 8601 時間戳",
  "repairs": "M/N 項（含 arch-decision K 項）"
}
```
更新頂層欄位：`current_step = "complete"`、`status = "completed"`。

（備註：此記錄純為 OODA 觀測日誌，不驅動任何執行。下次 run-system-audit-team.ps1 執行時自動開始新 OODA 週期。）

## 安全邊界（不可自動修復）
以下問題僅通知不修復：
- **scheduler-state.json** → 備份 + 通知人工介入（PS1 層 try-catch 已處理崩潰回復）
- **SKILL.md 內容異常** → 通知不修改（由 pre_write_guard.py 保護）
- **config/*.yaml 缺失** → 通知不重建
- **arch-decision.json 中的 schedule_adr / deferred / wontfix 項目** → 僅記錄不執行

## 輸出
完成後用 Write 建立 `task_result.txt`，包含 DONE_CERT：
```
===DONE_CERT_BEGIN===
{
  "status": "DONE",
  "task_type": "self-heal",
  "checklist": {
    "analysis_done": true,
    "repairs_attempted": N,
    "repairs_succeeded": M,
    "arch_decision_executed": arch_count,
    "notification_sent": true
  },
  "artifacts_produced": [],
  "quality_score": 4,
  "self_assessment": "自癒迴圈完成，修復 M/N 項（含 arch-decision arch_count 項）"
}
===DONE_CERT_END===
```
