# ADR-017 TODO/FIXME 掃描報告（2026-03-14）

## 摘要

- **目標**：265 → 80 處以下（ADR-017）
- **優先順序**：docs/plans/ → templates/ → prompts/
- **本報告**：落實 ADR-017 步驟 (1) 掃描並產出分類報告；後續由人工分批清理。

## 已落實項目

1. **new-auto-task.ps1 模板佔位符**：已使用角括號語法（`<描述此自動任務的用途>`、`<填入 skill 名稱>`、`<填入具體執行步驟>`），無 TODO 字樣，掃描誤報已消除。
2. **docs/plans/**：grep 命中多為 `TODOIST_API_TOKEN` 子串誤報，非技術債標記。
3. **templates/**：僅 audit-report.md 表頭「TODO/FIXME > 20」為規則說明，非待辦標記。
4. **prompts/team/**：多數命中為「Todoist」「TodoWrite」等詞彙，非 # TODO 標記；真實 TODO 需人工逐檔分類。

## 建議後續（人工分批）

- 使用 `skills/todo-scanner` 或 `uv run python -c "..."` 產出結構化 JSON 報告（依目錄分組）。
- 規範性（考慮…、可能需要…）→ 直接移除或改寫。
- 缺陷型 → 轉 issue 或保留並標註。
- 持續追蹤至 80 處以下。

## 參考

- ADR-20260314-017（context/adr-registry.json）
- context/tech-debt-backlog.json（含 false_positives 說明）
