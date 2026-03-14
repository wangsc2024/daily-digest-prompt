---
name: cache-optimizer
version: "0.5.0"
description: |
  快取效率分析與 TTL 調優工具。解析 JSONL 結構化日誌中的快取事件，
  計算各 API 來源的命中率，對比 cache-policy.yaml 的 TTL 設定，
  產出端點級診斷報告與具體 TTL 調整建議。
  Use when: 快取命中率偏低、TTL 調整決策、快取效率診斷、快取趨勢分析。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "快取優化"
  - "快取分析"
  - "cache optimization"
  - "TTL 調優"
  - "命中率分析"
  - "快取效率"
  - "快取診斷"
depends-on:
  - api-cache
  - scheduler-state
---

# Cache Optimizer — 快取效率分析與 TTL 調優

## 設計目的

系統快取命中率長期偏低（system-insight 報告 14.57%，門檻 40%）。
現有 `api-cache` Skill 處理運行時快取讀寫，但缺乏**事後分析**能力：
無法得知哪個端點命中率最低、TTL 是否合理、快取使用趨勢如何。

本 Skill 填補此缺口：從 JSONL 日誌提取快取事件 → 計算端點級命中率 → 對比 TTL → 產出調優建議。

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/api-cache/SKILL.md`（了解快取運行時機制）
3. 讀取 `config/cache-policy.yaml`（取得各來源 TTL 設定）

---

## 步驟 1：收集 JSONL 快取事件

掃描 `logs/structured/` 目錄下的 JSONL 日誌檔案，提取含 `cache-read` 標籤的事件。

```bash
uv run python -X utf8 -c "
import json, glob, os, sys
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=8))
cutoff = (datetime.now(tz) - timedelta(days=7)).isoformat()
log_files = sorted(glob.glob('logs/structured/*.jsonl'))

events = []
for f in log_files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tags = entry.get('tags', [])
                if 'cache-read' in tags:
                    events.append({
                        'timestamp': entry.get('timestamp', ''),
                        'tags': tags,
                        'summary': entry.get('summary', ''),
                        'session_id': entry.get('session_id', '')
                    })
    except Exception:
        continue

print(json.dumps({'total_events': len(events), 'events': events[-500:]}, ensure_ascii=False))
" > temp_cache_events.json
```

**降級**：若 `logs/structured/` 為空或不存在，記錄 `"no_logs_available": true`，跳至步驟 5 產出降級報告。

---

## 步驟 2：計算端點級命中率

解析事件，按 API 來源分組，計算命中率：

```bash
uv run python -X utf8 -c "
import json

with open('temp_cache_events.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

events = data.get('events', [])
sources = {}

for evt in events:
    tags = evt.get('tags', [])
    # 從 tags 提取來源名稱（api-cache Skill 會加 source tag）
    source = 'unknown'
    for t in tags:
        if t in ('todoist', 'pingtung-news', 'hackernews', 'knowledge', 'gmail', 'chatroom'):
            source = t
            break

    if source not in sources:
        sources[source] = {'reads': 0, 'misses': 0}
    sources[source]['reads'] += 1
    if 'cache-miss' in tags:
        sources[source]['misses'] += 1

report = {}
for src, counts in sources.items():
    reads = counts['reads']
    misses = counts['misses']
    hits = reads - misses
    rate = round(hits / reads * 100, 1) if reads > 0 else 0.0
    report[src] = {
        'total_reads': reads,
        'hits': hits,
        'misses': misses,
        'hit_rate_pct': rate
    }

print(json.dumps(report, ensure_ascii=False, indent=2))
" > temp_cache_hit_rates.json
```

---

## 步驟 3：對比 TTL 設定，產出調優建議

讀取 `config/cache-policy.yaml` 和步驟 2 的命中率報告，生成建議：

```bash
uv run python -X utf8 -c "
import json, sys

# 讀取命中率
with open('temp_cache_hit_rates.json', 'r', encoding='utf-8') as f:
    rates = json.load(f)

# 讀取 cache-policy.yaml 的 TTL（簡易解析）
import re
ttls = {}
try:
    with open('config/cache-policy.yaml', 'r', encoding='utf-8') as f:
        content = f.read()
    # 簡易提取 source name 和 ttl_minutes
    for match in re.finditer(r'(\w[\w-]*):\s*\n\s+file:.*\n\s+ttl_minutes:\s*(\d+)', content):
        name = match.group(1)
        ttl = int(match.group(2))
        ttls[name] = ttl
except Exception:
    pass

recommendations = []
for src, data in rates.items():
    hit_rate = data['hit_rate_pct']
    current_ttl = ttls.get(src, None)
    rec = {'source': src, 'hit_rate_pct': hit_rate, 'current_ttl_min': current_ttl}

    if hit_rate < 20:
        if current_ttl and current_ttl < 120:
            rec['suggestion'] = f'TTL 過短（{current_ttl}min），建議增至 {current_ttl * 3}min'
            rec['severity'] = 'high'
        else:
            rec['suggestion'] = '命中率極低，檢查快取寫入邏輯是否正常'
            rec['severity'] = 'high'
    elif hit_rate < 40:
        if current_ttl:
            rec['suggestion'] = f'建議將 TTL 從 {current_ttl}min 增至 {int(current_ttl * 1.5)}min'
            rec['severity'] = 'medium'
        else:
            rec['suggestion'] = '命中率偏低，建議加入快取策略'
            rec['severity'] = 'medium'
    elif hit_rate >= 80:
        rec['suggestion'] = '快取效率良好，維持現狀'
        rec['severity'] = 'ok'
    else:
        rec['suggestion'] = '命中率合理，可微調 TTL 嘗試提升'
        rec['severity'] = 'low'

    recommendations.append(rec)

# 排序：severity high 優先
order = {'high': 0, 'medium': 1, 'low': 2, 'ok': 3}
recommendations.sort(key=lambda x: order.get(x.get('severity', 'ok'), 3))

result = {
    'overall_hit_rate_pct': round(
        sum(r['hit_rate_pct'] * rates[r['source']]['total_reads'] for r in recommendations if r['source'] in rates) /
        max(sum(rates[r['source']]['total_reads'] for r in recommendations if r['source'] in rates), 1),
        1
    ),
    'sources_analyzed': len(recommendations),
    'recommendations': recommendations
}
print(json.dumps(result, ensure_ascii=False, indent=2))
" > temp_cache_recommendations.json
```

---

## 步驟 4：產出診斷報告

讀取步驟 2-3 結果，生成結構化診斷報告寫入 `results/cache-optimizer-report.json`：

```bash
uv run python -X utf8 -c "
import json
from datetime import datetime, timezone, timedelta

tz = timezone(timedelta(hours=8))

with open('temp_cache_hit_rates.json', 'r', encoding='utf-8') as f:
    rates = json.load(f)
with open('temp_cache_recommendations.json', 'r', encoding='utf-8') as f:
    recs = json.load(f)

report = {
    'generated_at': datetime.now(tz).isoformat(),
    'period_days': 7,
    'hit_rates_by_source': rates,
    'overall_hit_rate_pct': recs['overall_hit_rate_pct'],
    'sources_analyzed': recs['sources_analyzed'],
    'recommendations': recs['recommendations'],
    'action_items': [
        r for r in recs['recommendations']
        if r.get('severity') in ('high', 'medium')
    ]
}

with open('results/cache-optimizer-report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f\"Report generated: {recs['sources_analyzed']} sources, overall hit rate {recs['overall_hit_rate_pct']}%\")
print(f\"Action items: {len(report['action_items'])}\")
"
```

---

## 步驟 5：清理暫存檔

```bash
rm -f temp_cache_events.json temp_cache_hit_rates.json temp_cache_recommendations.json
```

---

## 輸出格式

### `results/cache-optimizer-report.json`

```json
{
  "generated_at": "ISO-8601",
  "period_days": 7,
  "hit_rates_by_source": {
    "todoist": {"total_reads": 50, "hits": 5, "misses": 45, "hit_rate_pct": 10.0},
    "hackernews": {"total_reads": 30, "hits": 20, "misses": 10, "hit_rate_pct": 66.7}
  },
  "overall_hit_rate_pct": 30.5,
  "sources_analyzed": 6,
  "recommendations": [
    {
      "source": "todoist",
      "hit_rate_pct": 10.0,
      "current_ttl_min": 45,
      "suggestion": "TTL 過短（45min），建議增至 135min",
      "severity": "high"
    }
  ],
  "action_items": []
}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `logs/structured/` 無 JSONL 檔案 | 產出空報告，`"no_logs_available": true`，建議先確認 post_tool_logger.py 正常運作 |
| `cache-policy.yaml` 讀取失敗 | 僅計算命中率，不產出 TTL 調優建議（`recommendations` 只含命中率） |
| 快取事件數 < 10 | 在報告中標記 `"low_confidence": true`，提示「樣本不足，建議累積更多日誌後重新分析」 |
| 所有來源命中率 > 80% | 產出「快取效率良好」報告，無 action_items |

---

## 與現有 Skill 的協作

| Skill | 協作方式 |
|-------|---------|
| `api-cache` | 本 Skill 分析其運行結果，不修改運行時邏輯 |
| `system-insight` | 本 Skill 的 `overall_hit_rate_pct` 可回饋 system-insight 的 `cache_hit_ratio` 指標 |
| `scheduler-state` | 讀取排程執行頻率，評估 TTL 是否匹配執行間隔 |

---

## 注意事項

- 所有 Python 腳本用 `uv run python -X utf8` 執行（非裸 `python`）
- 暫存檔案用完即刪，不留存
- 本 Skill 不修改 `config/cache-policy.yaml`，僅產出建議
- 不修改 `state/scheduler-state.json`（PowerShell 獨佔寫入）
- 禁止 `> nul`，使用 `> /dev/null 2>&1`
