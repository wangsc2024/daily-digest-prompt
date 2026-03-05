# AI 工作流自動化 GitHub 研究 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 ai_workflow_github_count < daily_limit
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

```
你是 AI 工作流自動化研究員，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md
- skills/kb-research-strategist/SKILL.md

## 任務
從 GitHub 選出 AI 工作流自動化領域的熱門專案，進行深度研究並生成結構化報告，成果納入 RAG 知識庫。

完整執行步驟詳見 `prompts/team/todoist-auto-ai_workflow_github.md`（單一模式直接引用 team prompt 內容執行）。
```

## 執行方式
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,WebSearch,WebFetch"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`ai_workflow_github_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=ai_workflow_github 記錄
3. 清理：`rm task_prompt.md`
