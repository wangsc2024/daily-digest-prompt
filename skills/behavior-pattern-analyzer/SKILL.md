---
name: behavior-pattern-analyzer
version: "1.0.0"
description: |
  Agent 行為模式分析器。讀取 context/behavior-patterns.json 的結構化行為記錄，
  依信心度、頻率、I/O 量聚類分析，識別可演化為新 Skill 的高價值行為模式，
  並產出結構化分析報告與 Skill 演化建議。
  Use when: 分析 Agent 行為模式、識別 Skill 演化候選、行為頻率統計、模式聚類、行為洞察報告。
allowed-tools: [Bash, Read, Write, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "行為模式分析"
  - "behavior pattern"
  - "模式挖掘"
  - "Skill 演化"
  - "行為聚類"
  - "agent 行為"
  - "behavior-pattern-analyzer"
depends-on:
  - system-insight
---

# behavior-pattern-analyzer — Agent 行為模式分析器

## 設計目的

系統透過 `hooks/behavior_tracker.py` 持續記錄 Agent 的工具呼叫行為模式至 `context/behavior-patterns.json`。
本 Skill 分析這些累積的行為數據，識別：
1. **高頻高信心模式**：穩定重複的行為，可能值得 Skill 化
2. **高 I/O 模式**：佔用大量 context window 的行為，可能需要優化或委派
3. **工具偏好分佈**：各工具的使用頻率與成功率，識別異常偏好
4. **Skill 演化候選**：綜合評分後推薦最值得演化為新 Skill 的模式

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立現有 Skill 認知地圖，用於去重比對）

---

## 步驟 1：載入行為模式數據

用 Read 讀取 `context/behavior-patterns.json`。

**數據結構確認**：
```json
{
  "version": 1,
  "patterns": {
    "<pattern_id>": {
      "tool": "工具名稱",
      "summary_sample": "行為摘要片段",
      "tags": ["標籤1", "標籤2"],
      "count": 7,
      "confidence": 0.4,
      "success_count": 7,
      "first_seen": "ISO timestamp",
      "last_seen": "ISO timestamp",
      "total_input": 4430,
      "total_output": 0
    }
  }
}
```

**降級**：檔案不存在或格式不符 → 記錄 `"error": "behavior-patterns.json 不存在或格式錯誤"`，跳至步驟 6。

---

## 步驟 2：模式聚類分析

用 Python 腳本執行四維度分析（用 Write 建立 `temp_bpa_analyze.py`，再用 `uv run python` 執行）：

```python
# temp_bpa_analyze.py
import json, sys
from collections import defaultdict
from datetime import datetime

with open('context/behavior-patterns.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

patterns = data.get('patterns', {})
total = len(patterns)

# 維度 1：信心度分佈
high_conf = {k: v for k, v in patterns.items() if v.get('confidence', 0) >= 0.8}
med_conf = {k: v for k, v in patterns.items() if 0.5 <= v.get('confidence', 0) < 0.8}
low_conf = {k: v for k, v in patterns.items() if v.get('confidence', 0) < 0.5}

# 維度 2：工具偏好分佈
tool_dist = defaultdict(lambda: {'count': 0, 'total_calls': 0, 'total_io': 0})
for p in patterns.values():
    tool = p.get('tool', 'unknown')
    tool_dist[tool]['count'] += 1
    tool_dist[tool]['total_calls'] += p.get('count', 0)
    tool_dist[tool]['total_io'] += p.get('total_input', 0) + p.get('total_output', 0)

# 維度 3：高 I/O 模式（top 10）
io_ranked = sorted(
    patterns.items(),
    key=lambda x: x[1].get('total_input', 0) + x[1].get('total_output', 0),
    reverse=True
)[:10]

# 維度 4：Skill 演化候選（高信心 + 高頻率 + 有標籤）
candidates = []
for pid, p in patterns.items():
    conf = p.get('confidence', 0)
    count = p.get('count', 0)
    tags = p.get('tags', [])
    io_total = p.get('total_input', 0) + p.get('total_output', 0)
    # 演化評分：信心度 * 40 + 頻率正規化 * 30 + 標籤豐富度 * 30
    freq_score = min(count / 20, 1.0) * 30
    tag_score = min(len(tags) / 5, 1.0) * 30
    score = conf * 40 + freq_score + tag_score
    candidates.append({
        'pattern_id': pid,
        'tool': p.get('tool', ''),
        'summary': p.get('summary_sample', '')[:100],
        'confidence': round(conf, 3),
        'count': count,
        'tags': tags,
        'io_total': io_total,
        'evolution_score': round(score, 2)
    })

candidates.sort(key=lambda x: x['evolution_score'], reverse=True)

result = {
    'total_patterns': total,
    'confidence_distribution': {
        'high': len(high_conf),
        'medium': len(med_conf),
        'low': len(low_conf)
    },
    'tool_distribution': {
        k: {'unique_patterns': v['count'], 'total_calls': v['total_calls'], 'total_io': v['total_io']}
        for k, v in sorted(tool_dist.items(), key=lambda x: x[1]['total_calls'], reverse=True)
    },
    'high_io_patterns': [
        {
            'pattern_id': pid,
            'tool': p.get('tool', ''),
            'io_total': p.get('total_input', 0) + p.get('total_output', 0),
            'summary': p.get('summary_sample', '')[:80]
        }
        for pid, p in io_ranked
    ],
    'evolution_candidates': candidates[:10]
}

with open('context/behavior-analysis-report.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"TOTAL_PATTERNS: {total}")
print(f"HIGH_CONFIDENCE: {len(high_conf)}")
print(f"TOP_CANDIDATE_SCORE: {candidates[0]['evolution_score'] if candidates else 0}")
print("ANALYSIS_OK")
```

執行：
```bash
uv run python -X utf8 temp_bpa_analyze.py
rm temp_bpa_analyze.py
```

**輸出**：`context/behavior-analysis-report.json`（完整分析報告）

---

## 步驟 3：Skill 演化判定

讀取 `context/behavior-analysis-report.json`，對 `evolution_candidates` 前 5 名：

1. **去重比對**：將候選的 `tags` 和 `tool` 與 `SKILL_INDEX.md` 的 triggers 比對
   - 重疊率 > 60% → 標記 `covered_by_existing_skill: true`
   - 重疊率 ≤ 60% → 標記為可演化候選

2. **演化建議生成**：對每個未被覆蓋的候選，生成建議：
   ```json
   {
     "pattern_id": "xxx",
     "suggested_skill_name": "基於 tags 和 tool 推導的 Skill 名稱",
     "rationale": "為何此模式值得 Skill 化（2-3 句）",
     "estimated_effort": "low | medium | high",
     "priority": "P1 | P2 | P3"
   }
   ```

3. 將演化建議寫入 `context/behavior-analysis-report.json` 的 `evolution_recommendations` 欄位

---

## 步驟 4：趨勢比對（可選，若有歷史報告）

檢查 `context/behavior-analysis-history/` 目錄是否有歷史報告：

```bash
ls context/behavior-analysis-history/*.json 2>/dev/null | wc -l
```

若有歷史報告（≥ 1 個），比對：
- 新增模式數量（本次 total - 上次 total）
- 信心度提升最多的模式
- 新出現的高頻模式

若無歷史報告 → 跳過此步驟。

---

## 步驟 5：歸檔與輸出

1. **歸檔當前報告**（保留歷史）：
   ```bash
   mkdir -p context/behavior-analysis-history
   cp context/behavior-analysis-report.json \
      "context/behavior-analysis-history/$(date +%Y%m%d).json"
   ```

2. **產出摘要**（供呼叫端使用）：

   從 `context/behavior-analysis-report.json` 提取關鍵指標：
   - 總模式數、高信心模式數
   - 工具偏好 top 3
   - 演化候選 top 3（含建議 Skill 名稱）
   - 高 I/O 模式 top 3（含優化建議）

---

## 步驟 6：結果 JSON（自動任務模式）

若作為自動任務呼叫，用 Write 建立結果 JSON：

```json
{
  "agent": "todoist-auto-behavior_pattern_analyzer",
  "task_type": "auto",
  "task_key": "behavior_pattern_analyzer",
  "status": "success",
  "total_patterns": 200,
  "high_confidence_count": 154,
  "evolution_candidates_count": 5,
  "top_candidate": {
    "pattern_id": "xxx",
    "suggested_skill_name": "...",
    "evolution_score": 85.0
  },
  "report_path": "context/behavior-analysis-report.json",
  "summary": "分析 200 個行為模式，識別 5 個 Skill 演化候選"
}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `behavior-patterns.json` 不存在 | `status: "failed"`，`error: "數據檔案不存在"` |
| `behavior-patterns.json` 為空或無 patterns | `status: "partial"`，產出空報告 |
| Python 執行失敗 | 記錄錯誤，`status: "failed"` |
| SKILL_INDEX.md 不可讀 | 跳過步驟 3 去重比對，僅輸出原始候選 |

---

## 輸出範例

### behavior-analysis-report.json 範例

```json
{
  "total_patterns": 85,
  "confidence_distribution": {
    "high": 54,
    "medium": 23,
    "low": 8
  },
  "tool_distribution": {
    "Bash": {"unique_patterns": 32, "total_calls": 847, "total_io": 124300},
    "Read": {"unique_patterns": 28, "total_calls": 653, "total_io": 89200},
    "Write": {"unique_patterns": 15, "total_calls": 201, "total_io": 32100}
  },
  "high_io_patterns": [
    {
      "pattern_id": "bash_curl_api_call_xyz",
      "tool": "Bash",
      "io_total": 15600,
      "summary": "curl -s -X POST http://localhost:3000/api/search/hybrid ..."
    }
  ],
  "evolution_candidates": [
    {
      "pattern_id": "read_config_yaml_pattern",
      "tool": "Read",
      "summary": "Read config/*.yaml 檔案以取得設定值",
      "confidence": 0.92,
      "count": 47,
      "tags": ["config", "yaml", "settings"],
      "io_total": 8900,
      "evolution_score": 78.4
    }
  ],
  "evolution_recommendations": [
    {
      "pattern_id": "read_config_yaml_pattern",
      "suggested_skill_name": "config-loader",
      "rationale": "高頻率讀取配置檔案（47 次），信心度 92%，可統一為配置載入 Skill 並加快取",
      "estimated_effort": "low",
      "priority": "P2"
    }
  ]
}
```

---

## 常見問題

### Q1：為何某些高頻模式的 evolution_score 很低？
**A**：evolution_score 綜合信心度、頻率、標籤豐富度三個維度。若模式雖高頻但信心度低（<0.5）或無標籤，評分會受影響。

### Q2：什麼樣的模式適合演化為 Skill？
**A**：符合以下條件的模式最適合：
- 信心度 ≥ 0.8（穩定重複）
- 頻率 ≥ 10 次（有使用需求）
- 有 3+ 個明確標籤（行為語義清晰）
- 總 I/O > 5000 tokens（有優化空間）

### Q3：如何手動觸發分析？
**A**：執行以下命令：
```bash
echo "請執行 behavior-pattern-analyzer Skill" | claude -p skills/behavior-pattern-analyzer/SKILL.md
```

---

## 注意事項

- 本 Skill 只讀取 `context/behavior-patterns.json`，**不修改**原始數據
- 分析報告寫入 `context/behavior-analysis-report.json`，歷史歸檔至 `context/behavior-analysis-history/`
- Python 腳本使用 `uv run python -X utf8` 執行
- 禁止 `> nul`，使用 `> /dev/null 2>&1`
- 所有暫存 Python 腳本執行後立即刪除
