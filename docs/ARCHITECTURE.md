# Daily Digest Prompt - 架構文件

> 本文件由 `docs/ARCHITECTURE.md` 維護，對應 CLAUDE.md 的「架構」章節引用。
> 架構圖可由 `generate-arch-diagrams.ps1` 自動更新。

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
    frequency-limits.yaml         # 自動任務頻率限制（19 個任務，47 次/日上限）
    benchmark.yaml                # 系統效能基準線（目標門檻、參考專案比較）
    scoring.yaml                  # TaskSense 優先級計分規則
    notification.yaml             # ntfy 通知配置（topic、標籤、模板）
    dedup-policy.yaml             # 研究去重策略（冷卻天數、飽和閾值、跨任務去重）
    digest-format.md              # 摘要輸出排版模板

  # 模板層（按需載入，不預載進 context window）
  templates/
    shared/
      preamble.md                 # 共用前言（nul 禁令 + Skill-First，一處定義）
      done-cert.md                # DONE_CERT 格式定義
      quality-gate.md             # 驗證閘門規則（迭代精修）
    sub-agent/                    # 子 Agent 任務模板（Todoist 路由後按需載入）
      skill-task.md               # 模板 A：有 Skill 匹配的任務
      research-task.md            # 模板 B：知識庫研究任務（含 KB 去重）
      code-task.md                # 模板 D：@code 任務（Plan-Then-Execute）
      game-task.md                # 模板 E：遊戲設計任務（品質分析→修改）
      general-task.md             # 模板 C：無 Skill 匹配的一般任務
      refinement.md               # 品質閘門精修 prompt
    auto-tasks/                   # 自動任務 prompt（無可處理項目或全部完成時按需載入）
      # 佛學研究（12 次/日，4 個任務用 2 個模板）
      shurangama-research.md      # 楞嚴經研究（5 次/日，專用模板）
      buddhist-research.md        # 通用佛學模板（教觀綱宗 3 次 + 法華經 2 次 + 淨土宗 2 次，共用參數化模板）
      # AI/技術研究（17 次/日）
      tech-research.md            # 每日任務技術研究（分析已完成任務所需技術）
      ai-deep-research.md         # AI 深度研究計畫（4 階段）
      unsloth-research.md         # Unsloth LLM fine-tuning 研究
      ai-github-research.md       # AI GitHub 熱門專案研究
      ai-smart-city-research.md   # AI 智慧城市研究
      ai-sysdev-research.md       # AI 系統開發研究
      # 系統優化（2 次/日）
      skill-audit.md              # Skill 品質審查 + 優化
      # 系統維護（5 次/日）
      log-audit.md                # 系統 Log 審查（8 步驟含修正）
      git-push.md                 # GitHub 推送流程
      # 遊戲創意（2 次/日）
      creative-game-optimize.md   # 創意遊戲優化（D:\Source\game 目錄）
      # 專案品質（2 次/日）
      qa-system-optimize.md       # QA 系統優化
      # 系統自省（4 次/日）
      system-insight.md           # 系統洞察分析
      self-heal.md                # 自愈迴圈
      # GitHub 靈感（1 次/日）
      github-scout.md             # GitHub 靈感蒐集（週三/週日）

  **Note**: 以上 16 個唯一模板對應 18 個自動任務（buddhist-research.md 被 3 個任務共用）。
  團隊模式 prompts 命名轉換規則：`templates/auto-tasks/<name>.md` → `prompts/team/todoist-auto-<name>.md`。
  部分簡化：去掉後綴（-research/-optimize）、合併連字號（log-audit → logaudit、git-push → gitpush）。

  # 執行腳本
  run-agent.ps1                   # 每日摘要執行腳本（單一模式，含重試）
  run-agent-team.ps1              # 每日摘要執行腳本（團隊並行模式，推薦）
  run-todoist-agent.ps1           # Todoist 任務規劃執行腳本（單一模式）
  run-todoist-agent-team.ps1      # Todoist 任務規劃執行腳本（3 階段並行，推薦）
  run-gmail-agent.ps1             # Gmail Agent 執行腳本
  run-system-audit.ps1            # 每日系統審查執行腳本（單一模式，備用）
  run-system-audit-team.ps1       # 每日系統審查執行腳本（團隊並行模式，推薦）
  setup-scheduler.ps1             # 排程設定工具（支援 HEARTBEAT.md 批次建立）
  check-health.ps1                # 健康檢查報告工具（快速一覽）
  scan-skills.ps1                 # 技能安全掃描工具（Cisco AI Defense）
  query-logs.ps1                  # 執行成果查詢工具（5 種模式）
  check-token.ps1                 # Todoist Token 驗證工具
  cleanup-tasks.ps1               # Todoist 任務清理工具
  fix-todoist-task.ps1            # Todoist 任務修正工具
  temp_query.ps1                  # 臨時查詢腳本（開發用）
  analyze-config.ps1              # 配置膨脹度量工具（寫入 state/config-metrics.json）
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
    on_stop_alert.py              # Stop - Session 結束時健康檢查 + ntfy 自動告警
    hook_utils.py                 # 共用模組（YAML 載入、日誌記錄、Injection Patterns）
    validate_config.py            # YAML Schema 驗證工具（獨立或 check-health 呼叫）
    query_logs.py                 # 結構化日誌查詢工具（CLI）
    cjk_guard.py                  # PostToolUse:Write/Edit - CJK 字元守衛

  # 團隊模式 Agent prompts
  prompts/team/
    # 每日摘要團隊模式（Phase 1 → Phase 2，共 6 個）
    fetch-todoist.md              # Phase 1: Todoist 資料擷取
    fetch-news.md                 # Phase 1: 屏東新聞資料擷取
    fetch-hackernews.md           # Phase 1: HN AI 新聞資料擷取
    fetch-gmail.md                # Phase 1: Gmail 郵件擷取
    fetch-security.md             # Phase 1: Cisco AI Defense 安全審查
    assemble-digest.md            # Phase 2: 摘要組裝 + 通知 + 狀態
    # 系統審查團隊模式（Phase 1 → Phase 2，共 5 個）
    fetch-audit-dim1-5.md         # Phase 1: 維度 1（資訊安全）+ 維度 5（技術棧）
    fetch-audit-dim2-6.md         # Phase 1: 維度 2（系統架構）+ 維度 6（系統文件）
    fetch-audit-dim3-7.md         # Phase 1: 維度 3（系統品質）+ 維度 7（系統完成度）
    fetch-audit-dim4.md           # Phase 1: 維度 4（系統工作流）
    assemble-audit.md             # Phase 2: 組裝結果 + 自動修正 + 報告 + RAG
    # Todoist 團隊模式（Phase 1 → Phase 2 → Phase 3，共 21 個）
    todoist-query.md              # Phase 1: Todoist 查詢 + 路由 + 計分 + 規劃
    todoist-assemble.md           # Phase 3: 組裝結果 + 關閉任務 + 通知
    todoist-auto-shurangama.md    # Phase 2: 自動楞嚴經研究
    todoist-auto-jiaoguangzong.md # Phase 2: 自動教觀綱宗研究
    todoist-auto-fahua.md         # Phase 2: 自動法華經研究
    todoist-auto-jingtu.md        # Phase 2: 自動淨土宗研究
    todoist-auto-tech-research.md # Phase 2: 自動技術研究
    todoist-auto-ai-deep-research.md # Phase 2: 自動 AI 深度研究
    todoist-auto-unsloth.md       # Phase 2: 自動 Unsloth 研究
    todoist-auto-ai-github.md     # Phase 2: 自動 AI GitHub 研究
    todoist-auto-ai-smart-city.md # Phase 2: 自動 AI 智慧城市研究
    todoist-auto-ai-sysdev.md     # Phase 2: 自動 AI 系統開發研究
    todoist-auto-skill-audit.md   # Phase 2: 自動 Skill 審查
    todoist-auto-logaudit.md      # Phase 2: 自動 Log 審查
    todoist-auto-git_push.md      # Phase 2: 自動 Git 推送
    todoist-auto-creative-game.md # Phase 2: 自動創意遊戲優化
    todoist-auto-qa-optimize.md   # Phase 2: 自動 QA 優化
    todoist-auto-system-insight.md # Phase 2: 自動系統洞察
    todoist-auto-self-heal.md     # Phase 2: 自動自愈迴圈
    todoist-auto-github-scout.md  # Phase 2: 自動 GitHub 靈感蒐集
  results/                        # 團隊模式中間結果（完成後清理）

  # 持久化資料
  context/
    digest-memory.json            # 摘要記憶（連續天數、待辦統計等）
    auto-tasks-today.json         # 自動任務頻率追蹤（每日歸零）
    research-registry.json        # 研究主題註冊表（跨任務去重，7 天滾動）
  cache/                          # API 回應快取（TTL 定義在 config/cache-policy.yaml）
    todoist.json / pingtung-news.json / hackernews.json / gmail.json
    status.json                   # PS 預計算快取狀態（Phase 0 生成，LLM 直接讀 valid 欄位）
  state/
    scheduler-state.json          # 執行記錄（最近 200 筆，PowerShell 獨佔寫入）
    todoist-history.json          # Todoist 自動任務歷史
    config-metrics.json           # 配置膨脹度量歷史（analyze-config.ps1 產生，30 筆滾動）

  # Skills（行為指引，自包含）
  skills/
    SKILL_INDEX.md                # Skill 索引與路由引擎（Agent 首先載入）
    todoist/ pingtung-news/ hackernews-ai-digest/ atomic-habits/
    learning-mastery/ pingtung-policy-expert/ knowledge-query/
    ntfy-notify/ digest-memory/ api-cache/ scheduler-state/
    gmail/ game-design/ system-insight/ web-research/
    kb-curator/ github-scout/
    kb-research-strategist/ groq/  # 共 19 核心 Skill
    task-manager/ skill-scanner/
    system-audit/ todoist-task-creator/
    arch-evolution/ git-smart-commit/
    chatroom-query/
    knowledge-domain-builder/
    writing-masters/ writing-plans/
    markdown-editor/              # 共 11 工具 Skill（合計 30 個，各含 SKILL.md）

  # 規格與文件
  specs/system-docs/              # 系統文件（SRD/SSD/ops-manual）
  docs/                           # 研究文件與優化計畫
    ARCHITECTURE.md               # 本文件：目錄結構 + 排程表 + 架構圖
    OPERATIONS.md                 # 運維手冊：執行流程 + Hooks 詳情 + 日誌指令
    skill-routing-guide.md        # Skill 路由指南：決策樹 + 鏈式組合 + 能力矩陣
  tests/                          # 測試套件（Todoist API/Gmail 格式測試）

  # 日誌
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
| todoist-team | 每小時半點 02-23 | run-todoist-agent-team.ps1 | 3 階段並行 |

Timeout 設定集中在 `config/timeouts.yaml`。

---

## Skills 總覽（共 30 個）

完整路由邏輯見 `docs/skill-routing-guide.md`。

| 類別 | Skills |
|------|--------|
| 核心資料（19 個） | todoist、pingtung-news、hackernews-ai-digest、atomic-habits、learning-mastery、pingtung-policy-expert、knowledge-query、ntfy-notify、digest-memory、api-cache、scheduler-state、gmail、game-design、system-insight、web-research、kb-curator、github-scout、kb-research-strategist、groq |
| 工具（11 個） | task-manager、skill-scanner、system-audit、todoist-task-creator、arch-evolution、git-smart-commit、chatroom-query、knowledge-domain-builder、writing-masters、writing-plans、markdown-editor |

---

<!-- AUTO-GENERATED DIAGRAMS START -->
<!-- AUTO-GENERATED DIAGRAMS END -->
