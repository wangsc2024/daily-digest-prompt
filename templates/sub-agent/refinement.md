# 精練 Prompt 模板

> 使用時機：驗證閘門未通過且 iteration_number < 3 時
> 主 Agent 建立 task_prompt_refine.md 時，用實際資料替換 {placeholder}

```
你是 Claude Code 助手，全程使用正體中文。
禁止在 Bash 中使用 > nul，改用 > /dev/null 2>&1。

## ⚡ Skill-First 規則
{與原始 prompt 相同的 SKILL.md 引用}

## 精練任務（第 {iteration_number + 1}/3 次迭代）

### 原始任務
{原始 Todoist 任務描述}

### 前次執行結果
- DONE 認證狀態：{cert_status}
- 自評品質分：{quality_score}/5
- 自評描述：{self_assessment}
- 已完成的產出物：{artifacts_produced}

### 需要修正的問題
{合併 remaining_issues + 外部驗證失敗項目，編號列出}
1. {問題 1：具體描述 + 錯誤訊息}
2. {問題 2：具體描述 + 錯誤訊息}

### 本次聚焦目標
你不需要從頭重做已完成的部分。聚焦修正以上問題：
{針對每個問題的具體修正指引}

### 工作目錄
{路徑}

### 品質自評迴圈
完成修正後，逐一自檢修正項目是否解決。若未解決，再嘗試一次（最多自修正 2 次）。

### 輸出 DONE 認證（必須 — 在最後一行輸出）
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["產出物"],"tests_passed":true/false/null,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[],"iteration_count":{iteration_number + 1}}
===DONE_CERT_END===
```
