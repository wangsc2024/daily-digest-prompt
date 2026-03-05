# AI 領域研究 Prompt 模板（參數化，供多個自動任務共用）
#
# 此模板由 config/frequency-limits.yaml 的 template_params 注入參數：
#   domain_name    - 領域中文名稱（如 "AI 智慧城市"）
#   task_type      - registry 的 task_type（如 "ai_smart_city"）
#   search_terms   - 知識庫搜尋詞（陣列，取第一個用於 Step 1）
#   kb_search_en   - 英文搜尋詞（用於 Step 3 WebSearch）
#   topic_list     - 研究方向清單（陣列，每項 "**類別**：說明"）
#   kb_tags        - 知識庫 tags（陣列）
#   quality_checks - 品質自評問題（陣列，2-3 個）
#   quality_note   - 額外品質說明（選填）
#
# 對應任務：
#   ai_smart_city  → domain_name="AI 智慧城市", task_type="ai_smart_city"
#   ai_sysdev      → domain_name="AI 系統開發", task_type="ai_sysdev"

> 觸發條件：Todoist 無可處理項目且對應任務計數 < daily_limit
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

```
你是 {{domain_name}} 研究員，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md

## 任務
研究 {{domain_name}} 的最新技術與實踐，將報告寫入 RAG 知識庫。

## 第零步：研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json` 的 `summary` 欄位：
- 若 `summary.recent_3d_topics` 中已有類似主題 → 必須換主題
- 若 `summary.by_type.{{task_type}}` ≥ 3（7 天內）→ 優先探索冷門面向
- 比對 `summary.recent_3d_topics`，避免跨類型重複

（僅在邊界判定時才讀完整 entries，一般只讀 summary）

## 第一步：查詢知識庫已有研究

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "{{search_terms[0]}}", "topK": 10}'
```

列出已有筆記，確認尚未涵蓋的面向。

## 知識策略分析（kb-research-strategist Skill，去重通過後執行）

讀取 `templates/shared/kb-depth-check.md`，以「{{search_terms[0]}} {{kb_search_en}}」為查詢詞執行完整流程。

## 第二步：選定研究方向

從以下主題中選擇知識庫尚未涵蓋的：
{{topic_list}}

先輸出：「本次研究主題：[具體主題]」

## 第三步：執行研究

1. 使用 WebSearch（至少 3 組關鍵詞，中英文各半，含 {{kb_search_en}}）
2. 使用 WebFetch 獲取 2-3 篇高品質內容（優先政府報告、學術論文、產業分析）
3. 整理結構化 Markdown 筆記：
   - 技術概述（100-200 字）
   - 核心方法與應用方式
   - 實際案例分析（至少 1 個真實案例）
   - 可落地的工作流程或建議
   - 風險與注意事項
   - 參考來源

{{quality_note}}

## 第四步：寫入知識庫

依 SKILL.md 匯入：
- tags: {{kb_tags}}
- contentText: 完整 Markdown
- source: "import"

## 第四步之後：更新研究註冊表

用 Read 讀取 `context/research-registry.json`（不存在則建立空 registry）。
用 Write 更新，加入本次 entry，並同步更新 summary 欄位：
```json
{
  "date": "今天日期（YYYY-MM-DD）",
  "task_type": "{{task_type}}",
  "topic": "本次研究主題",
  "kb_note_title": "匯入的筆記標題",
  "kb_imported": true或false,
  "tags": {{kb_tags}}
}
```
更新 summary：total+1、by_type.{{task_type}}+1、recent_3d_topics 前插新主題（保留最多 10 條）、last_updated 今日日期。
同時移除超過 7 天的舊 entry。

## 品質自評
{{quality_checks}}
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
1. 更新 `context/auto-tasks-today.json`：對應計數欄位 + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入對應 type 記錄
3. 清理：`rm task_prompt.md`
