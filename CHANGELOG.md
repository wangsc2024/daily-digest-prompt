# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- 系統審查報告 2026-03-19（Phase 2 組裝 + 1 項自動修正，85.38/A，-2.50）
- 系統審查報告 2026-03-18（Phase 2 組裝 + 1 項自動修正，87.88/A，+2.83）
- 系統審查報告 2026-03-17（Phase 2 組裝 + 1 項自動修正，85.05/A）
- 系統審查報告 2026-03-16（Phase 2 組裝 + 1 項自動修正，85.16/A）
- 系統審查報告 2026-03-15（Phase 2 組裝 + 2 項自動修正，86.18/A）
- 系統審查報告 2026-03-14（Phase 2 組裝 + 2 項自動修正，86.29/A）
- 系統審查報告 2026-03-12（87.18/A，+1.70）
- 系統審查報告 2026-03-10（Phase 2 組裝 + 3 項自動修正）
- feat: AI 架構治理方案完整實施（912 測試，14 項交付物）
- feat: CI 擴展 tests/skills/ 和 tests/tools/ 覆蓋範圍
- feat: `config/codex-auto-task-result.schema.json` — Codex 自動任務結果 schema
- feat: `skills/academic-paper-research/` — 學術論文研究 Skill
- feat: `skills/cache-optimizer/` — 快取優化 Skill
- feat: `skills/chatroom-task-delivery/` — 聊天室任務交付 Skill
- feat: `skills/skill-forge/` — Skill 鍛造工具 Skill
- feat: `templates/research/` — 研究模板目錄

### Changed
- chore: Skill 計數 20 → 26（19 核心 + 7 工具）
- chore: 自動任務頻率上限 40 → 47 次/日
- refactor: `config/hook-rules.yaml` v2 → v3（20 條規則 + 3 個 preset）
- refactor: `run-todoist-agent-team.ps1` 動態掃描 prompt 檔案（取代硬編碼路徑）
- feat: Groq 整合：fetch-hackernews（批次翻譯）、fetch-news（快速摘要）
- fix: Hook CWD 修復：`.claude/settings.json` 加 `cd /d` 包裝

### Fixed
- fix: Phase 2/3 結果檔案命名統一（`todoist-auto-` 前綴）
- fix: LoopDetector 跨進程持久化（state/loop-state-*.json）
- fix: MinGW 雙斜線路徑修正（`_normalize_windows_path`）
- fix: CJK 字元日文變體修正（10 個字元對映）
- fix: 4 個 prompt inline nul 殘留改為引用 preamble.md

### Removed
- 無項目移除（保留此章節供未來記錄）

### Security
- feat: `pre_read_guard.py` 新增（攔截敏感路徑讀取）
- feat: `validate_config.py` 新增（7 個 YAML Schema 驗證）
- docs: Prompt Injection 防護（3 處模板消毒指引）
- feat: 3 個安全 preset（strict/normal/permissive）
- feat: 機密外洩防護加強（子 shell 繞過 + base64 編碼攔截）

### Known Issues
- 964 個測試通過，行覆蓋率 10.39% 待改善（hooks+skills scope），模組覆蓋率 100%
- 6 個 config YAML 僅注釋引用無代碼實裝（cache-policy/scoring/notification 等）
- 17 處 Windows 硬編碼路徑（D:\Source\）待架構評估

## [0.2.0] - 2026-03-09

### Added
- feat: 系統熵增治理優化計畫全部完成（11 個核心優化項目）
- refactor: CLAUDE.md 587→~220 行，新建 docs/ARCHITECTURE.md、docs/OPERATIONS.md
- feat: `config/dedup-policy.yaml` — 研究去重策略（三層防護）
- feat: `config/topic-rotation.yaml` — 主題輪替演算法（LRU + 同日去重）
- feat: `analyze-config.ps1` — 配置膨脹度量工具（9 指標、30 天歷史）
- feat: `new-auto-task.ps1` — 自動任務一鍵建立工具
- feat: `context/metrics-daily.json` — 每日指標聚合（14 天滾動）
- feat: `config/slo.yaml` — SLO 配置（6 個 SLO 定義）
- docs: ADR-009 自建輕量級可觀測性框架（OTel 語義相容）
- test: 測試數量 675 → 682 個

## [0.1.1] - 2026-03-03

### Added
- feat: `skills/arch-evolution/` — 架構演進 Skill（OODA Decide 層，ADR 管理）
- feat: `skills/kb-research-strategist/` — 知識庫研究策略 Skill（五階段深度模型）
- feat: `skills/groq/` — Groq 超快推論 Skill（透過 groq-relay 中繼）
- feat: `skills/todoist-task-creator/` — Todoist 任務建立工具 Skill
- feat: `bot/groq-relay.js` — Groq API 中繼服務（port 3001，4 模式 + 速率限制）
- feat: `config/llm-router.yaml` — LLM 路由規則（Groq vs Claude 任務分配）
- feat: `config/ooda-workflow.yaml` — OODA 閉環工作流配置
- feat: `config/creative-game-mode.yaml` — 創意遊戲模式配置
- feat: `config/retro-games.yaml` — 復古遊戲評鑑配置
- feat: `config/schemas/` — YAML 驗證 Schema 目錄
- feat: `hooks/agent_guardian.py` — 三層守護（ErrorClassifier + CircuitBreaker + LoopDetector）
- feat: `hooks/cjk_guard.py` — CJK 字元守衛（偵測日文 Unicode 變體）
- feat: `hooks/behavior_tracker.py` — 行為模式識別
- feat: `context/adr-registry.json` — 架構決策記錄（8 個 ADR）
- feat: `context/research-series.json` — 永久系列研究追蹤
- feat: `templates/shared/kb-depth-check.md` — 共用 4-Phase KB 深度模板
- feat: 自動任務新增至 19 個（+4：system-insight、self-heal、github-scout、chatroom-optimize）
- test: 測試從 292 → 675 個（hooks 14 測試檔 + skills 3 測試檔 + bot 4 測試檔）
- feat: `circuit-breaker-utils.ps1` — 斷路器工具（5 個 API 健康追蹤）
- feat: `state/failure-stats.json` — 失敗統計（5 種類型 + 30 天保留）
- feat: `state/run-fsm.json` — 有限狀態機追蹤

## [0.1.0] - 2026-02-15

### Added
- feat: 文件驅動架構：Prompt 薄層調度器 + YAML 配置 + Markdown 模板
- feat: 20 個 Skills（17 核心 + 3 工具），含標準化 frontmatter
- feat: 每日摘要 Agent（單一模式 + 團隊並行模式）
- feat: Todoist 任務規劃 Agent（單一模式 + 3 階段並行模式）
- feat: Gmail 郵件摘要 Agent
- feat: Hooks 機器強制層（4 個 Hook：Bash guard / Write guard / Logger / Stop alert）
- feat: 結構化 JSONL 日誌系統（15+ 自動標籤）
- feat: 15 個自動任務（6 群組，40 次/日上限，round-robin 輪轉）
- feat: API 快取降級機制（24 小時內過期快取可用）
- feat: 跨次記憶持久化（digest-memory.json）
- feat: 研究去重機制（research-registry.json，7 天滾動）
- feat: ntfy 通知推播
- feat: Windows Task Scheduler 排程整合（HEARTBEAT.md 批次建立）
- feat: 健康檢查工具（check-health.ps1）
- feat: 執行成果查詢工具（query-logs.ps1，6 種模式）
- test: 135 個 Hook 測試 + 157 個 Skill 測試 = 292 個測試

### Security
- feat: Hook 攔截：nul 重導向、scheduler-state 寫入、force push、敏感環境變數、路徑遍歷
- feat: 機密管理：環境變數 + .gitignore + .env.example
- feat: 依賴鎖定：uv.lock（完整 hash 鎖定）
