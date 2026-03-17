---
name: context-budget-monitor
version: "1.0.0"
description: |
  Agent I/O 預算監控與 Context 保護強制執行。從 JSONL 結構化日誌解析 per-session
  I/O 位元組總量，識別超標 Agent（avg_io_per_call > 門檻），產出 agent-level 排名報告、
  具體超標 session 清單與改善建議（委派子 Agent、拆分大檔讀取）。
  支援 system-insight critical alert（avg_io_per_call 持續超標 5 倍）的根因定位。
  Use when: Context 保護分析、I/O 預算監控、session I/O 超標偵測、agent 預算排名、Context 膨脹根因分析。
allowed-tools: [Bash, Read, Write, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "context-budget-monitor"
  - "I/O 預算"
  - "Context 保護"
  - "Context 膨脹"
  - "session I/O"
  - "avg_io_per_call"
  - "I/O 超標"
  - "預算監控"
depends-on:
  - system-insight
  - ntfy-notify
---

# context-budget-monitor：Agent I/O 預算監控與 Context 保護強制執行

## 設計目的

system-insight 報告 `avg_io_per_call` 持續高達 24.7KB（門檻 5KB，超標 5 倍），
但僅提供系統級聚合指標，無法回答「哪個 Agent 最耗 Context？哪些 session 違規？」。
本 Skill 從 JSONL 日誌解析 per-session I/O，定位超標根因，產出可行動的改善建議。

**支援 ADR**：ADR-004（Evals 評估系統，partial）— 提供 per-agent 可觀測性。

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（確認不與現有 Skill 重複功能）
3. 讀取 `config/benchmark.yaml`（取得 `avg_io_per_call` 門檻值，預設 5000）

---

## 步驟 1：掃描 JSONL 日誌計算 per-session I/O

**輸入**：`logs/structured/*.jsonl`（近 N 天，預設 3 天）

JSONL 每條記錄格式：
```json
{
  "ts": "ISO 8601",
  "sid": "session-id",
  "trace_id": "trace-id",
  "agent": "agent-name",
  "tool": "Read|Write|Bash|...",
  "input_len": 80,
  "output_len": 5317,
  "has_error": false,
  "tags": ["team-mode"]
}
```

```bash
uv run python -X utf8 -c "
import json, glob, os
from datetime import datetime, timedelta
from collections import defaultdict

days = int(os.environ.get('CBM_DAYS', '3'))
cutoff = datetime.now() - timedelta(days=days)
threshold = int(os.environ.get('CBM_THRESHOLD', '5000'))

sessions = defaultdict(lambda: {
    'agent': '', 'trace_id': '', 'total_input': 0,
    'total_output': 0, 'call_count': 0, 'tools': defaultdict(int),
    'first_ts': '', 'last_ts': '', 'has_error': False
})

for fpath in sorted(glob.glob('logs/structured/*.jsonl')):
    fname = os.path.basename(fpath)
    try:
        fdate = datetime.strptime(fname[:10], '%Y-%m-%d')
        if fdate < cutoff:
            continue
    except ValueError:
        pass

    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = rec.get('sid', 'unknown')
            s = sessions[sid]
            s['agent'] = rec.get('agent', s['agent'] or 'unknown')
            s['trace_id'] = rec.get('trace_id', s['trace_id'] or '')
            s['total_input'] += rec.get('input_len', 0)
            s['total_output'] += rec.get('output_len', 0)
            s['call_count'] += 1
            s['tools'][rec.get('tool', 'unknown')] += 1
            ts = rec.get('ts', '')
            if not s['first_ts'] or ts < s['first_ts']:
                s['first_ts'] = ts
            if ts > s['last_ts']:
                s['last_ts'] = ts
            if rec.get('has_error'):
                s['has_error'] = True

# 計算 per-session avg_io
results = []
for sid, s in sessions.items():
    total_io = s['total_input'] + s['total_output']
    avg_io = total_io / max(s['call_count'], 1)
    results.append({
        'sid': sid,
        'agent': s['agent'],
        'trace_id': s['trace_id'],
        'total_io_bytes': total_io,
        'avg_io_per_call': round(avg_io),
        'call_count': s['call_count'],
        'top_tools': dict(sorted(s['tools'].items(), key=lambda x: -x[1])[:3]),
        'exceeds_threshold': avg_io > threshold,
        'first_ts': s['first_ts'][:19],
        'has_error': s['has_error']
    })

# 排序：超標的在前，按 total_io 降序
results.sort(key=lambda x: (-int(x['exceeds_threshold']), -x['total_io_bytes']))

exceeded = [r for r in results if r['exceeds_threshold']]
summary = {
    'period_days': days,
    'threshold': threshold,
    'total_sessions': len(results),
    'exceeded_sessions': len(exceeded),
    'exceeded_pct': round(len(exceeded) / max(len(results), 1) * 100, 1),
    'sessions': results[:30]
}
with open('temp_cbm_sessions.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f'SESSIONS: {len(results)}, EXCEEDED: {len(exceeded)} ({summary[\"exceeded_pct\"]}%)')
"
```

**降級**：若 `logs/structured/` 不存在或為空，記錄 `data_source: "no_logs"` 並跳至步驟 5。

---

## 步驟 2：Agent 級別聚合與排名

**輸入**：步驟 1 的 `temp_cbm_sessions.json`

```bash
uv run python -X utf8 -c "
import json
from collections import defaultdict

with open('temp_cbm_sessions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

agents = defaultdict(lambda: {
    'total_io': 0, 'total_calls': 0, 'session_count': 0,
    'exceeded_count': 0, 'worst_session_io': 0
})

for s in data['sessions']:
    a = agents[s['agent']]
    a['total_io'] += s['total_io_bytes']
    a['total_calls'] += s['call_count']
    a['session_count'] += 1
    if s['exceeds_threshold']:
        a['exceeded_count'] += 1
    if s['total_io_bytes'] > a['worst_session_io']:
        a['worst_session_io'] = s['total_io_bytes']

ranking = []
for name, a in agents.items():
    avg = a['total_io'] / max(a['total_calls'], 1)
    ranking.append({
        'agent': name,
        'avg_io_per_call': round(avg),
        'total_io_kb': round(a['total_io'] / 1024, 1),
        'session_count': a['session_count'],
        'exceeded_count': a['exceeded_count'],
        'violation_rate': round(a['exceeded_count'] / max(a['session_count'], 1) * 100, 1),
        'worst_session_kb': round(a['worst_session_io'] / 1024, 1)
    })

ranking.sort(key=lambda x: -x['avg_io_per_call'])

result = {
    'threshold': data['threshold'],
    'agent_ranking': ranking[:20],
    'chronic_violators': [r for r in ranking if r['violation_rate'] > 50]
}

with open('temp_cbm_ranking.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f'AGENTS: {len(ranking)}, CHRONIC_VIOLATORS: {len(result[\"chronic_violators\"])}')
for r in ranking[:5]:
    print(f'  {r[\"agent\"]}: avg={r[\"avg_io_per_call\"]}B, violations={r[\"violation_rate\"]}%')
"
```

---

## 步驟 3：根因分析與改善建議

**輸入**：步驟 2 的 `temp_cbm_ranking.json`

讀取 `temp_cbm_ranking.json`，對每個 chronic_violator（violation_rate > 50%）產出改善建議：

| 根因模式 | 偵測條件 | 建議 |
|---------|---------|------|
| 大量 Read 工具呼叫 | top_tools 中 Read > 60% | 「使用 Explore 子 Agent 委派檔案讀取，避免主 Agent 累積大量內容」 |
| 單次超大輸出 | worst_session > 50KB | 「拆分大檔讀取，使用 offset/limit 參數控制每次讀取量」 |
| Bash 輸出過多 | top_tools 中 Bash > 40% | 「Bash 命令加 head/tail 限制輸出行數，或重導向至檔案後 Read 摘要」 |
| 泛用高 I/O | 無明顯集中工具 | 「review 該 prompt 模板，加入 Context 保護規則提醒」 |

用 Write 建立 `temp_cbm_report.json`，彙整排名與建議。

---

## 步驟 4：持久化監控結果

讀取或初始化 `context/io-budget-history.json`：

```bash
uv run python -X utf8 -c "
import json, os
from datetime import datetime

history_file = 'context/io-budget-history.json'
if os.path.exists(history_file):
    with open(history_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
else:
    history = {'version': 1, 'entries': []}

with open('temp_cbm_sessions.json', 'r', encoding='utf-8') as f:
    sessions = json.load(f)
with open('temp_cbm_ranking.json', 'r', encoding='utf-8') as f:
    ranking = json.load(f)

entry = {
    'date': datetime.now().strftime('%Y-%m-%d'),
    'total_sessions': sessions['total_sessions'],
    'exceeded_sessions': sessions['exceeded_sessions'],
    'exceeded_pct': sessions['exceeded_pct'],
    'top_violator': ranking['agent_ranking'][0]['agent'] if ranking['agent_ranking'] else 'none',
    'chronic_violators_count': len(ranking['chronic_violators'])
}

history['entries'].append(entry)
history['entries'] = history['entries'][-14:]
history['updated_at'] = datetime.now().isoformat()

with open(history_file, 'w', encoding='utf-8') as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

print('PERSIST_OK')
# 趨勢判定
if len(history['entries']) >= 2:
    prev = history['entries'][-2]['exceeded_pct']
    curr = entry['exceeded_pct']
    delta = curr - prev
    trend = 'improving' if delta < -5 else ('worsening' if delta > 5 else 'stable')
    print(f'TREND: {trend} (delta={delta:+.1f}pp)')
"
```

---

## 步驟 5：產出監控報告

讀取 `temp_cbm_sessions.json` 和 `temp_cbm_ranking.json`，以 Markdown 格式輸出報告：

```
📊 Context I/O 預算監控報告（近 {period_days} 天）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
門檻值：{threshold} bytes/call
總 Session 數：{total_sessions}
超標 Session：{exceeded_sessions}（{exceeded_pct}%）

🏆 Agent I/O 排名（Top 10）
| # | Agent | 平均 I/O | 違規率 | 最差 Session |
|---|-------|---------|--------|-------------|
| 1 | {agent} | {avg_io}B | {violation_rate}% | {worst_kb}KB |

⚠️ 慣性超標 Agent（violation_rate > 50%）
- {agent}: {建議}

📈 趨勢：{trend}
```

---

## 步驟 6：告警判定與通知

**判定邏輯**：

| 條件 | 告警等級 | 動作 |
|------|---------|------|
| exceeded_pct > 80% | critical | 讀取 `skills/ntfy-notify/SKILL.md`，發送 priority=4 告警 |
| exceeded_pct > 50% | warning | 發送 priority=3 告警 |
| chronic_violators_count > 3 | warning | 發送 priority=3 告警 |
| 其他 | none | 僅輸出報告 |

**告警通知**（用 Write 工具建立 JSON 檔，再 curl 發送）：

```json
{
  "topic": "wangsc2025",
  "title": "⚠️ Context I/O 預算超標：{exceeded_pct}% sessions 違規",
  "message": "近 {days} 天 {exceeded_sessions}/{total_sessions} sessions 超標（門檻 {threshold}B）。Top violator: {top_agent}。建議：委派子 Agent 處理大量讀取。",
  "priority": 4,
  "tags": ["warning", "chart_with_upwards_trend"]
}
```

```bash
curl -s -X POST https://ntfy.sh/wangsc2025 \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @ntfy_cbm_alert.json
rm ntfy_cbm_alert.json
```

---

## 步驟 7：清理暫存檔

```bash
rm -f temp_cbm_sessions.json temp_cbm_ranking.json temp_cbm_report.json
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| JSONL 日誌不存在或為空 | 產出空報告，`data_source: "no_logs"`，跳過告警 |
| benchmark.yaml 無 avg_io_per_call 門檻 | 使用預設值 5000 |
| JSONL 記錄格式不符（缺 input_len/output_len） | 跳過該條目，記錄 `parse_errors` 計數 |
| `context/io-budget-history.json` 損壞 | 重新初始化，從當前資料建立新基線 |
| ntfy 通知發送失敗 | 記錄 `alert_sent: false`，不影響報告產出 |

---

## 與現有 Skill 的關係

| Skill | 關係 |
|-------|------|
| system-insight | 互補：system-insight 產出 avg_io_per_call 聚合值，context-budget-monitor 向下鑽取到 per-session/per-agent 層級 |
| quality-tracker | 無重疊：quality-tracker 追蹤 DONE_CERT 品質分數，context-budget-monitor 追蹤 I/O 位元組 |
| cache-optimizer | 無重疊：cache-optimizer 分析快取 TTL，context-budget-monitor 分析 Context 使用量 |
| behavior-pattern-analyzer | 互補：behavior-pattern-analyzer 識別行為模式，context-budget-monitor 量化 I/O 成本 |

---

## 輸出格式

本 Skill 的最終輸出為：

1. **持久化檔案**：`context/io-budget-history.json`（14 天滾動 I/O 預算趨勢）
2. **報告**：Markdown 格式 Context I/O 預算監控報告（含 agent 排名表格）
3. **告警**（條件觸發）：ntfy 推播通知

---

## 注意事項

- 所有 curl POST 必須用 Write 工具建立 JSON 檔案（Windows 環境限制）
- Python 腳本使用 `uv run python -X utf8` 執行
- 禁止使用 `> nul`，改用 `> /dev/null 2>&1`
- 暫存檔（`temp_cbm_*.json`）步驟完成後務必刪除
- `context/io-budget-history.json` 為持久檔案，不受 7 天 TTL 清理影響
- JSONL 日誌量可能很大（10MB+/天），使用逐行讀取避免 OOM
