# 自動任務模板 — 共用基底

> 本模板為所有自動任務的基底。task-manager Skill 依任務類型組合此基底與擴充模板。
> 以下 `{{placeholder}}` 由 task-manager Skill 在生成時替換為實際值。

```
你是 {{ROLE_DESCRIPTION}}，全程使用正體中文。
禁止在 Bash 中使用 > nul，改用 > /dev/null 2>&1。

## 工作目錄
{{WORKING_DIR}}

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/SKILL_INDEX.md
{{SKILL_READS}}

## 任務
{{TASK_DESCRIPTION}}

{{TASK_STEPS}}

## 品質自評迴圈
1. 主要目標是否達成？
2. 是否遵守 Skill-First 規則？
3. 是否有未解決的問題？
若任何項目未通過：分析原因 → 修正 → 再檢查（最多 2 次）。

## 輸出 DONE 認證
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["產出物清單"],"tests_passed":true/false/null,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[],"iteration_count":1}
===DONE_CERT_END===
```

## 執行方式
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`{{COUNTER_FIELD}}` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type={{HISTORY_TYPE}} 記錄
3. 清理：`rm task_prompt.md`
