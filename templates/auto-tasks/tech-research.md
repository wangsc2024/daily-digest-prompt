# 每日任務技術研究 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 tech_research_count < 5
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

```
你是技術研究助手，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md

## 任務
分析今日 Todoist 已完成任務所需的技術，選擇一項深入研究並寫入 RAG 知識庫。

## 第零步：研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":1,"entries":[]}`
- 存在 → 列出近 7 天內的 entries（所有 task_type）

**判定規則（必須遵守）：**
1. 若 registry 中 3 天內有 topic 與本次候選主題完全相同 → **必須換主題**
2. 若 registry 中 7 天內 task_type="tech_research" 已有 ≥3 個不同 topic → 優先探索冷門技術
3. 特別注意：其他 AI 類型（ai_deep_research, ai_github_research 等）的 topic 也要比對，避免跨類型重複

## 第一步：分析今日已完成任務的技術需求

讀取 `context/auto-tasks-today.json`，取得 `closed_task_ids`。
讀取 `state/todoist-history.json`，找出今天的 `daily_summary` 中已完成任務。

從已完成任務中提取技術關鍵字（例如：Cloudflare Pages、HTML5 遊戲、RAG、PowerShell、WebSearch）。
列出所有識別到的技術主題。

## 第二步：查詢知識庫去重

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "識別到的技術主題", "topK": 10}'
```

比對已有筆記，找出尚未深入研究的技術。
- 先輸出：「今日任務涉及技術：[列表]」
- 再輸出：「本次研究主題：XXX（因知識庫尚無此主題的深入研究）」

## 第三步：深入研究

1. 使用 WebSearch 搜尋該技術的最新進展（至少 3 組關鍵詞）
2. 使用 WebFetch 獲取 2-3 篇高品質文章
3. 整理為結構化 Markdown 筆記：
   - 技術概述（100-200 字）
   - 核心概念與原理
   - 最佳實踐與常見陷阱
   - 與本專案的關聯（如何應用在 daily-digest-prompt 或相關專案）
   - 程式碼範例（若適用）
   - 參考來源

## 第四步：寫入知識庫

依 SKILL.md 指示匯入：
- tags 必須包含 ["技術研究", "本次技術名稱", "daily-digest"]
- contentText 放完整 Markdown
- 必須用 Write 建立 JSON，不可用 inline JSON
- source 填 "import"

## 第四步之後：更新研究註冊表

用 Read 讀取 `context/research-registry.json`（不存在則建立空 registry）。
用 Write 更新，加入本次 entry：
```json
{
  "date": "今天日期（YYYY-MM-DD）",
  "task_type": "tech_research",
  "topic": "本次研究主題",
  "kb_note_title": "匯入的筆記標題",
  "kb_imported": true或false,
  "tags": ["技術研究", "本次技術名稱", "daily-digest"]
}
```
同時移除超過 7 天的舊 entry。

## 品質自評
1. 研究內容是否聚焦於今日任務實際所需？
2. 是否提供可操作的最佳實踐？
3. 內容是否超過 400 字？
若未通過：補充 → 修正（最多 2 次）。

## 輸出 DONE 認證
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["note-id"],"tests_passed":null,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[],"iteration_count":1}
===DONE_CERT_END===
```

## 執行方式
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,WebSearch,WebFetch"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`tech_research_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=tech_research 記錄
3. 清理：`rm task_prompt.md`
