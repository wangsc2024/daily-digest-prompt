---
name: kb-research-strategist
version: 1.0.0
description: |
  知識庫研究策略師。執行三層知識工作：
  （1）讀取 KB 相關文件全文，合成現有知識狀態；
  （2）偵測或建立長期研究系列，追蹤五階段進度（永久，無 TTL）；
  （3）制定「從現有知識往下一階段延伸」的結構化研究計畫。
  讓每次研究都能在既有知識基礎上往深處推進，並持久追蹤系列進度。
  Use when: 研究前策略規劃、知識系列管理、深化研究計畫、KB 擴充設計。
allowed-tools:
  - Bash
  - Write
  - Read
triggers:
  - "研究策略"
  - "系列研究"
  - "深化研究"
  - "知識差距分析"
  - "研究計畫"
  - "KB 擴充"
  - "知識系列"
  - "kb-research-strategist"
depends-on:
  - knowledge-query
---

# kb-research-strategist：知識庫研究策略師

## 五階段知識累積模型

每個研究系列（Series）依知識累積深度分為五個階段：

| 階段 | 英文鍵 | 研究目標 | 判定完成標準 |
|------|--------|---------|------------|
| 1 基礎建立 | `foundation` | 概念、術語、整體架構 | KB 有概論筆記，涵蓋核心概念定義 |
| 2 機制深化 | `mechanism` | 內部原理、演算法、實作細節 | KB 有「如何運作」的深度說明 |
| 3 應用實踐 | `application` | 程式碼範例、實際案例、部署方法 | KB 有可執行的實作指南 |
| 4 優化精進 | `optimization` | 效能、最佳實踐、邊緣案例 | KB 有效能分析與最佳化策略 |
| 5 整合昇華 | `synthesis` | 與其他主題連結、未來展望 | KB 有跨主題連結筆記 |

---

## 步驟 0：系列偵測（讀取 research-series.json）

用 Read 讀取 `context/research-series.json`：
- **不存在** → 用 Write 初始化：
  ```json
  {"version": 1, "updated_at": "now", "series": {}}
  ```
- **存在** → 載入現有系列清單

依研究主題關鍵字比對現有 series 的 `domain` 和 `tags`（比對規則：domain 包含主題詞，或 2+ tags 吻合）：
- **命中** → 載入系列上下文，記錄 `series_id` 和 `current_stage`
- **未命中** → 標記為新系列（步驟 4 決定是否建立）

---

## 步驟 1：KB 知識感測（topK=10，讀取 config/dedup-policy.yaml 確認參數）

> **Windows 注意**：POST 必須用 Write 工具建立 JSON 檔，不可 inline JSON

用 Read 讀取 `config/dedup-policy.yaml` 取得 `strategy_search.strategy_topK`（預設 10）。

寫入 `temp_krs_query.json`：
```json
{"query": "<研究主題關鍵字>", "topK": 10}
```

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @temp_krs_query.json -o temp_krs_results.json
rm temp_krs_query.json
```

失敗（exit code != 0 或無回應）→ 跳至步驟 7（降級），但仍繼續系列管理邏輯。

---

## 步驟 2：讀取相關筆記全文（score 0.4–0.85）

```bash
python -X utf8 -c "
import json, sys

with open('temp_krs_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

notes = data.get('results', [])
deep_read = [n for n in notes if 0.4 <= n.get('score', 0) < 0.85]
selected = sorted(deep_read, key=lambda x: x.get('score', 0), reverse=True)[:5]

result = {
    'high_dup': [n['title'] for n in notes if n.get('score', 0) >= 0.85],
    'selected': [
        {
            'title': n.get('title', ''),
            'score': round(n.get('score', 0), 3),
            'tags': n.get('tags', []),
            'content': n.get('contentText', '')[:2000]
        }
        for n in selected
    ]
}
print(json.dumps(result, ensure_ascii=False, indent=2))
" > temp_krs_selected.json
rm temp_krs_results.json
```

- 若 `selected` 為空 → 設 `recommendation: "explore_new"`（但仍執行系列管理）
- 若 `high_dup` 有結果 → 記錄「KB 已有高度相似筆記」，研究時必須選不同角度

---

## 步驟 3：合成現有知識狀態

讀取 `temp_krs_selected.json`，逐筆分析 `content` 欄位，整合判斷：

**知識深度評估**（對應五階段）：

| 深度等級 | 判定標準 |
|---------|---------|
| `foundation` | 只有概念定義與整體架構 |
| `mechanism` | 有內部原理、演算法說明 |
| `application` | 有程式碼、實際案例 |
| `optimization` | 有效能比較、最佳實踐 |
| `synthesis` | 有跨主題連結、未來展望 |

**概念覆蓋提取**：
- `covered_concepts`：已清楚說明的概念列表
- `partial_concepts`：提到但未深入的概念
- `missing_concepts`：完全未提及的重要概念（根據主題常識推斷）

---

## 步驟 4：系列狀態判定與下一階段規劃

### 情境 A：命中現有系列
```
從步驟 0 載入 series.current_stage
→ 本次研究目標：完成 current_stage 階段
→ 若 KB 已有此階段筆記（steps 2-3 的 depth_level >= current_stage）→ 推進到下一階段
```

### 情境 B：未命中但 KB 有相關基礎
```
KB 有 foundation 深度的筆記（步驟 3 判定）
→ 開新系列（is_new: true），series_id = "<topic-slug>"
→ 當前階段：mechanism（跳過 foundation）
```

### 情境 C：KB 無相關筆記
```
→ 開新系列（is_new: true），從 foundation 開始
→ recommendation: "explore_new"
```

**階段推進邏輯**：
- foundation 完成：KB 有 ≥1 筆概論筆記 + covered_concepts ≥ 3 個核心概念
- mechanism 完成：KB 有 ≥1 筆原理/演算法筆記 + 有說明性敘述（含關鍵詞「原理」「機制」「演算法」「架構」之一）
- application 完成：KB 有 ≥1 筆實作指南 + content 含程式碼片段（三個反引號）
- optimization 完成：KB 有效能比較或最佳實踐筆記（含「效能」「優化」「benchmark」之一）
- synthesis 完成：KB 有與其他主題的連結筆記（含「整合」「連結」「跨」之一）

---

## 步驟 5：制定結構化研究計畫（輸出 kb-research-brief.json）

用 Write 建立 `context/kb-research-brief.json`：

```json
{
  "generated_at": "ISO timestamp",
  "research_topic": "原始研究主題",
  "series": {
    "series_id": "topic-slug",
    "is_new": false,
    "current_stage": "application",
    "completion_pct": 40,
    "stage_context": "已完成 foundation + mechanism，本次目標：完成 application 階段"
  },
  "kb_foundation": {
    "notes_analyzed": 4,
    "depth_level": "mechanism",
    "synthesis": "KB 目前掌握原理知識，但缺乏實作程式碼",
    "covered_concepts": ["概念1", "概念2"],
    "partial_concepts": ["概念3（提及但未深入）"],
    "missing_concepts": ["概念4", "概念5"]
  },
  "knowledge_gaps": [
    {
      "type": "application",
      "gap": "缺少可直接使用的程式碼範例",
      "why_important": "KB 已有機制知識，但無實作指南",
      "builds_on": "現有的 mechanism 知識",
      "stage": "application"
    }
  ],
  "research_plan": {
    "stage": "application",
    "primary_question": "如何實作 [主題]？需要哪些函式庫或工具？",
    "approach": "官方文件 + 程式碼範例分析",
    "steps": [
      {
        "step": 1,
        "action": "搜尋實作程式碼與教學",
        "search_keywords": ["<主題> implementation tutorial 2026", "<主題> code example Python"],
        "expected_insight": "2-3 種主流實作方法"
      },
      {
        "step": 2,
        "action": "比較各方案的適用性",
        "search_keywords": ["<主題> comparison benchmark", "<主題> best practice"],
        "expected_insight": "最適合當前環境的方案"
      },
      {
        "step": 3,
        "action": "整合為完整實作指南",
        "search_keywords": [],
        "expected_insight": "含程式碼、設定說明、效能數據的完整筆記"
      }
    ],
    "kb_enrichment_plan": {
      "new_note_title": "<主題> 實作指南（<具體方法>）",
      "tags": ["<主題>", "<子類別>", "實作指南"],
      "references_from_existing": ["現有相關筆記標題"],
      "cross_reference_note": "承接「<前一階段>」知識，本文進入「<當前階段>」階段",
      "series_stage_completion": "application"
    }
  },
  "series_update": {
    "action": "update_stage",
    "series_id": "topic-slug",
    "stage_to_update": "application",
    "new_status": "in_progress",
    "next_stage_hint": "完成後進入 optimization：效能調優"
  },
  "recommendation": "deepen",
  "skip_reason": null
}
```

清理：
```bash
rm temp_krs_selected.json
```

**`recommendation` 取值說明**：
- `"deepen"` — 命中系列，依計畫深化
- `"series_continue"` — 命中系列，KB 部分缺乏，繼續已有方向
- `"explore_new"` — 新主題，自由選題（但已開新系列，foundation 階段）
- `"skip_kb_down"` — KB 不可用，依系列計畫執行（若有）

---

## 步驟 6：研究完成後更新系列狀態（由研究模板呼叫，非 Skill 本身）

研究與 KB 匯入完成後，讀取 `context/kb-research-brief.json` 的 `series_update` 欄位，更新 `context/research-series.json`：

```python
# 偽程式碼，由研究模板的 Python 腳本執行
series[series_id]["stages"][stage]["kb_notes"].append(new_note_title)
series[series_id]["stages"][stage]["covered_concepts"].extend(new_concepts)
if stage_complete:
    series[series_id]["stages"][stage]["status"] = "completed"
    series[series_id]["stages"][stage]["completed_at"] = today
    series[series_id]["current_stage"] = next_stage
series[series_id]["completion_pct"] = completed_stages * 20
series[series_id]["last_active"] = today
series[series_id]["next_research_hint"] = next_stage_hint
```

---

## 步驟 7：降級處理

KB 不可用（步驟 1 失敗）時：
- **仍執行步驟 0**：讀取 research-series.json
- **若有現有系列** → 依系列狀態生成研究計畫（無 KB 分析），`recommendation: "series_continue"`
- **無系列** → `recommendation: "skip_kb_down"`
- 輸出最簡版 `context/kb-research-brief.json`（僅含 series 欄位和 recommendation）

---

## 注意事項

- 所有 curl POST 必須用 Write 建立 JSON 檔案（Windows 環境限制）
- temp_krs_*.json 為暫存檔，步驟完成後務必刪除
- `context/research-series.json` 永久保留，不受 7 天 TTL 清理影響
- `context/kb-research-brief.json` 為跨步驟暫存，Phase D 清理
- 主題 slug 規則：英文小寫、連字號分隔（如 `rag-advanced-retrieval`、`langchain-agent`）
