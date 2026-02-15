# 自動任務模板 — 研究類擴充

> 本模板與 `_base.md` 組合使用，為研究類自動任務提供額外段落。
> 以下段落應插入在 `_base.md` 的 `{{TASK_STEPS}}` 位置。

## 必備額外 Skill 讀取
```
- skills/knowledge-query/SKILL.md
```

## 第零步：研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":1,"entries":[]}`
- 存在 → 列出近 7 天內的 entries（所有 task_type）

**判定規則（必須遵守）：**
1. 若 registry 中 3 天內有 topic 與本次候選主題完全相同 → **必須換主題**
2. 若 registry 中 7 天內同 task_type 已有 ≥3 個不同 topic → 優先探索較少涵蓋的面向
3. 列出「近期已研究主題」供 KB 去重時交叉比對

## 第一步：查詢知識庫已有研究（兩階段去重）

### 階段 1：語義搜尋
```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "{{SEARCH_QUERY}}", "topK": 15}'
```
- 成功 → 列出所有結果的 title，作為去重依據
- 失敗 → 進入階段 2

### 階段 2：標題搜尋（備援）
```bash
curl -s "http://localhost:3000/api/notes?search={{SEARCH_KEYWORD}}"
```

### 去重判定
- 若 KB 已有 ≥3 篇相同主題 → 必須選擇不同角度或子主題
- 若完全相同標題已存在 → 跳過此主題，選下一個

## 研究結束步驟：匯入知識庫

### 匯入步驟
依 knowledge-query SKILL.md 建立筆記：
- tags: {{TAGS}}
- contentText: 完整研究報告（Markdown 格式）
- source: "import"

### 更新研究註冊表
用 Read 讀取現有 `context/research-registry.json`，在 entries 陣列追加：
```json
{
  "topic": "本次研究主題",
  "task_type": "{{HISTORY_TYPE}}",
  "date": "ISO-8601 日期",
  "kb_imported": true
}
```
用 Write 寫回 `context/research-registry.json`。

## 額外品質自評項
- 研究主題是否與近期 KB 重複？
- 知識庫匯入是否成功？
- 研究註冊表是否已更新？
