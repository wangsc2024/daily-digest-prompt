---
name: "todoist-auto-log_audit"
template_type: "team_prompt"
version: "1.2.0"
released_at: "2026-03-23"
---
你是系統維護助手，全程使用正體中文。
你的任務是對 daily-digest-prompt 系統進行 Log 深度審查，找出問題並執行修正。
完成後將結果寫入 `results/todoist-auto-log_audit.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 立即行動：寫入 Fail-Safe 結果（最高優先）
讀完 preamble 後立即執行，用 Write 工具建立 `results/todoist-auto-log_audit.json`，內容：
`{"agent":"todoist-auto-log_audit","status":"failed","type":"log_audit","error":"task_did_not_complete_or_timeout","summary":"任務啟動但未完成","completed":false}`

（此 placeholder 將在步驟 8 成功完成後被覆寫為 status=success）

必須先讀取以下 SKILL.md：
- `skills/scheduler-state/SKILL.md`
- `skills/knowledge-query/SKILL.md`

---

## 前處理（Groq 加速）

在執行正式步驟前，嘗試用 Groq Relay 預分類日誌模式：

```bash
GROQ_OK=$(curl -s --max-time 3 http://localhost:3002/groq/health 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
```

若 `GROQ_OK` 為 `ok`：
1. 讀取 `state/scheduler-state.json`，取最近 10 筆 runs 的 status 欄位
2. 用 Write 工具建立 `temp/groq-req-log_audit.json`（UTF-8）：
   ```json
   {"mode": "classify", "content": "<最近10筆runs的status清單>"}
   ```
3. 執行：
   ```bash
   curl -s --max-time 20 -X POST http://localhost:3002/groq/chat -H "Content-Type: application/json; charset=utf-8" -d @temp/groq-req-log_audit.json > temp/groq-result-log_audit.json
   ```
4. Read `temp/groq-result-log_audit.json`，取得分類結果供步驟 1 直接使用

若 `GROQ_OK` 不為 `ok`：略過此步驟，由 Claude 自行完成（無降級邏輯改變）。

## 步驟 1：讀取系統狀態
1. 讀取 `state/scheduler-state.json` — 分析最近 30 筆執行記錄
2. 讀取 `context/digest-memory.json` — 分析記憶中的異常模式

## 步驟 1b：排程系統健康診斷（三項必查）

### 1b-1：執行錯誤彙總報告

```bash
pwsh -ExecutionPolicy Bypass -File query-logs.ps1 -Mode errors 2>&1
```

擷取輸出，整理：
- 失敗次數與類型（phase_failure / timeout / api_error）
- 失敗集中時段（哪些小時段高發？）
- 區塊降級統計（query failed / gmail failed 等）

用 Read 工具讀取 `state/failure-stats.json`，統計 `daily` 欄位中最近 7 天各日的 `phase_failure` 值。若**單日超過 10 次**，標記為 🔴 高風險，納入步驟 3 嚴重問題。

用 Read 工具讀取 `state/slo-budget-report.json`（若存在），確認 `slo_status` 各項的 `budget_consumed_pct`。若任一 SLO 超過 100%，標記為 🔴 告警並列出受影響 SLO 名稱。

### 1b-1a：phase_failure 趨勢（機器決定性，必跑）

**目的**：根治 LLM 以「全窗最大→全窗最小」或顛倒時間序誤判趨勢（例如 ERROR 21→5「改善中」）。

在專案根目錄執行（stdout 為單一 JSON 物件，必須保留於結果檔）：

```bash
uv run python tools/compute_log_audit_trend.py --days 7
```

- 若審查報告落款日需對齊「昨日」或特定基準日，可加 `--end-date YYYY-MM-DD`（與 `failure-stats.json` 的 `daily` 鍵一致）。
- **禁止**手寫或改寫 `summary_zh`、`short_term_vs_prior`、`narrative_guardrails_zh`；**必須**與指令 stdout **逐字一致**地併入步驟 8 之 `trend_analysis.phase_failure_stats`。
- 知識庫 Markdown（`import_note.json` 的 `contentText`）中「觀察／趨勢分析」段落：**必須**完整引用 `phase_failure_stats.summary_zh`（建議小標：`phase_failure（failure-stats）`）。若有 `data_lag_warning_zh`，亦須一併引用。
- **禁止**另寫與 `summary_zh` 矛盾的 phase_failure 趨勢句。**禁止**使用已廢棄欄位 `improvement_trend`（自由敘述易誤判）。

**子 Agent 彙總之 log grep（ERROR／WARN 等）若製表**：

1. 表格**僅能**依**日期欄由舊到新**排序。
2. 敘述「ERROR 趨勢」時**僅得**：同一欄位內，**時間序上最末筆有資料日**對 **其前一有資料日**；或「相較 YYYY-MM-DD 尖峰…」，且**不得**暗示終點為更早的較低值。
3. **禁止**以全窗最大 ERROR 銜接全窗最小 ERROR 寫成「A→B 改善」類句子。
4. **禁止**將 log `ERROR` 次數與 `phase_failure` 混在同一趨勢句（兩者定義不同）；若兩者都要寫，分開兩句並各註資料來源。

### 1b-2：偵測 autonomous-runtime.json 殭屍降級狀態

讀取 `state/autonomous-runtime.json`，執行過期判斷：

```bash
pwsh -Command "
\$r = Get-Content state/autonomous-runtime.json | ConvertFrom-Json
\$expired = \$false
if (\$r.override.active -and \$r.override.expires_at) {
    \$expiry = [datetime]::Parse(\$r.override.expires_at)
    \$expired = \$expiry -lt (Get-Date)
}
Write-Host ('mode=' + \$r.mode + ' override.active=' + \$r.override.active + ' expired=' + \$expired + ' generated_at=' + \$r.generated_at)
"
```

若 `mode=degraded` 且 `override.active=True` 且 `expired=True`：
- 標記為 🔴 嚴重問題（殭屍降級狀態）
- 計算持續時長：`(Get-Date) - [datetime]::Parse($r.override.expires_at)`
- **立即自動修正**（不等步驟 6）：用 Write 工具覆寫 `state/autonomous-runtime.json`，將 `mode` 設為 `normal`，`override.active` 設為 `false`，`blocked_task_keys` 清空，`allow_heavy_auto_tasks` / `allow_research_auto_tasks` 設為 `true`，`max_parallel_auto_tasks` 設為 `4`
- 寫入後記錄：「autonomous-runtime.json 殭屍狀態已自動清除，過期時長：X 分鐘」

### 1b-3：偵測 LLM 對話性回應模式（Phase 1 與 Phase 3 分別統計）

**Phase 1（todoist-query）偵測**：
```bash
# 偵測含 [query] 前綴的對話性回應（Phase 1 特徵）
grep -rl "^\s*\[query\].*\(你貼了\|已收到\|請問你希望\|請問需要\)" logs/ 2>/dev/null | grep "todoist-team" | wc -l
grep -rl "^\s*\[query\].*\(你貼了\|已收到\|請問你希望\|請問需要\)" logs/ 2>/dev/null | grep "todoist-team" | head -3
```

**Phase 3（assemble）偵測**：
```bash
# 偵測含 [assemble] 前綴的對話性回應（Phase 3 特徵）
grep -rl "^\s*\[assemble\].*\(你貼了\|已收到\|請問你希望\|請問需要\)" logs/ 2>/dev/null | grep "todoist-team" | wc -l
grep -rl "^\s*\[assemble\].*\(你貼了\|已收到\|請問你希望\|請問需要\)" logs/ 2>/dev/null | grep "todoist-team" | head -3
```

分別記錄 Phase 1 與 Phase 3 受影響的 run 數量與時段。

**Phase 1 防護確認**：用 Grep 工具確認 `run-todoist-agent-team.ps1` 是否有 `planWriteTime -lt` 關鍵字
- **存在** → 記錄「Phase 1 防護已到位」
- **不存在** → 納入步驟 5-6 修正清單

**Phase 3 防護確認**：用 Grep 工具確認 `run-todoist-agent-team.ps1` 是否有 `conversationalPattern` 關鍵字
- **存在** → 記錄「Phase 3 防護已到位」
- **不存在** → 納入步驟 5-6 修正清單，需加入輸出內容對話性偵測邏輯

若 Phase 1 和 Phase 3 均無偵測到：記錄「LLM 對話性回應：未偵測到，系統運行正常」。

---

## 步驟 2：委派 Explore 子 Agent 掃描 Log 檔案

**禁止主 Agent 逐一 Read 每個 log 檔案**（10+ 個大型 .log 檔案會耗盡 context）。
使用 Agent 工具（`subagent_type=Explore`）委派掃描，主 Agent 只接收摘要：

向子 Agent 提問（prompt 內容）：
> 請用 Bash 掃描 `logs/` 目錄下最近 7 天的 .log 檔案（`ls -t logs/*.log | head -10`）。
> 對每個 log 檔案用 `grep -c` 統計關鍵字出現次數：`ERROR`、`WARN`、`RETRY`、`TIMEOUT`、`failed`、`cache_degraded`、`nul`。
> 同時擷取每種關鍵字的最新一行（`grep -m1 "PATTERN" 檔案`）作為代表樣本。
> 回傳 JSON 格式：`{"file": "filename", "counts": {"ERROR": N, ...}, "samples": {"ERROR": "最新一行"}}`。
> 限制回傳 ≤ 50 行 JSON。

從子 Agent 回傳的摘要識別高頻問題（counts 大於 0 的類型）。

## 步驟 3：分析問題並分類
```
🔍 Log 審查發現
━━━━━━━━━━━━━━━━━━━━━
🔴 嚴重問題（立即修正，本次執行完成）：
🟠 中優先問題（本次執行完成或記錄待修）：
🟡 改善建議（記錄，不強制修正）：
🟢 正常狀態
```

**主動行動原則（強制）**：
- 🔴 嚴重問題 → **本次執行必須完成修正**，不留待後續
- 🟠 中優先問題 → **評估後立即修正**，若有風險則完整記錄根因與修正步驟
- 🟡 改善建議 → 記錄即可，下次審查追蹤
- 若全部 🟢 → 跳至步驟 7（僅記錄，不修正）

## 步驟 4：深入根因分析（主動查核）
對每個 🔴 和 🟠 問題，**必須執行深入查核**（不只是表面描述）：

1. **根因**：為什麼？追溯到具體程式碼行或配置值
2. **模式**：用 `grep -c` 或日誌時間軸確認是偶發還是規律
3. **影響範圍**：哪些 run 受影響？受影響任務的結果品質如何（quality_score < 50 視為低品質）？
4. **已有防護**：系統是否已有 retry / fallback 機制？是否生效？
5. **複現條件**：下次在什麼條件下會再次觸發？

查核時積極使用子 Agent（`subagent_type=Explore`）深入搜尋，主 Agent 接收摘要後決策。

## 步驟 5：擬定方案 + 正確性驗審

### 5.1 擬定修改方案（主動、完整）
- 修改檔案清單（精確到行號或區段）
- 修改內容（擬定具體改動，不只是方向）
- 預期效果（用量化指標描述：「phase_failure 減少 X%」「blocked 任務從 11 降至 0」）

### 5.2 方案正確性驗審（必做）

| # | 驗審項目 | 通過條件 |
|---|---------|---------|
| 1 | 邏輯正確 | 解決根因，非遮蔽症狀 |
| 2 | 副作用評估 | 不影響其他 Agent |
| 3 | 語法正確 | PowerShell/JSON 語法無誤 |
| 4 | 編碼規範 | .ps1=UTF-8 with BOM，JSON=UTF-8 |

4 項全通過 → 進入步驟 6。否則修正方案（最多 2 次），仍不通過記為「待手動處理」。

## 步驟 6：備份 + 執行修正 + 驗證

### 6.1 備份
```bash
cp "目標檔案" "目標檔案.bak"
```

### 6.2 執行修正
直接修改（使用 Edit 工具）或建立子 Agent 修正。

### 6.3 修改後驗證
1. `git diff` 確認修改範圍
2. 語法檢查
3. 關鍵邏輯未被破壞

驗證失敗 → 用備份還原：`cp "檔案.bak" "檔案"`

### 6.4 清理備份
驗證通過後：`rm -f D:/Source/daily-digest-prompt/*.bak`

## 步驟 7：寫入知識庫
將審查過程寫入 RAG 知識庫：

1. 用 Write 建立 `import_note.json`：
```json
{
  "notes": [{
    "title": "系統 Log 審查報告 - YYYY-MM-DD",
    "contentText": "完整 Markdown 審查報告",
    "tags": ["系統審查", "log分析", "優化"],
    "source": "import"
  }],
  "autoSync": true
}
```
2. `curl -s -X POST "http://localhost:3000/api/import" -H "Content-Type: application/json; charset=utf-8" -d @import_note.json`
3. `rm import_note.json`
4. 知識庫未啟動則跳過

## 步驟 8：寫入結果 JSON
用 Write 建立 `results/todoist-auto-log_audit.json`：
```json
{
  "agent": "todoist-auto-log_audit",
  "status": "success 或 partial 或 failed",
  "task_id": null,
  "type": "log_audit",
  "findings_count": 3,
  "fixes_count": 2,
  "kb_imported": true,
  "duration_seconds": 0,
  "done_cert": {
    "status": "DONE",
    "quality_score": 4,
    "remaining_issues": []
  },
  "trend_analysis": {
    "phase_failure_stats": {},
    "log_grep_daily": null
  },
  "summary": "發現 3 個問題，修正 2 個",
  "error": null
}
```

- `trend_analysis.phase_failure_stats`：**必填**（除非指令失敗且 status=failed，則可為 `null` 並在 `error` 說明）。將 `uv run python tools/compute_log_audit_trend.py --days 7` 的 stdout **整棵 JSON 物件**取代範例中的 `{}`，**禁止**手改其中 `summary_zh`／`short_term_vs_prior` 等欄位。
- `trend_analysis.log_grep_daily`：選填；若步驟 2 子 Agent 有按日聚合 log 關鍵字，則為陣列 `[{"date":"YYYY-MM-DD","ERROR":n,"WARN":n,...}, ...]`，**必須已按日期遞增排序**；無則 `null`。
- **禁止**在結果 JSON 使用自由文字欄位 `improvement_trend`（易與機器結論衝突）。
