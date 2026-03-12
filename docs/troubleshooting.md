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

### 1.2 todoist-team 排程執行中斷（日誌僅見 Phase 1 開頭即截斷）

**症狀**：`logs/todoist-team_yyyyMMdd_HHmmss.log` 僅有十餘行，最後一行為 `[Phase1] G28 chatroom-query job started (Job N)`，其後無 Phase 1 完成、Phase 2/3 或「done」紀錄。

**已知案例**：2026-03-11 20:30 排程（`todoist-team_20260311_203001.log`）啟動後於 Phase 1 的 `Wait-Job` 等待主 query 時程序被終止，同日 19:30 已於 19:46 正常結束，無重疊。

**可能根因**：
1. **程序遭外部終止**：主腳本在 `Wait-Job -Timeout 420` 阻塞時，pwsh 被 Task Scheduler、休眠/睡眠、或手動結束。
2. **Task Scheduler 執行時間限制**：若工作「若執行超過下列時間就停止」被設成過短（例如 7 分鐘），會強制結束；HEARTBEAT 預期為 4000s（約 67 分鐘）。
3. **資源或系統**：記憶體不足、系統休眠等。

**排查步驟**：
1. 確認排程的執行時間限制：以管理員開啟「工作排程器」→ 找到 `Claude_todoist-team` → 內容 → **「設定」** 索引標籤 → 「若執行超過下列時間就停止」應為 **約 67 分鐘**（或 1 小時 6 分鐘），**不是 7 分鐘**。若顯示為 7 分鐘會導致 Phase 1 約 7 分鐘時被強制結束。
2. **修正為 4000 秒**：以**系統管理員身分**開啟 PowerShell，執行：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File "D:\Source\daily-digest-prompt\scripts\check-task-limit.ps1" -SetTo4000
   ```
   或重新從 HEARTBEAT 註冊排程：`.\setup-scheduler.ps1 -FromHeartbeat`（會將 todoist-team 的 timeout 設為 4000s）。
3. 檢查當日 19:30 是否逾時或異常延遲（若 19:30 跑超過 1 小時，可能與 20:30 重疊；腳本已加單例鎖避免並行）。
4. 日誌開頭是否出現 `[SKIP] Another instance is running`（表示上一班仍在跑，本次依設計跳過）。

**已實施改善**：
- **單例鎖**：`run-todoist-agent-team.ps1` 使用 `state/run-todoist-agent-team.lock`，若上一班仍在執行則本班直接 exit，避免並行寫入 `results/` 與日誌混亂。
- **防禦日誌**：Phase 1 在進入 `Wait-Job` 前寫入 `[Phase1] Waiting for main query job (timeout Ns)...` 與 `[PID] N`，便於判斷中斷發生在「等待主 query」階段。

**預防**：
- 排程建立後以 `Get-ScheduledTask -TaskName Claude_todoist-team | Select-Object *` 或工作排程器 GUI 確認 ExecutionTimeLimit 為 4000 秒。
- 避免在執行時段內手動結束 pwsh 或讓主機進入休眠。

### 1.3 自動任務結果檔損壞（Codex 執行輸出被寫入結果檔案）

**症狀**：Phase 3 組裝摘要顯示「❌ [任務類型]：失敗 — 原因：執行結果檔案損壞（Codex 執行輸出被寫入結果檔案）」；日誌出現 `[Phase2] auto-tech_research result file補寫 (138841 chars, 426s)` 等大字數補寫。

**損壞情形**：
- **原因**：使用 Codex / OpenRouter 後端時，Agent 若未用 Write 產出 `results/todoist-auto-{key}.json`（或產出過小 &lt; 500 bytes），Phase 2 會以 **補寫（fallback）** 將該 Job 的 **整段 stdout** 寫入結果檔。
- **結果**：結果檔內容變成「後端 CLI 的完整終端輸出」（可達 10 萬字以上），而非 prompt 要求的結構化 JSON（`agent`、`type`、`status`、`summary` 等）。Phase 3 讀取時無法當成有效任務結果，故判定為「結果檔損壞」。
- **常見觸發**：`tech_research` 使用 `codex_exec`，Codex 的 stdout 為整段對話/工具輸出，若 Agent 未正確寫入結果檔即會觸發補寫。

**已實施優化**（run-todoist-agent-team.ps1）：
1. **結構化失敗取代整段 stdout**：補寫時不再寫入 `output = $fullOutput`（整段 stdout），改為寫入 **結構化失敗物件**：`agent`、`type`、`status: "failed"`、`reason: "result_file_missing_or_invalid"`、`backend_stdout_preview`（僅前 2000 字）、`backend`、`elapsed_seconds`。Phase 3 可正常解析並顯示「失敗（未產出有效結果檔）」。
2. **既有有效檔不覆蓋**：若結果檔已存在且 ≥ 500 bytes，且含 `type`/`agent` 與 `status` 欄位，視為 Agent 已產出有效結構，不執行補寫，避免覆蓋正確結果。

**若仍希望 Agent 產出有效檔**：
- 確認對應 prompt（如 `prompts/team/todoist-auto-tech_research.md`）明確要求「第一步用 Write 建立 results/todoist-auto-xxx.json 佔位，最後一步覆寫完整內容」。
- 必要時可將該任務改為 Claude 後端（較穩定產出 JSON），或檢查 Codex 執行環境是否導致 Write 工具未寫入預期路徑。

**楞嚴經研究（shurangama）同款失敗**：若報告顯示「❌ 楞嚴經研究 — 原因：Codex 後端未產出有效結果檔（codex_exec gpt-5.4，耗時 380s）」：
- 同上 1.3 機制：Codex 跑完但未產出 `results/todoist-auto-shurangama.json`（或檔案 &lt; 500 bytes / 缺 `agent`、`type`、`status`），腳本已寫入結構化失敗檔，Phase 3 可正常顯示失敗原因。
- 可能原因：Codex 在 WebSearch/WebFetch 或 KB 匯入階段耗時過長或中斷，未執行到第五步寫入結果 JSON。
- 建議：若連續失敗，可將 `config/frequency-limits.yaml` 的 `task_rules.codex_exec` 中暫時移除 `shurangama`，並在 `task_rules.claude_sonnet45` 加入 `shurangama`，改由 Claude 產出結果檔（較穩定）；或檢查當次 Phase 2 日誌中該 job 的 stdout 預覽（`backend_stdout_preview`）是否顯示錯誤或中斷。

### 1.4 自動任務大量 result_file_missing（Phase 3 用錯 task key）

**症狀**：ntfy 出現「自動任務失敗追蹤（10 項）、原因 result_file_missing」，且多個任務（podcast_jiaoguangzong、ai_deep_research、tech_research、arch_evolution 等）重複失敗；Phase 2 實際可能已產出 `results/todoist-auto-{key}.json`。

**根因**：`plan.auto_tasks.selected_tasks` 為**物件陣列**（每項有 `.key`、`.name` 等）。Phase 3 若以「整個物件」當 task key，PowerShell 會將物件轉成字串 `@{key=podcast_jiaoguangzong; name=...}`，導致：
- 結果檔路徑變成 `todoist-auto-@{ key=... }.json`，永遠找不到檔案；
- `state/failed-auto-tasks.json` 的 `task_key` 被寫成該字串，失敗補跑與 self_heal 讀取時無法對應到純 key。

**已實施修復**（run-todoist-agent-team.ps1）：
1. **Get-NormalizedAutoTaskKey**：從 selected_tasks 項目（物件或字串）取出並正規化為純 key（與 Phase 2 的 key/別名一致）。
2. Phase 3 失敗追蹤改為使用 **normalizedKey** 組 result 路徑並寫入 failed-auto-tasks，使用 **rawKey** 對應 `$sections`（timeout 判斷）。
3. **Update-FailedAutoTasks** 讀取時正規化既有條目的 `task_key`（`@{key=...}` → 純 key），再比對與寫回。

**既有資料修正**：若 `state/failed-auto-tasks.json` 已含錯誤格式的 task_key，可執行一次：
```powershell
pwsh -ExecutionPolicy Bypass -File scripts/normalize-failed-auto-tasks.ps1
```
會將 task_key 正規化為純 key 並依 key 合併重複條目。

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
