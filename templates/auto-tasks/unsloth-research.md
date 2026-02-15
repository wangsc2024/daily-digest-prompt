# Unsloth 研究 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 unsloth_research_count < 2
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

```
你是 LLM Fine-Tuning 研究助手，全程使用正體中文。
禁止在 Bash 中使用 > nul，改用 > /dev/null 2>&1。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md

## 任務
研究 Unsloth — 2-5x 更快的 LLM 微調框架（80% 更少記憶體用量）。

## 第零步：研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":1,"entries":[]}`
- 存在 → 列出近 7 天內的 entries（所有 task_type）

**判定規則（必須遵守）：**
1. 若 registry 中 3 天內有 topic 與本次候選主題完全相同 → **必須換主題**
2. 若 registry 中 7 天內 task_type="unsloth_research" 已有 ≥3 個不同 topic → 優先探索冷門面向
3. 比對其他 AI 類型的 topic，避免跨類型重複

## 第一步：查詢知識庫已有研究

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "Unsloth fine-tuning LLM 微調", "topK": 10}'
```

列出已有筆記標題，確認尚未研究的面向。

## 第二步：選定研究方向

從以下主題中選擇知識庫尚未涵蓋的：
- Unsloth 架構原理（為何 2-5x 加速）
- 支援模型（Llama 3.x, Mistral, Gemma, Qwen, Phi）
- LoRA vs QLoRA 配置最佳實踐
- 資料集準備與格式（Alpaca, ShareGPT, ORPO/DPO）
- 訓練參數調優（learning rate, batch size, gradient accumulation）
- Unsloth 與 TRL / Hugging Face Trainer 整合
- GGUF 量化與匯出（推論部署）
- 實際案例分析（繁中 LLM 微調）
- 與其他框架比較（Axolotl, LLaMA-Factory, torchtune）
- Unsloth Pro / Studio 功能

先輸出：「本次研究主題：XXX」

## 第三步：執行研究

1. 使用 WebSearch 搜尋：
   - "Unsloth [主題] 2025 2026"
   - "Unsloth tutorial [主題]"
   - "unsloth fine-tuning [主題] best practices"
2. 使用 WebFetch 獲取 2-3 篇高品質內容（優先官方文件 + GitHub）
3. 整理為結構化 Markdown 筆記：
   - 概述（100-200 字）
   - 核心技術/操作步驟
   - 程式碼範例（Python，含關鍵參數說明）
   - 效能對比數據（若有）
   - 常見問題與解法
   - 與現有知識庫內容的關聯
   - 參考來源

## 第四步：寫入知識庫

依 SKILL.md 指示匯入：
- tags: ["Unsloth", "LLM", "fine-tuning", "本次主題"]
- contentText: 完整 Markdown
- source: "import"

## 第四步之後：更新研究註冊表

用 Read 讀取 `context/research-registry.json`（不存在則建立空 registry）。
用 Write 更新，加入本次 entry：
```json
{
  "date": "今天日期（YYYY-MM-DD）",
  "task_type": "unsloth_research",
  "topic": "本次研究主題",
  "kb_note_title": "匯入的筆記標題",
  "kb_imported": true或false,
  "tags": ["Unsloth", "LLM", "fine-tuning", "本次主題"]
}
```
同時移除超過 7 天的舊 entry。

## 品質自評
1. 是否包含可執行的程式碼範例？
2. 是否與知識庫已有 Unsloth 筆記有所區隔？
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
1. 更新 `context/auto-tasks-today.json`：`unsloth_research_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=unsloth_research 記錄
3. 清理：`rm task_prompt.md`
