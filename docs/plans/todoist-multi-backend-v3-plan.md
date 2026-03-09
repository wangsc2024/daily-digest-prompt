# 計畫：Todoist 多後端模型分派優化 v3（Codex 研究優先版）
## Context
**問題**：Claude Code token 日耗量高達 16.3M（2026-03-07 峰值），遠超 1.5M 警告線 10 倍以上，且 2026-03-08 08:30 已達 2.85M（當日上午）。

**根本原因分析**（三層）：
1. Phase 2 任務全用 claude-sonnet，研究任務 token 消耗最高（WebSearch + 長輸出）
2. Phase 1/3 每次 team run 各消耗 1 個 claude 回合，46 runs/日 × 2 = 92 回合未受控制
3. frequency-limits.yaml 雖有 model 欄位，但從未真正路由至非 Claude 後端
4. bot/process_messages.ps1 Worker 也呼叫 claude -p，額外消耗未納入統計

**解決方案層級**：
- 層 1（Quick Win）：Phase 2 system 任務降至 claude-haiku（節省 ~30%）
- 層 2（核心）：Phase 2 研究任務 → Codex CLI（零 Claude token，內建 WebSearch）
- 層 3（維護）：Phase 2 無 WebSearch 任務 → OpenRouter（零 Claude token）
- 層 4（進階）：Phase 1/3 加 token budget 上限 + critical 時降至 haiku
- 層 5（BOT）：bot/process_messages.ps1 研究型任務路由至 Codex（選用）

**關鍵技術確認**：
Codex CLI（openai/codex）非互動模式：codex exec --full-auto task → stdout
- 內建 WebSearch（預設 cached，--search 啟用即時；官方 CLI 不支援 --enable-live-websearch）
- 支援 shell、檔案讀寫、MCP、code interpreter
- 模型：GPT-5-Codex（針對 agentic 優化）
- 環境變數：CODEX_API_KEY
- 完全不消耗 Claude token

**使用者約束**：
- 不使用中國模型（DeepSeek、Qwen）
- 系統優化任務（self_heal、system_insight、log_audit）一律用 Claude
- Codex CLI 列為研究型任務優先選項
- 實施前備份必要檔案

---
## 任務分類與後端指派
**任務分三類**：
A. 系統優化類（用 Claude）：self_heal、system_insight、log_audit
B. 研究類（用 Codex 優先）：shurangama、jingtu、jiaoguangzong、fahua、ai_sysdev、ai_workflow_github、ai_github_research、ai_deep_research、tech_research
C. 維護類（用 OpenRouter）：git_push、chatroom_optimize、skill_audit

---
## 模型特點與限制分析
| 後端 | 模型 | 優點 | 限制 | 適用 |
|------|------|------|------|------|
| claude-sonnet-4-6 | 預設 | 最高品質、工具完整 | 高 token 成本 | Phase 1/3，系統分析 |
| claude-haiku-4-5 | 降級 | 快速低成本 | 複雜推理弱 | 系統優化任務、fallback |
| codex_exec | GPT-5-Codex | 零 Claude token、內建 WebSearch（cached+live）、強編碼推理 | 需 CODEX_API_KEY、非 Claude 工具鏈 | 研究類任務（最優先）|
| openrouter_research | google/gemini-flash-1.5 | 零 Claude token、1M context、快速 | 品質略遜 Claude | 研究類 Codex fallback |
| openrouter_research | mistralai/mixtral-8x22b-instruct | 零 Claude token、強推理、MOE 架構 | 較慢 | 研究類深度分析 |
| openrouter_standard | meta-llama/llama-3.3-70b | 零 Claude token、快速、工具支援佳 | 知識截止較早 | 維護類任務 |

---
## 後端決策矩陣（Per-Task）
| 任務 key | 類別 | 目標後端 | 指定模型 | 理由 |
|----------|------|---------|---------|------|
| self_heal | A-系統 | claude_haiku | claude-haiku-4-5 | 用戶規定：系統優化用 Claude |
| system_insight | A-系統 | claude_haiku | claude-haiku-4-5 | 用戶規定：系統優化用 Claude |
| log_audit | A-系統 | claude_haiku | claude-haiku-4-5 | 用戶規定：系統優化用 Claude |
| shurangama | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 佛學研究，Codex 內建 WebSearch |
| jingtu | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 佛學研究，Codex 內建 WebSearch |
| jiaoguangzong | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 佛學研究，Codex 內建 WebSearch |
| fahua | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 佛學研究，Codex 內建 WebSearch |
| ai_sysdev | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | AI 系統研究，即時搜尋 |
| ai_workflow_github | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | GitHub AI 研究 |
| ai_github_research | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 架構深度分析 + WebSearch |
| ai_deep_research | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 4 階段深度研究 |
| tech_research | B-研究 | codex_exec | GPT-5-Codex（WebSearch） | 跨來源技術研究 |
| git_push | C-維護 | openrouter_standard | meta-llama/llama-3.3-70b | 固定 Bash 序列，無 WebSearch |
| chatroom_optimize | C-維護 | openrouter_standard | meta-llama/llama-3.3-70b | 評估計算，無 WebSearch |
| skill_audit | C-維護 | openrouter_standard | meta-llama/llama-3.3-70b | Skill 掃描，Read 為主 |

預估 Claude token 節省：
- 研究類（9任務）→ Codex：省 100% Claude token
- 維護類（3任務）→ OpenRouter：省 100% Claude token
- 系統類（3任務）→ haiku：省 ~70% Claude token vs sonnet
- Phase 1/3 加 token budget：省 ~40% 協調層消耗
- 整體預估：~90-95% Claude token 節省
---
## 前置需求（實施前必備）

### Codex CLI 安裝
安裝指令（PowerShell 7，需 Node.js 18+）：
    npm install -g @openai/codex

Windows 已知問題：npm 安裝後可能缺少原生模組，解法：
    $v = (npm show @openai/codex version)
    npm install -g "@openai/codex@$v" "@openai/codex-win32-x64@npm:@openai/codex@$v-win32-x64"

安裝驗證：
    Get-Command codex -ErrorAction SilentlyContinue
    codex --version
    codex exec --full-auto "echo test"

Get-TaskBackend 偵測邏輯（已內建自動 fallback）：
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        # 自動降級至 openrouter_research，記錄 WARN
    }

### OPENROUTER_API_KEY 設定
取得 API Key：
1. 前往 openrouter.ai/keys -> 登入後建立 API Key
2. 複製以 sk-or-v1- 開頭的金鑰

設定到 .env（專案根目錄）：
    CODEX_API_KEY=sk-...               # OpenAI Platform API Key
    OPENROUTER_API_KEY=sk-or-v1-...   # OpenRouter API Key

驗證設定（PowerShell）：
    Get-Content .env | Where-Object { $_ -match 'OPENROUTER_API_KEY' }
    Invoke-RestMethod -Uri https://openrouter.ai/api/v1/models `
        -Headers @{Authorization = "Bearer $env:OPENROUTER_API_KEY"} | Select-Object -First 3

---
## 實作步驟
### 步驟 0：備份關鍵檔案（零風險，實施前必做）
備份路徑：backups/YYYYMMDD/（由 PS 自動建立）
備份清單：config/frequency-limits.yaml、config/model-selection.yaml、run-todoist-agent-team.ps1、check-health.ps1
還原指令：Copy-Item backups/YYYYMMDD/run-todoist-agent-team.ps1 . -Force
---
### 步驟 1：Quick Win — 修改 config/frequency-limits.yaml（零風險）
僅修改 model 欄位，系統優化類立即降至 haiku。
異動清單：
- self_heal: claude-haiku-4-5（新增）
- system_insight: claude-haiku-4-5（新增）
- log_audit: claude-haiku-4-5（新增）
- jiaoguangzong: claude-haiku-4-5（原 sonnet-4-5，暫降，步驟 3 後改 codex）
- fahua: claude-haiku-4-5（原 sonnet-4-5，暫降，步驟 3 後改 codex）
- chatroom_optimize: claude-haiku-4-5（原 sonnet-4-6）
- skill_audit: claude-haiku-4-5（新增）
- ai_sysdev: claude-haiku-4-5（新增，步驟 3 後改 codex）
- ai_workflow_github: claude-haiku-4-5（新增，步驟 3 後改 codex）
關鍵檔案：config/frequency-limits.yaml
驗證：日誌搜尋 --model claude-haiku-4-5 確認降級。
---
### 步驟 2：新建 config/model-selection.yaml（純新建，零風險）
定義後端類型、token 閾值、fallback 鏈。
token_thresholds: warn=1500000, critical=8000000, emergency=12000000
backends:
  claude_haiku: type=claude_code, cli_flag=--model claude-haiku-4-5, fallback=claude_sonnet
  claude_sonnet: type=claude_code, cli_flag=空字串（預設）
  codex_exec: type=codex, cmd=codex exec --full-auto, websearch=cached, fallback=openrouter_research
  openrouter_research: type=openrouter_runner, model=google/gemini-flash-1.5, fallback_model=mistralai/mixtral-8x22b-instruct, tools=[Read,Write,Bash,Grep,WebFetch], fallback=claude_haiku
  openrouter_standard: type=openrouter_runner, model=meta-llama/llama-3.3-70b, tools=[Read,Write,Bash,Grep], fallback=claude_haiku
task_rules:
  claude_haiku: [self_heal, system_insight, log_audit]
  codex_exec: [shurangama, jingtu, jiaoguangzong, fahua, ai_sysdev, ai_workflow_github, ai_github_research, ai_deep_research, tech_research]
  openrouter_standard: [git_push, chatroom_optimize, skill_audit]
phase_overrides:
  critical: phase1_model=--model claude-haiku-4-5, phase1_max_tokens=30000, phase3_model=--model claude-haiku-4-5
  emergency: phase1_model=--model claude-haiku-4-5, phase1_max_tokens=20000, phase3_model=--model claude-haiku-4-5
codex:
  require_installed: true
  fallback_if_missing: openrouter_research
  live_websearch_tasks: [ai_deep_research, tech_research, ai_github_research]
關鍵檔案：config/model-selection.yaml（新建）
---
### 步驟 3：在 run-todoist-agent-team.ps1 加入 4 個輔助函式（+110 行）
插入位置：Write-Span 函式結束後（約第 353 行），不修改任何現有函式。
函式 1 ConvertFrom-YamlViapy（約 10 行）：uv run python PyYAML，YAML -> JSON -> PS 物件。
函式 2 Get-TaskBackend（約 55 行）：
- 讀 state/token-usage.json -> 計算 token_level
- 查 model-selection.yaml task_rules -> 取 backend 名稱
- codex_exec 時：Get-Command codex -ErrorAction SilentlyContinue 不存在 -> 自動降級 openrouter_research
- CODEX_API_KEY 未設定 -> 降級 openrouter_research
- OPENROUTER_API_KEY 未設定 -> 降級 claude_haiku
- 失敗保護：catch -> 回傳 type=claude_code, cli_flag=空
函式 3 Start-CodexJob（約 30 行）：
- Start-Job 啟動：prompt 管道至 codex exec --full-auto [--search 即時 WebSearch]
- 設定 CODEX_API_KEY, CLAUDE_TEAM_MODE, DIGEST_TRACE_ID, AGENT_PHASE, AGENT_NAME
- 回傳 Job，整合到 phase2Jobs 陣列
函式 4 Start-OpenRouterJob（約 25 行）：
- Start-Job 啟動 node tools/agentic-openrouter-runner.js
- 設定 OPENROUTER_API_KEY, CLAUDE_TEAM_MODE, DIGEST_TRACE_ID, AGENT_PHASE, AGENT_NAME
- 回傳 Job，整合到 phase2Jobs 陣列
關鍵檔案：run-todoist-agent-team.ps1（+110 行，插入第 353 行後）
---
### 步驟 4：新建 tools/agentic-openrouter-runner.js（約 250 行）
作為 OpenRouter 後端的 agentic 執行器（Codex fallback 及維護任務用）。
介面：stdin -> stdout（與 claude -p 管道介面相同）
核心工具：Read、Write、Bash（白名單）、Grep、WebFetch（research 限定，直接 curl 呼叫）
工具循環：最多 15 輪，Promise.all 並行 tool_call
失敗：exit 1，PS Job 偵測後自動降級 claude_haiku
環境變數：OPENROUTER_API_KEY（無需 Brave Search API）
關鍵檔案：tools/agentic-openrouter-runner.js（新建）
驗證：echo 摘要 config/timeouts.yaml | node tools/agentic-openrouter-runner.js
---
### 步驟 5：修改 Phase 2 Auto 任務啟動迴圈（+60 行，約第 830 行）
路由邏輯（foreach 迴圈內，promptContent 讀取後、Start-Job 之前）：
1. Get-TaskBackend 取得 {type, model, tools, fallback, reason}
2. codex -> Start-CodexJob（live websearch 依 codex.live_websearch_tasks）
3. openrouter_runner -> Start-OpenRouterJob
4. claude_code -> 原有 Start-Job + cliFlag 注入
5. Write-Span 加入 backend/model/reason 欄位
向後相容：model-selection.yaml 不存在 -> 完全等同現有行為
關鍵檔案：run-todoist-agent-team.ps1（+60 行）
---
### 步驟 6：Phase 1/3 Token Budget 控制（+20 行）
修改位置：Phase 1 claude 呼叫（約第 580 行）、Phase 3 claude 呼叫（約第 950 行）。
新增邏輯：
- 讀 token_level（已由 Get-TaskBackend 快取）
- critical/emergency：Phase 1/3 加 --model claude-haiku-4-5
- 任何 level：Phase 1 加 --max-tokens 80000 防止單次超限
關鍵檔案：run-todoist-agent-team.ps1（+20 行）
---
### 步驟 7：加入環境變數載入（+12 行，約第 397 行）
CODEX_API_KEY：未設定 -> codex 任務降級 openrouter_research，記錄 WARN
OPENROUTER_API_KEY：未設定 -> openrouter 任務降級 claude_haiku，記錄 WARN
.env 新增欄位：CODEX_API_KEY=...、OPENROUTER_API_KEY=sk-or-v1-...
（無需 BRAVE_SEARCH_API_KEY，已移除）
關鍵檔案：run-todoist-agent-team.ps1（+12 行）
---
### 步驟 8：研究品質評分機制（新建 tools/score-research-quality.py，約 80 行）
輸入：results/todoist-auto-{task_key}.json（每個研究任務完成後呼叫）
評分維度（共 100 分）：
- source_count（0-25）：引用來源數量（5 個以上得滿分）
- source_diversity（0-20）：來源域名多樣性（3 個不同域得滿分）
- kb_novelty（0-25）：與 context/research-registry.json 比對，新主題/新角度
- output_depth（0-20）：結果字元長度（500 字以上得滿分）
- tool_utilization（0-10）：是否有效使用 WebSearch（有搜尋結果得分）
輸出：追加至 state/research-quality.json（30 日滾動窗口）
低分處置（score < 60）：記錄 [QualityAlert]，下次執行升級 fallback -> claude_sonnet
觸發時機：Phase 2 結果收集迴圈，每個研究 Job 完成後呼叫
關鍵檔案：tools/score-research-quality.py（新建），state/research-quality.json（自動建立）
---
### 步驟 9：可觀測性（+65 行）
修改 A：run-todoist-agent-team.ps1 Phase 2 結果收集後（約第 916 行）加入：
- backend 分布日誌：[ModelSelect] backend 分布: codex=9, openrouter_standard=3, claude_haiku=3
- 研究品質摘要：[QualityScore] shurangama=82, ai_deep_research=74, avg=78.5
修改 B：check-health.ps1 加入兩個新區塊（+50 行）：
  [Token 節省效率]：近 7 天 backend 分布 + 節省率估算（codex=100%，standard=100%，haiku=70%）
  [研究品質趨勢]：近 30 天各任務品質評分 + 低分任務預警清單
關鍵檔案：run-todoist-agent-team.ps1（+15 行）、check-health.ps1（+50 行）
---
## BOT 啟動任務考量

### 現況分析
bot/process_messages.ps1 是 BOT 的 Worker 腳本，呼叫 claude -p 執行所有使用者下達的任務：
- 研究型任務（is_research=true）：先執行 KB 研究策略（krsPrompt，line 267）-> 再執行主任務（line 337）
- 一般任務（is_research=false）：直接執行 claude -p --allowedTools Read,Bash,Write（line 342）
- 更新步驟：完成後執行 claude -p --max-turns 5 寫回結果（line 373）

消耗估算：BOT 任務為使用者互動驅動（非定時），頻率較低，估計額外 ~1-3M/日。

### 建議策略
| 任務類型 | 目前 | 建議 | 理由 |
|---------|------|------|------|
| BOT 研究型任務（is_research=true） | claude -p | Codex CLI（優先，後續迭代） | 零 Claude token；互動品質要求高 |
| BOT 一般任務 | claude -p | 保持 claude | 使用者互動品質要求高，暫不路由 |
| KB 研究策略（krsPrompt） | claude -p | 保持 claude | 需存取本地知識庫 API，claude 最穩定 |

### 實施選項
選項 A（保守，本次採用）：BOT 任務保持現有 claude -p，先觀察 Todoist 路由後的節省效果。
選項 B（後續升級）：在 process_messages.ps1 加入 Get-BotBackend 函式：
- is_research=true 且 Codex 已安裝 -> codex exec --full-auto
- 否則 -> 保持 claude -p
- 預計額外節省 ~0.5-1.5M/日

本計畫採用選項 A：BOT 任務路由列為後續迭代，不影響本次主計畫實施。
---
## 關鍵檔案清單
| 步驟 | 操作 | 檔案 |
|------|------|------|
| 0 | 備份（自動） | backups/YYYYMMDD/ |
| 1 | 修改（YAML 欄位） | config/frequency-limits.yaml |
| 2 | 新建 | config/model-selection.yaml |
| 3 | 修改（+110 行，第 353 行後） | run-todoist-agent-team.ps1 |
| 4 | 新建（約 250 行） | tools/agentic-openrouter-runner.js |
| 5 | 修改（+60 行，第 830 行區域） | run-todoist-agent-team.ps1 |
| 6 | 修改（+20 行，Phase 1/3 呼叫） | run-todoist-agent-team.ps1 |
| 7 | 修改（+12 行，第 397 行後） | run-todoist-agent-team.ps1 |
| 8 | 新建（約 80 行） | tools/score-research-quality.py |
| 9 | 修改（+65 行） | run-todoist-agent-team.ps1、check-health.ps1 |
可複用現有函式（run-todoist-agent-team.ps1 第 64-352 行）：
Write-Log、Update-State、Update-FailureStats、Send-FailureAlert、Set-FsmState、Write-Span、Remove-StderrIfBenign
---
## Token 節省完整性評估
| 來源 | 原消耗（估） | 新方案 | 節省 |
|------|------------|--------|------|
| Phase 2 研究類（9任務） | ~8.5M/日 | 0（Codex） | 100% |
| Phase 2 維護類（3任務） | ~2.8M/日 | 0（OpenRouter） | 100% |
| Phase 2 系統類（3任務） | ~2.8M/日 | ~0.84M（haiku） | 70% |
| Phase 1/3 協調層（92回合） | ~2.2M/日 | ~0.9M（budget+降級） | 60% |
| BOT Worker（選項 A，後續迭代） | ~1-3M/日 | 不變 | 0% |
| 合計（不含 BOT） | ~16.3M/日 | ~1.74M/日 | ~89% |
結論：預計降至 ~1.74M/日，接近 1.5M 警告線。若需進一步降低，可選填：
- 將 Phase 1/3 全面改為 haiku（再省 ~0.5M/日）
- 降低 todoist-team 排程頻率（目前 30 分鐘，改 45 分鐘再省 ~33%）
- 實施 BOT 選項 B（研究型 BOT 任務路由 Codex，再省 ~1M/日）
---
## 驗證方式
1. 步驟 0：確認 backups/ 目錄有備份檔案
2. 前置需求：codex --version 回傳版本，Get-Command codex 輸出路徑
3. 步驟 1：日誌確認 self_heal/system_insight/log_audit 使用 claude-haiku-4-5
4. 步驟 3 Codex：codex exec --full-auto "搜尋楞嚴經最新研究" 回傳正常輸出
5. 步驟 4 OpenRouter：echo 摘要 | node tools/agentic-openrouter-runner.js 回傳正常
6. 步驟 5：日誌搜尋 [ModelSelect] 確認 shurangama->codex、git_push->openrouter_standard
7. 步驟 8：uv run python tools/score-research-quality.py results/todoist-auto-shurangama.json 輸出 JSON 評分
8. 整體：state/token-usage.json 當日 estimated_tokens 目標低於 2M
9. 可觀測性：check-health.ps1 顯示 [Token 節省效率] 和 [研究品質趨勢]
---
## 風險與對策
| 風險 | 對策 |
|------|------|
| codex 未安裝 | Get-TaskBackend 偵測，不存在 -> openrouter_research（自動 fallback） |
| CODEX_API_KEY 未設定 | codex -> openrouter_research fallback，記錄 WARN |
| Codex 輸出非正體中文 | 在 codex exec prompt 前綴加「請以正體中文輸出」；cjk_guard 偵測 |
| OpenRouter 不可達 | runner exit 1 -> claude_haiku fallback |
| 研究品質低（score<60） | 自動升級 fallback -> claude_sonnet，記錄 [QualityAlert] |
| Phase 1/3 仍超 token | phase_overrides 啟用，降至 haiku + max_tokens（已在計畫中） |
| codex exec 被 pre_bash_guard.py 攔截 | 加入白名單：codex exec 模式，對齊 config/hook-rules.yaml |
| model-selection.yaml 解析失敗 | catch -> 完全等同現有行為（claude_code/空 cli_flag） |
| Windows npm @openai/codex-win32-x64 缺失 | 使用 npm 版本別名安裝法（已列入前置需求） |
| BOT 任務仍消耗 Claude token | 本計畫選項 A 保持現狀；高消耗時啟動選項 B 路由研究型 BOT 任務 |
