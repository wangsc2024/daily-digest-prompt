---
name: task-quality-gate
version: "1.0.0"
description: |
  LLM-as-a-Judge 品質門檻評估。使用 Claude Haiku 快速評估自動任務輸出的完整性、連貫性、準確性（0-10 分），低於門檻（<7）則標記為 needs_review。
  Use when: 自動任務完成後、寫入最終結果前
allowed-tools:
  - Read
  - Write
  - Bash
triggers:
  - "品質評估"
  - "quality gate"
  - "LLM-as-a-judge"
  - "輸出品質檢查"
  - "task quality"
---

# Task Quality Gate Skill（LLM-as-a-Judge 品質門檻）

> **靈感來源**：Langfuse LLM Engineering Platform（GitHub 23.5k stars）

自動評估自動任務輸出品質（語義層級），補充現有 schema 驗證的不足。

## 評估流程

### 步驟 1：讀取評估標準

用 Read 讀取 `config/evaluation-criteria.yaml`，取得：
- `pass_threshold`（通過門檻，預設 7/10）
- `model`（評估用 LLM，預設 Haiku）
- `criteria_by_task_type`（依任務類型的評估標準）

### 步驟 2：準備評估 prompt

用 Write 建立 `tmp/quality-eval-prompt-{timestamp}.md`：

```markdown
你是品質評審 LLM。評估以下自動任務輸出的品質（0-10 分）：

**任務類型**: {task_type}
**輸出摘要**: {summary}
**預期標準**:
{criteria}

評估維度：
1. **完整性**（是否包含所有必填欄位或關鍵資訊）
2. **連貫性**（邏輯是否清晰，前後一致）
3. **準確性**（資訊是否正確，無明顯錯誤）

只回覆 JSON（不加 markdown code fence）：
{"score": 0-10, "reason": "一句話原因（20字內）"}
```

**變數替換**：
- `{task_type}`：從結果 JSON 的 `task_type` 或 `task_key` 欄位
- `{summary}`：從結果 JSON 的 `summary` 欄位（截取前 500 字）
- `{criteria}`：從 `evaluation-criteria.yaml` 的 `criteria_by_task_type[task_type]` 讀取，格式化為列表

### 步驟 3：執行評估

```bash
timestamp=$(date +%s)
cat tmp/quality-eval-prompt-${timestamp}.md | claude -p --model claude-haiku-4-5-20251001 > tmp/quality-score-${timestamp}.json 2>/dev/null
```

若 claude 呼叫失敗（exit code ≠ 0）：
- 跳過評估，保持原 status 不變
- 在結果 JSON 新增 `quality_gate_skipped: true, quality_gate_reason: "評估服務不可用"`
- 繼續執行（不阻斷流程）

### 步驟 4：解析評估結果

用 Bash 解析 JSON：
```bash
score=$(grep -o '"score":[0-9]*' tmp/quality-score-${timestamp}.json | grep -o '[0-9]*')
reason=$(grep -o '"reason":"[^"]*"' tmp/quality-score-${timestamp}.json | sed 's/"reason":"//' | sed 's/"$//')
```

若解析失敗（score 為空）：
- 跳過評估，保持原 status
- 新增 `quality_gate_skipped: true, quality_gate_reason: "評估結果格式錯誤"`

### 步驟 5：判定是否通過

- `score >= pass_threshold` → 通過
  - 在結果 JSON 新增 `quality_score: {score}, quality_passed: true`
  - 保持原 status 不變
- `score < pass_threshold` → 未通過
  - 將 status 改為 `needs_review`
  - 新增 `quality_score: {score}, quality_passed: false, quality_reason: "{reason}"`
  - 發送 ntfy 告警（見步驟 6）

### 步驟 6：ntfy 告警（未通過時）

```bash
# 用 Write 建立 notify-quality.json
{
  "topic": "wangsc2025",
  "title": "⚠️ 品質評估未通過",
  "message": "任務: {task_type}\n分數: {score}/10\n原因: {reason}\n狀態已標記為 needs_review",
  "tags": ["warning"]
}

# 發送
curl -H "Content-Type: application/json; charset=utf-8" \
  -d @tmp/notify-quality-${timestamp}.json https://ntfy.sh

# 清理
rm tmp/quality-eval-prompt-${timestamp}.md tmp/quality-score-${timestamp}.json tmp/notify-quality-${timestamp}.json
```

### 步驟 7：清理暫存檔（無論通過與否）

```bash
rm -f tmp/quality-eval-prompt-${timestamp}.md tmp/quality-score-${timestamp}.json tmp/notify-quality-${timestamp}.json
```

## 錯誤處理與降級

| 錯誤情境 | 處理方式 |
|----------|---------|
| claude 呼叫失敗（嵌套 session） | 跳過評估，保持原 status，新增 quality_gate_skipped=true |
| 評估結果格式錯誤（JSON 解析失敗） | 跳過評估，保持原 status，新增 quality_gate_skipped=true |
| evaluation-criteria.yaml 不存在 | 使用預設標準（完整性、連貫性、準確性各佔 1/3） |
| 結果 JSON 缺少 summary 欄位 | 使用 task_key 作為替代輸入 |

## 整合點

### todoist-assemble.md 整合

在 `prompts/team/todoist-assemble.md` 步驟 6（寫入結果前）新增：

```markdown
### 步驟 6.5：品質評估（新增）

用 Read 讀取 `skills/task-quality-gate/SKILL.md`，依其步驟執行品質評估。

若評估未通過（quality_passed=false）：
- status 已改為 needs_review
- 已發送 ntfy 告警

若評估被跳過（quality_gate_skipped=true）：
- 保持原 status
- 不影響後續流程
```

## 注意事項

- 評估失敗不阻斷流程（降級為跳過評估）
- 使用 Haiku 確保低成本（< 500 tokens/次）
- 所有暫存檔案加 timestamp 後綴，避免多實例衝突
- quality_score, quality_passed, quality_reason 欄位為可選，僅在評估執行時新增
- 此 Skill 不修改原有欄位（task_key, summary, status 等），僅新增評估相關欄位
