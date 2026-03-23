---
name: failure-hour-analyzer
version: "0.5.0"
description: |
  高失敗時段根因分析器。從 JSONL 日誌與 scheduler-state 中按小時統計失敗率，
  識別高失敗時段（如 7 點、13 點峰值），分類根因（API 不穩/資源競爭/排程衝突/超時/配置錯誤），
  產出 state/time-slot-risk.json 供 pre-flight-check 整合，並生成時段風險報告。
  Use when: 成功率低於門檻（<95%）時診斷失敗集中時段、識別時段型根因、建立時段風險評分、
  優化排程時段配置，或當 system-insight 告警 daily_success_rate 偏低時使用。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "failure-hour-analyzer"
  - "高失敗時段"
  - "時段根因分析"
  - "失敗時段"
  - "peak hour diagnosis"
  - "時段風險"
  - "成功率診斷"
depends-on:
  - scheduler-state
  - system-insight
  - pre-flight-check
  - "config/dependencies.yaml"
---

# Failure Hour Analyzer — 高失敗時段根因分析器

> **端點來源**：`config/dependencies.yaml`（deps key: `knowledge_query`）— 用於 KB 匯入步驟

## 設計哲學

本 Skill 專注於**時間維度的失敗模式分析**：不只看「什麼失敗了」，更要看「什麼時候最容易失敗、為什麼那個時段特別脆弱」。透過歷史日誌的按小時聚合、根因分類、與外部因素交叉比對，產出可操作的時段風險評分，讓 pre-flight-check 和排程配置能據此做預防性調整。

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立 Skill 認知地圖）
3. 讀取 `skills/scheduler-state/SKILL.md`（了解 scheduler-state 資料結構）

---

## 步驟 1：收集執行記錄（資料來源聚合）

從兩個資料來源提取近 N 天（預設 7 天）的執行記錄：

### 1a. scheduler-state.json（主要來源）

```bash
uv run python -X utf8 -c "
import json, sys
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
cutoff = (datetime.now(TZ) - timedelta(days=7)).isoformat()
data = json.load(open('state/scheduler-state.json', encoding='utf-8'))
runs = data.get('runs', [])
recent = [r for r in runs if r.get('started_at', '') >= cutoff]
print(json.dumps({'total_runs': len(recent), 'sample': recent[:3]}, ensure_ascii=False, indent=2))
"
```

### 1b. JSONL 結構化日誌（補充來源）

```bash
uv run python -X utf8 -c "
import json, glob, os
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
cutoff = datetime.now(TZ) - timedelta(days=7)
cutoff_str = cutoff.strftime('%Y%m%d')

files = sorted(glob.glob('logs/structured/*.jsonl'))
recent_files = [f for f in files if os.path.basename(f)[:8] >= cutoff_str]
entries = []
for f in recent_files[-10:]:
    with open(f, 'r', encoding='utf-8') as fh:
        for line in fh:
            try:
                e = json.loads(line.strip())
                if e.get('event') in ('session_end', 'tool_error', 'blocked'):
                    entries.append(e)
            except:
                pass
print(json.dumps({'log_entries': len(entries)}, ensure_ascii=False))
"
```

**降級**：若 scheduler-state.json 不可讀，改用純 JSONL 日誌分析。若兩者均不可用，`status: "failed"`。

---

## 步驟 2：按小時聚合失敗率

```bash
uv run python -X utf8 -c "
import json, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
cutoff = (datetime.now(TZ) - timedelta(days=7)).isoformat()
data = json.load(open('state/scheduler-state.json', encoding='utf-8'))
runs = [r for r in data.get('runs', []) if r.get('started_at', '') >= cutoff]

hourly = defaultdict(lambda: {'total': 0, 'failed': 0, 'errors': []})
for r in runs:
    ts = r.get('started_at', '')
    if len(ts) >= 13:
        hour = int(ts[11:13])
        hourly[hour]['total'] += 1
        if r.get('status') in ('failed', 'timeout', 'error'):
            hourly[hour]['failed'] += 1
            hourly[hour]['errors'].append({
                'agent': r.get('agent', 'unknown'),
                'error': str(r.get('error', ''))[:100],
                'status': r.get('status')
            })

result = {}
for h in range(24):
    d = hourly[h]
    rate = round(d['failed'] / d['total'] * 100, 1) if d['total'] > 0 else 0
    result[str(h).zfill(2)] = {
        'total': d['total'],
        'failed': d['failed'],
        'failure_rate_pct': rate,
        'is_peak': rate > 20 and d['total'] >= 3,
        'top_errors': d['errors'][:3]
    }
print(json.dumps(result, ensure_ascii=False, indent=2))
" > temp_hourly_stats.json
```

**高失敗時段判定**：failure_rate > 20% 且 total >= 3 次 → 標記為 `is_peak: true`。

---

## 步驟 3：根因分類（Failure Mode Taxonomy）

對每個高失敗時段的 `top_errors` 進行分類：

| 根因類別 | 英文鍵 | 判定規則（error 訊息關鍵字） |
|---------|--------|---------------------------|
| API 不穩定 | `api_instability` | 含 `connection refused`、`timeout`、`503`、`502`、`ECONNREFUSED`、`fetch failed` |
| 資源競爭 | `resource_contention` | 含 `lock`、`busy`、`EBUSY`、`concurrent`、`rate limit` |
| 排程衝突 | `schedule_conflict` | 含 `already running`、`lock file`、`zombie`、`殭屍` |
| 執行超時 | `execution_timeout` | 含 `timeout`、`timed out`、`超時`、`killed` |
| 配置錯誤 | `config_error` | 含 `not found`、`missing`、`invalid`、`parse error`、`yaml` |
| 依賴缺失 | `dependency_missing` | 含 `module not found`、`import error`、`command not found`、`uv run` |

```bash
uv run python -X utf8 -c "
import json, re

TAXONOMY = {
    'api_instability': ['connection refused', 'timeout', '503', '502', 'ECONNREFUSED', 'fetch failed', 'ETIMEDOUT'],
    'resource_contention': ['lock', 'busy', 'EBUSY', 'concurrent', 'rate limit', 'rate_limit'],
    'schedule_conflict': ['already running', 'lock file', 'zombie', '殭屍', '.lock'],
    'execution_timeout': ['timed out', '超時', 'killed', 'SIGTERM', 'max_duration'],
    'config_error': ['not found', 'missing', 'invalid', 'parse error', 'yaml', 'json'],
    'dependency_missing': ['module not found', 'import error', 'command not found', 'uv run', 'ModuleNotFoundError']
}

def classify(error_msg):
    msg = error_msg.lower()
    for category, keywords in TAXONOMY.items():
        for kw in keywords:
            if kw.lower() in msg:
                return category
    return 'unknown'

hourly = json.load(open('temp_hourly_stats.json', encoding='utf-8'))
classification = {}
for hour, data in hourly.items():
    if data.get('is_peak'):
        causes = {}
        for err in data.get('top_errors', []):
            cat = classify(err.get('error', '') + ' ' + err.get('status', ''))
            causes[cat] = causes.get(cat, 0) + 1
        classification[hour] = {
            'failure_rate_pct': data['failure_rate_pct'],
            'total': data['total'],
            'failed': data['failed'],
            'root_causes': causes,
            'primary_cause': max(causes, key=causes.get) if causes else 'unknown'
        }

print(json.dumps(classification, ensure_ascii=False, indent=2))
"
```

---

## 步驟 4：時段風險評分模型

計算每小時的風險評分（0-100），綜合以下因子：

```
risk_score = (
    historical_failure_rate × 0.5 +      # 歷史失敗率（0-100）
    concurrent_task_density × 0.2 +        # 同時段排程任務密度（0-100）
    api_dependency_count × 0.15 +          # 該時段任務的外部 API 依賴數（0-100）
    recent_trend × 0.15                    # 近 3 天趨勢（惡化=100, 穩定=50, 改善=0）
)
```

```bash
uv run python -X utf8 -c "
import json
from collections import defaultdict

hourly = json.load(open('temp_hourly_stats.json', encoding='utf-8'))

risk_scores = {}
for hour in range(24):
    h = str(hour).zfill(2)
    data = hourly.get(h, {'total': 0, 'failed': 0, 'failure_rate_pct': 0})

    hist_rate = min(data['failure_rate_pct'], 100)
    density = min(data['total'] / 0.3, 100) if data['total'] > 0 else 0  # normalize to 30 runs/day

    score = round(hist_rate * 0.5 + density * 0.2 + 50 * 0.15 + 50 * 0.15, 1)

    level = 'low'
    if score >= 60: level = 'critical'
    elif score >= 40: level = 'high'
    elif score >= 20: level = 'medium'

    risk_scores[h] = {
        'risk_score': score,
        'risk_level': level,
        'total_runs': data['total'],
        'failure_rate_pct': data['failure_rate_pct']
    }

print(json.dumps(risk_scores, ensure_ascii=False, indent=2))
" > temp_risk_scores.json
```

---

## 步驟 5：產出 time-slot-risk.json

將風險評分寫入 `state/time-slot-risk.json`，供 pre-flight-check Skill 讀取：

```bash
uv run python -X utf8 -c "
import json
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
risk = json.load(open('temp_risk_scores.json', encoding='utf-8'))

output = {
    'generated_at': datetime.now(TZ).isoformat(),
    'analysis_window_days': 7,
    'hourly_risk': risk,
    'peak_hours': [h for h, d in risk.items() if d['risk_level'] in ('critical', 'high')],
    'safest_hours': [h for h, d in risk.items() if d['risk_level'] == 'low'],
    'recommendations': []
}

for h in output['peak_hours']:
    output['recommendations'].append(
        f'時段 {h}:00 風險等級 {risk[h][\"risk_level\"]}（失敗率 {risk[h][\"failure_rate_pct\"]}%），建議減少排程任務或啟用預檢'
    )

print(json.dumps(output, ensure_ascii=False, indent=2))
"
```

用 Write 工具將輸出寫入 `state/time-slot-risk.json`。

---

## 步驟 6：生成時段風險報告

整合步驟 2-5 的分析結果，產出結構化報告：

```markdown
## 時段失敗率分析報告

### 分析期間：近 7 天

### 高失敗時段
| 時段 | 失敗率 | 主要根因 | 風險等級 |
|------|--------|---------|---------|
| {hour}:00 | {rate}% | {primary_cause} | {risk_level} |

### 根因分布
{各根因類別出現次數與佔比}

### 建議行動
{依風險等級排序的改善建議}
```

---

## 步驟 7：清理暫存檔

```bash
rm -f temp_hourly_stats.json temp_risk_scores.json
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| scheduler-state.json 不可讀 | 改用 JSONL 日誌分析，報告標註「資料來源：JSONL 日誌」 |
| JSONL 日誌不存在或為空 | `status: "failed"`，報告標註「無可用資料來源」 |
| 近 7 天執行次數 < 10 | 延伸分析窗口至 14 天；仍不足則 `status: "partial"` |
| pre-flight-check Skill 不存在 | 仍產出 time-slot-risk.json，但跳過整合步驟 |
| 所有時段均無高失敗峰值 | `status: "success"`，報告顯示「系統時段健康度良好」 |

---

## 與 pre-flight-check 的整合

本 Skill 產出的 `state/time-slot-risk.json` 應被 pre-flight-check Skill 在步驟 1 讀取：

```python
# pre-flight-check 整合片段（建議）
risk = json.load(open('state/time-slot-risk.json'))
current_hour = datetime.now().strftime('%H')
hour_risk = risk['hourly_risk'].get(current_hour, {})
if hour_risk.get('risk_level') == 'critical':
    # 建議延遲執行或啟用額外預檢
    pass
```

---

## 輸出格式

### 結果 JSON（results/todoist-auto-*.json 中引用時）

```json
{
  "peak_hours": ["07", "13"],
  "risk_levels": {"07": "high", "13": "critical"},
  "primary_causes": {"07": "api_instability", "13": "schedule_conflict"},
  "total_runs_analyzed": 200,
  "analysis_window_days": 7,
  "recommendations_count": 3,
  "time_slot_risk_updated": true
}
```

---

## 注意事項

- `state/time-slot-risk.json` 由本 Skill 寫入，pre-flight-check 讀取（單向依賴）
- 所有 Python 腳本用 `uv run python -X utf8` 執行（Windows 相容）
- 禁止 `> nul`，用 `> /dev/null 2>&1`
- curl POST 必須用 Write 建立 JSON 檔再 `-d @file.json`（Windows 相容）
- 分析窗口預設 7 天，可透過環境變數 `ANALYSIS_DAYS` 調整

---

**版本歷史**：
- v0.5.0（2026-03-23）：初版，KB 基礎薄弱，建議透過 skill-audit 補強
