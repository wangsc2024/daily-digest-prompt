---
name: quality-tracker
version: "0.5.0"
description: |
  Agent 輸出品質追蹤與回歸偵測。從結構化 JSONL 日誌萃取 DONE_CERT 品質分數，
  聚合每日品質指標（quality_score、schema_check 通過率、任務成功率），
  計算 7 天移動平均並偵測品質回歸（連續 2 天低於基線），產出趨勢報告與告警。
  支援 ADR-004（Evals 評估系統）的品質趨勢追蹤需求。
  Use when: 品質追蹤、品質回歸偵測、品質趨勢分析、DONE_CERT 品質彙總、Agent 品質監控。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Grep]
cache-ttl: "N/A"
triggers:
  - "品質追蹤"
  - "品質回歸"
  - "quality tracking"
  - "quality regression"
  - "品質趨勢"
  - "quality trend"
  - "品質閘門"
  - "DONE_CERT 分析"
  - "品質監控"
depends-on:
  - ntfy-notify
---

# quality-tracker：Agent 輸出品質追蹤與回歸偵測

## 設計目的

系統每日執行 130+ 次 Agent 任務，每次產出 DONE_CERT（含 quality_score 1-5 分、schema_check pass/fail）。
目前這些品質資料散落在 JSONL 日誌中，無系統化追蹤。本 Skill 將品質資料聚合為每日指標，
偵測品質回歸趨勢，在品質持續下降時發送告警。

**支援 ADR**：ADR-004（Evals 評估系統，partial）— 實現品質分數趨勢化追蹤。

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（確認不與現有 Skill 重複功能）
3. 讀取 `templates/shared/done-cert.md`（確認 DONE_CERT 格式定義）

---

## 步驟 1：掃描 JSONL 日誌萃取 DONE_CERT

**輸入**：`logs/structured/*.jsonl`（Hook post_tool_logger 產出的結構化日誌）

**萃取邏輯**：用 Python 腳本從 JSONL 日誌中搜尋包含 `DONE_CERT_BEGIN` 的條目。

```bash
uv run python -X utf8 -c "
import json, glob, os, re
from datetime import datetime, timedelta

days = int(os.environ.get('QT_DAYS', '7'))
cutoff = datetime.now() - timedelta(days=days)
cert_pattern = re.compile(r'===DONE_CERT_BEGIN===\s*(\{.*?\})\s*===DONE_CERT_END===', re.DOTALL)

certs = []
for fpath in sorted(glob.glob('logs/structured/*.jsonl')):
    fname = os.path.basename(fpath)
    # 從檔名推斷日期（格式：YYYYMMDD_HHMMSS.jsonl 或含日期）
    try:
        date_str = fname[:8]
        fdate = datetime.strptime(date_str, '%Y%m%d')
        if fdate < cutoff:
            continue
    except ValueError:
        pass  # 無法解析日期的檔案仍然掃描

    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        for m in cert_pattern.finditer(content):
            try:
                cert = json.loads(m.group(1))
                cert['_source_file'] = fname
                cert['_date'] = fname[:8] if len(fname) >= 8 else 'unknown'
                certs.append(cert)
            except json.JSONDecodeError:
                pass

print(json.dumps({'total_certs': len(certs), 'certs': certs}, ensure_ascii=False))
" > temp_qt_certs.json
```

**降級**：若 `logs/structured/` 不存在或為空，嘗試掃描 `logs/*.log`。
若仍無資料，記錄 `data_source: "no_logs"` 並跳至步驟 5 產出空報告。

---

## 步驟 2：每日品質指標聚合

**輸入**：步驟 1 產出的 `temp_qt_certs.json`

```bash
uv run python -X utf8 -c "
import json
from collections import defaultdict

with open('temp_qt_certs.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

daily = defaultdict(lambda: {
    'scores': [], 'schema_pass': 0, 'schema_fail': 0, 'schema_skip': 0,
    'status_done': 0, 'status_partial': 0, 'status_failed': 0, 'total': 0
})

for cert in data.get('certs', []):
    date = cert.get('_date', 'unknown')
    checklist = cert.get('checklist', {})
    qs = checklist.get('quality_score')
    sc = checklist.get('schema_check', 'skip')
    status = cert.get('status', 'UNKNOWN')

    d = daily[date]
    d['total'] += 1
    if qs is not None:
        d['scores'].append(qs)
    if sc == 'pass':
        d['schema_pass'] += 1
    elif sc == 'fail':
        d['schema_fail'] += 1
    else:
        d['schema_skip'] += 1
    if status == 'DONE':
        d['status_done'] += 1
    elif status == 'PARTIAL':
        d['status_partial'] += 1
    elif status == 'FAILED':
        d['status_failed'] += 1

result = {}
for date, d in sorted(daily.items()):
    avg_score = round(sum(d['scores']) / len(d['scores']), 2) if d['scores'] else 0
    schema_rate = round(d['schema_pass'] / max(d['schema_pass'] + d['schema_fail'], 1), 3)
    success_rate = round(d['status_done'] / max(d['total'], 1), 3)
    result[date] = {
        'avg_quality_score': avg_score,
        'schema_pass_rate': schema_rate,
        'success_rate': success_rate,
        'total_certs': d['total'],
        'score_count': len(d['scores']),
        'schema_fail_count': d['schema_fail']
    }

print(json.dumps(result, ensure_ascii=False, indent=2))
" > temp_qt_daily.json
```

**輸出**：`temp_qt_daily.json`，每日一條記錄，含 `avg_quality_score`、`schema_pass_rate`、`success_rate`。

---

## 步驟 3：趨勢計算與回歸偵測

**輸入**：步驟 2 的 `temp_qt_daily.json`

**回歸偵測規則**：
- 計算 7 天移動平均 `quality_score`
- 若連續 2 天的 `avg_quality_score` 低於移動平均 × 0.8 → 標記 `regression_detected: true`
- 若任一天 `schema_fail_count > 5` → 標記 `schema_alert: true`

```bash
uv run python -X utf8 -c "
import json

with open('temp_qt_daily.json', 'r', encoding='utf-8') as f:
    daily = json.load(f)

dates = sorted(daily.keys())
scores = [daily[d]['avg_quality_score'] for d in dates]

# 7 天移動平均
if len(scores) >= 3:
    window = min(7, len(scores))
    moving_avg = round(sum(scores[-window:]) / window, 2)
else:
    moving_avg = round(sum(scores) / max(len(scores), 1), 2)

# 回歸偵測：連續 2 天低於移動平均 × 0.8
threshold = moving_avg * 0.8
regression_detected = False
regression_days = []
if len(scores) >= 2:
    for i in range(-1, -min(3, len(scores)+1), -1):
        if scores[i] < threshold and scores[i] > 0:
            regression_days.append(dates[i])
    regression_detected = len(regression_days) >= 2

# Schema 告警
schema_alert = any(daily[d].get('schema_fail_count', 0) > 5 for d in dates)

# 趨勢方向
if len(scores) >= 2:
    delta = scores[-1] - scores[-2]
    trend = 'improving' if delta > 0.2 else ('declining' if delta < -0.2 else 'stable')
else:
    trend = 'insufficient_data'

result = {
    'period_days': len(dates),
    'moving_average': moving_avg,
    'latest_score': scores[-1] if scores else 0,
    'trend': trend,
    'regression_detected': regression_detected,
    'regression_days': regression_days,
    'schema_alert': schema_alert,
    'threshold': round(threshold, 2),
    'daily_summary': {d: {
        'score': daily[d]['avg_quality_score'],
        'success_rate': daily[d]['success_rate'],
        'total': daily[d]['total_certs']
    } for d in dates[-7:]}
}
print(json.dumps(result, ensure_ascii=False, indent=2))
" > temp_qt_trend.json
```

---

## 步驟 4：持久化品質趨勢

讀取 `temp_qt_trend.json`，將結果寫入 `context/quality-trend.json`（滾動保留 14 天）。

```bash
uv run python -X utf8 -c "
import json, os
from datetime import datetime

trend_file = 'context/quality-trend.json'
with open('temp_qt_trend.json', 'r', encoding='utf-8') as f:
    new_trend = json.load(f)

# 讀取或初始化歷史
if os.path.exists(trend_file):
    with open(trend_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
else:
    history = {'version': 1, 'entries': []}

# 追加本次
entry = {
    'date': datetime.now().strftime('%Y-%m-%d'),
    'moving_average': new_trend['moving_average'],
    'latest_score': new_trend['latest_score'],
    'trend': new_trend['trend'],
    'regression_detected': new_trend['regression_detected'],
    'schema_alert': new_trend['schema_alert'],
    'period_days': new_trend['period_days']
}
history['entries'].append(entry)

# 滾動保留 14 天
history['entries'] = history['entries'][-14:]
history['updated_at'] = datetime.now().isoformat()

with open(trend_file, 'w', encoding='utf-8') as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

print('PERSIST_OK')
print(json.dumps(entry, ensure_ascii=False))
"
```

---

## 步驟 5：產出品質趨勢報告

讀取 `temp_qt_trend.json`，以 Markdown 格式輸出報告：

```
📊 品質趨勢報告（近 {period_days} 天）
━━━━━━━━━━━━━━━━━━━━━━━━
移動平均：{moving_average}/5
最新評分：{latest_score}/5
趨勢方向：{trend}
回歸偵測：{regression_detected}

每日明細：
| 日期 | 品質分 | 成功率 | 任務數 |
|------|--------|--------|--------|
| ... | ... | ... | ... |
```

---

## 步驟 6：告警判定與通知

**判定邏輯**：

| 條件 | 告警等級 | 動作 |
|------|---------|------|
| `regression_detected: true` | critical | 讀取 `skills/ntfy-notify/SKILL.md`，發送 priority=4 告警 |
| `schema_alert: true` | warning | 發送 priority=3 告警 |
| `trend == "declining"` | info | 包含在報告中，不另外告警 |
| 其他 | none | 僅輸出報告 |

**告警通知**（用 Write 工具建立 JSON 檔，再 curl 發送）：

```json
{
  "topic": "wangsc2025",
  "title": "⚠️ 品質回歸偵測：{latest_score}/5（移動平均 {moving_average}）",
  "message": "連續 {len(regression_days)} 天品質分低於門檻 {threshold}。回歸日期：{regression_days}。建議檢查近期 prompt 修改或 API 變更。",
  "priority": 4,
  "tags": ["warning", "chart_with_downwards_trend"]
}
```

```bash
curl -s -X POST https://ntfy.sh \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @ntfy_qt_alert.json
rm ntfy_qt_alert.json
```
（JSON 發送時必須 POST 到根網址 `https://ntfy.sh`，不可用 topic URL，否則整段 JSON 會變成通知內文。）

---

## 步驟 7：清理暫存檔

```bash
rm -f temp_qt_certs.json temp_qt_daily.json temp_qt_trend.json
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| JSONL 日誌不存在或為空 | 產出空報告，`data_source: "no_logs"`，跳過告警 |
| DONE_CERT 格式解析失敗 | 跳過該條目，記錄 `parse_errors` 計數 |
| `context/quality-trend.json` 損壞 | 重新初始化，從當前資料建立新基線 |
| ntfy 通知發送失敗 | 記錄 `alert_sent: false`，不影響報告產出 |

---

## 輸出格式

本 Skill 的最終輸出為：

1. **持久化檔案**：`context/quality-trend.json`（14 天滾動品質趨勢）
2. **報告**：Markdown 格式品質趨勢報告（含每日明細表格）
3. **告警**（條件觸發）：ntfy 推播通知

---

## 與現有 Skill 的關係

| Skill | 關係 |
|-------|------|
| system-insight | 互補：system-insight 追蹤系統指標（成功率、快取命中率），quality-tracker 追蹤品質指標（quality_score、schema_check） |
| system-audit | 互補：system-audit 做靜態評分（7 維度 38 子項），quality-tracker 做動態趨勢追蹤 |
| cache-optimizer | 無重疊：cache-optimizer 分析快取效率，quality-tracker 分析輸出品質 |

---

## 注意事項

- 所有 curl POST 必須用 Write 工具建立 JSON 檔案（Windows 環境限制）
- Python 腳本使用 `uv run python -X utf8` 執行
- 禁止使用 `> nul`，改用 `> /dev/null 2>&1`
- 暫存檔（`temp_qt_*.json`）步驟完成後務必刪除
- `context/quality-trend.json` 為持久檔案，不受 7 天 TTL 清理影響
