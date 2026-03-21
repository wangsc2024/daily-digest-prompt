---
name: context-compressor
version: "0.5.0"
description: |
  Context Window 壓縮策略工具。分析當前 Session I/O 用量，識別高 I/O 工具呼叫，
  提供 BufferWindow（保留最近 N 筆摘要）與 Summary（壓縮長文為固定長度）兩種壓縮策略，
  產出壓縮建議報告與可直接引用的壓縮摘要。與 context-budget-monitor（監控）互補，
  本 Skill 專注於主動壓縮與減量行動。
  Use when: avg_io_per_call 超標、Context Window 負載過高、需壓縮長文輸入、Phase 結果摘要、
  大量檔案讀取前的預壓縮評估。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "context-compressor"
  - "Context 壓縮"
  - "壓縮策略"
  - "I/O 減量"
  - "BufferWindow"
  - "Summary 壓縮"
  - "Context 瘦身"
  - "壓縮摘要"
depends-on:
  - context-budget-monitor
  - "config/budget.yaml"
---

# Context Compressor — Context Window 壓縮策略工具

> **定位**：context-budget-monitor 負責「偵測超標」，本 Skill 負責「主動壓縮」。
> 兩者搭配形成完整的 Context 保護閉環：偵測 → 壓縮 → 驗證。

## 設計原則

1. **被動監控不夠**：avg_io_per_call 持續超標（26567 vs 5000 門檻），僅監控無法降低 I/O
2. **壓縮而非丟棄**：保留關鍵資訊，壓縮冗餘部分
3. **策略可選**：依場景選擇 BufferWindow 或 Summary 策略
4. **可量測**：壓縮前後字數比較，計算壓縮率

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `config/budget.yaml`（取得 per-phase I/O 預算上限）

```bash
BUDGET_LIMIT=$(uv run python -X utf8 -c "
import yaml
try:
    d = yaml.safe_load(open('config/budget.yaml'))
    print(d.get('per_phase_budget', {}).get('max_io_chars', 50000))
except:
    print(50000)
" 2>/dev/null)
echo "BUDGET_LIMIT: $BUDGET_LIMIT"
```

---

## 步驟 1：I/O 用量分析（識別壓縮目標）

掃描最近的 JSONL 日誌，找出當前 Session 或近期的高 I/O 工具呼叫：

```bash
uv run python -X utf8 -c "
import json, glob, os
from collections import defaultdict

logs = sorted(glob.glob('logs/structured/*.jsonl'), key=os.path.getmtime, reverse=True)[:3]
tool_io = defaultdict(lambda: {'count': 0, 'total_chars': 0, 'max_chars': 0})

for logfile in logs:
    with open(logfile, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                tool = entry.get('tool', 'unknown')
                output_len = entry.get('output_len', 0) or 0
                tool_io[tool]['count'] += 1
                tool_io[tool]['total_chars'] += output_len
                tool_io[tool]['max_chars'] = max(tool_io[tool]['max_chars'], output_len)
            except:
                continue

ranked = sorted(tool_io.items(), key=lambda x: x[1]['total_chars'], reverse=True)[:10]
print('=== Top 10 高 I/O 工具 ===')
for tool, stats in ranked:
    avg = stats['total_chars'] // max(stats['count'], 1)
    print(f'{tool}: total={stats[\"total_chars\"]:,} chars, count={stats[\"count\"]}, avg={avg:,}, max={stats[\"max_chars\"]:,}')
" > temp/context-compressor-analysis.txt 2>/dev/null
```

讀取 `temp/context-compressor-analysis.txt`，識別壓縮目標：
- total_chars 最高的 3 個工具類型
- avg > 5000 chars 的工具呼叫

---

## 步驟 2：選擇壓縮策略

根據步驟 1 的分析結果，為每個壓縮目標選擇策略：

### 策略 A：BufferWindow（適合重複性讀取）

**場景**：同一檔案被多次讀取、多筆 API 回應需合併
**做法**：只保留最近 N 筆結果的摘要（每筆 ≤ 200 字），丟棄較早的完整輸出

```
BufferWindow 參數：
  window_size: 20    # 保留最近 20 筆
  summary_len: 200   # 每筆摘要上限（字元）
  priority: recency  # 最近的優先保留
```

**適用判斷**：
- 同一檔案 Read 次數 > 3 → BufferWindow
- API 回應累積 > 10 筆 → BufferWindow

### 策略 B：Summary（適合長文壓縮）

**場景**：Phase 1 結果傳遞給 Phase 2、多檔案分析結果匯總
**做法**：將長文壓縮為固定長度摘要，保留關鍵資訊

```
Summary 參數：
  target_len: 500    # 目標壓縮長度（字元）
  preserve: keys     # 保留 JSON key 結構
  strategy: extract  # 提取式（非生成式）
```

**適用判斷**：
- 單一輸出 > 5000 chars → Summary
- Phase 結果 JSON > 3000 chars → Summary

### 策略 C：Delegation（適合大量讀取）

**場景**：需讀取 5+ 個檔案的分析任務
**做法**：委派 Explore 子 Agent 讀取並回傳 ≤ 200 行 JSON 摘要

**適用判斷**：
- 預計讀取檔案數 > 5 → Delegation
- 預計讀取總量 > 50KB → Delegation

---

## 步驟 3：執行壓縮（Python 工具）

### 3a. Summary 壓縮（提取式）

```bash
uv run python -X utf8 -c "
import json, sys

def extract_summary(text, target_len=500):
    \"\"\"提取式壓縮：保留首段 + 關鍵行 + 末段\"\"\"
    lines = text.strip().split('\n')
    if len(text) <= target_len:
        return text

    # 首段（前 3 行）
    head = '\n'.join(lines[:3])
    # 末段（後 2 行）
    tail = '\n'.join(lines[-2:])
    # 中間：挑含關鍵詞的行
    keywords = ['結論', '建議', '錯誤', 'error', 'warning', '重要', 'TODO', '摘要', 'summary']
    middle_lines = []
    for line in lines[3:-2]:
        if any(kw in line.lower() for kw in keywords):
            middle_lines.append(line)
    middle = '\n'.join(middle_lines[:5])

    result = f'{head}\n...\n{middle}\n...\n{tail}'
    if len(result) > target_len:
        result = result[:target_len] + '... [已截斷]'
    return result

# 從 stdin 或檔案讀取
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--file', required=True, help='要壓縮的檔案路徑')
parser.add_argument('--target-len', type=int, default=500)
parser.add_argument('--output', help='輸出檔案路徑（不指定則 stdout）')
args = parser.parse_args()

with open(args.file, 'r', encoding='utf-8') as f:
    content = f.read()

original_len = len(content)
compressed = extract_summary(content, args.target_len)
compressed_len = len(compressed)
ratio = round((1 - compressed_len / max(original_len, 1)) * 100, 1)

output = {
    'original_chars': original_len,
    'compressed_chars': compressed_len,
    'compression_ratio': f'{ratio}%',
    'strategy': 'extract_summary',
    'content': compressed
}

if args.output:
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'壓縮完成：{original_len:,} → {compressed_len:,} chars（{ratio}% 壓縮率）')
else:
    print(json.dumps(output, ensure_ascii=False, indent=2))
" --file <FILE_PATH> --target-len 500 --output temp/compressed-output.json
```

### 3b. JSON 結構壓縮（保留 key，壓縮 value）

```bash
uv run python -X utf8 -c "
import json, sys

def compress_json(data, max_value_len=100):
    \"\"\"壓縮 JSON：保留所有 key，截斷過長 value\"\"\"
    if isinstance(data, dict):
        return {k: compress_json(v, max_value_len) for k, v in data.items()}
    elif isinstance(data, list):
        if len(data) > 5:
            return [compress_json(data[0], max_value_len), f'... ({len(data)-2} items omitted)', compress_json(data[-1], max_value_len)]
        return [compress_json(item, max_value_len) for item in data]
    elif isinstance(data, str) and len(data) > max_value_len:
        return data[:max_value_len] + '...'
    return data

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--file', required=True)
parser.add_argument('--max-value-len', type=int, default=100)
parser.add_argument('--output', required=True)
args = parser.parse_args()

with open(args.file, 'r', encoding='utf-8') as f:
    data = json.load(f)

original = json.dumps(data, ensure_ascii=False)
compressed = compress_json(data, args.max_value_len)
result = json.dumps(compressed, ensure_ascii=False, indent=2)

print(f'JSON 壓縮：{len(original):,} → {len(result):,} chars')
with open(args.output, 'w', encoding='utf-8') as f:
    f.write(result)
" --file <JSON_FILE> --max-value-len 100 --output temp/compressed-json.json
```

---

## 步驟 4：產出壓縮建議報告

用 Write 工具建立 `temp/compression-report.json`：

```json
{
  "generated_at": "<ISO 8601>",
  "analysis": {
    "total_io_chars": 0,
    "top_3_sources": [
      {"tool": "Read", "total_chars": 0, "recommendation": "Delegation"},
      {"tool": "Bash", "total_chars": 0, "recommendation": "Summary"},
      {"tool": "WebFetch", "total_chars": 0, "recommendation": "BufferWindow"}
    ]
  },
  "applied_compressions": [
    {
      "target": "<file or tool>",
      "strategy": "Summary",
      "original_chars": 0,
      "compressed_chars": 0,
      "ratio": "0%"
    }
  ],
  "budget_status": {
    "limit": 50000,
    "current_estimate": 0,
    "within_budget": true
  },
  "recommendations": [
    "建議將 skills/ 目錄掃描改為委派 Explore 子 Agent（預計減少 30KB I/O）",
    "Phase 1 結果傳遞 Phase 2 時，使用 Summary 壓縮至 500 chars"
  ]
}
```

---

## 步驟 5：清理暫存檔

```bash
rm -f temp/context-compressor-analysis.txt temp/compressed-output.json temp/compressed-json.json
```

保留 `temp/compression-report.json` 供呼叫端使用。

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| JSONL 日誌不存在 | 跳過步驟 1 分析，直接使用預設建議（Read > 5 檔案→Delegation，單檔 > 5KB→Summary） |
| budget.yaml 不存在 | 使用預設 per_phase_budget=50000 chars |
| Python 執行失敗 | 輸出文字版建議（不含量化數據），status 標記 partial |
| temp/ 目錄不存在 | 先建立 `mkdir -p temp` |

---

## 與其他 Skill 的協作

| 搭配 Skill | 協作模式 |
|------------|---------|
| **context-budget-monitor** | monitor 偵測超標 → compressor 執行壓縮 → monitor 驗證壓縮效果 |
| **system-insight** | insight 提供 avg_io_per_call 趨勢 → compressor 調整壓縮閾值 |
| **groq** | 大量文本壓縮時，可先透過 Groq relay 做快速摘要再壓縮 |

---

## 壓縮策略速查表

| 場景 | 策略 | 參數建議 |
|------|------|---------|
| 同一檔案重複讀取 > 3 次 | BufferWindow | window=20, summary_len=200 |
| Phase 結果 JSON > 3KB | Summary | target_len=500 |
| 需讀取 > 5 個檔案 | Delegation | 委派 Explore 子 Agent |
| API 回應累積 > 10 筆 | BufferWindow | window=10, summary_len=150 |
| 單一 Read 輸出 > 5KB | Summary | target_len=1000 |
| SKILL.md 全文掃描 | Delegation | Explore 回傳 frontmatter 摘要 |
