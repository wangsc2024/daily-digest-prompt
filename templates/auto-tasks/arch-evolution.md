# 架構演進決策模板

> **注意**：本任務直接在 team prompt (`prompts/team/todoist-auto-arch_evolution.md`) 中執行，此檔案僅作為 pre-commit hook 檢查的佔位符。

## 設計理念

`arch_evolution` 任務整合多個 Skill（system-audit, system-insight），需要複雜的步驟編排，因此不適合拆分為獨立的 sub-agent template。所有執行邏輯已完整定義於 team prompt 中。

## 執行流程

詳見 `prompts/team/todoist-auto-arch_evolution.md`。
