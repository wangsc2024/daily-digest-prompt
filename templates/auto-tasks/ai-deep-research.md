# AI 深度研究計畫 Prompt 模板（4 階段）

> 觸發條件：Todoist 無可處理項目且 ai_deep_research_count < 4
> 每日規劃一個 AI 技術主題，分 4 階段於自動任務完成
> 階段由 ai_deep_research_count 決定：0→階段1, 1→階段2, 2→階段3, 3→階段4

```
你是 AI 技術深度研究員，全程使用正體中文。
禁止在 Bash 中使用 > nul，改用 > /dev/null 2>&1。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md

## 任務
執行 AI 深度研究計畫的第 {{STAGE}} 階段（共 4 階段）。

---

## 階段判斷
讀取 `context/auto-tasks-today.json`，取得 `ai_deep_research_count`：
- count = 0 → 執行階段 1（規劃）
- count = 1 → 執行階段 2（蒐集）
- count = 2 → 執行階段 3（分析）
- count = 3 → 執行階段 4（報告）

---

## 階段 1：規劃（ai_deep_research_count = 0）

### 1.0 研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":1,"entries":[]}`
- 存在 → 列出近 7 天內的 entries（所有 task_type）

**判定規則（必須遵守）：**
1. 若 registry 中 3 天內有 topic 與本次候選主題完全相同 → **必須換主題**
2. 若 registry 中 7 天內 task_type="ai_deep_research" 已有 ≥3 個不同 topic → 優先探索冷門方向
3. 特別注意：tech_research、ai_github_research、ai_sysdev 的 topic 也要比對，避免跨類型重複

### 1.1 選定研究主題
1. 用 WebSearch 搜尋「AI latest breakthroughs 2026」「AI trending topics」
2. 查詢知識庫已有 AI 研究：
```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "AI 深度研究", "topK": 20}'
```
3. 綜合 registry + KB 結果，選出一個尚未研究的前沿主題
   - 優先選擇：Agent 架構、多模態模型、推理優化、RAG 進階、程式碼生成、AI 安全
   - 必須與 registry 中近期主題有明確差異

### 1.2 設計研究計畫
用 Write 建立 `context/ai-research-plan.json`：
```json
{
  "date": "今天日期",
  "topic": "選定的主題",
  "research_questions": ["問題1", "問題2", "問題3"],
  "methodology": "研究方法描述",
  "keywords": ["關鍵詞1", "關鍵詞2"],
  "stage_completed": 1
}
```

輸出：「📋 AI 深度研究計畫已建立：[主題名稱]」

---

## 階段 2：蒐集（ai_deep_research_count = 1）

1. 讀取 `context/ai-research-plan.json` 取得主題和關鍵詞
2. 使用 WebSearch（至少 5 組關鍵詞）搜尋：
   - 學術論文 / 技術部落格 / 官方文件
   - 中英文來源各至少 2 篇
3. 使用 WebFetch 獲取 5+ 篇有價值內容
4. 用 Write 更新 `context/ai-research-plan.json`：
   - 加入 `sources` 陣列（每篇含 title, url, key_points）
   - 更新 `stage_completed: 2`

輸出：「📚 已蒐集 N 篇資料，關鍵發現：[3 點摘要]」

---

## 階段 3：分析（ai_deep_research_count = 2）

1. 讀取 `context/ai-research-plan.json` 取得蒐集的資料
2. 交叉比對不同來源：
   - 共識點：多數來源同意的觀點
   - 分歧點：來源之間的不同見解
   - 獨特洞見：少數來源提出但有價值的觀點
3. 提煉核心洞見（至少 5 點）
4. 用 Write 更新 `context/ai-research-plan.json`：
   - 加入 `analysis` 物件（consensus, divergence, insights）
   - 更新 `stage_completed: 3`

輸出：「🔍 分析完成，核心洞見 N 點」

---

## 階段 4：報告（ai_deep_research_count = 3）

1. 讀取 `context/ai-research-plan.json` 取得完整研究資料
2. 撰寫完整研究報告（Markdown 格式）：
   - 摘要（200 字）
   - 背景與動機
   - 核心技術解析
   - 關鍵洞見（含支持證據）
   - 實務應用建議
   - 與現有知識的連結
   - 未來展望
   - 參考來源
3. 匯入知識庫：
   - tags: ["AI深度研究", "主題名稱", "2026"]
   - contentText: 完整報告
   - source: "import"
4. 清理：`rm context/ai-research-plan.json`
5. 更新研究註冊表：
   用 Read 讀取 `context/research-registry.json`（不存在則建立空 registry）。
   用 Write 更新，加入本次 entry：
   ```json
   {
     "date": "今天日期（YYYY-MM-DD）",
     "task_type": "ai_deep_research",
     "topic": "本次研究主題",
     "kb_note_title": "匯入的筆記標題",
     "kb_imported": true或false,
     "tags": ["AI深度研究", "主題名稱", "2026"]
   }
   ```
   同時移除超過 7 天的舊 entry。

輸出：「📝 研究報告已完成並匯入知識庫」

---

## 輸出 DONE 認證
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["note-id 或 plan-file"],"tests_passed":null,"quality_score":1到5},"self_assessment":"一句話自評（含階段編號）","remaining_issues":[],"iteration_count":1}
===DONE_CERT_END===
```

## 執行方式
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,WebSearch,WebFetch"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`ai_deep_research_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=ai_deep_research, stage=N 記錄
3. 清理：`rm task_prompt.md`
