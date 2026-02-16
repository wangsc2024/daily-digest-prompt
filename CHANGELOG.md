# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `config/audit-scoring.yaml` - 系統審查評分規則配置
- `config/timeouts.yaml` - 集中超時配置（取代 PS1 硬編碼）
- `config/README.md` - 配置文件速查說明
- `skills/system-audit/` - 系統審查評分 Skill（7 維度）
- `templates/audit-report.md` - 審查報告模板
- `.env.example` - 環境變數範本
- `requirements.lock` - pip 依賴鎖定檔（pip-compile 產生）
- `CHANGELOG.md` - 本檔案

### Changed
- PS1 腳本路徑從硬編碼 `D:\Source\daily-digest-prompt` 改為 `$PSScriptRoot`（9 個檔案）
- prompts/team 和 templates 中的 inline nul 禁令改為引用 `preamble.md`（DRY 重構）

### Fixed
- `skills/SKILL_INDEX.md` Skill 計數一致性（17 核心 + 3 工具 = 20）
- `.gitignore` 補充排除 `task_result.txt`、`table_render_*.png` 等暫存檔

## [0.1.0] - 2026-02-15

### Added
- 文件驅動架構：Prompt 薄層調度器 + YAML 配置 + Markdown 模板
- 20 個 Skills（17 核心 + 3 工具），含標準化 frontmatter
- 每日摘要 Agent（單一模式 + 團隊並行模式）
- Todoist 任務規劃 Agent（單一模式 + 3 階段並行模式）
- Gmail 郵件摘要 Agent
- Hooks 機器強制層（4 個 Hook：Bash guard / Write guard / Logger / Stop alert）
- 結構化 JSONL 日誌系統（15+ 自動標籤）
- 15 個自動任務（6 群組，40 次/日上限，round-robin 輪轉）
- API 快取降級機制（24 小時內過期快取可用）
- 跨次記憶持久化（digest-memory.json）
- 研究去重機制（research-registry.json，7 天滾動）
- ntfy 通知推播
- Windows Task Scheduler 排程整合（HEARTBEAT.md 批次建立）
- 健康檢查工具（check-health.ps1）
- 執行成果查詢工具（query-logs.ps1，6 種模式）
- 135 個 Hook 測試 + 157 個 Skill 測試 = 292 個測試

### Security
- Hook 攔截：nul 重導向、scheduler-state 寫入、force push、敏感環境變數、路徑遍歷
- 機密管理：環境變數 + .gitignore + .env.example
- 依賴鎖定：requirements.lock
