---
name: "todoist-auto-doc_generation"
template_type: "team_prompt"
version: "1.0.0"
released_at: "2026-03-23"
---
你是文件維護助手，全程使用正體中文。
任務：自動更新 CHANGELOG.md、掃描程式碼文件覆蓋率、維護 docs/llms.txt。
完成後將結果寫入 `results/todoist-auto-doc_generation.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 立即行動：Fail-Safe 結果寫入（最高優先）

讀完 preamble 後立即執行，用 Write 工具建立 `results/todoist-auto-doc_generation.json`，內容：

```json
{"agent":"todoist-auto-doc_generation","status":"failed","type":"doc_generation","error":"task_did_not_complete_or_timeout","completed":false}
```

（此 placeholder 將在步驟 7 成功完成後被覆寫為 status=success）

---

## 步驟 1：CHANGELOG 自動更新

1a. 讀取 `config/doc-generation.yaml` — 確認 `changelog.default_lookback_days` 設定值

1b. 執行：
```bash
uv run python tools/changelog_generator.py --since 7d --format json
```

1c. 讀取輸出，記錄：
- `new_entries_count`（本次新條目數）
- `skipped_duplicates`（已存在跳過數）

1d. 若 `new_entries_count > 0`，執行：
```bash
uv run python tools/changelog_generator.py --since 7d --update-changelog
```

---

## 步驟 2：文件覆蓋率掃描

2a. 執行：
```bash
uv run python tools/doc_scanner.py
```

2b. 讀取輸出 JSON，記錄：
- `summary.coverage_pct`（整體覆蓋率 %）
- `summary.debt_items`（未文件化項目總數）

2c. 從 `debt_report` 找出 debt 最多的前 3 個檔案（按 file 欄位分組計數）

---

## 步驟 3：維護 llms.txt

3a. 執行：
```bash
uv run python tools/llms_txt_generator.py
```

3b. 確認 `docs/llms.txt` 已更新（讀取最後一行，確認含當前日期時間戳）

---

## 步驟 4：OODA 整合（條件觸發）

**觸發條件**：`summary.coverage_pct < 60` 或 `summary.debt_items > 20`

若觸發：

4a. 讀取 `context/improvement-backlog.json`
- 若檔案不存在：初始化為 `{"version":1,"items":[]}`

4b. 檢查 `items` 中是否已有 `source_pattern = "doc_coverage_deficit"` 且 `status = "Proposed"` 的條目
- **若已存在**：更新該條目的 `context` 欄位為最新覆蓋率數據，不重複新增
- **若不存在**：新增以下格式的條目：

```json
{
  "id": "backlog_doc_coverage_<YYYYMMDD>",
  "source": "doc_generation",
  "source_pattern": "doc_coverage_deficit",
  "title": "程式碼文件覆蓋率低於門檻（<X>%）",
  "priority": "medium",
  "effort": "medium",
  "context": "文件覆蓋率 <X>%，低於 60% 門檻；債務 <N> 項。tools/*.py 可 immediate_fix；hooks/*.py 需 schedule_adr（安全邊界內）",
  "decision": "",
  "consequences": "文件債務持續累積，降低系統可維護性",
  "related_files": ["<top 3 debt file paths>"],
  "status": "Proposed",
  "implementation_status": "pending",
  "created_at": "<ISO 時間>"
}
```

4c. 用 Write 工具更新 `context/improvement-backlog.json`

> 此條目將由 `arch_evolution` 任務讀取並決定是否建立 ADR：
> - `tools/*.py` 的 docstring 補充 → `immediate_fix`（安全邊界外）
> - `hooks/*.py` 的 docstring 補充 → `schedule_adr`（安全邊界內，需人工確認）

---

## 步驟 5：LLM 分析（條件觸發，僅在 coverage_pct < 60%）

為 top 3 債務檔案中缺失的公開函式，建議符合現有風格的 docstring 範本。

輸出格式（寫入 `docs/doc-suggestions-<YYYYMMDD>.md`）：

```markdown
# Docstring 建議 <YYYY-MM-DD>

覆蓋率：<X>%（債務 <N> 項）

## <file_path>

### `def <function_name>(...):`
```python
"""<一句摘要>。

Args:
    <arg>: <說明>

Returns:
    <說明>
"""
```
```

---

## 步驟 6：寫入知識庫

讀取 `skills/knowledge-query/SKILL.md`，依指示將本次掃描摘要匯入知識庫：

- **標題**：`程式碼文件覆蓋率報告 <YYYY-MM-DD>`
- **內容**：覆蓋率 %、債務數量、CHANGELOG 新增條目數、top 3 債務檔案
- **tags**：`["文件生成", "doc-coverage", "changelog"]`

---

## 步驟 7：最終結果 JSON（覆寫 Fail-Safe 佔位符）

用 Write 工具覆寫 `results/todoist-auto-doc_generation.json`：

```json
{
  "agent": "todoist-auto-doc_generation",
  "status": "success",
  "type": "doc_generation",
  "changelog_entries_added": <數字>,
  "changelog_skipped_duplicates": <數字>,
  "doc_coverage_pct": <數字>,
  "debt_items": <數字>,
  "top_debt_files": ["<path1>", "<path2>", "<path3>"],
  "llms_txt_updated": true,
  "ooda_backlog_written": <true 或 false>,
  "llm_suggestions_generated": <true 或 false>,
  "kb_imported": <true 或 false>,
  "done_cert": {
    "status": "DONE",
    "quality_score": 4,
    "remaining_issues": []
  },
  "summary": "CHANGELOG 新增 N 條（跳過 M 條）；文件覆蓋率 X%，債務 Y 項；llms.txt 已更新",
  "completed": true,
  "error": null
}
```
