# 自動任務：Chatroom 整合品質優化

> 由 round-robin 自動觸發，每日最多 2 次

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則。

---

## 步驟 1：讀取 Skill 與指標資料

### 1.1 讀取 Skill
讀取 `skills/chatroom-query/SKILL.md`，了解 bot.js API 端點。

### 1.2 讀取 Circuit Breaker 狀態
用 Read 讀取 `state/api-health.json`，取得 `gun-bot` 的狀態：
- `state`：closed / half_open / open
- `failure_count`：連續失敗次數
- `last_success_at`：最後成功時間

### 1.3 從結構化日誌提取 Chatroom 指標

取今日與昨日的 JSONL 日誌，用 Python 分析：
```bash
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null)
cat "logs/structured/${TODAY}.jsonl" "logs/structured/${YESTERDAY}.jsonl" 2>/dev/null | \
python -c "
import json, sys, datetime
records = [json.loads(l) for l in sys.stdin if l.strip()]

# 篩選 chatroom 相關工具呼叫
chatroom_records = [r for r in records if 'chatroom' in r.get('tags', [])]
claim_records = [r for r in records if any('claim' in str(r.get('summary','')) for _ in [1])]

# 計算指標
total = len(chatroom_records)
success = sum(1 for r in chatroom_records if not r.get('has_error', True))
success_rate = (success / total * 100) if total > 0 else None

# 認領衝突（409 回應）
conflicts = sum(1 for r in chatroom_records if '409' in str(r.get('summary','')))
conflict_rate = (conflicts / total * 100) if total > 0 else None

# 平均耗時（從 summary 或 duration 欄位）
durations = [r.get('duration_ms', 0) for r in chatroom_records if r.get('duration_ms')]
avg_time = sum(durations) / len(durations) / 1000 if durations else None

print(json.dumps({
    'total_calls': total,
    'success_rate': round(success_rate, 1) if success_rate is not None else None,
    'conflict_rate': round(conflict_rate, 1) if conflict_rate is not None else None,
    'avg_exec_seconds': round(avg_time, 1) if avg_time is not None else None,
    'gun_bot_errors': sum(1 for r in records if 'gun-bot' in str(r.get('tags',[])) and r.get('has_error'))
}))
"
```

---

## 步驟 2：評估問題並決定調整方案

根據收集的指標，按以下規則判斷是否需要調整：

| 指標 | 閾值 | 問題等級 | 處理方式 |
|------|------|---------|---------|
| 成功率 | < 50% | 嚴重 | 清除 chatroom.json 快取 + ntfy 警告 |
| 成功率 | 50-70% | 警告 | 記錄但不調整（觀察） |
| 成功率 | ≥ 70% | 正常 | 無需調整 |
| 認領衝突率 | > 30% | 高衝突 | 讀取 routing.yaml，max_tasks_per_run = max(1, 現值-1) |
| 認領衝突率 | 10-30% | 中衝突 | 記錄，建議手動評估 |
| 平均執行時間 | > 300s | 過慢 | ntfy 警告（超過單次 Phase 2 timeout 50%） |
| gun-bot state | open | 斷路 | 清除快取 + 更高優先 ntfy 警告 |

---

## 步驟 3：執行自動調整（只執行安全調整）

### 3.1 清除過期快取（若成功率 < 50% 或 gun-bot=open）
```bash
rm -f cache/chatroom.json
```

### 3.2 調整 max_tasks_per_run（若衝突率 > 30%）
讀取 `config/routing.yaml`，找出 `chatroom_task_source.max_tasks_per_run` 當前值：
- 若當前值 > 1 → 減 1（用 Edit 工具更新）
- 若已為 1 → 記錄「已達最低值，無法再降」

> 注意：修改 config/routing.yaml 屬於配置調整（非禁止的 SKILL.md/scheduler-state.json）。
> 但本次調整後需在報告中記錄，供人工審核。

### 3.3 無需調整時
記錄「指標正常，無需調整」。

---

## 步驟 4：寫入優化記錄

用 Write 建立 `context/chatroom-optimize-history.json`（追加模式）：
若檔案不存在，初始化；若存在，讀取後追加：
```json
{
  "history": [
    {
      "date": "YYYY-MM-DD",
      "run_at": "ISO8601",
      "metrics": {
        "total_calls": N,
        "success_rate": X,
        "conflict_rate": Y,
        "avg_exec_seconds": Z
      },
      "actions_taken": ["清除快取", "降低 max_tasks_per_run 2→1"],
      "gun_bot_state": "closed",
      "optimized": true
    }
  ]
}
```
保留最新 30 筆記錄（超過刪除最舊的）。

---

## 步驟 5：發送通知

若有問題或調整：依 `skills/ntfy-notify/SKILL.md` 發送到 `wangsc2025`：
- **嚴重**（成功率 < 50% 或 gun-bot=open）：`priority: 4`，tags: `["warning"]`
- **一般**（衝突率高或執行時間過長）：`priority: 3`，tags: `["chart_with_downwards_trend"]`
- **正常**：不發送通知（靜默成功）

---

## 輸出
完成後用 Write 建立 `task_result.txt`：
```
===DONE_CERT_BEGIN===
{
  "status": "DONE",
  "task_type": "chatroom-optimize",
  "checklist": {
    "metrics_collected": true,
    "issues_found": N,
    "adjustments_made": M,
    "notification_sent": true_or_false
  },
  "artifacts_produced": ["context/chatroom-optimize-history.json"],
  "quality_score": 4,
  "self_assessment": "Chatroom 品質優化完成，調整 M 項"
}
===DONE_CERT_END===
```
