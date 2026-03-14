---
name: academic-paper-research
version: "1.0.0"
description: |
  指定議題的學術研究與報告生成框架。聚焦同行評審論文、學術專書、會議論文、學位論文與研究機構報告，產出具學術論文水準的中文研究報告。
  Use when: 學術研究、文獻回顧、指定議題研究、研究報告、論文等級來源、同行評審、systematic review、literature review。
allowed-tools: Read, Write, WebSearch, WebFetch, Bash
depends-on:
  - web-research
  - knowledge-query
triggers:
  - "學術研究"
  - "文獻回顧"
  - "研究報告"
  - "指定議題研究"
  - "論文等級"
  - "同行評審"
  - "literature review"
  - "systematic review"
  - "academic research"
---

# Academic Paper Research

用於「指定一個議題，蒐集學術等級材料，生成一份可閱讀、可引用、可存檔的研究報告」。

## 目標

輸出一份具以下特徵的報告：
- 明確研究問題
- 明確文獻納入標準
- 核心證據來自學術等級來源
- 不只是摘要，而是有比較、批判與綜合
- 可直接匯入知識庫或改寫成正式報告

## 來源等級規則

核心證據僅可優先採用以下來源：

| 等級 | 類型 | 說明 |
|------|------|------|
| A | 同行評審期刊論文 | 最優先 |
| A | 學術出版社專書/專書章節 | 可作理論背景 |
| B | 國際會議論文 | 技術與新興議題可接受 |
| B | 博碩士論文 | 可補充，但不應取代核心期刊 |
| B | 政府/大學/國際組織研究報告 | 可用於政策與統計背景 |
| C | 官方技術文件/標準文件 | 僅作補充，不作核心學術結論 |

以下資料不可作核心證據：
- 新聞
- 一般部落格
- 論壇
- 自媒體
- 無作者或無機構頁面

## 執行流程

### 1. 定義研究問題

先產出：
- 1 個核心研究問題
- 3-5 個子問題
- 研究範圍
- 排除範圍

若主題過大，先縮限：
- 時間
- 地域
- 方法
- 子領域

### 2. 設計檢索策略

至少建立 3 組查詢：
- 概念查詢：`{topic} overview OR definition`
- 理論/方法查詢：`{topic} theory OR framework OR methodology`
- 實證查詢：`{topic} empirical study OR experiment OR case study`

技術主題補：
- benchmark
- evaluation
- ablation
- survey

人文社會主題補：
- discourse
- historical context
- comparative study
- policy analysis

優先英文查詢；若主題強烈在地化，再加入中文查詢。

### 3. 蒐集與篩選文獻

最低要求：
- 候選文獻 >= 12
- 核心納入文獻 >= 6
- A/B 級文獻 >= 6

每篇核心文獻至少記錄：
- title
- authors
- year
- source
- source_type
- research_question
- method
- key_findings
- limitations
- relevance

若資料不足，必須明講：
`目前可取得的高品質學術證據不足，以下結論僅為有限文獻下的暫時判斷。`

### 4. 批判性綜合

報告不能只列摘要，必須比較：
- 學界共識
- 學界分歧
- 方法差異
- 樣本限制
- 外部效度問題
- 尚未解決的研究缺口

若文獻互相衝突，必須分析可能原因：
- 研究設計不同
- 樣本不同
- 時間背景不同
- 操作化定義不同

### 5. 報告輸出

使用以下結構：

```markdown
# 標題

## 摘要
## 研究問題界定
## 檢索策略與納入標準
## 核心文獻整理
## 綜合分析
## 結論
## 參考文獻
## 附錄：研究信心水準
```

### 6. 品質底線

必須滿足：
- 每個重要主張可回溯到文獻
- 不虛構 DOI / 作者 / 期刊
- 不把非學術來源包裝成學術來源
- 不把單篇研究結論誇大成學界共識

## 可直接套用模板

執行時先讀：
- `templates/research/academic-paper-research-prompt.md`

若需存入知識庫，再依：
- `skills/knowledge-query/SKILL.md`

## 建議輸出附錄

最後附一段結構化摘要：

```json
{
  "topic": "研究主題",
  "core_question": "核心問題",
  "sources_screened": 12,
  "sources_included": 6,
  "source_distribution": {
    "peer_reviewed_journal": 4,
    "conference_paper": 1,
    "thesis": 0,
    "institutional_report": 1
  },
  "confidence": "high|medium|low",
  "key_consensus_count": 3,
  "key_disagreement_count": 2
}
```
