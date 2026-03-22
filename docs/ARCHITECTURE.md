# Daily Digest Prompt - 架構文件

> 本文件由 `docs/ARCHITECTURE.md` 維護，對應 CLAUDE.md 的「架構」章節引用。
> 最後更新：2026-03-20（v5：新增 Autonomous Harness、SLO 管理、29 個自動任務、52 個 Skills）

## 目錄結構

本專案採用**文件驅動架構**：Prompt 是薄層調度器，所有可變邏輯抽入結構化配置文件與模板，按需載入。

```
daily-digest-prompt/
  # Prompt 層（薄層調度器，讀配置 → 按管線執行）
  daily-digest-prompt.md          # 每日摘要 Agent（~80 行，引用 config/ + templates/）
  hour-todoist-prompt.md          # Todoist 任務規劃 Agent（~140 行，引用 config/ + templates/）
  daily-gmail-prompt.md           # Gmail Agent（獨立排程）
  HEARTBEAT.md                    # 排程元資料（cron 定義，供 setup-scheduler.ps1 讀取）

  # 配置層（數據型配置，修改無需動 prompt）
  config/
    pipeline.yaml                 # 每日摘要管線：步驟順序、Skill 依賴、後處理
    routing.yaml                  # Todoist 三層路由：標籤映射、關鍵字映射、排除清單
    cache-policy.yaml             # 快取策略：各 API 的 TTL、降級時限
    frequency-limits.yaml         # 自動任務頻率限制（29 個任務，~40 次/日上限，round-robin 輪轉）
                                  # ⭐ 同時定義後端路由規則（codex/cursor_cli/claude_sonnet45 等）
    autonomous-harness.yaml       # 自主運行框架配置（FSM 閾值、dispatch、runtime profiles）
    benchmark.yaml                # 系統效能基準線（Fitness Functions、參考專案比較）
    scoring.yaml                  # TaskSense 優先級計分規則（6 因子，同分 Tiebreaker）
    notification.yaml             # ntfy 通知配置（topic、標籤、模板）
    notification-events.yaml      # 事件型通知定義（event→ntfy 映射）
    dedup-policy.yaml             # 研究去重策略（冷卻天數、飽和閾值、跨任務去重）
    slo.yaml                      # SLO 定義（成功率、Timeout、每日目標）
    ooda-workflow.yaml            # OODA 閉環配置（Observe→Orient→Decide→Act 步驟定義）
    llm-router.yaml               # LLM 路由規則（task_type → backend mapping，O(1) lookup）
    budget.yaml                   # Token 預算治理（80%警告/100%暫停 閾值）
    hook-rules.yaml               # Hook 攔截規則（20 條，3 preset：strict/normal/permissive）
    audit-scoring.yaml            # 系統審查 7 維度計分規則
    health-scoring.yaml           # 健康評分 6 維度權重
    agent-pool.yaml               # Agent Pool 配置（coordinator/done_cert 設定）
    timeouts.yaml                 # 各 Agent 超時配置（phase2_timeout_by_task）
    topic-rotation.yaml           # 主題輪替演算法（LRU + 同日去重）
    media-pipeline.yaml           # 媒體管線設定（TTS/FFmpeg/R2 上傳流程）
    podcast.yaml                  # Podcast 生成配置（主持人角色、語音模型、節目格式）
    kb-content-scoring.yaml       # 知識庫筆記評分規則（Podcast 選材）
    long_term_memory.yaml         # 長期記憶模組配置（壓縮策略、保留規則）
    insight-briefing-workflow.yaml # 洞察簡報工作流配置
    digest-format.md              # 摘要輸出排版模板
    schemas/
      results-auto-task-schema.json    # 自動任務結果統一格式（v1.1.0）
      execution-trace-schema.json      # Agent 執行追蹤統一 Schema（v1.0.0）
      agent-result.schema.json         # Agent 結果驗證 Schema（供 agent-result-validator Skill）
      skill-registry.schema.json       # Skill 登記表 Schema（供 sync_skill_registry.py）
      codex-auto-task-result.schema.json # Codex 任務結果格式驗證

  # 工作流驗證層（workflow-forge 產出物）
  workflows/
    index.yaml                        # workflow 產出物索引（Agent 執行前依 task_type 篩選適用 workflow）
    prompt-output-validation-checklist.md    # Prompt 輸出規範驗證清單（29 個自動任務 prompt）
    results-validation-checklist.md          # 結果檔案格式驗證清單（results/todoist-auto-*.json）
    config-consistency-validation-checklist.md # Config 一致性驗證清單（config/*.yaml 與檔案系統一致性）

  # 模板層（按需載入，不預載進 context window）
  templates/
    shared/
      preamble.md                 # 共用前言（nul 禁令 + Skill-First，一處定義）
      done-cert.md                # DONE_CERT 格式定義（含 file_hash 串流讀取）
      quality-gate.md             # 驗證閘門規則（迭代精修）
    sub-agent/                    # 子 Agent 任務模板（Todoist 路由後按需載入）
      skill-task.md               # 模板 A：有 Skill 匹配的任務
      research-task.md            # 模板 B：知識庫研究任務（含 KB 去重）
      code-task.md                # 模板 D：@code 任務（Plan-Then-Execute）
      game-task.md                # 模板 E：遊戲設計任務（品質分析→修改）
      general-task.md             # 模板 C：無 Skill 匹配的一般任務
      refinement.md               # 品質閘門精修 prompt
    auto-tasks/                   # 自動任務 prompt 模板（29 個任務，按需載入）
      shurangama-research.md      # 楞嚴經研究（cursor_cli/claude_sonnet45）
      buddhist-research.md        # 通用佛學模板（教觀綱宗/法華經/淨土宗 共用參數化）
      ai-deep-research.md         # AI 深度研究計畫（4 階段，codex_exec）
      ai-github-research.md       # AI GitHub 熱門專案研究（codex_exec）
      ai-domain-research.md       # 通用 AI 領域研究模板（ai_smart_city/ai_sysdev 共用）
      ai-workflow-github-research.md  # AI 工作流 GitHub 研究（codex_exec）
      tech-research.md            # 每日任務技術研究（codex_exec）
      unsloth-research.md         # Unsloth fine-tuning 研究（停用 daily_limit=0）
      skill-audit.md              # Skill 品質審查（claude_sonnet45）
      log-audit.md                # 系統 Log 審查（claude_sonnet45）
      git-push.md                 # GitHub 推送流程（claude_sonnet45）
      creative-game-optimize.md   # 創意遊戲優化（停用 daily_limit=0）
      qa-system-optimize.md       # QA 系統優化（停用 daily_limit=0）
      system-insight.md           # 系統洞察分析（claude_sonnet45）
      arch-evolution.md           # 架構演進（佔位符，實際邏輯在 team prompt）
      self-heal.md                # 系統自癒迴圈（claude_sonnet45）
      chatroom-optimize.md        # Chatroom 優化（停用 daily_limit=0）
      github-scout.md             # GitHub 靈感蒐集（codex_standard）
      podcast-create.md           # Podcast 生成（cursor_cli）
      podcast-jiaoguangzong.md    # 教觀綱宗 Podcast（claude_sonnet45）

  # 執行腳本
  run-agent.ps1                   # 每日摘要執行腳本（單一模式，含重試）
  run-agent-team.ps1              # 每日摘要執行腳本（團隊並行模式，推薦）
  run-todoist-agent.ps1           # Todoist 任務規劃執行腳本（單一模式）
  run-todoist-agent-team.ps1      # Todoist 任務規劃執行腳本（3 階段並行，推薦）
  run-gmail-agent.ps1             # Gmail Agent 執行腳本
  run-system-audit.ps1            # 每日系統審查執行腳本（單一模式，備用）
  run-system-audit-team.ps1       # 每日系統審查執行腳本（團隊並行模式，推薦）
  setup-scheduler.ps1             # 排程設定工具（支援 HEARTBEAT.md 批次建立）
  check-health.ps1                # 健康檢查報告工具（含 6 區塊：自動任務/研究/快取/配置/根因分析/SLO）
  scan-skills.ps1                 # 技能安全掃描工具（Cisco AI Defense）
  query-logs.ps1                  # 執行成果查詢工具（5 種模式）
  analyze-config.ps1              # 配置膨脹度量工具（9 指標、4 閾值、30 天歷史）
  generate-arch-diagrams.ps1      # 架構圖自動生成工具（Mermaid，需 claude -p）
  new-auto-task.ps1               # 一鍵新增自動任務工具

  # Hooks 機器強制層
  .claude/
    settings.json                 # Hooks 設定（PreToolUse/PostToolUse/Stop）
  hooks/
    pre_bash_guard.py             # PreToolUse:Bash - 攔截 nul 重導向、危險操作
    pre_write_guard.py            # PreToolUse:Write/Edit - 攔截 nul 寫入、敏感檔案
    pre_read_guard.py             # PreToolUse:Read - 攔截敏感路徑讀取（.ssh、.env 等）
    post_tool_logger.py           # PostToolUse:* - 結構化 JSONL 日誌（自動標籤 + 50MB 輪轉）
    on_stop_alert.py              # Stop - Session 結束健康檢查 + ntfy 告警
    hook_pipeline.py              # DeerFlow 式 Hook 中介軟體（短路機制，規則鏈）
    hook_utils.py                 # 共用模組（YAML 載入、日誌記錄、Injection Patterns）
    validate_config.py            # YAML Schema 驗證工具（可由 check-health.ps1 呼叫）
    query_logs.py                 # 結構化日誌查詢工具（CLI）
    cjk_guard.py                  # PostToolUse:Write/Edit - CJK 字元守衛

  # 團隊模式 Agent prompts
  prompts/team/
    # 每日摘要（Phase 1→Phase 2）
    fetch-todoist.md              # Phase 1: Todoist 資料擷取
    fetch-news.md                 # Phase 1: 屏東新聞資料擷取
    fetch-hackernews.md           # Phase 1: HN AI 新聞資料擷取
    fetch-gmail.md                # Phase 1: Gmail 郵件擷取
    fetch-security.md             # Phase 1: Cisco AI Defense 安全審查
    fetch-chatroom.md             # Phase 1: Chatroom 狀態擷取
    assemble-digest.md            # Phase 2: 摘要組裝 + 通知 + 狀態
    # 系統審查（Phase 1→Phase 2）
    fetch-audit-dim1-5.md         # Phase 1: 維度 1（資訊安全）+ 維度 5（技術棧）
    fetch-audit-dim2-6.md         # Phase 1: 維度 2（系統架構）+ 維度 6（系統文件）
    fetch-audit-dim3-7.md         # Phase 1: 維度 3（系統品質）+ 維度 7（系統完成度）
    fetch-audit-dim4.md           # Phase 1: 維度 4（系統工作流）
    assemble-audit.md             # Phase 2: 組裝結果 + 自動修正 + 報告 + RAG
    # Todoist（Phase 1→Phase 2→Phase 3）
    todoist-query.md              # Phase 1: Todoist 查詢 + 路由 + 計分 + 規劃
    todoist-assemble.md           # Phase 3: 組裝結果 + 關閉任務 + 通知
    chatroom-query.md             # 即時 Chatroom 查詢
    # 自動任務 prompts（29 個，命名規則：todoist-auto-{task_key}.md，底線命名）
    todoist-auto-shurangama.md         # 楞嚴經研究（claude_sonnet45）
    todoist-auto-jiaoguangzong.md      # 教觀綱宗研究（claude_sonnet45）
    todoist-auto-fahua.md              # 法華經研究（cursor_cli）
    todoist-auto-jingtu.md             # 淨土宗研究（codex_exec）
    todoist-auto-tech_research.md      # 每日任務技術研究（codex_exec）
    todoist-auto-ai_deep_research.md   # AI 深度研究計畫（codex_exec）
    todoist-auto-unsloth_research.md   # Unsloth 研究（停用）
    todoist-auto-ai_github_research.md # AI GitHub 熱門專案（codex_exec）
    todoist-auto-ai_smart_city.md      # AI 智慧城市研究（codex_exec）
    todoist-auto-ai_sysdev.md          # AI 系統開發研究（codex_exec）
    todoist-auto-ai_workflow_github.md # AI 工作流 GitHub（codex_exec）
    todoist-auto-skill_audit.md        # Skill 審查（claude_sonnet45）
    todoist-auto-log_audit.md          # Log 審查（claude_sonnet45）
    todoist-auto-git_push.md           # GitHub 推送（claude_sonnet45）
    todoist-auto-creative_game_optimize.md # 創意遊戲（停用）
    todoist-auto-qa_optimize.md        # QA 優化（停用）
    todoist-auto-system_insight.md     # 系統洞察（claude_sonnet45）
    todoist-auto-arch_evolution.md     # 架構演進決策（claude_sonnet45）
    todoist-auto-self_heal.md          # 系統自癒（claude_sonnet45）
    todoist-auto-chatroom_optimize.md  # Chatroom 優化（停用）
    todoist-auto-github_scout.md       # GitHub 靈感蒐集（codex_standard）
    todoist-auto-podcast_create.md     # Podcast 生成（cursor_cli）
    todoist-auto-podcast_jiaoguangzong.md # 教觀綱宗 Podcast（claude_sonnet45）
    todoist-auto-skill_forge.md        # Skill 自動鑄造（claude_sonnet45）
    todoist-auto-ntfy_review.md        # ntfy 通知審查（claude_opus46）
    todoist-auto-future_plan_optimize.md # 未來計畫優化（cursor_cli）
    todoist-auto-kb_insight_evaluation.md # KB 洞察評估（codex_exec）
    todoist-auto-workflow_forge.md     # Workflow 鑄造廠（claude_sonnet45）
    todoist-auto-insight_briefing.md   # 深度洞察簡報（claude_sonnet45）
  results/                        # 團隊模式中間結果（完成後清理）

  # 持久化資料
  context/
    digest-memory.json            # 摘要記憶（連續天數、待辦統計等，Agent 獨佔寫入）
    auto-tasks-today.json         # 自動任務頻率追蹤（每日歸零，next_execution_order 跨日保留）
    research-registry.json        # 研究主題註冊表（跨任務去重，7 天滾動，含 summary 欄位）
    arch-decision.json            # 架構決策清單（OODA Decide 輸出，供 self-heal 執行）
    workflow-state.json           # OODA 工作流狀態（current_step: observe/orient/decide/act）
    system-insight.json           # 系統洞察快照（最新系統狀態摘要）
    improvement-backlog.json      # 待改進項目清單（goal_id/adr_ref 對應）
    mission.yaml                  # 系統目標繼承鏈（G01-G05）
    adr-registry.json             # ADR 架構決策登記表（自動維護）
    behavior-patterns.json        # 系統行為模式記錄
    research-series.json          # 研究系列追蹤（五階段模型，無 TTL）
    continuity/                   # 自動任務連續性記錄（per-task JSON）
  cache/                          # API 回應快取（TTL 定義在 config/cache-policy.yaml）
    todoist.json / pingtung-news.json / hackernews.json / gmail.json
    status.json                   # PS 預計算快取狀態（Phase 0 生成，LLM 直接讀 valid 欄位）
  state/
    scheduler-state.json          # 執行記錄（最近 200 筆，PowerShell 獨佔寫入）
    todoist-history.json          # Todoist 自動任務歷史
    config-metrics.json           # 配置膨脹度量歷史（analyze-config.ps1 產生，30 筆滾動）
    run-fsm.json                  # 執行 FSM 狀態機（running/idle/failed 等）
    last-audit.json               # 最新系統審查結果（含總分、等級、7 維度分數）
    failure-stats.json            # 失敗統計（per-agent 成功率、連敗次數）
    failed-auto-tasks.json        # 失敗自動任務清單（recovery worker 使用）
    token-budget-state.json       # Token 預算狀態（warn/critical/emergency 等級）
    token-usage.json              # Token 使用量記錄
    scheduler-heartbeat.json      # 排程心跳（autonomous harness 監控用）
    api-health.json               # API 健康狀態（circuit breaker 狀態）
    auto-task-fairness-hint.json  # 自動任務公平性提示（starvation 偵測）
    alert-registry.json           # 告警登記表（去重防護）
    autonomous-harness-plan.json  # Autonomous Harness 規劃輸出
    autonomous-recovery-queue.json # 自主回復佇列
    autonomous-runtime.json       # 運行時狀態（current_profile: normal/degraded/recovery）
    autonomous-runtime-overrides.json # 臨時覆蓋設定（TTL 限時生效）
    autonomous-agent-registry.json # Agent 實例登記表
    autonomous-resource-snapshot.json # 系統資源快照（CPU/Memory/GPU）
    slo-budget-report.json        # SLO 預算報告（tools/slo_budget_manager.py 產生）
    kb-note-scores.json           # 知識庫筆記評分快取（Podcast 選材用）
    research-quality.json         # 研究品質評分記錄
    long_term_memory_sync_queue.json # 長期記憶同步失敗待重送佇列
    template-versions.json        # 模板版本追蹤（add_prompt_versions.py 產生）

  # 長期記憶模組
  memory/
    long_term_memory.py           # 多層摘要記憶、倒排索引、metadata-aware retrieval
  tools/                          # Python 工具集
    # 核心同步
    digest_sync.py                # 摘要同步到知識庫、佇列重送、檢索入口
    long_term_memory.py           # research-registry / continuity 壓縮維護
    long_term_memory_rollback.py  # 長期記憶快照與回退
    # 自主運行框架
    autonomous_harness.py         # Autonomous Harness（FSM 分析、恢復規劃、dispatch）
    autonomous_recovery_worker.py # Recovery Worker（執行恢復動作、override 注入）
    # LLM 路由
    llm_router.py                 # LLM 路由器（mapping O(1) lookup + validate_relay_response）
    llm_classifier.py             # LLM-as-Router（Instructor 式重試，Groq classify）
    invoke-llm.ps1                # PowerShell LLM 呼叫封裝（mapping 格式）
    # 品質與審計
    audit_verify.py               # 審計日誌驗證（SHA256 鏈式 hash）
    validate_adr.py               # ADR 自動化驗證
    validate_results.py           # 結果檔案格式驗證
    score-kb-notes.py             # 知識庫筆記評分（Podcast 選材）
    score-research-quality.py     # 研究品質評分
    agent_pool/                   # Agent Pool 模組
      coordinator.py              # 任務協調器
      done_cert.py                # 完成憑證（SHA256 串流 hash，64KB 塊讀取防 OOM）
    # 系統觀測
    trace_analyzer.py             # 規則式根因分析（check-health.ps1 呼叫）
    budget_guard.py               # Token 預算守衛（80%警告/100%暫停）
    slo_budget_manager.py         # SLO 預算管理（成功率/Timeout 監控）
    sync_skill_registry.py        # Skill 登記表同步（context/skill-registry.json）
    collect_system_data.py        # 系統資料收集（供 system-insight 使用）
    # 媒體生產
    generate_tts.py               # TTS 音頻生成
    concat_audio.py               # 音頻合併（FFmpeg 封裝）
    run_podcast_create.py         # Podcast 生成主腳本
    generate_podcast_audio.py     # Podcast 音頻完整流程
    generate_long_term_memory_manual.py # 長期記憶手冊自動生成
    # 工具輔助
    config_loader.py              # 配置載入器（YAML 解析 + Schema 驗證）
    add_prompt_versions.py        # 模板版本號批次添加工具
    trip_plan_outline.py          # 旅程計畫大綱工具
    markdown-tools.py             # Markdown 工具集
    generate_report_pdf.py        # 報告 PDF 生成

  # Skills（行為指引，自包含，共 52 個）
  skills/
    SKILL_INDEX.md                # Skill 索引與路由引擎（Agent 首先載入）
    # 核心資料 Skills
    todoist/                      # Todoist 任務管理
    pingtung-news/                # 屏東縣政府新聞
    hackernews-ai-digest/         # HN AI 新聞篩選
    atomic-habits/                # 原子習慣方法論
    learning-mastery/             # 深度學習技術
    pingtung-policy-expert/       # 屏東縣政策專家
    knowledge-query/              # 個人知識庫查詢
    ntfy-notify/                  # ntfy 任務通知
    digest-memory/                # 摘要記憶管理
    api-cache/                    # API 快取管理
    scheduler-state/              # 排程狀態追蹤
    gmail/                        # Gmail 郵件處理
    game-design/                  # 遊戲設計指引
    game-workflow-design/         # 遊戲工作流設計
    system-insight/               # 系統洞察分析
    web-research/                 # 網路研究
    kb-curator/                   # 知識庫策展管理
    github-scout/                 # GitHub 靈感偵察
    kb-research-strategist/       # KB 研究策略（五階段模型）
    groq/                         # Groq 超快推理
    # 工具 Skills
    task-manager/                 # 任務管理工具
    skill-scanner/                # Skill 安全掃描
    system-audit/                 # 7 維度系統審查評分
    todoist-task-creator/         # Todoist 任務建立
    arch-evolution/               # 架構演進決策
    git-smart-commit/             # Smart Commit 分群提交
    chatroom-query/               # Chatroom 即時查詢
    chatroom-task-delivery/       # Chatroom 任務派發
    knowledge-domain-builder/     # 知識領域建構
    writing-masters/              # 西方文學寫作技巧
    writing-plans/                # TDD 式實作計畫撰寫
    markdown-editor/              # Markdown 編輯器
    skill-forge/                  # Skill 自動鑄造
    skill-lifecycle-manager/      # Skill 生命週期管理
    skill-registry-sync/          # Skill 登記表同步
    skill-test-scaffolder/        # Skill 測試鷹架
    workflow-forge/               # Workflow 鑄造廠
    insight-briefing/             # 洞察簡報
    academic-paper-research/      # 學術論文研究
    agent-result-validator/       # Agent 結果驗證
    behavior-pattern-analyzer/    # 行為模式分析
    cache-optimizer/              # 快取效率優化
    context-budget-monitor/       # Context Window 預算監控
    cursor-cli/                   # Cursor CLI 整合
    execution-journal/            # 執行日誌
    hook-registry/                # Hook 登記管理
    pre-flight-check/             # 執行前健康檢查
    prompt-lint/                  # Prompt 品質檢查
    quality-tracker/              # 品質追蹤
    slo-budget-manager/           # SLO 預算管理
    task-fairness-analyzer/       # 任務公平性分析
    todo-scanner/                 # TODO 掃描器

  # 規格與文件
  specs/system-docs/              # 系統文件（SRD/SSD/ops-manual）
  docs/                           # 研究文件與優化計畫
    ARCHITECTURE.md               # 本文件：目錄結構 + 排程表 + 架構圖
    OPERATIONS.md                 # 運維手冊：執行流程 + Hooks 詳情 + 日誌指令
    skill-routing-guide.md        # Skill 路由指南：決策樹 + 鏈式組合 + 能力矩陣
    user-manuals/                 # 操作手冊（長期記憶、系統使用說明等）
  tests/                          # 測試套件（856 個測試：hooks 529 + skills 27 + tools 300）
  logs/
    structured/                   # 結構化 JSONL 日誌（hooks 自動產生）
```

---

## 排程配置

排程定義集中在 `HEARTBEAT.md`，支援批次建立：

| 排程 | 觸發時間 | 腳本 | 模式 |
|------|---------|------|------|
| system-audit | 每日 00:40 | run-system-audit-team.ps1 | 團隊並行審查 |
| daily-digest-am | 每日 08:00 | run-agent-team.ps1 | 團隊並行 |
| daily-digest-mid | 每日 11:15 | run-agent-team.ps1 | 團隊並行 |
| daily-digest-pm | 每日 21:15 | run-agent-team.ps1 | 團隊並行 |
| todoist-single | 每小時整點 02-23 | run-todoist-agent.ps1 | 單一 |
| todoist-team | 每 30 分鐘 整點及半點 01-23 | run-todoist-agent-team.ps1 | 3 階段並行 |

Timeout 設定集中在 `config/timeouts.yaml`。

---

## 自動任務總覽（29 個，~40 次/日）

| 群組 | 任務 | daily_limit | 後端 | execution_order |
|------|------|------------|------|----------------|
| 佛學研究 | shurangama（楞嚴經） | 1 | claude_sonnet45 | 1 |
| 佛學研究 | jiaoguangzong（教觀綱宗） | 2 | claude_sonnet45 | 2 |
| 佛學研究 | fahua（法華經） | 3 | cursor_cli | 3 |
| 佛學研究 | jingtu（淨土宗） | 2 | codex_exec | 4 |
| AI/技術 | tech_research | 2 | codex_exec | 5 |
| AI/技術 | ai_deep_research | 3 | codex_exec | 6 |
| AI/技術 | unsloth_research | **0（停用）** | — | 7 |
| AI/技術 | ai_github_research | 1 | codex_exec | 8 |
| AI/技術 | ai_smart_city | 1 | codex_exec | 9 |
| AI/技術 | ai_sysdev | 1 | codex_exec | 10 |
| 系統優化 | skill_audit | 1 | claude_sonnet45 | 11 |
| 系統維護 | log_audit | 2 | claude_sonnet45 | 12 |
| 系統維護 | git_push | 1 | claude_sonnet45 | 13 |
| 遊戲創意 | creative_game_optimize | **0（停用）** | — | 14 |
| 專案品質 | qa_optimize | **0（停用）** | — | 15 |
| 系統自省 | system_insight | 2 | claude_sonnet45 | 16 |
| 系統自省 | arch_evolution | 2 | claude_sonnet45 | 17 |
| 系統自省 | self_heal | 2 | claude_sonnet45 | 18 |
| Chatroom | chatroom_optimize | **0（停用）** | — | 19 |
| AI工作流 | ai_workflow_github | 1 | codex_exec | 20 |
| Podcast | podcast_create | 2 | cursor_cli | 21 |
| Podcast | podcast_jiaoguangzong | 3 | claude_sonnet45 | 22 |
| GitHub靈感 | github_scout | 1 | codex_standard | 23 |
| Skill 鑄造 | skill_forge | 2 | claude_sonnet45 | 24 |
| ntfy 審查 | ntfy_review | 1 | claude_opus46 | 25 |
| 未來計畫 | future_plan_optimize | 1 | cursor_cli | 26 |
| KB 洞察 | kb_insight_evaluation | 1 | codex_exec | 27 |
| 工作流 | workflow_forge | 1 | claude_sonnet45 | 28 |
| 洞察簡報 | insight_briefing | 1 | claude_sonnet45 | 29 |

**活躍任務合計**：25 個活躍任務，~40 次/日

---

## 後端路由架構

`config/frequency-limits.yaml` 定義任務→後端對應（**唯一真相來源**）：

| 後端 | 適用任務類型 | 特性 |
|------|------------|------|
| `claude_sonnet45` | 系統任務、佛學研究、Podcast | 完整工具鏈、本地狀態存取 |
| `cursor_cli` | 法華經研究、Podcast 生成、未來計畫 | 非互動模式、完整工具權限 |
| `codex_exec` | AI/技術研究、佛學（淨土） | gpt-5.4、內建 WebSearch（live/cached）|
| `codex_standard` | 創意/QA/GitHub 偵察 | gpt-5.3-codex、強程式碼生成 |
| `claude_opus46` | ntfy 審查 | 高品質推理 |
| `claude_haiku` | 緊急降級 | 低成本、快速 |
| `openrouter_research` | codex 失效 fallback | free tier 自動路由 |

Fallback 鏈：`codex_exec → openrouter_research → claude_sonnet45 → claude_sonnet`

---

## Autonomous Harness 自主運行框架

> 位於 `tools/autonomous_harness.py`，配置於 `config/autonomous-harness.yaml`

```
Autonomous Harness 運作週期：
  ┌─ 監控 ─────────────────────────────────────────────────────┐
  │  scheduler-heartbeat.json   [stale > 20min?]               │
  │  run-fsm.json               [stale > 45min?]               │
  │  failure-stats.json         [失敗 ≥ 2 次?]                 │
  │  api-health.json            [circuit open?]                 │
  │  token-budget-state.json    [critical/emergency?]           │
  │  auto-task-fairness-hint.json [starvation > 3 次?]         │
  └─────────────────────────────────────────────────────────────┘
         ↓
  ┌─ 決策 ─────────────────────────────────────────────────────┐
  │  正常 → profile=normal（4 並行、完整功能）                 │
  │  降級 → profile=degraded（2 並行、禁止重任務）             │
  │  回復 → profile=recovery（1 並行、最小化）                 │
  └─────────────────────────────────────────────────────────────┘
         ↓
  ┌─ 執行 ─────────────────────────────────────────────────────┐
  │  autonomous-harness-plan.json   規劃輸出                   │
  │  autonomous-recovery-queue.json 回復動作佇列               │
  │  autonomous-runtime.json        當前 profile               │
  │  autonomous-runtime-overrides.json 臨時覆蓋（TTL 限時）    │
  └─────────────────────────────────────────────────────────────┘
         ↓
  recovery_worker.py → 執行 dispatch（restart command）→ 注入 override
```

**Runtime Profiles**：
- `normal`：max 4 並行自動任務、允許重任務與研究任務
- `degraded`：max 2 並行、禁止重任務、阻斷 security/chatroom fetch
- `recovery`：max 1 並行、禁止重任務與研究任務、阻斷 gmail/security/chatroom

---

## OODA 閉環架構

| 步驟 | 工具/Agent | 輸出 |
|------|-----------|------|
| **Observe** | run-system-audit-team.ps1 | last-audit.json、系統審查報告 |
| **Orient** | system_insight 自動任務 | system-insight.json、improvement-backlog.json |
| **Decide** | arch_evolution 自動任務 | arch-decision.json |
| **Act** | self_heal 自動任務 | 修復執行、context 更新 |

觸發路徑：每日 00:40 `run-system-audit-team.ps1` → Phase 2 組裝後 **Phase 3 直接跑 arch-evolution**（backlog 可空）→ 成功則 **Phase 4 self-heal**；冷卻與「修正／退步略過冷卻」見 `docs/OPERATIONS.md`。Todoist round-robin 另可觸發 arch_evolution／self-heal（`workflow-state.json`）。

---

## Skills 總覽（共 52 個）

完整路由邏輯見 `docs/skill-routing-guide.md`。

| 類別 | 數量 | Skills（節錄） |
|------|------|--------------|
| 核心資料 | 20 | todoist、pingtung-news、hackernews-ai-digest、atomic-habits、learning-mastery、pingtung-policy-expert、knowledge-query、ntfy-notify、digest-memory、api-cache、scheduler-state、gmail、game-design、system-insight、web-research、kb-curator、github-scout、kb-research-strategist、groq、chatroom-query |
| 系統工具 | 15 | task-manager、skill-scanner、system-audit、todoist-task-creator、arch-evolution、git-smart-commit、chatroom-task-delivery、knowledge-domain-builder、writing-masters、writing-plans、markdown-editor、skill-forge、workflow-forge、insight-briefing、academic-paper-research |
| 品質監控 | 10 | agent-result-validator、behavior-pattern-analyzer、cache-optimizer、context-budget-monitor、execution-journal、pre-flight-check、prompt-lint、quality-tracker、slo-budget-manager、task-fairness-analyzer |
| 生命週期 | 7 | skill-lifecycle-manager、skill-registry-sync、skill-test-scaffolder、hook-registry、game-workflow-design、cursor-cli、todo-scanner |

---

## 測試套件基線（2026-03-11）

| 分類 | 數量 |
|------|------|
| Hooks 測試 | 529 |
| Skills 測試 | 27 |
| Tools 測試 | 300 |
| **總計** | **856** |

覆蓋率計算範圍：`hooks/` + `skills/`（pyproject.toml 設定），tools 測試不計入覆蓋率但仍需通過。

---

<!-- AUTO-GENERATED DIAGRAMS START -->
<!-- AUTO-GENERATED DIAGRAMS END -->
