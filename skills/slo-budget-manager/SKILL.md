---
name: slo-budget-manager
version: "0.5.0"
description: |
  SLO/Error Budget 治理工具。盤點近 N 天失敗 runs 並建立 failure mode taxonomy，
  定義 SLI/SLO 與 28 天滾動 Error Budget，計算 budget burn rate，
  當單一 failure class 消耗超過 20% budget 時觸發 postmortem 提案。
  輸出 state/slo-budget-report.json 供 system-insight 與 arch-evolution 消費。
  Use when: 成功率治理、失敗分類、Error Budget 計算、SLO 定義、postmortem 觸發、穩定性改善。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "slo-budget-manager"
  - "SLO 治理"
  - "Error Budget"
  - "失敗分類"
  - "failure mode"
  - "成功率治理"
  - "postmortem"
  - "budget burn"
  - "穩定性治理"
depends-on:
  - scheduler-state
  - system-insight
  - arch-evolution
  - ntfy-notify
  - "config/dependencies.yaml"
---

# SLO/Error Budget 治理工具

> **信號來源**：improvement-backlog rank 12（P1）、ADR-032（immediate_fix）、system-insight warning（daily_success_rate 84.6% < 90%）
> **設計參考**：Google SRE Error Budget Policy、Microsoft Reliability/FMA

## 設計哲學

本 Skill 將系統穩定性從「被動修 bug」提升為「主動治理」：
- **SLI（指標）**：定義哪些數字代表「健康」
- **SLO（目標）**：設定可量化的健康門檻
- **Error Budget（預算）**：用預算制度平衡穩定性與變更速度
- **Failure Mode Taxonomy（分類）**：讓每次失敗都有歸類，不再是未分類噪音

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（Skill 認知地圖）
3. 讀取 `config/slo.yaml`（若存在，載入現有 SLO 定義；不存在則步驟 2 建立）

---

## 步驟 1：資料收集（並行）

同時讀取以下資料來源：

**1a. scheduler-state.json（唯讀）**
```bash
uv run python -X utf8 -c "
import json
with open('state/scheduler-state.json', encoding='utf-8') as f:
    data = json.load(f)
runs = data.get('runs', [])[-200:]
total = len(runs)
failed = sum(1 for r in runs if r.get('status') != 'success')
print(f'TOTAL_RUNS: {total}')
print(f'FAILED_RUNS: {failed}')
print(f'SUCCESS_RATE: {(total - failed) / total * 100:.1f}%' if total > 0 else 'SUCCESS_RATE: N/A')
"
```

**1b. results/*.json（近 7 天結果檔）**
```bash
find results/ -name "todoist-auto-*.json" -mtime -7 -exec basename {} \; 2>/dev/null | head -50
```

**1c. system-insight.json**
```
Read context/system-insight.json
提取：metrics.daily_success_rate、alerts[]、statistics.failed_runs
```

**1d. 結構化日誌（failure 事件）**
```bash
uv run python -X utf8 -c "
import json, glob, os
from datetime import datetime, timedelta
cutoff = (datetime.now() - timedelta(days=7)).isoformat()
failures = []
for f in sorted(glob.glob('logs/structured/*.jsonl'))[-7:]:
    with open(f, encoding='utf-8') as fh:
        for line in fh:
            try:
                entry = json.loads(line)
                if entry.get('tags') and 'error' in str(entry.get('tags', [])).lower():
                    failures.append({
                        'timestamp': entry.get('timestamp', ''),
                        'tool': entry.get('tool', ''),
                        'tags': entry.get('tags', []),
                        'output_preview': str(entry.get('output', ''))[:200]
                    })
            except: pass
print(f'FAILURE_EVENTS: {len(failures)}')
for f in failures[:20]:
    print(json.dumps(f, ensure_ascii=False))
"
```

---

## 步驟 2：SLI/SLO 定義（若 config/slo.yaml 不存在則建立）

讀取 `config/slo.yaml`：
- **存在** → 載入現有定義，跳至步驟 3
- **不存在** → 用 Write 工具建立預設 SLO 配置：

```yaml
# SLO 定義（SLO/Error Budget 治理）
# 參考：Google SRE Error Budget Policy
version: 1
window_days: 28  # 滾動窗口

slis:
  daily_success_rate:
    description: "每日排程任務成功率"
    source: "state/scheduler-state.json → runs[].status"
    unit: "ratio"
  auto_task_completion_rate:
    description: "自動任務完成率（Phase 2 成功 / Phase 2 嘗試）"
    source: "results/todoist-auto-*.json → status"
    unit: "ratio"
  phase2_success_rate:
    description: "Phase 2 Agent 成功率"
    source: "state/scheduler-state.json → runs[].phase2_status"
    unit: "ratio"

slos:
  daily_success_rate:
    target: 0.90
    warning: 0.85
    critical: 0.80
  auto_task_completion_rate:
    target: 0.85
    warning: 0.75
    critical: 0.65
  phase2_success_rate:
    target: 0.90
    warning: 0.80
    critical: 0.70

error_budget:
  calculation: "1 - SLO target"
  window_days: 28
  postmortem_trigger:
    single_incident_burn_pct: 20
    weekly_burn_pct: 50
  actions:
    budget_remaining_gt_50pct: "正常變更速度"
    budget_remaining_25_50pct: "減速，優先修復穩定性"
    budget_remaining_lt_25pct: "凍結非關鍵變更，強制 postmortem"
    budget_exhausted: "全面凍結，專注修復"

failure_modes:
  timeout:
    description: "Agent 或 API 呼叫超時"
    retry: true
    max_retries: 1
    blast_radius: "single_task"
  api_failure:
    description: "外部 API 不可用（KB、Todoist、ntfy）"
    retry: true
    max_retries: 1
    blast_radius: "dependent_tasks"
  parse_error:
    description: "結果 JSON 格式錯誤或 schema 不符"
    retry: false
    blast_radius: "single_task"
  quota_exceeded:
    description: "Token 或 API 配額耗盡"
    retry: false
    blast_radius: "all_tasks"
  template_missing:
    description: "Prompt 模板不存在"
    retry: false
    blast_radius: "single_task"
  config_error:
    description: "配置檔案解析錯誤"
    retry: false
    blast_radius: "all_tasks"
  unknown:
    description: "未分類失敗"
    retry: false
    blast_radius: "unknown"
```

---

## 步驟 3：失敗分類（Failure Mode Taxonomy）

對步驟 1 收集的所有失敗事件，依 `config/slo.yaml` 的 `failure_modes` 進行分類：

```bash
uv run python -X utf8 -c "
import json, glob, re
from collections import Counter

# 載入 SLO 配置
import yaml
with open('config/slo.yaml', encoding='utf-8') as f:
    slo = yaml.safe_load(f)

# 分類規則（關鍵字比對）
RULES = {
    'timeout': ['timeout', 'timed out', 'exceeded', '超時', 'SIGTERM'],
    'api_failure': ['connection refused', 'ECONNREFUSED', '503', '502', '500', 'curl: (7)', '服務未啟動'],
    'parse_error': ['json', 'parse', 'schema', 'decode', 'SyntaxError', 'KeyError'],
    'quota_exceeded': ['quota', 'rate limit', '429', 'budget', 'token limit'],
    'template_missing': ['template', 'prompt not found', '模板不存在', 'FileNotFoundError'],
    'config_error': ['yaml', 'config', 'configuration', 'YAML']
}

def classify(text):
    text_lower = text.lower()
    for mode, keywords in RULES.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return mode
    return 'unknown'

# 掃描結果檔
results_dir = 'results'
taxonomy = Counter()
classified = []
for f in glob.glob(f'{results_dir}/todoist-auto-*.json'):
    try:
        with open(f, encoding='utf-8') as fh:
            data = json.load(fh)
        if data.get('status') not in ('success', None):
            error_text = str(data.get('error', '')) + str(data.get('summary', ''))
            mode = classify(error_text)
            taxonomy[mode] += 1
            classified.append({'file': f, 'mode': mode, 'error': error_text[:150]})
    except: pass

print('=== FAILURE MODE TAXONOMY ===')
for mode, count in taxonomy.most_common():
    print(f'{mode}: {count}')
print(f'TOTAL_CLASSIFIED: {sum(taxonomy.values())}')
print(f'UNKNOWN_RATE: {taxonomy.get(\"unknown\", 0) / max(sum(taxonomy.values()), 1) * 100:.1f}%')
"
```

**品質門檻**：`UNKNOWN_RATE` 應 < 10%。若 > 10%，檢查分類規則並補充關鍵字。

---

## 步驟 4：Error Budget 計算

```bash
uv run python -X utf8 -c "
import json, yaml
from datetime import datetime, timedelta

# 載入 SLO 配置
with open('config/slo.yaml', encoding='utf-8') as f:
    slo = yaml.safe_load(f)

# 載入排程狀態
with open('state/scheduler-state.json', encoding='utf-8') as f:
    scheduler = json.load(f)

window = slo.get('window_days', 28)
cutoff = (datetime.now() - timedelta(days=window)).isoformat()

# 計算 28 天窗口內的成功率
runs = [r for r in scheduler.get('runs', []) if r.get('started_at', '') >= cutoff]
total = len(runs)
success = sum(1 for r in runs if r.get('status') == 'success')
actual_rate = success / total if total > 0 else 0

# 對每個 SLO 計算 budget
budgets = {}
for sli_name, slo_def in slo.get('slos', {}).items():
    target = slo_def['target']
    budget_total = 1 - target  # e.g., 0.10 for 90% SLO
    budget_consumed = max(0, target - actual_rate) / budget_total if budget_total > 0 else 0
    budget_remaining = max(0, 1 - budget_consumed)
    budgets[sli_name] = {
        'target': target,
        'actual': round(actual_rate, 4),
        'budget_total': round(budget_total, 4),
        'budget_consumed_pct': round(budget_consumed * 100, 1),
        'budget_remaining_pct': round(budget_remaining * 100, 1)
    }

print('=== ERROR BUDGET STATUS ===')
for name, b in budgets.items():
    status = '🟢' if b['budget_remaining_pct'] > 50 else '🟡' if b['budget_remaining_pct'] > 25 else '🔴'
    print(f\"{name}: actual={b['actual']:.1%} target={b['target']:.0%} budget_remaining={b['budget_remaining_pct']}% {status}\")

# Postmortem 觸發檢查
trigger = slo.get('error_budget', {}).get('postmortem_trigger', {})
for name, b in budgets.items():
    if b['budget_consumed_pct'] >= trigger.get('weekly_burn_pct', 50):
        print(f'⚠️ POSTMORTEM_TRIGGER: {name} budget consumed {b[\"budget_consumed_pct\"]}% >= {trigger[\"weekly_burn_pct\"]}%')

print(json.dumps(budgets, ensure_ascii=False, indent=2))
"
```

---

## 步驟 5：產出報告（state/slo-budget-report.json）

用 Write 工具建立 `state/slo-budget-report.json`：

```json
{
  "generated_at": "<ISO 8601>",
  "window_days": 28,
  "slo_status": {
    "daily_success_rate": {
      "target": 0.90,
      "actual": "<步驟 4 計算值>",
      "budget_total": 0.10,
      "budget_consumed_pct": "<步驟 4 計算值>",
      "budget_remaining_pct": "<步驟 4 計算值>",
      "status": "<green|yellow|red>"
    }
  },
  "failure_taxonomy": {
    "timeout": "<count>",
    "api_failure": "<count>",
    "parse_error": "<count>",
    "quota_exceeded": "<count>",
    "template_missing": "<count>",
    "config_error": "<count>",
    "unknown": "<count>"
  },
  "unknown_rate_pct": "<步驟 3 計算值>",
  "postmortem_triggered": false,
  "postmortem_reasons": [],
  "recommendations": [
    "<依 budget 狀態與 failure taxonomy 產出的具體改善建議>"
  ],
  "action_level": "<normal|slow_down|freeze_non_critical|full_freeze>"
}
```

---

## 步驟 6：Postmortem 提案（條件觸發）

若步驟 4 偵測到 `POSTMORTEM_TRIGGER`：

1. 識別消耗最多 budget 的 failure mode（步驟 3 taxonomy 最高計數）
2. 建立 postmortem 提案至 `context/improvement-backlog.json`（用 Edit 工具追加）：
   - priority: P0
   - pattern: "Postmortem：{failure_mode} 導致 {sli_name} SLO 違規"
   - description: 含具體數字（budget consumed %、failure count、affected runs）
   - execution_plan: 4 步驟（根因分析 → 修復方案 → 驗證 → 回顧）
3. 發送 ntfy 告警（讀取 `skills/ntfy-notify/SKILL.md` 依指示發送）：
   - title: "⚠️ SLO 違規：{sli_name}"
   - message: "Error Budget 已消耗 {consumed}%，主要失敗模式：{top_failure_mode}（{count} 次）"
   - priority: 4
   - tags: ["warning", "chart"]

若未觸發 postmortem，僅記錄報告，不發送告警。

---

## 步驟 7：整合至 system-insight

若 `context/system-insight.json` 存在，用 Edit 工具在 `recommendations[]` 末尾追加：
- 若 budget_remaining > 50%：不追加（健康狀態）
- 若 budget_remaining 25-50%：追加「【P2】Error Budget 剩餘 {remaining}%，建議減少非關鍵變更」
- 若 budget_remaining < 25%：追加「【P0】Error Budget 剩餘 {remaining}%，建議凍結非關鍵變更，優先處理 {top_failure_mode}」

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| scheduler-state.json 不可讀 | 僅從 results/*.json 計算，標記 `data_source: "results_only"` |
| config/slo.yaml 不存在 | 步驟 2 自動建立預設配置 |
| 結構化日誌不存在 | 僅從 results/*.json 分類，標記 `data_source: "results_only"` |
| 無任何失敗事件 | 報告 `action_level: "normal"`，budget 100%，不觸發 postmortem |
| improvement-backlog.json 不可寫 | 跳過步驟 6 的 backlog 追加，僅發送 ntfy 告警 |

---

## 輸出檔案

| 檔案 | 用途 | 消費者 |
|------|------|--------|
| `state/slo-budget-report.json` | SLO 狀態 + failure taxonomy + budget burn | system-insight、arch-evolution |
| `config/slo.yaml` | SLO 定義（首次建立後持久化） | 本 Skill、check-health.ps1 |

---

## 注意事項

- `state/scheduler-state.json` 為**唯讀**（PowerShell 獨佔寫入）
- 所有 curl POST 必須用 Write 建立 JSON 檔再 `-d @file.json`（Windows 環境）
- Python 用 `uv run python`，不用裸 `python`
- 禁止 `> nul`，用 `> /dev/null 2>&1`
- failure_modes 分類規則可在 `config/slo.yaml` 中自定義擴充
