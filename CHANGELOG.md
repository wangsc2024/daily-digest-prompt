# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added（2026-02-16 ~ 2026-03-17）
- 系統審查報告 2026-03-17（Phase 2 組裝 + 1 項自動修正，85.05/A）
- 系統審查報告 2026-03-16（Phase 2 組裝 + 1 項自動修正，85.16/A）
- 系統審查報告 2026-03-15（Phase 2 組裝 + 2 項自動修正，86.18/A）
- 系統審查報告 2026-03-14（Phase 2 組裝 + 2 項自動修正，86.29/A）
- 系統審查報告 2026-03-12（87.18/A，+1.70）
- 系統審查報告 2026-03-10（Phase 2 組裝 + 3 項自動修正）
- AI 架構治理方案完整實施（912 測試，14 項交付物）
- CI 擴展 tests/skills/ 和 tests/tools/ 覆蓋範圍
- `config/codex-auto-task-result.schema.json` — Codex 自動任務結果 schema
- `skills/academic-paper-research/` — 學術論文研究 Skill
- `skills/cache-optimizer/` — 快取優化 Skill
- `skills/chatroom-task-delivery/` — 聊天室任務交付 Skill
- `skills/skill-forge/` — Skill 鍛造工具 Skill
- `templates/research/` — 研究模板目錄

### Removed
- 無項目移除（保留此章節供未來記錄）

### Known Issues
- 964 個測試通過，行覆蓋率 10.39% 待改善（hooks+skills scope），模組覆蓋率 100%
- 6 個 config YAML 僅注釋引用無代碼實裝（cache-policy/scoring/notification 等）
- 17 處 Windows 硬編碼路徑（D:\Source\）待架構評估

### Previously Added（2026-02-16 ~ 2026-03-09）
- 系統熵增治理優化計畫全部完成（11 個核心優化項目）
- CLAUDE.md 587→~220 行，新建 docs/ARCHITECTURE.md、docs/OPERATIONS.md
- `config/dedup-policy.yaml` - 研究去重策略（三層防護）
- `config/topic-rotation.yaml` - 主題輪替演算法（LRU + 同日去重）
- `analyze-config.ps1` - 配置膨脹度量工具（9 指標、30 天歷史）
- `new-auto-task.ps1` - 自動任務一鍵建立工具
- `context/metrics-daily.json` - 每日指標聚合（14 天滾動）
- `config/slo.yaml` - SLO 配置（6 個 SLO 定義）
- ADR-009 自建輕量級可觀測性框架（OTel 語義相容）
- 測試數量 675 → 682 個

### Previously Added（2026-02-16 ~ 2026-03-03）
- `skills/arch-evolution/` - 架構演進 Skill（OODA Decide 層，ADR 管理）
- `skills/kb-research-strategist/` - 知識庫研究策略 Skill（五階段深度模型）
- `skills/groq/` - Groq 超快推論 Skill（透過 groq-relay 中繼）
- `skills/todoist-task-creator/` - Todoist 任務建立工具 Skill
- `bot/groq-relay.js` - Groq API 中繼服務（port 3001，4 模式 + 速率限制）
- `config/llm-router.yaml` - LLM 路由規則（Groq vs Claude 任務分配）
- `config/ooda-workflow.yaml` - OODA 閉環工作流配置
- `config/creative-game-mode.yaml` - 創意遊戲模式配置
- `config/retro-games.yaml` - 復古遊戲評鑑配置
- `config/schemas/` - YAML 驗證 Schema 目錄
- `hooks/agent_guardian.py` - 三層守護（ErrorClassifier + CircuitBreaker + LoopDetector）
- `hooks/cjk_guard.py` - CJK 字元守衛（偵測日文 Unicode 變體）
- `hooks/behavior_tracker.py` - 行為模式識別
- `context/adr-registry.json` - 架構決策記錄（8 個 ADR）
- `context/research-series.json` - 永久系列研究追蹤
- `templates/shared/kb-depth-check.md` - 共用 4-Phase KB 深度模板
- 自動任務新增至 19 個（+4：system-insight、self-heal、github-scout、chatroom-optimize）
- 測試從 292 → 675 個（hooks 14 測試檔 + skills 3 測試檔 + bot 4 測試檔）
- `circuit-breaker-utils.ps1` - 斷路器工具（5 個 API 健康追蹤）
- `state/failure-stats.json` - 失敗統計（5 種類型 + 30 天保留）
- `state/run-fsm.json` - 有限狀態機追蹤

### Changed
- Skill 計數 20 → 26（19 核心 + 7 工具）
- 自動任務頻率上限 40 → 47 次/日
- `config/hook-rules.yaml` v2 → v3（20 條規則 + 3 個 preset）
- `run-todoist-agent-team.ps1` 動態掃描 prompt 檔案（取代硬編碼路徑）
- Groq 整合：fetch-hackernews（批次翻譯）、fetch-news（快速摘要）
- Hook CWD 修復：`.claude/settings.json` 加 `cd /d` 包裝

### Fixed
- Phase 2/3 結果檔案命名統一（`todoist-auto-` 前綴）
- LoopDetector 跨進程持久化（state/loop-state-*.json）
- MinGW 雙斜線路徑修正（`_normalize_windows_path`）
- CJK 字元日文變體修正（10 個字元對映）
- 4 個 prompt inline nul 殘留改為引用 preamble.md

### Security
- `pre_read_guard.py` 新增（攔截敏感路徑讀取）
- `validate_config.py` 新增（7 個 YAML Schema 驗證）
- Prompt Injection 防護（3 處模板消毒指引）
- 3 個安全 preset（strict/normal/permissive）
- 機密外洩防護加強（子 shell 繞過 + base64 編碼攔截）

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
- 依賴鎖定：uv.lock（完整 hash 鎖定）
