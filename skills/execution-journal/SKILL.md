---
name: execution-journal
version: "0.5.0"
description: |
  統一執行追蹤日誌。為每次 Agent 執行產生結構化 trace entry，
  記錄 task_key、Skill chain、cache 命中狀態、各 Phase 耗時、失敗點與輸出 artifact 路徑，
  支援跨 Phase 因果關聯分析與失敗模式回溯。
  Use when: 執行追蹤、trace 分析、失敗回溯、Skill chain 記錄、跨 Phase 因果關聯、執行日誌。
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "execution-journal"
  - "執行追蹤"
  - "trace 分析"
  - "失敗回溯"
  - "Skill chain"
  - "執行日誌"
  - "跨 Phase 因果"
depends-on:
  - scheduler-state
  - system-insight
  - "config/dependencies.yaml"
---

# Execution Journal — 統一執行追蹤日誌

> **端點來源**：`config/dependencies.yaml`（ADR-001 Phase 3）
> **設計靈感**：langfuse trace schema + OpenTelemetry Span 語義（ADR-009）

## 設計哲學

本 Skill 解決一個核心問題：**現有系統的執行紀錄分散在三個位置**（`results/*.json`、`logs/structured/*.jsonl`、`state/scheduler-state.json`），無法回答「這次執行經過哪些 Skill？在哪個 Phase 失敗？cache 命中了多少？」等跨切面問題。

execution-journal 產生 **per-execution trace entry**，採用 OTel 語義欄位命名，將分散的執行數據整合為單一結構化記錄。

---

## Schema 定義（execution-journal entry）

每次 Agent 執行（一次 `claude -p` 呼叫）產生一筆 entry，寫入 `context/execution-journal.jsonl`（JSONL 追加格式）：

```json
{
  "trace_id": "從 $DIGEST_TRACE_ID 環境變數取得",
  "agent_name": "從 $AGENT_NAME 環境變數取得",
  "task_key": "skill_forge",
  "started_at": "ISO 8601",
  "ended_at": "ISO 8601",
  "duration_ms": 45000,
  "status": "success | partial | failed | timeout",
  "phase": "phase1 | phase2 | phase3 | single",
  "skill_chain": [
    {"skill": "todoist", "action": "query", "cache_hit": false, "duration_ms": 3200},
    {"skill": "knowledge-query", "action": "hybrid_search", "cache_hit": true, "duration_ms": 120},
    {"skill": "ntfy-notify", "action": "send", "cache_hit": false, "duration_ms": 800}
  ],
  "cache_summary": {
    "total_calls": 5,
    "hits": 2,
    "hit_ratio": 0.4
  },
  "failure_point": null,
  "error_message": null,
  "artifacts_produced": ["results/todoist-auto-skill_forge.json"],
  "io_summary": {
    "total_read_bytes": 15000,
    "total_write_bytes": 3000,
    "tool_calls": 25
  }
}
```

### 欄位說明

| 欄位 | 來源 | 說明 |
|------|------|------|
| `trace_id` | `$DIGEST_TRACE_ID` 環境變數 | 唯一識別此次執行（排程注入） |
| `agent_name` | `$AGENT_NAME` 環境變數 | Agent 名稱（如 `todoist-auto-skill_forge`） |
| `task_key` | prompt 對應的 task key | 與 `frequency-limits.yaml` 一致 |
| `started_at` / `ended_at` | 執行開始和結束時間 | ISO 8601 + Asia/Taipei |
| `duration_ms` | 計算得出 | 端到端耗時（毫秒） |
| `status` | 最終執行狀態 | success / partial / failed / timeout |
| `phase` | 執行階段 | phase1（查詢）/ phase2（執行）/ phase3（組裝）/ single |
| `skill_chain` | 逐步記錄 | 按執行順序記錄每個 Skill 呼叫，含 cache 命中與耗時 |
| `cache_summary` | 彙總 | 本次執行的整體 cache 命中率 |
| `failure_point` | 失敗時填寫 | 失敗發生的 Skill 名稱和步驟 |
| `error_message` | 失敗時填寫 | 錯誤訊息（截斷至 200 字元） |
| `artifacts_produced` | 產出檔案 | 本次執行產生的結果/狀態檔案路徑 |
| `io_summary` | 彙總 | Read/Write 位元組數和 tool call 次數 |

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（Skill 認知地圖）
3. 讀取 `skills/api-cache/SKILL.md`（步驟 2 cache_hit 判定使用）

---

## 步驟 1：收集執行上下文

在 Agent 執行**結束前**（寫入 results JSON 之後），收集以下資訊：

```bash
TRACE_ID=${DIGEST_TRACE_ID:-"interactive-$(date +%Y%m%d_%H%M%S)"}
AGENT_NAME=${AGENT_NAME:-"claude-code-interactive"}
STARTED_AT=$(date -Iseconds)
```

從本次執行中回顧：
- 呼叫了哪些 Skill（依讀取 SKILL.md 的順序）
- 每個 Skill 的 cache 命中狀態（是否讀取了 `cache/*.json`）
- 是否有失敗發生及失敗位置
- 產出了哪些 artifacts

---

## 步驟 2：建構 Skill Chain

按本次執行的時間順序，記錄每個 Skill 呼叫：

```json
{
  "skill": "Skill 名稱（對應 SKILL_INDEX.md）",
  "action": "具體操作（query / search / send / import / analyze）",
  "cache_hit": true,
  "duration_ms": 0
}
```

**cache_hit 判定規則**（依 api-cache Skill 邏輯）：
- 讀取了 `cache/*.json` 且 `valid` 欄位為 `true` → `true`
- 呼叫了外部 API（curl POST/GET） → `false`
- 純本地操作（Read/Write/Grep） → `null`（不適用）

> TTL 判定由 PowerShell Phase 0 預計算寫入 `cache/status.json`，Agent 直接讀取 `valid` 布林值，不自行計算時間差（依 api-cache Skill 規範）。

---

## 步驟 3：計算彙總指標

```bash
uv run python -X utf8 -c "
import json, sys

chain = json.loads(sys.argv[1])
api_calls = [s for s in chain if s.get('cache_hit') is not None]
hits = sum(1 for s in api_calls if s.get('cache_hit'))
total = len(api_calls)

summary = {
    'total_calls': total,
    'hits': hits,
    'hit_ratio': round(hits / total, 2) if total > 0 else 0.0
}
print(json.dumps(summary))
" '<skill_chain_json>'
```

---

## 步驟 4：寫入 Journal Entry

用 Write 工具建立暫存 JSON 檔 `temp_journal_entry.json`，包含完整 trace entry。

追加到 `context/execution-journal.jsonl`：

```bash
cat temp_journal_entry.json >> context/execution-journal.jsonl
echo "" >> context/execution-journal.jsonl
rm temp_journal_entry.json
```

---

## 步驟 5：Journal 檔案維護

### 大小控管
```bash
JOURNAL_SIZE=$(wc -c < context/execution-journal.jsonl 2>/dev/null || echo 0)
if [ "$JOURNAL_SIZE" -gt 1048576 ]; then
  # 超過 1MB，保留最近 500 筆
  tail -500 context/execution-journal.jsonl > context/execution-journal.tmp
  mv context/execution-journal.tmp context/execution-journal.jsonl
  echo "JOURNAL_ROTATED: kept last 500 entries"
fi
```

### 每日摘要（供 system-insight 使用）

在每日第一次執行時（或由 system-insight 觸發），從 journal 產生當日摘要：

```bash
uv run python -X utf8 -c "
import json, sys
from datetime import date

today = date.today().isoformat()
entries = []
with open('context/execution-journal.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if e.get('started_at', '').startswith(today):
                entries.append(e)
        except json.JSONDecodeError:
            continue

total = len(entries)
success = sum(1 for e in entries if e.get('status') == 'success')
failed = sum(1 for e in entries if e.get('status') in ('failed', 'timeout'))
avg_duration = sum(e.get('duration_ms', 0) for e in entries) / total if total else 0

# Skill frequency
skill_freq = {}
for e in entries:
    for s in e.get('skill_chain', []):
        name = s.get('skill', 'unknown')
        skill_freq[name] = skill_freq.get(name, 0) + 1

# Cache overall
cache_hits = sum(e.get('cache_summary', {}).get('hits', 0) for e in entries)
cache_total = sum(e.get('cache_summary', {}).get('total_calls', 0) for e in entries)

summary = {
    'date': today,
    'total_executions': total,
    'success_rate': round(success / total, 3) if total else 0,
    'failed_count': failed,
    'avg_duration_ms': round(avg_duration),
    'cache_hit_ratio': round(cache_hits / cache_total, 3) if cache_total else 0,
    'top_skills': sorted(skill_freq.items(), key=lambda x: -x[1])[:10],
    'failure_points': [
        {'agent': e.get('agent_name'), 'point': e.get('failure_point'), 'error': e.get('error_message', '')[:100]}
        for e in entries if e.get('status') in ('failed', 'timeout')
    ]
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
" > context/journal-daily-summary.json
```

---

## 步驟 6：跨 Phase 因果關聯查詢

提供結構化查詢介面，從 journal 中分析：

### 查詢失敗模式
```bash
uv run python -X utf8 -c "
import json
entries = []
with open('context/execution-journal.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except:
                pass

failed = [e for e in entries if e.get('status') in ('failed', 'timeout')]
# Group by failure_point
from collections import Counter
points = Counter(e.get('failure_point', 'unknown') for e in failed)
print('Failure Points (top 10):')
for point, count in points.most_common(10):
    print(f'  {point}: {count}')
"
```

### 查詢 Skill Chain 熱點
```bash
uv run python -X utf8 -c "
import json
from collections import Counter
entries = []
with open('context/execution-journal.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except:
                pass

chains = []
for e in entries:
    chain_str = ' → '.join(s.get('skill', '?') for s in e.get('skill_chain', []))
    if chain_str:
        chains.append(chain_str)

print('Top Skill Chains:')
for chain, count in Counter(chains).most_common(10):
    print(f'  [{count}x] {chain}')
"
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| 環境變數不存在（`$DIGEST_TRACE_ID`） | 生成 `interactive-{timestamp}` 替代 |
| `context/execution-journal.jsonl` 不存在 | 自動建立空檔案 |
| JSONL 追加失敗（權限問題） | 記錄 warn 日誌，不阻斷主任務 |
| Journal 檔案損壞（含無效 JSON 行） | 查詢時跳過無效行，不影響有效紀錄 |
| 舊版 entry 缺少新增欄位 | 查詢時用 `.get()` + 預設值容錯 |

---

## 與現有系統的整合點

| 系統 | 整合方式 |
|------|---------|
| **system-insight** | 讀取 `journal-daily-summary.json` 取得當日 success_rate、cache_hit_ratio、failure_points |
| **quality-tracker** | 從 journal entry 的 `status` + `duration_ms` 補充品質維度 |
| **trace_analyzer.py** | 可從 journal JSONL 取代部分 JSONL 日誌分析邏輯 |
| **check-health.ps1** | 新增 [執行追蹤] 區塊，讀取 journal 摘要 |
| **post_tool_logger** | journal 記錄 session 級追蹤，post_tool_logger 記錄 tool 級追蹤，互補不衝突 |

---

**版本歷史**：
- v0.5.0（2026-03-19）：初始版本，skill-forge 自動生成
