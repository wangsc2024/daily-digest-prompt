---
name: pre-flight-check
version: "0.5.0"
description: |
  執行前飛行檢查。在 Agent 排程任務實際執行前，探測所有外部依賴健康狀態
  （KB API、Todoist API、ntfy、Groq relay），讀取 scheduler-state.json 歷史失敗資料
  計算當前時段風險分數，並輸出 go/no-go 決策與建議 timeout 調整。
  Use when: 排程任務執行前健康檢查、外部依賴可用性偵測、時段風險評估、timeout 動態調整、預防性失敗迴避。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強。
allowed-tools: [Bash, Read, Write, Grep]
cache-ttl: "5min"
triggers:
  - "pre-flight-check"
  - "執行前檢查"
  - "飛行檢查"
  - "依賴健康"
  - "時段風險"
  - "go/no-go"
  - "預防性檢查"
depends-on:
  - scheduler-state
  - api-cache
---

# Pre-Flight Check — 執行前飛行檢查

> **端點來源**：`config/dependencies.yaml`（ADR-001 Phase 3）— 請讀取 YAML 取得對應 base_url（deps key: knowledge_query + todoist + ntfy_notify + groq_relay）。

## 設計哲學

本 Skill 在排程任務**執行前**探測外部依賴健康狀態，結合歷史失敗時段資料計算風險分數，
提供 go/no-go 決策。目標：將可預防的失敗（依賴不可用、高風險時段）在執行前攔截，
避免浪費 token 和排程 slot。

執行鏈：
```
依賴探測（4 端點並行 curl）→ 歷史風險計算（scheduler-state.json）
→ 風險評分（0-100）→ go/no-go 決策 → 建議 timeout 調整 → 輸出報告
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（確認依賴 Skill 存在）

---

## 步驟 1：外部依賴健康探測

對以下 4 個端點執行並行 health check（每個 max-time 5 秒）：

```bash
# 並行探測 4 個端點
KB_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "http://localhost:3000/api/health" 2>/dev/null || echo "000")
TODOIST_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TODOIST_API_TOKEN" "https://api.todoist.com/api/v1/tasks?limit=1" 2>/dev/null || echo "000")
NTFY_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "https://ntfy.sh/health" 2>/dev/null || echo "000")
GROQ_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "http://localhost:3002/groq/health" 2>/dev/null || echo "000")

echo "KB=$KB_STATUS TODOIST=$TODOIST_STATUS NTFY=$NTFY_STATUS GROQ=$GROQ_STATUS"
```

**健康判定**：

| 端點 | 健康（HTTP） | 權重 | 降級影響 |
|------|------------|------|---------|
| KB API (localhost:3000) | 200 | 30% | 知識庫查詢/匯入失敗 |
| Todoist API | 200-299 | 30% | 任務查詢/更新失敗 |
| ntfy.sh | 200 | 20% | 通知發送失敗（不影響主流程） |
| Groq relay (localhost:3002) | 200 | 20% | 前處理加速不可用（可降級） |

**輸出**：`dependency_score`（0-100），各端點健康狀態。

---

## 步驟 2：時段風險計算

讀取 `state/scheduler-state.json`（唯讀），提取最近 7 天的執行記錄：

```bash
# 取得當前小時
CURRENT_HOUR=$(date +"%H")
echo "CURRENT_HOUR=$CURRENT_HOUR"
```

用以下 Python 腳本讀取 `state/scheduler-state.json` 並計算時段風險：

```bash
TIME_RISK_JSON=$(uv run python -X utf8 -c "
import json, os
from datetime import datetime, timedelta, timezone

# 讀取當前小時
current_hour = datetime.now(timezone(timedelta(hours=8))).hour

# 讀取 scheduler-state.json
sched_file = 'state/scheduler-state.json'
if not os.path.exists(sched_file):
    print(json.dumps({'time_risk_score': 0, 'hour_failure_rate': 0, 'in_high_risk_list': False, 'consecutive_failures': 0, 'error': 'scheduler-state not found'}))
    exit(0)

sched = json.load(open(sched_file, encoding='utf-8'))
runs = sched.get('runs', [])

# 統計過去 7 天當前小時的執行記錄
seven_days_ago = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=7)
total_at_hour = 0
failed_at_hour = 0
last_3_at_hour = []

for run in runs:
    run_time = datetime.fromisoformat(run['timestamp'])
    if run_time < seven_days_ago:
        continue
    if run_time.hour == current_hour:
        total_at_hour += 1
        if run['status'] in ['failed', 'timeout']:
            failed_at_hour += 1
            last_3_at_hour.append(False)
        else:
            last_3_at_hour.append(True)

hour_failure_rate = failed_at_hour / total_at_hour if total_at_hour > 0 else 0

# 讀取 system-insight.json
insight_file = 'context/system-insight.json'
high_failure_hours = []
if os.path.exists(insight_file):
    insight = json.load(open(insight_file, encoding='utf-8'))
    high_failure_hours = insight.get('high_failure_hours', [])

in_high_risk_list = current_hour in high_failure_hours

# 計算時段風險分數
time_risk_score = 0

# 基於歷史失敗率（0-50 分）
if hour_failure_rate > 0.5:
    time_risk_score += 50
elif hour_failure_rate > 0.3:
    time_risk_score += 35
elif hour_failure_rate > 0.15:
    time_risk_score += 20

# 是否在高風險清單（0-30 分）
if in_high_risk_list:
    time_risk_score += 30

# 連續失敗加權（0-20 分）
last_3 = last_3_at_hour[:3] if len(last_3_at_hour) >= 3 else []
last_2 = last_3_at_hour[:2] if len(last_3_at_hour) >= 2 else []

if len(last_3) == 3 and not any(last_3):
    time_risk_score += 20
elif len(last_2) == 2 and not any(last_2):
    time_risk_score += 10

print(json.dumps({
    'time_risk_score': time_risk_score,
    'hour_failure_rate': round(hour_failure_rate, 3),
    'in_high_risk_list': in_high_risk_list,
    'consecutive_failures': 3 if (len(last_3) == 3 and not any(last_3)) else (2 if (len(last_2) == 2 and not any(last_2)) else 0),
    'total_at_hour': total_at_hour,
    'failed_at_hour': failed_at_hour
}))
" 2>/dev/null || echo "{\"time_risk_score\": 0, \"error\": \"script failed\"}")

echo "$TIME_RISK_JSON"
```

**輸出**：`time_risk_score`（0-100）、`hour_failure_rate`、`in_high_risk_list`。

---

## 步驟 3：綜合風險評分與 Go/No-Go 決策

用以下 Python 腳本計算綜合風險並輸出決策：

```bash
DECISION_JSON=$(uv run python -X utf8 -c "
import json, sys

# 假設從步驟 1 和 2 取得的數值
# 實際使用時，這些值應從 Bash 變數傳入或從暫存檔讀取
dependency_score = ${DEPENDENCY_SCORE:-80}
time_risk_score_data = json.loads('${TIME_RISK_JSON}')
time_risk_score = time_risk_score_data.get('time_risk_score', 0)

# 計算綜合風險
overall_risk = (100 - dependency_score) * 0.6 + time_risk_score * 0.4

# 決策邏輯
if overall_risk <= 30:
    decision = 'GO'
    action = '正常執行，使用預設 timeout'
    timeout_multiplier = 1.0
elif overall_risk <= 60:
    decision = 'GO_CAUTIOUS'
    action = '執行但 timeout × 1.5，啟用降級模式'
    timeout_multiplier = 1.5
elif overall_risk <= 80:
    decision = 'CONDITIONAL'
    action = '僅執行不依賴失敗端點的任務，timeout × 2'
    timeout_multiplier = 2.0
else:
    decision = 'NO_GO'
    action = '建議延後執行，記錄原因，排程下次重試'
    timeout_multiplier = None

print(json.dumps({
    'overall_risk': round(overall_risk, 2),
    'decision': decision,
    'action': action,
    'timeout_multiplier': timeout_multiplier
}))
" 2>/dev/null || echo "{\"overall_risk\": 0, \"decision\": \"UNKNOWN\", \"error\": \"script failed\"}")

echo "$DECISION_JSON"
```

**決策表**：

| 綜合風險 | 決策 | 建議行動 |
|---------|------|---------|
| 0-30 | **GO** | 正常執行，使用預設 timeout |
| 31-60 | **GO（謹慎）** | 執行但 timeout × 1.5，啟用降級模式 |
| 61-80 | **CONDITIONAL** | 僅執行不依賴失敗端點的任務，timeout × 2 |
| 81-100 | **NO-GO** | 建議延後執行，記錄原因，排程下次重試 |

---

## 步驟 4：Timeout 建議計算

讀取 `config/timeouts.yaml`，依風險等級調整：

```
if overall_risk <= 30:
    timeout_multiplier = 1.0
elif overall_risk <= 60:
    timeout_multiplier = 1.5
elif overall_risk <= 80:
    timeout_multiplier = 2.0
else:
    timeout_multiplier = null  # NO-GO，不計算
```

**輸出建議**（不修改 config，僅建議）：
```json
{
  "phase1_timeout": "原值 × multiplier",
  "phase2_timeout": "原值 × multiplier",
  "phase3_timeout": "原值 × multiplier"
}
```

---

## 步驟 5：輸出報告

用 Write 工具建立 `context/pre-flight-report.json`：

```json
{
  "generated_at": "<ISO 8601>",
  "current_hour": 14,
  "dependencies": {
    "kb_api": {"status": 200, "healthy": true},
    "todoist_api": {"status": 200, "healthy": true},
    "ntfy": {"status": 200, "healthy": true},
    "groq_relay": {"status": 0, "healthy": false}
  },
  "dependency_score": 80,
  "time_risk": {
    "hour_failure_rate": 0.15,
    "in_high_risk_list": false,
    "consecutive_failures": 0,
    "time_risk_score": 20
  },
  "overall_risk": 20,
  "decision": "GO",
  "timeout_multiplier": 1.0,
  "timeout_recommendations": {
    "phase1_timeout": 300,
    "phase2_timeout": 2400,
    "phase3_timeout": 180
  },
  "unavailable_dependencies": ["groq_relay"],
  "summary": "3/4 依賴健康，時段風險低，建議正常執行"
}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| scheduler-state.json 不可讀 | 跳過時段風險計算，`time_risk_score = 0`，僅依賴依賴健康分數 |
| system-insight.json 不存在 | `high_failure_hours = []`，不加高風險時段分數 |
| 所有端點 timeout | `dependency_score = 0`，`overall_risk` 可能 > 80，建議 NO-GO |
| curl 不可用 | 無法執行，回報錯誤，`decision = "UNKNOWN"` |
| config/timeouts.yaml 不可讀 | 使用預設值：phase1=300s, phase2=2400s, phase3=180s |

---

## 整合方式

本 Skill 設計為**被其他 prompt/腳本呼叫**的前置步驟：

1. **PowerShell 排程腳本**：在 `run-todoist-agent-team.ps1` Phase 0 後、Phase 1 前呼叫
2. **Prompt 引用**：在 `templates/shared/preamble.md` 新增可選前置步驟
3. **自動任務 prompt**：在任務執行前讀取 `context/pre-flight-report.json`

讀取方式：
```bash
# 檢查報告是否存在且新鮮（5 分鐘內）
REPORT_AGE=$(uv run python -X utf8 -c "
import json, os
from datetime import datetime, timezone, timedelta
f = 'context/pre-flight-report.json'
if not os.path.exists(f):
    print('STALE')
else:
    d = json.load(open(f, encoding='utf-8'))
    gen = datetime.fromisoformat(d['generated_at'])
    now = datetime.now(timezone(timedelta(hours=8)))
    print('FRESH' if (now - gen).total_seconds() < 300 else 'STALE')
" 2>/dev/null || echo "STALE")
```

若 `STALE` → 重新執行本 Skill 全流程。
若 `FRESH` → 直接讀取 `context/pre-flight-report.json` 的 `decision` 欄位。

---

## 注意事項

- **不修改任何配置檔**：本 Skill 僅產出建議報告，不修改 `config/timeouts.yaml` 或 `state/scheduler-state.json`
- **不阻擋執行**：即使決策為 NO-GO，最終是否執行由呼叫者（PS 腳本或 Agent）決定
- **報告有效期 5 分鐘**：`cache-ttl: 5min`，避免過時資料誤導決策
- **Windows 相容**：所有 curl 使用標準語法，Python 用 `uv run python`，禁止 `> nul`
