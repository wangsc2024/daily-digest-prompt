# Troubleshooting Guide

常見問題與解決方案，依問題類型分類。

## 1. Phase 2/3 結果檔案缺失

**症狀**：Phase 2 自動任務被 skip，Phase 3 報「結果檔案缺失」。

**已知根因（3 次）**：

| 次序 | 根因 | 修復 |
|------|------|------|
| 1 | LLM 輸出連字號 key（`tech-research`），與底線 key 不匹配 | 8f94e41 加正規化修復 |
| 2 | `todoist-query.md` 無 `plan_key` 欄 → LLM 自行推斷 key | 同上修復 |
| 3 | prompt 檔案重命名但 `$dedicatedPrompts` hardcoded 路徑未更新 | 改為動態掃描 `Get-ChildItem todoist-auto-*.md` |

**排查步驟**：
1. 確認 `results/` 目錄下有對應的 JSON 檔案
2. 比對 prompt 中定義的輸出檔名與 `$dedicatedPrompts` 預期路徑
3. 檢查 `frequency-limits.yaml` 的 key 與 prompt 檔名是否一致（底線 `_` 非連字號 `-`）

**預防**：prompt 檔命名必須遵循 `todoist-auto-{plan_key}.md`（底線），與 `frequency-limits.yaml` key 一致。

### 1.1 plan_type = "tasks" 時某任務顯示「Phase 2 結果缺失、已降優先級」

**症狀**：通知顯示「成功 2 / 失敗 1」，失敗項為「Phase 2 結果缺失，已降優先級」；或日誌出現 `[Phase2] Missing result file: todoist-result-N.json`。

**可能原因**：
- 該任務 Phase 2 逾時被強制結束（`Wait-Job -Timeout` 到期後 `Stop-Job`），agent 尚未寫入 `results/todoist-result-{rank}.json` 即被終止。
- 多 run 並行（排程重疊或手動與排程同時跑），共用同一 `results/`，結果檔被覆寫或只讀到部分檔案。
- Agent 未依 prompt 產出結果檔（罕見，可查該 task 的 Phase 2 日誌是否有錯誤）。

**排查步驟**：
1. 查該次 run 的 Phase 2 日誌：是否有 `[Phase2] task-N TIMEOUT - stopping` 或 `[Phase2] task-N failed`。
2. 若有 Missing result file 日誌：對照 `job state=`（timeout / failed / success）與任務內容，確認是否為逾時導致。
3. 查 `config/timeouts.yaml` 的 `todoist_team.phase2_timeout_by_type`（code / research / skill）與動態 timeout 日誌 `[Dynamic] Phase2 timeout = ...`，必要時略為提高對應類型或依 HEARTBEAT 確認排程未重疊。
4. 確認同一時段僅有一個 Todoist 團隊模式 run（避免兩次排程或手動與排程並行）。

**預防**：
- 腳本已對多任務並行加約 15% 或最多 120s 的 Phase 2 緩衝；若仍常逾時，可調高 `config/timeouts.yaml` 的 `phase2_timeout_by_type.code` / `research`。
- 排程設定避免相鄰整點/半點重疊（見 HEARTBEAT.md），必要時以 `state/scheduler-state.json` 或檔案鎖避免多 run 同時寫入 `results/`。

---

## 2. Todoist API 呼叫失敗

### 2.1 401 Unauthorized

**症狀**：API 回傳 401，快取降級模式下任務關閉/評論失敗。

**根因**：`TODOIST_API_TOKEN` 無效、已撤銷或已過期；或排程執行時未載入 `.env`。

**解決方案**：
1. 前往 [Todoist 設定 → 整合 → API token](https://todoist.com/prefs/integrations)
2. 複製 token 或點「重新產生」取得新 token
3. 更新專案 `.env`：`TODOIST_API_TOKEN=<新 token>`
4. **排程未使用 .env**：重新執行 `.\setup-scheduler.ps1 -FromHeartbeat` 註冊排程，會改經 `run-with-env.ps1` 載入 `.env` 後再執行腳本

### 2.2 410 Gone / 篩選結果為空

**症狀**：API 回傳 410 Gone 或篩選結果為空。

**根因**：REST API v2（`/rest/v2/`）已於 2026-02 棄用。

**解決方案**：
- 使用 API v1（`/api/v1/`）
- 篩選端點：`/api/v1/tasks/filter?query=today`（非 `/api/v1/tasks?filter=`，後者靜默忽略 filter 參數）
- 新回應格式：`{ "results": [...], "next_cursor": ... }`（非直接陣列）
- Task ID 格式從純數字改為英數混合字串

---

## 3. ntfy 通知亂碼

**症狀**：ntfy 推播中文標題或內容顯示為亂碼。

**根因**：Windows Bash 環境下 inline JSON 字串的編碼問題。

**解決方案**：
1. 用 Write 工具建立 UTF-8 JSON 檔案（不可用 `echo` 或 heredoc 建檔）
2. 加 `charset=utf-8` header：
   ```bash
   curl -s -H "Content-Type: application/json; charset=utf-8" -d @file.json https://ntfy.sh
   ```
3. 發送後刪除暫存 JSON 檔

---

## 4. Hooks 靜默失敗

**症狀**：所有 Hook 不執行，無攔截也無日誌。

**根因**：Windows Store 的 `python3` 是空殼（exit 49）。

**解決方案**：
- `.claude/settings.json` 中 hook 命令必須用 `python`（非 `python3`）
- 正確格式：`uv run --project D:/Source/daily-digest-prompt python D:/Source/daily-digest-prompt/hooks/<hook>.py`

---

## 5. PowerShell 5.1 UTF-8 編碼問題

**症狀**：Start-Job 背景作業輸出中文亂碼。

**根因**：PS 5.1 的 Start-Job 缺少 `-WorkingDirectory`，`$OutputEncoding` 預設 ASCII。

**解決方案**：
- 所有 .ps1 改用 `pwsh`（PowerShell 7）
- Start-Job 加 `-WorkingDirectory $AgentDir` 和 `$OutputEncoding = [System.Text.UTF8Encoding]::new()`
- `setup-scheduler.ps1` 的 `-Execute` 使用 `pwsh.exe`

---

## 6. nul 檔案意外產生

**症狀**：專案根目錄出現名為 `nul` 的實體檔案。

**根因**：在 Git Bash 中使用 `> nul`（cmd 語法），Bash 將 `nul` 視為普通檔名。

**解決方案**：
- 使用 `> /dev/null 2>&1`（Bash）或 `| Out-Null`（PowerShell）
- Hook `pre_bash_guard.py` 會自動攔截 `> nul` 語法

---

## 7. Circuit Breaker 誤判 API 不可用

**症狀**：API 正常但 circuit breaker 狀態為 open。

**排查步驟**：
1. 檢查 `state/api-health.json` 的 `consecutive_failures` 和 `cooldown_until`
2. 若需手動重置：
   ```powershell
   . ./circuit-breaker-utils.ps1
   Update-ApiHealth -ApiName "todoist" -Success $true
   ```
3. 檢查 `state/failure-stats.json` 了解失敗類型分布

---

## 診斷工具速查

| 工具 | 用途 |
|------|------|
| `query-logs.ps1 -Mode errors` | 近 7 天錯誤彙總 |
| `query-logs.ps1 -Mode trace -TraceId <id>` | 追蹤特定執行 |
| `check-health.ps1` | 全面健康檢查 |
| `uv run python hooks/query_logs.py --blocked` | Hook 攔截事件 |
| `analyze-config.ps1` | 配置膨脹度量 |
