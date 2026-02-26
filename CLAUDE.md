# Daily Digest Prompt - 專案指引

## 專案概述
每日摘要 Agent：透過 Windows 排程器定時執行 Claude Code，自動彙整待辦事項、在地新聞與禪語，並推播通知。
具備跨次記憶、API 快取降級、排程狀態追蹤等機制（靈感來自 NanoClaw 架構）。

## ⚡ Skill-First 策略（最高原則）

本專案的 Agent 是 **Skill 驅動型**，所有行為都由 Skill 指引。

### 核心規則
1. **先讀 `skills/SKILL_INDEX.md`**：Agent 啟動的第一個動作就是載入 Skill 索引
2. **能用 Skill 就用 Skill**：禁止自行拼湊已有 Skill 覆蓋的邏輯
3. **先讀 SKILL.md 再動手**：每個步驟都必須先讀取對應的 SKILL.md
4. **Skill 鏈式組合**：積極串聯多個 Skill 實現更高價值
5. **Skill 匹配篩選**：Todoist Agent 篩選任務時，主動比對 SKILL_INDEX 觸發關鍵字

### Skill 索引
`skills/SKILL_INDEX.md` 包含：
- 23 個 Skill 速查表（17 核心 + 6 工具，名稱、觸發關鍵字、用途）
- 路由決策樹（任務 → Skill 匹配邏輯）
- 鏈式組合模式（如：新聞 → 政策解讀 → 知識庫匯入 → 通知）
- 能力矩陣（依任務類型、依外部服務查找 Skill）
- 禁止行為清單

### Skill 使用強度
- **必用**（每次必定使用）：todoist、pingtung-news、pingtung-policy-expert、hackernews-ai-digest、atomic-habits、learning-mastery、ntfy-notify、digest-memory、api-cache、scheduler-state
- **積極用**（有機會就用）：knowledge-query、gmail
- **搭配用**：pingtung-policy-expert 必搭 pingtung-news、api-cache 必搭任何 API 呼叫、skill-scanner 搭配 Log 審查或新增 Skill 時、arch-evolution 搭配 system-audit 執行後轉化 ADR

## 🤝 Agent Team & 子 Agent 策略（積極並行）

本專案的核心價值在於**並行加速**。Agent 應積極善用團隊模式與子 Agent，而非串行逐步執行。

### 核心原則
1. **團隊模式優先**：有團隊版腳本（`*-team.ps1`）時，一律優先使用團隊模式，單一模式僅作備用
2. **主動拆分並行**：遇到 2 個以上獨立任務時，主動用 Task 工具（subagent_type）啟動多個子 Agent 並行處理，不要串行等待
3. **保護主 Context Window**：研究、搜尋、程式碼分析等大量輸出的工作，委派給子 Agent（Explore / general-purpose），避免撐爆主 Agent 的上下文
4. **子 Agent 專責分工**：每個子 Agent 只做一件事，職責明確，結果透過檔案（`results/*.json`）或直接回傳交接

### 何時啟動子 Agent
| 情境 | 做法 |
|------|------|
| 多個 API 呼叫互不依賴 | 並行啟動多個子 Agent 同時呼叫（如 Todoist + 新聞 + HN） |
| 研究 / 探索任務 | 用 `subagent_type=Explore` 深度搜尋，主 Agent 繼續其他工作 |
| 程式碼修改 + 測試 | 修改後用子 Agent 跑測試，主 Agent 同步處理下一項任務 |
| 多檔案分析 | 各檔案交給獨立子 Agent 分析，最後匯整結果 |
| 耗時操作（build / lint / 大型搜尋） | 用 `run_in_background=true` 背景執行，不阻塞主流程 |

### 何時用 Agent Team（TeamCreate）
| 情境 | 做法 |
|------|------|
| 複雜多步驟任務（3+ 步驟且有依賴關係） | 建立 Team，用任務清單協調分工 |
| 需要多個 Agent 持續協作（非一次性） | Team 模式提供持久化任務追蹤與成員通訊 |
| 前端 + 後端 / 研究 + 實作 同步進行 | 不同 Agent 各司其職，Team Lead 統籌 |

### 禁止行為
- **禁止串行處理可並行的獨立任務**：有 3 個 API 要呼叫就啟動 3 個子 Agent，不要一個一個等
- **禁止主 Agent 獨攬所有工作**：能委派的就委派，主 Agent 專注在調度與決策
- **禁止忽略 background 模式**：耗時超過 30 秒的操作應考慮背景執行

### 本專案的並行模式參考
- **每日摘要**：Phase 1 五路並行擷取 → Phase 2 單一組裝（`run-agent-team.ps1`）
- **Todoist 任務**：Phase 1 查詢規劃 → Phase 2 N 路並行執行 → Phase 3 組裝通知（`run-todoist-agent-team.ps1`）
- **系統審查**：Phase 1 四路並行評估 → Phase 2 組裝修正報告（`run-system-audit-team.ps1`）
- **互動式開發**：主動用 Task 工具的 `subagent_type` 並行處理研究、測試、分析等獨立工作

## 文件驅動架構設計原則

| 原則 | 說明 |
|------|------|
| **Prompt 是薄層調度器** | Prompt 只含角色宣告、步驟骨架、容錯語義；數據型邏輯全部外部化 |
| **配置用 YAML、模板用 Markdown** | YAML 支援注釋、層級清晰；Markdown 是 LLM 最自然的理解格式 |
| **按需載入** | 子 Agent 模板、自動任務 prompt 只在觸發時才 Read，不預載進 context window |
| **單一定義處** | nul 禁令、Skill-First 規則只在 `templates/shared/preamble.md` 定義一次 |
| **改配置不改 prompt** | 調 TTL → 改 `config/cache-policy.yaml`；調路由 → 改 `config/routing.yaml` |

### 配置文件速查

| 文件 | 用途 | 引用者 |
|------|------|--------|
| `config/pipeline.yaml` | 每日摘要管線步驟 | daily-digest-prompt.md |
| `config/routing.yaml` | Todoist 三層路由規則 | hour-todoist-prompt.md |
| `config/cache-policy.yaml` | 各 API 快取 TTL | daily-digest-prompt.md |
| `config/frequency-limits.yaml` | 自動任務頻率限制 | hour-todoist-prompt.md |
| `config/scoring.yaml` | TaskSense 優先級計分 | hour-todoist-prompt.md |
| `config/notification.yaml` | ntfy 通知配置 | hour-todoist-prompt.md、assemble-digest.md |
| `config/digest-format.md` | 摘要輸出排版模板 | daily-digest-prompt.md、assemble-digest.md |
| `config/dedup-policy.yaml` | 研究去重策略（冷卻天數、飽和閾值） | 所有研究模板 |
| `config/audit-scoring.yaml` | 系統審查 7 維度 38 子項計分規則 | system-audit Skill、run-system-audit-team.ps1 |
| `config/benchmark.yaml` | 系統效能基準線（7 指標 + 參考專案比較） | system-insight Skill、品質閘門 |
| `config/health-scoring.yaml` | 健康評分 6 維度權重（成功率、錯誤率等） | query-logs.ps1 -Mode health-score |
| `config/hook-rules.yaml` | Hooks 規則外部化（Bash/Write guard 規則） | pre_bash_guard.py、pre_write_guard.py |
| `config/timeouts.yaml` | 各 Agent 超時配置（單一/團隊模式 timeout） | run-todoist-agent-team.ps1 |
| `config/topic-rotation.yaml` | 主題輪替演算法（LRU + 同日去重） | 研究任務（AI/佛學研究模板） |
| `templates/shared/preamble.md` | 共用前言（nul 禁令 + Skill-First） | 所有 prompt |

## 架構

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
    frequency-limits.yaml         # 自動任務頻率限制（18 個任務，45 次/日上限）
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

  # Hooks 機器強制層
  .claude/
    settings.json                 # Hooks 設定（PreToolUse/PostToolUse/Stop）
  hooks/
    pre_bash_guard.py             # PreToolUse:Bash - 攔截 nul 重導向、危險操作
    pre_write_guard.py            # PreToolUse:Write/Edit - 攔截 nul 寫入、敏感檔案、SKILL.md 保護
    pre_read_guard.py             # PreToolUse:Read - 攔截敏感路徑讀取（.ssh、.env 等）
    post_tool_logger.py           # PostToolUse:* - 結構化 JSONL 日誌（自動標籤 + 50MB 輪轉）
    on_stop_alert.py              # Stop - Session 結束時健康檢查 + ntfy 自動告警
    hook_utils.py                 # 共用模組（YAML 載入、日誌記錄、Injection Patterns）
    validate_config.py            # YAML Schema 驗證工具（獨立或 check-health 呼叫）
    query_logs.py                 # 結構化日誌查詢工具（CLI）

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
    # Todoist 團隊模式（Phase 1 → Phase 2 → Phase 3，共 20 個）
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
    todoist-auto-gitpush.md       # Phase 2: 自動 Git 推送
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
  state/
    scheduler-state.json          # 執行記錄（最近 200 筆，PowerShell 獨佔寫入）
    todoist-history.json          # Todoist 自動任務歷史

  # Skills（行為指引，自包含）
  skills/
    SKILL_INDEX.md                # Skill 索引與路由引擎（Agent 首先載入）
    todoist/ pingtung-news/ hackernews-ai-digest/ atomic-habits/
    learning-mastery/ pingtung-policy-expert/ knowledge-query/
    ntfy-notify/ digest-memory/ api-cache/ scheduler-state/
    gmail/ game-design/ system-insight/ web-research/
    kb-curator/ github-scout/     # 共 17 核心 Skill
    task-manager/ skill-scanner/
    system-audit/ todoist-task-creator/
    arch-evolution/               # 共 6 工具 Skill（合計 23 個，各含 SKILL.md）

  # 規格與文件
  specs/system-docs/              # 系統文件（SRD/SSD/ops-manual）
  docs/                           # 研究文件與優化計畫
  tests/                          # 測試套件（Todoist API/Gmail 格式測試）

  # 日誌
  logs/
    structured/                   # 結構化 JSONL 日誌（hooks 自動產生）
```

## 執行流程

### 每日摘要（daily-digest-prompt.md）
1. Windows Task Scheduler 觸發 `run-agent.ps1`
2. 腳本自動建立 context/、cache/、state/ 目錄
3. 腳本讀取 `daily-digest-prompt.md` 作為 prompt（~80 行薄層調度器）
4. 透過 `claude -p --allowedTools "Read,Bash,Write"` 執行
5. Agent 載入共用前言（`templates/shared/preamble.md`）+ Skill 索引
6. 讀取 `config/pipeline.yaml` 取得管線定義 + `config/cache-policy.yaml` 取得快取 TTL
7. 依 pipeline.yaml 的 `init` → `steps` → `finalize` 順序執行，每步依對應 SKILL.md 操作
8. 摘要格式依 `config/digest-format.md` 排版 → ntfy 推播 → 寫入記憶
9. 若執行失敗，腳本自動重試一次（間隔 2 分鐘）

### 每日摘要 - 團隊並行模式（run-agent-team.ps1）
1. Windows Task Scheduler 觸發 `run-agent-team.ps1`
2. **Phase 1**：用 `Start-Job` 同時啟動 5 個 `claude -p`（Todoist + 新聞 + HN + Gmail + 安全審查）
3. 各 Agent 獨立執行快取檢查 + API 呼叫，結果寫入 `results/*.json`
4. 等待全部完成（timeout 300s），收集各 Agent 狀態
5. **Phase 2**：啟動組裝 Agent 讀取 `results/*.json`（timeout 420s）
6. 組裝 Agent 加上政策解讀、習慣提示、學習技巧、知識庫查詢、禪語
7. 整理完整摘要 → ntfy 推播 → 更新記憶/狀態 → 清理 results/
8. Phase 2 失敗可自動重試一次（間隔 60 秒）
9. 預期耗時約 1 分鐘（單一模式約 3-4 分鐘）

### Todoist 任務規劃 - 單一模式（run-todoist-agent.ps1）
1. Windows Task Scheduler 觸發 `run-todoist-agent.ps1`（timeout 2100s）
2. Agent 載入共用前言 + Skill 索引（~140 行薄層調度器）
3. 讀取 `config/routing.yaml` 取得三層路由規則 + `config/frequency-limits.yaml` 取得頻率限制
4. 查詢 Todoist → 依 routing.yaml 路由 → 按 `config/scoring.yaml` 計分排序
5. 子 Agent 模板從 `templates/sub-agent/` 按需載入（不預載）
6. 無可處理項目或全部完成時，自動任務 prompt 從 `templates/auto-tasks/` 按需載入
7. 品質驗證依 `templates/shared/quality-gate.md` + `templates/shared/done-cert.md`
8. 通知格式依 `config/notification.yaml`
9. **自動任務頻率限制**（定義在 config/frequency-limits.yaml）：18 個任務，合計 45 次/日上限，round-robin 輪轉
10. **研究任務 KB 去重**（定義在 templates/sub-agent/research-task.md）：研究前先查詢知識庫避免重複

### Todoist 任務規劃 - 團隊並行模式（run-todoist-agent-team.ps1，推薦）
1. Windows Task Scheduler 觸發 `run-todoist-agent-team.ps1`
2. **Phase 1**：1 個查詢 Agent（Todoist 查詢 + 過濾 + 路由 + 規劃，timeout 300s）
3. 輸出計畫類型：`tasks`（有待辦）/ `auto`（觸發自動任務）/ `idle`（跳過）
4. **Phase 2**：N 個並行執行 Agent（依計畫分配，動態 timeout 按任務類型計算）
   - research: 600s、code: 900s、skill/general: 300s、auto: 600s、gitpush: 360s
5. **Phase 3**：1 個組裝 Agent（關閉任務 + 更新狀態 + 推播通知，timeout 180s）
6. Phase 3 失敗可自動重試一次（間隔 60 秒）

## 技術棧
- **執行環境**: PowerShell 7 (pwsh)
- **排程**: Windows Task Scheduler
- **Agent**: Claude Code CLI（`claude -p`）
- **通知**: ntfy.sh（topic: `wangsc2025`）

## Hooks 機器強制層（Harness Enforcement）

從「Agent 自律」升級到「機器強制」。透過 Claude Code Hooks 在 runtime 攔截工具呼叫，違規操作在執行前就被阻斷。

### 設定檔
`.claude/settings.json`（專案級，commit 到 repo，所有開發者共享）

### Hook 清單

| Hook | 類型 | Matcher | 用途 |
|------|------|---------|------|
| `pre_bash_guard.py` | PreToolUse | Bash | 攔截 nul 重導向、scheduler-state 寫入、危險刪除、force push、敏感環境變數讀取、機密外洩 |
| `pre_write_guard.py` | PreToolUse | Write, Edit | 攔截 nul 檔案建立、scheduler-state 寫入、敏感檔案寫入、路徑遍歷攻擊、SKILL.md 修改保護 |
| `pre_read_guard.py` | PreToolUse | Read | 攔截敏感系統路徑（.ssh/.gnupg）、敏感檔案（.env/credentials）、Windows 憑據路徑 |
| `post_tool_logger.py` | PostToolUse | *（所有工具） | 結構化 JSONL 日誌，自動標籤分類，50MB 緊急輪轉 |
| `validate_config.py` | 工具（非 Hook） | — | YAML 配置 Schema 驗證（可由 check-health.ps1 呼叫或獨立執行） |
| `on_stop_alert.py` | Stop | — | Session 結束時分析日誌，異常時自動 ntfy 告警（使用安全暫存檔） |

### 強制規則對照表（Prompt 自律 → Hook 強制）

| 規則 | 之前（Prompt 宣告） | 之後（Hook 攔截） |
|------|-------------------|------------------|
| 禁止 `> nul` 重導向 | Prompt 寫「禁止」，Agent 自律 | `pre_bash_guard.py` 在執行前攔截，回傳 block reason |
| 禁止寫入 `nul` 檔案 | Prompt 寫「禁止」，Agent 自律 | `pre_write_guard.py` 攔截 file_path 為 nul 的 Write |
| scheduler-state.json 只讀 | Prompt 寫「Agent 只讀」 | Hook 攔截所有對此檔案的寫入/編輯/重導向 |
| 敏感檔案保護 | .gitignore 排除 | Hook 攔截 .env/credentials/token/secrets/.htpasswd 的寫入 |
| force push 保護 | 開發者口頭約定 | Hook 攔截 `git push --force` 到 main/master |
| 路徑遍歷防護 | 無 | `pre_write_guard.py` 攔截 `../` 逃逸專案目錄的路徑 |
| 敏感環境變數保護 | 無 | `pre_bash_guard.py` 攔截 echo/printenv/env 讀取 TOKEN/SECRET/KEY/PASSWORD |
| 機密外洩防護 | 無 | `pre_bash_guard.py` 攔截 curl/wget 傳送敏感變數 |
| SKILL.md 修改保護 | 無 | `pre_write_guard.py` 攔截所有對 SKILL.md 的 Write/Edit 操作 |
| 敏感路徑讀取保護 | 無 | `pre_read_guard.py` 攔截 .ssh/.gnupg/.env/credentials 等路徑的讀取 |
| Prompt Injection 防護 | 無 | 三處 prompt 模板加入消毒指引（todoist-query + research-task + fetch-hackernews） |

### 結構化日誌系統

`post_tool_logger.py` 對每個工具呼叫自動產生 JSONL 記錄，含：

**自動標籤分類**：
| 標籤 | 觸發條件 | 用途 |
|------|---------|------|
| `api-call` | Bash 指令含 `curl` | API 呼叫追蹤 |
| `todoist` / `pingtung-news` / `hackernews` / `knowledge` / `gmail` | URL 模式匹配 | API 來源識別 |
| `cache-read` / `cache-write` | 讀寫 `cache/*.json` | 快取操作追蹤 |
| `skill-read` / `skill-index` | 讀取 `SKILL.md` / `SKILL_INDEX.md` | Skill 使用追蹤 |
| `memory-read` / `memory-write` | 讀寫 `digest-memory.json` | 記憶操作追蹤 |
| `sub-agent` | Bash 指令含 `claude -p` | 子 Agent 追蹤 |
| `blocked` | PreToolUse hook 攔截 | 違規操作記錄 |
| `error` | 工具輸出含錯誤關鍵字 | 錯誤追蹤 |

**JSONL 格式**：
```json
{"ts":"2026-02-14T08:01:30+08:00","sid":"abc123","tool":"Bash","event":"post","summary":"curl -s https://api.todoist.com/...","output_len":1234,"has_error":false,"tags":["api-call","todoist"]}
```

### 自動告警機制

`on_stop_alert.py` 在 Agent session 結束時自動分析：

| 檢查項 | 條件 | 告警等級 |
|--------|------|---------|
| 違規攔截 | blocked > 0 | warning（≥3 則 critical） |
| 工具錯誤 | errors ≥ 1 | warning（≥5 則 critical） |
| 全部正常 | 無上述問題 | 不告警（靜默記錄 session-summary） |

告警透過 ntfy 推送到 `wangsc2025`，含：呼叫統計、攔截詳情、錯誤摘要。

### 查詢結構化日誌

```bash
# 今日摘要
python hooks/query_logs.py

# 近 7 天
python hooks/query_logs.py --days 7

# 僅攔截事件
python hooks/query_logs.py --blocked

# 僅錯誤
python hooks/query_logs.py --errors

# 快取使用審計
python hooks/query_logs.py --cache-audit

# Session 摘要
python hooks/query_logs.py --sessions --days 7

# JSON 輸出（供程式處理）
python hooks/query_logs.py --format json
```

### 前置需求
- Python 3.8+（hooks 用 Python 解析 JSON，跨平台相容）
- Windows 環境使用 `python`（非 `python3`，因 Windows Store 的 `python3` 空殼會靜默失敗）

## NanoClaw 啟發的優化機制

### 1. 跨次記憶持久化
- 每次執行讀取/更新 `context/digest-memory.json`
- 追蹤：連續執行天數、待辦完成率、習慣/學習連續天數
- 摘要開頭顯示「連續報到第 N 天」

### 2. HTTP 回應快取
- API 成功回應存入 `cache/*.json`（含時間戳與 TTL）
- 每次 API 呼叫前先檢查快取有效性
- API 故障時自動降級使用過期快取（24 小時內）

### 3. 排程狀態管理
- 各 `run-*.ps1` 腳本記錄每次執行狀態到 `state/scheduler-state.json`
- 失敗時自動重試一次（間隔依腳本不同：60s～120s）
- `check-health.ps1` 提供近 7 天健康度報告

### 4. 自動任務輪轉（round-robin）
- 18 個自動任務定義在 `config/frequency-limits.yaml`，合計 45 次/日上限
- 8 大群組：佛學研究(12)、AI/技術研究(17)、系統優化(2)、系統維護(5)、遊戲創意(2)、專案品質(2)、系統自省(4)、GitHub靈感(1)
- 維護 `next_execution_order` 指針（跨日保留），確保所有任務公平輪轉
- 觸發條件：無可處理 Todoist 項目 **或** 今日任務全部完成

## 架構決策索引（ADR 速查）

> 完整 ADR 詳情由 `arch-evolution` Skill 維護於 `context/adr-registry.json`。
> 本節為人類與 Agent 的快速查閱表，理解「為什麼這樣設計」。

| ADR | 決策標題 | 根本原因 | 狀態 |
|-----|---------|---------|------|
| ADR-001 | **Skill-First 策略**：必用先查 SKILL_INDEX | 禁止自行拼湊已有 Skill 邏輯，確保行為可審計、可替換 | ✅ Accepted |
| ADR-002 | **文件驅動架構**：Prompt 薄層 + YAML 外部配置 | 改配置不改 Prompt，降低 LLM 迭代成本；Markdown 是 LLM 最自然的理解格式 | ✅ Accepted |
| ADR-003 | **PowerShell 7 (pwsh)** 作為執行環境 | PS 5.1 的 Start-Job 缺少 `-WorkingDirectory`，`$OutputEncoding` 預設 ASCII，導致 UTF-8 亂碼 | ✅ Accepted |
| ADR-004 | **Team 並行模式優先**於單一模式 | 串行執行約 3-4 分鐘；並行模式約 1 分鐘，5 路 Phase 1 同時擷取資料 | ✅ Accepted |
| ADR-005 | **Hook 機器強制層**取代 Prompt 自律 | Agent 自律可被上下文壓縮或指令覆蓋；Hook 在 runtime 攔截，無法繞過 | ✅ Accepted |
| ADR-006 | **scheduler-state.json 由 PowerShell 獨佔寫入** | 避免 PS 腳本與 Agent 並發寫入導致競態條件與資料覆蓋 | ✅ Accepted |
| ADR-007 | **研究去重三層防護**（registry + KB + 冷卻） | KB 中 46/100 筆 AI 相關，4 組完全重複，各 auto-task 獨立去重互不知曉 | ✅ Accepted |
| ADR-008 | **OODA 閉環架構**（system-insight→audit→arch-evolution→self-heal） | 三個自省 auto-task 各自獨立，缺統一「Decide」層整合感測與診斷結果 | ✅ Accepted |

> **如何新增 ADR**：執行 `arch-evolution 模組 A`，系統審查後自動從 `context/improvement-backlog.json` 轉化建議為持久化 ADR。

---

## Skills（專案內自包含，共 23 個）

完整清單見 `skills/SKILL_INDEX.md`。Skills 來源：`D:\Source\skills\`，複製到專案內確保自包含。

## ntfy 通知注意事項
- Windows 環境必須用 JSON 檔案方式發送，不可用 inline JSON 字串（會亂碼）
- 必須加 `charset=utf-8` header：`curl -H "Content-Type: application/json; charset=utf-8" -d @file.json https://ntfy.sh`
- 用 Write 工具建立 JSON 檔確保 UTF-8 編碼，不可用 Bash echo 建檔
- 發送後刪除暫存 JSON 檔

## 慣例
- 全程使用正體中文
- 日誌檔名格式：`yyyyMMdd_HHmmss.log`
- 日誌保留 7 天，自動清理
- prompt 內容修改後無需重新部署，下次排程自動生效
- 所有 .ps1 腳本使用 PowerShell 7 (`pwsh`) 執行，UTF-8 為預設編碼
- `.ps1` 檔案建議使用 UTF-8 with BOM 編碼（向下相容 PowerShell 5.1）

### 嚴禁產生 nul 檔案（最高優先級 — Hook 機器強制）
以下行為全部禁止，違反將產生名為 `nul` 的垃圾檔案：
- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`（這是 cmd 語法，在 bash 中會建立實體檔案）
- 禁止使用 Write 工具寫入任何名為 `nul` 的檔案路徑
- 禁止在任何指令中將 `nul` 作為輸出目標
- 要抑制輸出請改用：`| Out-Null`（PowerShell）或 `> /dev/null`（bash）或直接不重導向
- 要丟棄 stderr 請用 `2>/dev/null`（bash）或 `2>$null`（PowerShell）

> **機器強制**：此規則已由 `hooks/pre_bash_guard.py` 和 `hooks/pre_write_guard.py` 在 runtime 攔截。
> Agent 即使違反，工具呼叫也會被 block，並記錄到結構化日誌。

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

### 每日系統審查 - 團隊並行模式（run-system-audit-team.ps1，推薦）

每日 00:40 自動執行系統審查，使用 `system-audit` Skill 評估 7 個維度、38 個子項：

1. Windows Task Scheduler 觸發 `run-system-audit-team.ps1`
2. **Phase 1**：用 `Start-Job` 同時啟動 4 個 `claude -p` 並行審查
   - Agent 1: 評估維度 1（資訊安全）+ 維度 5（技術棧），輸出 `results/audit-dim1-5.json`
   - Agent 2: 評估維度 2（系統架構）+ 維度 6（系統文件），輸出 `results/audit-dim2-6.json`
   - Agent 3: 評估維度 3（系統品質）+ 維度 7（系統完成度），輸出 `results/audit-dim3-7.json`
   - Agent 4: 評估維度 4（系統工作流），輸出 `results/audit-dim4.json`
3. 等待全部完成（timeout 600s），收集各 Agent 狀態
4. **Phase 2**：啟動組裝 Agent 讀取 Phase 1 的 4 個 JSON（timeout 1200s）
5. 組裝 Agent 計算加權總分 → 識別問題 → 自動修正（最多 5 項）→ 生成報告 → 寫入 RAG → 更新狀態
6. Phase 2 失敗可自動重試一次（間隔 60 秒）
7. 預期耗時約 15-20 分鐘（單一模式需 25-30 分鐘）

**輸出**：
- 審查報告：`docs/系統審查報告_YYYYMMDD_HHMM.md`
- 狀態檔案：`state/last-audit.json`（含總分、等級、7 維度分數）
- 知識庫：自動匯入 RAG (localhost:3000)，含 metadata
- Phase 1 日誌：`logs/audit-phase1-YYYYMMDD_HHMMSS.log`
- Phase 2 日誌：`logs/audit-phase2-YYYYMMDD_HHMMSS.log`
- 中間結果：`results/audit-dim*.json`（完成後自動清理）

**手動觸發**：
```powershell
# 團隊並行模式（推薦）
pwsh -ExecutionPolicy Bypass -File run-system-audit-team.ps1

# 單一模式（備用）
pwsh -ExecutionPolicy Bypass -File run-system-audit.ps1
```

## 常用操作
```powershell
# 手動執行每日系統審查（團隊並行模式，推薦）
pwsh -ExecutionPolicy Bypass -File run-system-audit-team.ps1

# 手動執行每日系統審查（單一模式，備用）
pwsh -ExecutionPolicy Bypass -File run-system-audit.ps1

# 手動執行每日摘要（團隊並行模式，推薦）
pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1

# 手動執行每日摘要（單一模式，備用）
pwsh -ExecutionPolicy Bypass -File run-agent.ps1

# 手動執行 Todoist 任務規劃（團隊並行模式，推薦）
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1

# 手動執行 Todoist 任務規劃（單一模式，備用）
pwsh -ExecutionPolicy Bypass -File run-todoist-agent.ps1

# 從 HEARTBEAT.md 批次建立排程（需管理員權限）
.\setup-scheduler.ps1 -FromHeartbeat

# 設定排程（傳統方式）
.\setup-scheduler.ps1 -Time "08:00" -Script "run-agent-team.ps1"

# 查看排程狀態
schtasks /query /tn ClaudeDailyDigest /v

# 查看系統健康度（快速一覽）
pwsh -ExecutionPolicy Bypass -File check-health.ps1

# 查詢執行成果（靈活查詢）
.\query-logs.ps1                              # 近 7 天摘要
.\query-logs.ps1 -Days 3 -Agent todoist       # 近 3 天 Todoist
.\query-logs.ps1 -Mode detail -Date 2026-02-12 # 特定日期詳情
.\query-logs.ps1 -Mode errors                  # 錯誤彙總
.\query-logs.ps1 -Mode todoist                 # 自動任務歷史
.\query-logs.ps1 -Mode trend -Days 14          # 趨勢分析
.\query-logs.ps1 -Mode summary -Format json    # JSON 輸出

# 掃描 Skills 安全性
.\scan-skills.ps1
.\scan-skills.ps1 -Format markdown -UseBehavioral

# 查看最新日誌
Get-Content (Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1)

# Hook 結構化日誌查詢
python hooks/query_logs.py                     # 今日摘要
python hooks/query_logs.py --days 7             # 近 7 天
python hooks/query_logs.py --blocked            # 攔截事件
python hooks/query_logs.py --errors             # 錯誤事件
python hooks/query_logs.py --cache-audit        # 快取使用審計
python hooks/query_logs.py --sessions --days 7  # Session 健康摘要
```
