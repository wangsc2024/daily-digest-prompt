# Daily Digest Prompt - 運維手冊

> 本文件由 `docs/OPERATIONS.md` 維護，對應 CLAUDE.md 的「執行流程」與「Hooks 機器強制層」引用。
> 最後更新：2026-03-20（v4：新增 Autonomous Harness、SLO 管理、多後端路由）

---

## 執行流程

### 每日摘要 - 團隊並行模式（run-agent-team.ps1，推薦）

1. Windows Task Scheduler 觸發 `run-agent-team.ps1`
2. **Phase 0**：PS 預計算快取狀態，生成 `cache/status.json`（LLM 直接讀 `valid` 欄位，不計算時間差）
3. **Phase 1**：用 `Start-Job` 同時啟動最多 6 個 `claude -p`（Todoist + 新聞 + HN + Gmail + 安全審查 + Chatroom）
   - 各 Agent 讀取 `cache/status.json` 判斷是否命中快取；結果寫入 `results/*.json`
4. 等待全部完成（timeout 300s），完成後 PS 回寫快取
5. **Phase 2**：啟動組裝 Agent 讀取 `results/*.json`（timeout 420s）
   - 加上政策解讀、習慣提示、學習技巧、知識庫查詢
   - 整理完整摘要 → ntfy 推播 → 更新記憶/狀態 → 清理 results/
6. Phase 2 失敗可自動重試一次（間隔 60 秒）
7. **預期耗時**：約 1 分鐘（快取命中）～ 2 分鐘（全部 API 呼叫）

### Todoist 任務規劃 - 團隊並行模式（run-todoist-agent-team.ps1，推薦）

1. Windows Task Scheduler 觸發 `run-todoist-agent-team.ps1`
2. **Phase 0**（Pre-check）：讀取 `state/token-budget-state.json` 判斷降級等級；`Get-TaskBackend` 函數讀取 `config/frequency-limits.yaml` 決定後端
3. **Phase 1**（1 個查詢 Agent，timeout 420s）：
   - 查詢 Todoist `/api/v1/tasks/filter?query=today`
   - 三層路由：task_type_labels → template_priority → modifier_labels
   - 按 `config/scoring.yaml` 計分排序（6 因子）
   - 輸出：`tasks`（有待辦）/ `auto`（觸發自動任務）/ `idle`（跳過）
4. **Phase 2**（N 個並行 Agent，動態 timeout）：
   - research: 600s、code: 900s、skill/general: 300s、auto: 600s、gitpush: 360s
   - 後端由 `frequency-limits.yaml` 的 `task_rules` 決定（codex/cursor_cli/claude 等）
5. **Phase 3**（1 個組裝 Agent，timeout 180s）：關閉任務 + 更新狀態 + 推播通知
6. Phase 3 失敗可自動重試一次（間隔 60 秒）

**自動任務觸發條件**：
- 三層路由篩選後無可處理任務
- 步驟 4 執行完畢後重新查詢，可處理項目 = 0

### 每日系統審查 - 團隊並行模式（run-system-audit-team.ps1，推薦）

每日 00:40 自動執行，使用 `system-audit` Skill 評估 7 個維度、38 個子項：

1. **Phase 0**：PS 預計算快取狀態，生成 `cache/status.json`
2. **Phase 1**：同時啟動 4 個 `claude -p` 並行審查（timeout 600s 各）
   - Agent 1: 維度 1（資訊安全）+ 維度 5（技術棧）→ `results/audit-dim1-5.json`
   - Agent 2: 維度 2（系統架構）+ 維度 6（系統文件）→ `results/audit-dim2-6.json`
   - Agent 3: 維度 3（系統品質）+ 維度 7（系統完成度）→ `results/audit-dim3-7.json`
   - Agent 4: 維度 4（系統工作流）→ `results/audit-dim4.json`
3. **Phase 2**：組裝 Agent 計算加權總分 → 識別問題 → 自動修正（最多 5 項）→ 報告 → RAG 匯入（timeout 1200s）
4. **Phase 3**（審查後）：若 `improvement-backlog.json` 非空，直接觸發 `arch_evolution` 任務

**輸出**：
- 審查報告：`docs/系統審查報告_YYYYMMDD_HHMM.md`
- 狀態：`state/last-audit.json`（含總分、等級、7 維度分數）
- 知識庫：自動匯入 RAG (localhost:3000)
- 日誌：`logs/audit-phase1-*.log`、`logs/audit-phase2-*.log`

**預期耗時**：約 15-20 分鐘（單一模式需 25-30 分鐘）

---

## Autonomous Harness 自主運行框架

### 概述

`tools/autonomous_harness.py` 是系統的自主監控與恢復層，配置於 `config/autonomous-harness.yaml`。

### 手動觸發

```powershell
# 分析系統狀態（不執行恢復）
uv run python tools/autonomous_harness.py --analyze

# 執行恢復規劃（寫入 autonomous-harness-plan.json）
uv run python tools/autonomous_harness.py --plan

# Recovery Worker 執行規劃中的恢復動作
uv run python tools/autonomous_recovery_worker.py --execute
```

### 監控閾值（config/autonomous-harness.yaml）

| 監控項 | 閾值 | 觸發動作 |
|--------|------|---------|
| 排程心跳停止 | > 20 分鐘 | degraded/recovery |
| FSM stale | > 45 分鐘 | restart |
| 失敗次數 | ≥ 2 次（10 分鐘窗口） | degraded |
| API circuit open | ≥ 1 | 阻斷對應 fetch agent |
| Starvation | > 3 次 | 調整 round-robin 指針 |

### Runtime Profiles

| Profile | 並行任務上限 | 允許重任務 | 允許研究任務 | 阻斷 Agent |
|---------|------------|----------|------------|----------|
| normal | 4 | ✅ | ✅ | 無 |
| degraded | 2 | ❌ | ✅ | security, chatroom |
| recovery | 1 | ❌ | ❌ | gmail, security, chatroom |

---

## SLO 預算管理

### 工具

```powershell
# 查看當前 SLO 狀態
uv run python tools/slo_budget_manager.py --status

# 產出完整報告（寫入 state/slo-budget-report.json）
uv run python tools/slo_budget_manager.py --report

# 檢查特定任務
uv run python tools/slo_budget_manager.py --task ai_deep_research
```

### SLO 定義（config/slo.yaml）

- 成功率目標、Timeout 上限、每日執行目標均定義在此
- 報告由 `tools/slo_budget_manager.py` 讀取 `state/failure-stats.json` 計算

---

## Token 預算治理

```powershell
# 查看預算狀態
uv run python tools/budget_guard.py --status

# 手動觸發降級評估
uv run python tools/budget_guard.py --check
```

**閾值（config/budget.yaml + config/frequency-limits.yaml）**：

| 等級 | estimated_tokens | Phase 1/3 降級 |
|------|-----------------|---------------|
| normal | < 10M | 正常模式 |
| critical | 10M-18M | Haiku（30K max tokens）|
| emergency | 18M-28M | Haiku（20K max tokens）|

---

## Hooks 機器強制層（Harness Enforcement）

從「Agent 自律」升級到「機器強制」。Hook 命令格式：
```
uv run --project D:/Source/daily-digest-prompt python D:/Source/daily-digest-prompt/hooks/<hook>.py
```

### Hook 清單

| Hook | 類型 | 用途 |
|------|------|------|
| `pre_bash_guard.py` | PreToolUse:Bash | 攔截 nul 重導向、scheduler-state 寫入、危險刪除、force push、敏感環境變數、機密外洩 |
| `pre_write_guard.py` | PreToolUse:Write,Edit | 攔截 nul、scheduler-state、敏感檔案；專案外路徑僅 structured log + ntfy 告警（不阻擋） |
| `pre_read_guard.py` | PreToolUse:Read | 攔截敏感系統路徑（.ssh/.gnupg）、敏感檔案（.env/credentials）、Windows 憑據路徑 |
| `post_tool_logger.py` | PostToolUse:* | 結構化 JSONL 日誌，自動標籤分類，50MB 緊急輪轉 |
| `hook_pipeline.py` | 中介軟體 | DeerFlow 式短路機制，規則鏈串接，失敗回退硬編碼規則 |
| `cjk_guard.py` | PostToolUse:Write,Edit | CJK 字元守衛（日文 Unicode 變體修正） |
| `on_stop_alert.py` | Stop | Session 結束分析日誌，異常時自動 ntfy 告警 |
| `validate_config.py` | 工具（非 Hook） | YAML 配置 Schema 驗證（check-health.ps1 呼叫或獨立執行） |

### Hook 規則外部化

規則定義在 `config/hook-rules.yaml`（v3，20 條規則）：
- Bash 守衛：13 條（nul、scheduler-state、危險刪除、force push、環境變數、外洩防護）
- Write 守衛：4 條（nul、scheduler-state、敏感檔案、專案外路徑 warn_only）
- Read 守衛：3 條（敏感路徑、Windows 憑據）
- 三個 preset（strict/normal/permissive）

### 結構化日誌系統

`post_tool_logger.py` 對每個工具呼叫自動產生 JSONL 記錄：

**自動標籤**：

| 標籤 | 觸發條件 |
|------|---------|
| `api-call` | Bash 指令含 `curl` |
| `todoist` / `pingtung-news` / `hackernews` / `knowledge` / `gmail` | URL 模式匹配 |
| `cache-read` / `cache-write` | 讀寫 `cache/*.json` |
| `skill-read` / `skill-index` | 讀取 `SKILL.md` / `SKILL_INDEX.md` |
| `memory-read` / `memory-write` | 讀寫 `digest-memory.json` |
| `sub-agent` | Bash 指令含 `claude -p` |
| `blocked` | PreToolUse hook 攔截 |
| `error` | 工具輸出含錯誤關鍵字 |
| `skill-modified` | Write/Edit SKILL.md |

**JSONL 格式範例**：
```json
{"ts":"2026-03-20T08:01:30+08:00","sid":"abc123","tool":"Bash","event":"post","summary":"curl -s https://api.todoist.com/...","output_len":1234,"has_error":false,"tags":["api-call","todoist"]}
```

### 自動告警機制（on_stop_alert.py）

| 檢查項 | 條件 | 告警等級 |
|--------|------|---------|
| 違規攔截 | blocked > 0 | warning（≥3 則 critical） |
| 工具錯誤 | errors ≥ 1 | warning（≥5 則 critical） |
| SKILL.md 修改 | skill-modified > 0 | info（附修改路徑清單） |
| 全部正常 | 無上述問題 | 靜默記錄 session-summary |

---

## 查詢工具速查

### 結構化日誌查詢

```bash
# 今日摘要
uv run python hooks/query_logs.py

# 近 7 天
uv run python hooks/query_logs.py --days 7

# 僅攔截事件
uv run python hooks/query_logs.py --blocked

# 僅錯誤
uv run python hooks/query_logs.py --errors

# 快取使用審計
uv run python hooks/query_logs.py --cache-audit

# Session 摘要
uv run python hooks/query_logs.py --sessions --days 7

# JSON 輸出
uv run python hooks/query_logs.py --format json
```

### 執行成果查詢（query-logs.ps1）

```powershell
# 近 7 天摘要
.\query-logs.ps1

# 近 3 天 Todoist
.\query-logs.ps1 -Days 3 -Agent todoist

# 錯誤彙總
.\query-logs.ps1 -Mode errors

# 趨勢分析
.\query-logs.ps1 -Mode trend -Days 14
```

### 系統健康檢查

```powershell
# 完整健康報告（6 區塊）
pwsh -ExecutionPolicy Bypass -File check-health.ps1
# 包含：自動任務一致性、研究註冊表、快取效率、配置膨脹、根因分析、SLO 狀態

# 配置膨脹度量
.\analyze-config.ps1                 # 目前度量值
.\analyze-config.ps1 -Trend          # 7 天趨勢
```

### 追蹤與審計工具

```powershell
# LLM 路由測試
uv run python tools/llm_router.py --task-type news_summary --dry-run

# 任務對齊審計
uv run python tools/audit_verify.py --mission-alignment

# 根因分析（近 3 天）
uv run python tools/trace_analyzer.py --days 3

# 預算狀態
uv run python tools/budget_guard.py --status
```

---

## 常見問題排查

### 問題：Phase 2 未產出結果檔案

**根因 1**：prompt 檔名與 `frequency-limits.yaml` 的 task_key 不一致（連字號 vs 底線）
- 確認：`prompts/team/todoist-auto-{task_key}.md` 全部為底線命名
- 確認：`$dedicatedPrompts` 使用動態掃描（`Get-ChildItem todoist-auto-*.md`）

**根因 2**：LLM 輸出連字號 key（如 `tech-research`）
- 修復：`run-todoist-agent-team.ps1` 的 key 正規化邏輯

**根因 3**：Codex 在 Windows 無法穩定持久化 results/ 檔案
- 解決：改走 `claude_sonnet45` 後端（見 `task_rules` 配置）

### 問題：自動任務不均勻執行

- 確認 `state/context/auto-tasks-today.json` 的 `next_execution_order` 是否正常推進
- 確認 `state/auto-task-fairness-hint.json` 中 starvation 計數
- 執行 `uv run python tools/slo_budget_manager.py --status` 查看公平性指標

### 問題：Hook 全部靜默失敗

- Windows Store 的 `python3` 是空殼（exit 49）
- 確認 `.claude/settings.json` Hook 命令使用 `uv run --project ...`，非裸 `python` 或 `python3`

### 問題：ntfy 中文通知亂碼

- 必須用 Write 工具建立 UTF-8 JSON 檔案 + `curl -d @file.json -H "Content-Type: application/json; charset=utf-8"`
- 禁止用 Bash echo 建檔或 inline JSON 字串

### 問題：Todoist API 返回空結果或 410

- REST API v2（`/rest/v2/`）已棄用，改用 `/api/v1/`
- 篩選端點：`/api/v1/tasks?filter=` 靜默忽略 filter 參數，應用 `/api/v1/tasks/filter?query=today`
- 新回應格式：`{ "results": [...], "next_cursor": ... }`

---

## 前置需求

- Python 3.11+（由 uv 管理，`uv sync` 安裝所有依賴）
- uv（`pip install uv` 或 `winget install astral-sh.uv`）
- PowerShell 7（pwsh）：`winget install Microsoft.PowerShell`
- 依賴宣告於 `pyproject.toml`（`requirements.txt` 已廢棄）
- Windows 環境使用 `uv run python`（非裸 `python`，因 Windows Store 的 `python3` 空殼會靜默失敗）
