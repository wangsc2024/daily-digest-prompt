---
name: research-saturation-analyzer
version: "0.1.0"
description: |
  ⚠️ 草稿版（KB 不可用時生成）
  研究主題飽和度分析與收穫遞減偵測。讀取 research-registry.json 的全量研究記錄，
  進行主題關鍵詞聚類、多因子飽和度評分（研究次數×新穎度×時間間隔×深度），
  識別已飽和主題（收穫遞減）與待深化高潛力主題，產出研究方向建議並更新 research-series.json。
  Use when: 研究方向規劃、主題飽和度分析、收穫遞減偵測、研究資源最佳化配置、知識差距識別。
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
cache-ttl: "24h"
triggers:
  - "研究飽和度"
  - "收穫遞減"
  - "主題飽和"
  - "研究主題分析"
  - "saturation analysis"
  - "diminishing returns"
  - "研究方向建議"
  - "待深化主題"
  - "research saturation"
depends-on:
  - kb-research-strategist
  - knowledge-query
  - system-insight
---

# Research Saturation Analyzer — 研究主題飽和度分析器

## 設計哲學

本 Skill 是 **kb-research-strategist 的分析補強層**：
kb-research-strategist 規劃「下一步研究什麼」，本 Skill 分析「哪些主題已經研究夠了、哪些值得繼續深挖」。

執行鏈：
```
讀取資料（registry + series）→ 主題聚類 → 飽和度評分 → 收穫遞減偵測
→ 待深化主題識別 → 方向建議生成 → 更新 research-series.json → 產出報告
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守所有共用規則）
2. 讀取 `skills/SKILL_INDEX.md`（確認現有 Skill 認知地圖）
3. 讀取 `config/dedup-policy.yaml`（取得 retention_days、topic_cooldown_days 等參數）

---

## 步驟 1：資料收集

並行讀取以下資料來源：

**1a. `context/research-registry.json`**
- 讀取 `topics_index`（主題→日期對映）和 `summary`（頂層摘要）
- 統計總研究數量、日期分佈、主題清單

**1b. `context/research-series.json`**
- 讀取 `series` 各系列的 `stages`、`completion_pct`、`saturation_score`、`last_active`
- 識別已有飽和度評分的系列

**1c. 知識庫統計（可選）**
- 若 KB API 可用（`curl -s --max-time 3 http://localhost:3000/api/health`）：
  - 取得 `GET /api/stats` 的筆記總數與標籤分佈
  - 作為「KB 知識深度」的補充指標
- 若不可用：略過，僅依 registry 與 series 資料分析

---

## 步驟 2：主題關鍵詞聚類

使用 Python 對 `topics_index` 的所有主題進行關鍵詞聚類：

```bash
uv run python -X utf8 -c "
import json, re
from collections import defaultdict

registry = json.load(open('context/research-registry.json', encoding='utf-8'))
topics = registry.get('topics_index', {})

# 定義聚類關鍵詞（領域→關鍵詞列表）
CLUSTERS = {
    '佛學': ['佛', '經', '淨土', '楞嚴', '法華', '天台', '教觀', '禪', '菩薩', '圓通', '阿彌陀', '華嚴', '般若'],
    'AI技術': ['AI', 'LLM', 'GPT', 'Claude', 'Agent', 'RAG', 'ML', 'Transformer', 'embedding', 'fine-tuning', 'vLLM', 'Groq', 'AutoGen'],
    '系統開發': ['系統', 'Skill', 'Hook', 'Cache', 'API', 'Schema', 'Trace', 'Pipeline', '架構', 'SLO', 'Context', 'Bot', 'Webhook'],
    '遊戲開發': ['遊戲', 'Game', 'Canvas', 'Flame', 'Flutter', 'Dig Dug', '卡卡頌'],
    '行為科學': ['習慣', '學習', '思維', '認知', '動機', '決策', 'Metacognition', 'Deep Work', '費曼', '後設認知'],
    '智慧城市': ['智慧', '城市', '治理', '公共', '環境監測', '交通', '公文', '政策'],
    'Podcast': ['Podcast', '播客', '音頻', '節目'],
    '研究方法': ['研究', '論證', '文獻', 'methodology', '方法論'],
}

# 聚類
cluster_topics = defaultdict(list)
unclustered = []
for topic, date in topics.items():
    matched = False
    for cluster, keywords in CLUSTERS.items():
        if any(kw.lower() in topic.lower() for kw in keywords):
            cluster_topics[cluster].append({'topic': topic, 'date': date})
            matched = True
            break
    if not matched:
        unclustered.append({'topic': topic, 'date': date})

# 統計
result = {}
for cluster, entries in sorted(cluster_topics.items(), key=lambda x: -len(x[1])):
    dates = sorted([e['date'] for e in entries])
    result[cluster] = {
        'count': len(entries),
        'first_date': dates[0],
        'last_date': dates[-1],
        'span_days': (
            (lambda d1, d2: (d2 - d1).days)(
                __import__('datetime').date.fromisoformat(dates[0]),
                __import__('datetime').date.fromisoformat(dates[-1])
            ) if len(dates) > 1 else 0
        ),
    }

result['_unclustered'] = {'count': len(unclustered)}
result['_total'] = len(topics)

print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

將輸出存為 `analysis/research-topic-clusters.json`（用 Write 工具）。

---

## 步驟 3：飽和度評分

對每個聚類計算 saturation_score（0.0-1.0）：

```
saturation_score = (
    研究次數因子 × 0.4 +     # count / max_count（正規化）
    (1 - 新穎度因子) × 0.3 + # 1 - (unique_subtopics / count)
    時間集中度 × 0.2 +        # 1 - (span_days / max_span_days)
    (1 - 深度因子) × 0.1      # 1 - (avg_completion_pct / 100)（來自 research-series）
)
```

```bash
uv run python -X utf8 -c "
import json

clusters = json.load(open('analysis/research-topic-clusters.json', encoding='utf-8'))
series = json.load(open('context/research-series.json', encoding='utf-8'))

# 過濾掉元資料 key
real_clusters = {k: v for k, v in clusters.items() if not k.startswith('_')}

if not real_clusters:
    print('NO_CLUSTERS')
    exit()

max_count = max(c['count'] for c in real_clusters.values())
max_span = max(c.get('span_days', 1) for c in real_clusters.values()) or 1

scores = {}
for name, data in real_clusters.items():
    count = data['count']
    span = data.get('span_days', 0)

    # 研究次數因子
    count_factor = min(count / max(max_count, 1), 1.0)

    # 新穎度因子（簡化：用 count 的倒數近似，count 越多越不新穎）
    novelty_factor = 1.0 / max(count, 1)

    # 時間集中度（span 越短，時間越集中）
    time_concentration = 1.0 - min(span / max(max_span, 1), 1.0)

    # 深度因子（從 research-series 取平均 completion_pct）
    related_series = [s for sid, s in series.get('series', {}).items()
                      if any(kw.lower() in sid.lower() for kw in name.split()[:2])]
    avg_completion = (sum(s.get('completion_pct', 0) for s in related_series) / len(related_series)
                      if related_series else 20)
    depth_factor = avg_completion / 100.0

    sat = (count_factor * 0.4 +
           (1 - novelty_factor) * 0.3 +
           time_concentration * 0.2 +
           (1 - depth_factor) * 0.1)

    scores[name] = {
        'saturation_score': round(sat, 3),
        'count': count,
        'span_days': span,
        'avg_completion_pct': round(avg_completion, 1),
        'classification': (
            'saturated' if sat > 0.7 else
            'moderate' if sat > 0.3 else
            'underdeveloped'
        )
    }

# 排序輸出
sorted_scores = dict(sorted(scores.items(), key=lambda x: -x[1]['saturation_score']))
print(json.dumps(sorted_scores, ensure_ascii=False, indent=2))
"
```

將輸出存為 `analysis/research-saturation-scores.json`（用 Write 工具）。

---

## 步驟 4：收穫遞減偵測

對 `classification == 'saturated'` 的聚類，進一步分析：

1. 從 `research-registry.json` 的 `entries[]`（若存在）取該聚類最近 5 筆研究
2. 比較相鄰研究的主題差異度（字面不同字數 / 總字數）
3. 若最近 3 筆的差異度 < 15%（高度重複），標記為 `diminishing_returns: true`

```bash
uv run python -X utf8 -c "
import json

scores = json.load(open('analysis/research-saturation-scores.json', encoding='utf-8'))
registry = json.load(open('context/research-registry.json', encoding='utf-8'))
topics_index = registry.get('topics_index', {})

saturated = [k for k, v in scores.items() if v['classification'] == 'saturated']

CLUSTERS_KW = {
    '佛學': ['佛', '經', '淨土', '楞嚴', '法華', '天台'],
    'AI技術': ['AI', 'LLM', 'GPT', 'Claude', 'Agent', 'RAG'],
    '系統開發': ['系統', 'Skill', 'Hook', 'Cache', 'API', 'Schema'],
    '遊戲開發': ['遊戲', 'Game', 'Canvas'],
    '行為科學': ['習慣', '學習', '思維', '認知'],
    '智慧城市': ['智慧', '城市', '治理'],
    'Podcast': ['Podcast', '播客'],
    '研究方法': ['研究', '論證', '方法論'],
}

results = {}
for cluster in saturated:
    kws = CLUSTERS_KW.get(cluster, cluster.split()[:2])
    related = [(t, d) for t, d in topics_index.items()
               if any(kw.lower() in t.lower() for kw in kws)]
    related.sort(key=lambda x: x[1], reverse=True)
    recent_5 = related[:5]

    if len(recent_5) >= 3:
        titles = [t for t, _ in recent_5[:3]]
        # 簡單差異度：相鄰標題的不同字元比例
        diffs = []
        for i in range(len(titles) - 1):
            common = sum(1 for a, b in zip(titles[i], titles[i+1]) if a == b)
            max_len = max(len(titles[i]), len(titles[i+1]))
            diff = 1 - (common / max_len if max_len > 0 else 0)
            diffs.append(round(diff, 3))
        avg_diff = sum(diffs) / len(diffs) if diffs else 1.0
        diminishing = avg_diff < 0.15
    else:
        avg_diff = 1.0
        diminishing = False

    results[cluster] = {
        'recent_topics': [t for t, _ in recent_5[:3]],
        'avg_title_diff': round(avg_diff, 3),
        'diminishing_returns': diminishing
    }

print(json.dumps(results, ensure_ascii=False, indent=2))
"
```

將收穫遞減結果合併至 `analysis/research-saturation-scores.json`。

---

## 步驟 5：待深化主題識別

對 `classification == 'underdeveloped'` 的聚類：

1. 檢查 `research-series.json` 中是否有對應系列的 `next_research_hint`
2. 若 KB API 可用，搜尋該主題相關筆記數量（`POST /api/search/hybrid`）
3. 標記為高潛力條件：`count < 5` 且 `completion_pct < 40%` 且 `相關 KB 筆記 ≥ 1`

將結果存為 `analysis/high-potential-topics.json`：

```json
[
  {
    "cluster": "聚類名稱",
    "count": 3,
    "completion_pct": 20,
    "kb_related_notes": 2,
    "potential_score": 0.85,
    "suggested_questions": [
      "建議研究問題 1",
      "建議研究問題 2"
    ]
  }
]
```

---

## 步驟 6：研究方向建議生成

根據步驟 3-5 的分析結果，生成結構化建議：

| 分類 | 建議動作 |
|------|---------|
| `saturated` + `diminishing_returns: true` | **暫停**：建議暫停 1 個月，或轉向子主題 |
| `saturated` + `diminishing_returns: false` | **換角度**：列出 2-3 個未探索的子方向 |
| `moderate` | **維持**：依現有節奏繼續，無需調整 |
| `underdeveloped` + 高潛力 | **優先研究**：列出 3 個具體研究問題 |
| `underdeveloped` + 低潛力 | **觀察**：暫不投入，等待新信號 |

將完整建議寫入 `analysis/research-direction-recommendations.json`。

---

## 步驟 7：更新 research-series.json

對有對應系列的聚類，用 Edit 工具更新 `context/research-series.json` 中的 `saturation_score`：

```python
# 對每個聚類，找到 research-series.json 中匹配的 series
# 更新 saturation_score 為步驟 3 計算的值
# 若 diminishing_returns == true，在 next_research_hint 加入「收穫遞減，建議暫停或轉向」
```

---

## 步驟 8：產出摘要報告

將所有分析結果整合為結構化摘要，格式：

```json
{
  "analysis_date": "YYYY-MM-DD",
  "total_topics": 152,
  "clusters_count": 8,
  "saturated_clusters": ["佛學", "AI技術"],
  "underdeveloped_clusters": ["遊戲開發", "Podcast"],
  "diminishing_returns": ["佛學"],
  "high_potential": ["遊戲開發"],
  "top_3_recommendations": [
    "佛學研究已達飽和（score=0.85），建議暫停 1 個月或轉向應用研究",
    "遊戲開發待深化（score=0.15），建議啟動 Flutter/Flame 實作系列",
    "Podcast 待深化（score=0.20），建議研究音頻編輯自動化工具鏈"
  ]
}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| research-registry.json 不存在或為空 | `status: "failed"`，記錄錯誤原因 |
| research-series.json 不存在 | 僅使用 registry 分析，跳過深度因子（設為 0.5） |
| KB API 不可用 | 跳過步驟 5 的 KB 筆記數查詢，僅依 registry 資料評估 |
| 聚類結果 < 3 個 | 降低聚類粒度（合併小聚類），確保有足夠資料分析 |
| Python 執行失敗 | 用 Bash 的 jq + awk 替代，產出簡化版分析 |

---

## 輸出檔案清單

| 檔案 | 用途 |
|------|------|
| `analysis/research-topic-clusters.json` | 主題聚類結果 |
| `analysis/research-saturation-scores.json` | 飽和度評分 |
| `analysis/high-potential-topics.json` | 待深化高潛力主題 |
| `analysis/research-direction-recommendations.json` | 研究方向建議 |

---

**版本歷史**：
- v0.1.0（2026-03-22）：草稿版，基於 improvement-backlog 需求生成
