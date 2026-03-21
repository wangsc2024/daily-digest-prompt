# Daily Digest Prompt - 系統使用手冊

> 版本：2.0 | 最後更新：2026-03-20
> 適用對象：日常使用者（非開發者）

---

## 系統簡介

Daily Digest Prompt 是一套**全自動 AI 代理人系統**，每天自動執行以下工作：

| 工作 | 執行時間 | 說明 |
|------|---------|------|
| 每日摘要 | 08:00 / 11:15 / 21:15 | 彙整待辦、新聞、HN AI 消息 → ntfy 通知 |
| Todoist 任務 | 每 30 分鐘 | 自動規劃並執行今日待辦任務 |
| 自動研究 | 每小時 | 依輪轉機制執行 29 種研究/維護任務 |
| 系統審查 | 每日 00:40 | 7 維度系統健康評估，自動修正問題 |

---

## 快速啟動

### 一、首次安裝

```powershell
# 1. 安裝 Python 環境
pip install uv
uv sync

# 2. 設定 Windows 排程（需管理員權限）
pwsh -ExecutionPolicy Bypass -File setup-scheduler.ps1 -FromHeartbeat

# 3. 驗證健康狀態
pwsh -ExecutionPolicy Bypass -File check-health.ps1
```

### 二、手動觸發（任何時候）

```powershell
# 立即執行每日摘要
pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1

# 立即執行 Todoist 任務規劃
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1

# 立即執行系統審查
pwsh -ExecutionPolicy Bypass -File run-system-audit-team.ps1
```

---

## 日常使用

### 查看今日摘要

通知透過 **ntfy** 推送到 `wangsc2025` topic。
- 手機/電腦安裝 ntfy app，訂閱 `wangsc2025`
- 或直接查看：https://ntfy.sh/wangsc2025

### 查看執行成果

```powershell
# 今日執行摘要（快速）
.\query-logs.ps1

# 近 3 天 Todoist 執行情況
.\query-logs.ps1 -Days 3 -Agent todoist

# 查看錯誤
.\query-logs.ps1 -Mode errors
```

### 查看系統健康

```powershell
# 完整健康報告（約 30 秒）
pwsh -ExecutionPolicy Bypass -File check-health.ps1
```

報告包含 6 個區塊：
1. **自動任務一致性**：prompt 檔案 vs 配置一致性
2. **研究註冊表健康度**：去重機制狀態
3. **快取效率**：API 快取命中率
4. **配置膨脹指標**：配置文件複雜度趨勢
5. **根因分析**：最近失敗的根因識別
6. **SLO 狀態**：成功率、Timeout 情況

---

## 自動研究系統

### 研究任務輪轉

系統有 **29 個自動任務**，以 round-robin 輪轉執行，每日約執行 40 次：

**佛學研究（8 次/日）**
- 楞嚴經（1 次）、教觀綱宗（2 次）、法華經（3 次）、淨土宗（2 次）

**AI/技術研究（9 次/日）**
- AI 深度研究（3 次）、技術研究（2 次）、GitHub AI（1 次）、智慧城市（1 次）、系統開發（1 次）、AI 工作流（1 次）

**系統維護（10 次/日）**
- 系統洞察（2 次）、架構演進（2 次）、自癒迴圈（2 次）、Log 審查（2 次）、Skill 審查（1 次）、Git 推送（1 次）

**Podcast（6 次/日）**
- 通用 Podcast（2 次）、教觀綱宗 Podcast（3 次）、GitHub 靈感（1 次）

**其他（7 次/日）**
- Skill 鑄造（2 次）、ntfy 審查（1 次）、未來計畫（1 次）、KB 洞察（1 次）、Workflow 鑄造（1 次）、洞察簡報（1 次）

### 研究去重機制

研究前自動查詢 3 層防護，避免重複研究相同主題：
1. `context/research-registry.json`（7 天滾動紀錄）
2. 知識庫混合搜尋（語義 + 關鍵字）
3. `config/dedup-policy.yaml`（3 天冷卻期、飽和閾值）

---

## 知識庫整合

### 查詢個人知識庫

```powershell
# 在 Claude Code 中
# 查詢知識庫：AI 系統開發
```

知識庫 API 位於 `localhost:3000`，研究成果自動匯入，每日 git-push 任務同步至 GitHub。

### 手動同步記憶

```powershell
# 同步摘要記憶到知識庫
uv run python tools/digest_sync.py --base-url http://localhost:3000

# 查詢摘要記憶
uv run python tools/digest_sync.py --query "AI 技術" --task-type ai_sysdev
```

---

## Todoist 任務管理

### 任務標籤規範

系統透過標籤自動路由任務到對應的處理模板：

| 標籤 | 路由到 | 說明 |
|------|--------|------|
| `研究`、`深度思維` | research-task.md | 知識庫研究流程 |
| `@code`、`GitHub` | code-task.md | Plan-Then-Execute 模式 |
| `遊戲開發` | game-task.md | 品質分析 + 修改 |
| 有 Skill 關鍵字 | skill-task.md | Skill 驅動處理 |
| 無特殊標籤 | general-task.md | 一般任務 |

### 任務計分規則（config/scoring.yaml）

6 因子計分（priority × confidence × description × time_proximity × label_count × recency_penalty）。

同分 Tiebreaker：截止時間 → priority → 標籤數量 → Task ID 字典序。

---

## 系統自癒機制（OODA 閉環）

系統每日自動執行 OODA（Observe-Orient-Decide-Act）閉環：

```
00:40 系統審查（Observe）
  ↓
system_insight（Orient）→ improvement-backlog.json
  ↓
arch_evolution（Decide）→ arch-decision.json
  ↓
self_heal（Act）→ 自動修復問題
```

若 `workflow-state.json` 的 `current_step=act` 且 `arch-decision.json` 存在，self_heal 任務會被強制優先執行。

---

## LINE 訊息回覆

訊息透過 Gun.js Relay 加密轉發，回覆路徑：

```
任務完成 → routes.js → bot.js（Gun payload 加密）
  → https://gun-relay-bxdc.onrender.com/
  → 解密 → postToLine（group/user）
```

**注意**：`LINE_CHANNEL_ACCESS_TOKEN` 在 Render 環境變數中，bot.js 本地不直接推播。

---

## Podcast 系統

### 自動 Podcast 生成

系統每日自動從知識庫選材生成 AI 雙主持人對話 Podcast：

- **通用 Podcast**：選非佛學類別最佳 3 篇筆記（cursor_cli）
- **教觀綱宗 Podcast**：每日 3 集，TTS 合成後上傳 R2

### 手動生成

```powershell
# 執行單次 Podcast 生成
uv run python tools/run_podcast_create.py

# 完整淨土教觀學苑 Podcast 流程
pwsh tools/run-jiaoguang-podcast-next.ps1
```

---

## 通知配置

### ntfy 設定

- Topic：`wangsc2025`
- 必須使用 JSON 檔案方式發送（Windows 環境）
- 加 `charset=utf-8` header 避免亂碼

### 自動告警

系統異常時會自動發送 ntfy 告警：
- **Session 結束健康檢查**（on_stop_alert.py）：攔截事件 ≥ 3 或錯誤 ≥ 5 則 critical
- **API circuit open**：自動降級並告警
- **FSM stale > 45 分鐘**：Autonomous Harness 觸發重啟

---

## 排程管理

### 查看排程狀態

```powershell
# 查看 Windows 排程器任務
Get-ScheduledTask | Where-Object TaskPath -like "*daily-digest*"

# 查看最後執行時間
Get-ScheduledTaskInfo -TaskName "daily-digest-am"
```

### 重建排程

```powershell
# 從 HEARTBEAT.md 批次建立（需管理員）
pwsh -ExecutionPolicy Bypass -File setup-scheduler.ps1 -FromHeartbeat
```

### 排程時間表

| 名稱 | 時間 | 腳本 |
|------|------|------|
| system-audit | 每日 00:40 | run-system-audit-team.ps1 |
| daily-digest-am | 每日 08:00 | run-agent-team.ps1 |
| daily-digest-mid | 每日 11:15 | run-agent-team.ps1 |
| daily-digest-pm | 每日 21:15 | run-agent-team.ps1 |
| todoist-single | 整點 02-23 | run-todoist-agent.ps1 |
| todoist-team | 整點+半點 01-23 | run-todoist-agent-team.ps1 |

---

## 緊急操作

### 系統降級（手動）

```powershell
# 注入 recovery profile（TTL 30 分鐘）
uv run python tools/autonomous_recovery_worker.py --inject-override recovery --ttl 30
```

### 清除異常狀態

```powershell
# 重置 FSM 狀態
$state = @{ "state" = "idle"; "updated_at" = (Get-Date -Format "o") } | ConvertTo-Json
[System.IO.File]::WriteAllText("state/run-fsm.json", $state, [System.Text.Encoding]::UTF8)

# 清除失敗任務記錄
echo '{"failed_tasks":[]}' > state/failed-auto-tasks.json
```

### 強制執行特定自動任務

在 `context/auto-tasks-today.json` 中：
- 將 `next_execution_order` 設為目標任務的 `execution_order`
- 將對應的 `*_count` 重置為 0

---

## 附錄

### 關鍵配置檔案速查

| 修改目的 | 配置檔案 |
|---------|---------|
| 新增/停用自動任務 | `config/frequency-limits.yaml` |
| 調整後端路由 | `config/frequency-limits.yaml` task_rules |
| 調整研究去重冷卻期 | `config/dedup-policy.yaml` |
| 調整 ntfy 通知格式 | `config/notification.yaml` |
| 調整系統評分維度 | `config/audit-scoring.yaml` |
| 調整 Token 預算閾值 | `config/budget.yaml` |
| 調整 Hook 攔截規則 | `config/hook-rules.yaml` |
| 調整各任務 Timeout | `config/timeouts.yaml` |

### 日誌位置

| 日誌類型 | 位置 |
|---------|------|
| 結構化工具日誌（JSONL） | `logs/structured/*.jsonl` |
| 系統審查報告 | `docs/系統審查報告_*.md` |
| 系統審查 Phase 日誌 | `logs/audit-phase*.log` |
| 自動任務歷史 | `state/todoist-history.json` |

### 技術支援

如遇問題，依序檢查：
1. `pwsh check-health.ps1`（健康報告）
2. `uv run python hooks/query_logs.py --errors`（近期錯誤）
3. `state/run-fsm.json`（FSM 狀態）
4. `state/failure-stats.json`（失敗統計）
5. `docs/OPERATIONS.md`（詳細運維說明）
6. `docs/ARCHITECTURE.md`（系統架構說明）
