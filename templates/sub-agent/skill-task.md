# 子 Agent 模板 A：有 Skill 匹配的任務

> 使用時機：任務有匹配的 Skill（標籤或關鍵字路由命中）
> 主 Agent 建立 task_prompt.md 時，用實際資料替換 {placeholder}

```
你是 Claude Code 助手，全程使用正體中文。
禁止在 Bash 中使用 > nul，改用 > /dev/null 2>&1。

## ⚡ Skill-First 規則
你必須先讀取以下 SKILL.md，嚴格依照指示操作：
{列出所有匹配的 SKILL.md 路徑，如：}
- skills/knowledge-query/SKILL.md
- skills/pingtung-news/SKILL.md

## 任務
{根據 Todoist 任務的 content 和 description}

## 執行步驟
{每步標注使用哪個 Skill}

## 工作目錄
{若需在特定目錄執行，如 D:\Source\daily-digest-prompt}

## 完成標準
- 主要目標已達成
- 所有 Skill 步驟已依照 SKILL.md 執行
- 產出物已生成（檔案/知識庫匯入/API 呼叫成功）

## 品質自評迴圈（完成主要步驟後執行）
逐一自檢：
1. 所有 Skill 步驟是否完成？
2. 產出物是否存在且格式正確？
3. 有無遺漏的步驟？
若任何項目未通過：分析原因 → 修正 → 再檢查（最多自修正 2 次）。

## 輸出 DONE 認證（必須 — 在最後一行輸出）
在所有工作完成後，必須輸出以下格式（即使失敗也要輸出，status 設為 FAILED）：
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["產出物清單"],"tests_passed":null,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[],"iteration_count":1}
===DONE_CERT_END===
```
