# AI 系統開發研究 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 ai_sysdev_count < 2
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

```
你是 AI 輔助系統開發研究員，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md

## 任務
研究 AI 應用於系統開發的最新技術與實踐，將報告寫入 RAG 知識庫。

## 第零步：研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":1,"entries":[]}`
- 存在 → 列出近 7 天內的 entries（所有 task_type）

**判定規則（必須遵守）：**
1. 若 registry 中 3 天內有 topic 與本次候選主題完全相同 → **必須換主題**
2. 若 registry 中 7 天內 task_type="ai_sysdev" 已有 ≥3 個不同 topic → 優先探索冷門面向
3. 比對其他 AI 類型的 topic，避免跨類型重複（如 tech_research 已研究 Claude Code，則選其他主題）

## 第一步：查詢知識庫已有研究

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "AI 系統開發 software development", "topK": 10}'
```

列出已有筆記，確認尚未涵蓋的面向。

## 第二步：選定研究方向

從以下主題中選擇知識庫尚未涵蓋的：
- **AI-Assisted Coding**：Copilot/Cursor/Claude Code 最佳實踐、Prompt Engineering for Code
- **自動測試生成**：AI 生成單元測試、E2E 測試、Mutation Testing 自動化
- **架構優化**：AI 驅動的架構決策、程式碼品質分析、技術債檢測
- **DevOps 智能化**：AI 日誌分析、自動 incident response、智能監控告警
- **程式碼審查**：AI Code Review、漏洞自動偵測、風格一致性檢查
- **需求工程**：AI 需求分析、使用者故事生成、驗收條件自動化
- **持續整合**：AI 驅動的 CI/CD 優化、構建時間預測、flaky test 偵測
- **Agent 開發**：Claude Agent SDK、Multi-Agent 系統、Tool Use 設計模式
- **文件生成**：AI 自動文件化、API 文件生成、變更日誌自動化

先輸出：「本次研究主題：[具體主題]」

## 第三步：執行研究

1. 使用 WebSearch（至少 3 組關鍵詞）
2. 使用 WebFetch 獲取 2-3 篇高品質內容
3. 整理結構化 Markdown 筆記：
   - 技術概述（100-200 字）
   - 核心方法與工具
   - 實際工作流程（step-by-step）
   - 程式碼/配置範例
   - 效果量化（生產力提升數據，若有）
   - 與本專案的應用場景（daily-digest-prompt 如何受益）
   - 風險與注意事項
   - 參考來源

## 第四步：寫入知識庫

依 SKILL.md 匯入：
- tags: ["AI", "系統開發", "本次主題", "software-engineering"]
- contentText: 完整 Markdown
- source: "import"

## 第四步之後：更新研究註冊表

用 Read 讀取 `context/research-registry.json`（不存在則建立空 registry）。
用 Write 更新，加入本次 entry：
```json
{
  "date": "今天日期（YYYY-MM-DD）",
  "task_type": "ai_sysdev",
  "topic": "本次研究主題",
  "kb_note_title": "匯入的筆記標題",
  "kb_imported": true或false,
  "tags": ["AI", "系統開發", "本次主題", "software-engineering"]
}
```
同時移除超過 7 天的舊 entry。

## 品質自評
1. 是否包含可執行的工作流程（不只是概念）？
2. 是否有程式碼或配置範例？
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
1. 更新 `context/auto-tasks-today.json`：`ai_sysdev_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=ai_sysdev 記錄
3. 清理：`rm task_prompt.md`
