---
name: task-fairness-analyzer
version: "0.5.0"
description: |
  自動任務公平性分析器。讀取 frequency-limits.yaml 配置與多日執行歷史，
  計算任務級別的飢餓偵測指標、Gini 不均等係數、群組執行偏差，
  並產出結構化的權重再平衡建議報告。
  與 system-insight 互補：system-insight 報告公平性數值，本 Skill 診斷根因並建議修正。
  Use when: 自動任務公平性診斷、任務飢餓偵測、排程權重再平衡建議、round-robin 偏差分析。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "任務公平性"
  - "排程公平"
  - "任務飢餓"
  - "task fairness"
  - "starvation"
  - "任務再平衡"
  - "rebalance"
  - "公平性分析"
  - "round-robin 偏差"
depends-on:
  - scheduler-state
  - system-insight
---

# task-fairness-analyzer：自動任務公平性分析器

## 設計哲學

system-insight 告訴你「公平性數值是 0.66」，本 Skill 告訴你「為什麼是 0.66，以及怎麼降到 0.5 以下」。

分析鏈：
```
讀取配置 → 讀取執行歷史 → 計算飢餓指標 → 群組偏差分析 → 根因診斷 → 再平衡建議 → 輸出報告
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立 Skill 認知地圖）
3. 讀取 `skills/scheduler-state/SKILL.md`（了解排程狀態資料結構）

---

## 步驟 1：載入配置與歷史資料

並行讀取以下檔案（用 Read 工具）：

| 檔案 | 用途 | 關鍵欄位 |
|------|------|---------|
| `config/frequency-limits.yaml` | 任務定義與 daily_limit | `tasks.*`、`selection_strategy`、`max_auto_per_run` |
| `context/auto-tasks-today.json` | 今日執行計數 | `*_count`、`next_execution_order` |
| `state/run-fsm.json` | 最近執行狀態 | `last_run`、`phase2_tasks` |
| `context/system-insight.json` | 現有公平性指標 | `metrics.auto_task_fairness`、`alerts` |

**降級**：若任一檔案不存在，記錄缺失原因，用預設值補足（daily_limit 預設 1，count 預設 0）。

---

## 步驟 2：計算飢餓指標（Python 強制計算）

用 Write 工具建立 `temp_fairness_calc.py`，再用 Bash 執行：

```python
# temp_fairness_calc.py
import json, yaml, sys, math
from pathlib import Path
from datetime import datetime

# 讀取 frequency-limits.yaml
with open('config/frequency-limits.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

tasks = config.get('tasks', {})

# 讀取今日執行計數
today_file = Path('context/auto-tasks-today.json')
today_data = json.loads(today_file.read_text(encoding='utf-8')) if today_file.exists() else {}

# 讀取 system-insight 的 7 日統計
insight_file = Path('context/system-insight.json')
insight = json.loads(insight_file.read_text(encoding='utf-8')) if insight_file.exists() else {}

# --- 計算各任務指標 ---
results = []
active_tasks = []  # daily_limit > 0 的任務

for task_key, task_def in tasks.items():
    daily_limit = task_def.get('daily_limit', 0)
    counter_field = task_def.get('counter_field', f'{task_key}_count')
    today_count = today_data.get(counter_field, 0)
    execution_order = task_def.get('execution_order', 999)
    group = task_def.get('name', task_key)

    entry = {
        'task_key': task_key,
        'name': task_def.get('name', task_key),
        'daily_limit': daily_limit,
        'today_count': today_count,
        'execution_order': execution_order,
        'utilization': round(today_count / daily_limit, 3) if daily_limit > 0 else None,
        'is_starved': daily_limit > 0 and today_count == 0,
        'is_disabled': daily_limit == 0,
    }
    results.append(entry)
    if daily_limit > 0:
        active_tasks.append(entry)

# --- Gini 係數計算（僅 active tasks）---
if active_tasks:
    utilizations = [t['utilization'] for t in active_tasks]
    n = len(utilizations)
    if n > 0 and sum(utilizations) > 0:
        sorted_u = sorted(utilizations)
        cumulative = sum((2 * (i + 1) - n - 1) * sorted_u[i] for i in range(n))
        gini = cumulative / (n * sum(sorted_u))
        gini = round(max(0, min(1, gini)), 4)
    else:
        gini = 0.0
else:
    gini = 0.0

# --- 飢餓任務清單 ---
starved = [t for t in active_tasks if t['is_starved']]
starved_rate = round(len(starved) / len(active_tasks), 3) if active_tasks else 0.0

# --- 群組偏差分析 ---
# 按 execution_order 分群（每 5 個一組）
groups = {}
for t in active_tasks:
    group_id = (t['execution_order'] - 1) // 5
    if group_id not in groups:
        groups[group_id] = {'tasks': [], 'total_util': 0}
    groups[group_id]['tasks'].append(t['task_key'])
    groups[group_id]['total_util'] += t['utilization']

# --- 輸出結果 ---
report = {
    'timestamp': datetime.now().isoformat(),
    'active_task_count': len(active_tasks),
    'disabled_task_count': len([t for t in results if t['is_disabled']]),
    'gini_coefficient': gini,
    'starved_tasks': [t['task_key'] for t in starved],
    'starved_rate': starved_rate,
    'fairness_grade': 'A' if gini < 0.2 else 'B' if gini < 0.4 else 'C' if gini < 0.6 else 'D',
    'task_details': results,
    'group_deviation': groups,
    'system_insight_fairness': insight.get('metrics', {}).get('auto_task_fairness', None)
}

print(json.dumps(report, ensure_ascii=False, indent=2))
```

執行：
```bash
uv run python -X utf8 temp_fairness_calc.py > context/fairness-report.json 2>&1
rm temp_fairness_calc.py
```

---

## 步驟 3：根因診斷

讀取 `context/fairness-report.json`，依以下決策樹診斷根因：

### 3a. 飢餓任務分析

對每個 `starved_tasks` 中的任務，逐一檢查：

| 檢查項目 | 判斷方式 | 根因分類 |
|---------|---------|---------|
| daily_limit 過低 | daily_limit = 1 且 round-robin 尚未輪到 | `schedule_position` |
| execution_order 在後段 | execution_order > 15 且今日輪轉尚未到達 | `late_order` |
| 被高 limit 任務擠佔 | 同群組有 daily_limit >= 3 的任務 | `resource_crowding` |
| 對應後端離線 | task_rules 指定的後端當日失敗 | `backend_failure` |
| 任務本身被暫停 | daily_limit = 0 但非預期 | `accidentally_disabled` |

### 3b. 群組偏差分析

對 `group_deviation`：
- 計算群組間 utilization 標準差
- 標準差 > 0.3 → 群組不均衡，識別最低群組

### 3c. 結構性問題偵測

| 問題模式 | 偵測方式 |
|---------|---------|
| round-robin 指針卡住 | `next_execution_order` 連續 3 天未變化 |
| 高 limit 任務壟斷 | 單一任務 daily_limit > 總配額 20% |
| 已停用任務佔位 | daily_limit=0 但 execution_order 仍在輪轉範圍 |

---

## 步驟 4：生成再平衡建議

根據步驟 3 的根因，產出**具體可執行的建議**（非抽象概念）：

### 建議類型

| 根因分類 | 建議動作 | 範例 |
|---------|---------|------|
| `resource_crowding` | 降低擠佔者的 daily_limit | 「建議 ai_deep_research: daily_limit 5→3」 |
| `late_order` | 調整 execution_order 至前段 | 「建議 system_insight: execution_order 16→8」 |
| `schedule_position` | 增加 max_auto_per_run | 「建議 team_mode: max_auto_per_run 2→3」 |
| `backend_failure` | 新增 fallback 或切換後端 | 「建議 qa_optimize: 後端從 codex_standard 改為 claude_sonnet45」 |
| `accidentally_disabled` | 恢復 daily_limit | 「建議 github_scout: daily_limit 0→1」 |

### 建議格式

每條建議包含：
```json
{
  "type": "limit_adjustment",
  "target": "ai_deep_research",
  "field": "daily_limit",
  "current": 5,
  "suggested": 3,
  "reason": "佔總配額 22%，導致 OODA 群組飢餓",
  "expected_impact": "公平性指標預估從 0.66 降至 0.45"
}
```

---

## 步驟 5：模擬驗證（可選）

若時間允許，用 Python 模擬調整後的公平性：

```python
# 模擬：假設採用建議後的 daily_limit，重新計算 Gini
# 輸出：adjusted_gini、compared_with_current
```

此步驟非強制，但能增強建議的可信度。

---

## 步驟 6：輸出分析報告

用 Write 工具建立 `context/fairness-analysis.json`：

```json
{
  "generated_at": "ISO timestamp",
  "period": "today",
  "metrics": {
    "gini_coefficient": 0.45,
    "fairness_grade": "C",
    "starved_tasks": ["system_insight", "arch_evolution"],
    "starved_rate": 0.25,
    "active_task_count": 16,
    "disabled_task_count": 5
  },
  "root_causes": [
    {
      "task_key": "system_insight",
      "cause": "late_order",
      "detail": "execution_order=16，今日 round-robin 僅執行到 order=12"
    }
  ],
  "recommendations": [
    {
      "type": "limit_adjustment",
      "target": "ai_deep_research",
      "field": "daily_limit",
      "current": 5,
      "suggested": 3,
      "reason": "佔比過高導致 OODA 群組飢餓",
      "expected_impact": "Gini 預估 0.45 → 0.30"
    }
  ],
  "simulation": {
    "current_gini": 0.45,
    "projected_gini": 0.30,
    "improvement_pct": 33
  },
  "system_insight_comparison": {
    "insight_fairness": 0.659,
    "our_gini": 0.45,
    "note": "Gini 係數與 system-insight fairness 計算方式不同，互為補充"
  }
}
```

---

## 步驟 7：整合結果至呼叫端

若由自動任務呼叫，將分析結果寫入 `results/todoist-auto-{task_key}.json`，格式依呼叫端要求。

若由互動式呼叫，直接輸出報告摘要：
```
📊 公平性分析報告
- Gini 係數：0.45（等級 C）
- 飢餓任務：system_insight、arch_evolution（2/16 = 12.5%）
- 建議：ai_deep_research daily_limit 5→3（預估改善 33%）
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| frequency-limits.yaml 無法讀取 | 終止分析，報告錯誤 |
| auto-tasks-today.json 不存在 | 使用全零計數，僅分析配置層面問題 |
| system-insight.json 不存在 | 跳過對比分析，僅輸出本 Skill 計算結果 |
| Python 執行失敗 | 回報錯誤，不產出報告 |
| 所有任務 daily_limit = 0 | 報告「無啟用任務，無需分析」 |

---

## 注意事項

- 本 Skill 是**唯讀分析**，不修改任何配置檔案
- 修改建議需由人工或 task-manager Skill 執行
- Gini 係數 0 = 完全公平，1 = 完全不公平
- fairness_grade：A(<0.2) B(<0.4) C(<0.6) D(>=0.6)
- 暫存檔 `temp_fairness_calc.py` 執行後立即刪除
- 所有 Python 執行使用 `uv run python -X utf8`
