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

### 1.5 LINE 指派研究型任務執行失敗（Codex model refresh timeout）

**症狀**：透過 LINE/Gun 聊天室指派的「研究型」任務（如「詳細研究禪宗」）回傳「任務完畢」，但結果內容為 Codex 錯誤訊息，例如：
- `ERROR codex_core::models_manager::manager: failed to refresh available models: timeout waiting for child process to exit`
- 其後可能還有 `Reading prompt from stdin...`、`OpenAI Codex v0.111.0`、`## Cursor CLI 與 Skill-First 指引` 等片段（即錯誤輸出被當成任務結果回傳）。

**根因**：Codex CLI 啟動時會刷新可用模型清單（spawn 子程序）；若該子程序逾時未結束（網路、防毒、或 Codex 本身逾時設定過短），會印出上述 ERROR 並可能以非零 exit 結束。腳本若未正確偵測失敗，會把 Codex 的 stderr/stdout 當成任務結果送回聊天室。

**已實施行為**（bot/process_messages.ps1）：
1. **失敗偵測**：Codex 執行後檢查 (1) `$LASTEXITCODE -ne 0`、(2) 輸出是否含 `failed to refresh available models`、`timeout waiting for child process to exit` 或 `ERROR codex_core`。
2. **重試一次**：第一次偵測到失敗時自動再執行一次 Codex。
3. **Fallback 至 Cursor CLI**：重試仍失敗則改以 `agent -p ... --model composer-1.5` 執行同一任務，並將該輸出作為結果回傳，避免把錯誤訊息當成結果。

**若仍常發生**：
- 手動在終端執行一次 `codex exec --full-auto -m gpt-5.4` 並輸入一句簡單指令，確認是否能正常完成（若手動也逾時，為 Codex/環境問題）。
- 更新 Codex CLI 至最新版（該錯誤可能已在後續版本修正）。
- 檢查網路與防毒是否阻擋或延遲 Codex 子程序；必要時暫時關閉即時掃描對 `codex.exe` 的掃描。
- 不需停用研究型任務：腳本會自動 fallback 至 Cursor CLI，任務仍會完成，僅執行後端由 Codex 改為 Cursor。

### 1.5 已處理完的任務未回傳結果至 Gun/LINE

**症狀**：Worker（process_messages.ps1）已執行完任務並呼叫 `/processed`，但聊天室或 LINE 未收到「任務完畢」的結果。

**回傳流程**：Worker 呼叫 `PATCH /api/records/:uid/processed`（body 含 `claim_generation`、`result`）→ bot 的 `markProcessed()` → 若狀態為 `completed` 且 `result != null`，呼叫 `sendReply()`（即 `sendSystemReply`）→ 加密後寫入 Gun relay；LINE 來源則另由 relay 或 bot 的 LINE push 回傳。

**常見原因與排查**：

| 原因 | 說明 | 如何確認 |
|------|------|----------|
| **1. sharedSecrets 為空** | Bot 未與 my-gun-relay（或任一客戶端）完成 ECDH 握手，`sendSystemReply` 直接 return，不寫入 Gun。 | Bot 日誌出現 `[sendSystemReply] 無已連線節點（sharedSecrets 為空）`；或 `[routes/processed] 未回傳至 Gun relay：sendReply 不可用`。 |
| **2. /processed 回傳 400（invalid_state）** | 任務在 store 內不是 `processing`（例如 Worker 未成功做「狀態→processing」即完成工作並呼叫 /processed）。 | Bot 日誌出現 `[routes/processed] 未回傳至聊天室：任務狀態非 processing`；Worker 日誌可能有「狀態轉換為 processing 失敗」後仍繼續執行（舊版腳本）。 |
| **3. /processed 回傳 409（stale_claim）** | 認領逾時後被釋放，Worker 仍用舊的 `claim_generation` 呼叫 /processed，bot 拒絕並未發送回覆。 | Worker 日誌出現 `[WARN] /processed 回傳 409（認領已過期）`。 |
| **4. Worker 未呼叫 /processed** | 腳本在完成工作前逾時被 kill、或例外未進入 Step 4，結果未送給 bot。 | Worker 日誌無「狀態已更新為 completed」；chatroom-scheduler 日誌可能有「process_messages.ps1 超時」。 |
| **5. result 未帶入 body** | 請求 body 遺失或 `result` 為 null，route 內不呼叫 `sendReply`。 | 檢查 Worker 組裝的 `$completeBody` 與實際 HTTP 請求；bot 端無對應錯誤時多為 body/編碼問題。 |

**建議動作**：
1. 確認 **my-gun-relay**（如 https://gun-relay-bxdc.onrender.com/gun）已啟動，且 bot 的 `GUN_RELAY_URL` 指向該 relay；relay 會自行註冊為「客戶端」，握手成功後 `sharedSecrets` 即有值。
2. 查 **bot 主機日誌**：是否有上述 `[sendSystemReply]` 或 `[routes/processed]` 的警告。
3. 查 **Worker 日誌**（`bot/logs/task_log_*.log`）：是否有「狀態轉換為 processing 失敗」、`/processed 回傳 400/409`、或缺少「狀態已更新為 completed」。

### 1.6 任務執行超過 X 分鐘會不會一直執行同一個任務？

**兩種逾時**（`bot/lib/fsm.js`，依「單任務預估 5–30 分鐘」原則設定）：

| 類型 | 用途 | 目前設定（各類型一致） |
|------|------|------------------------|
| **Claim timeout** | 任務在 **claimed** 狀態若超過此時長未轉成 processing，會被釋放回 pending | 5 分鐘 |
| **Processing timeout** | 任務在 **processing** 狀態若超過此時長（從 claimed_at 起算），會被回收回 pending（worker 崩潰/卡住時恢復） | 45 分鐘（30 min + 緩衝） |

**「執行超過 5 / 45 分鐘」**：
- Worker 認領後通常數十秒內就會 PATCH 成 `processing`，所以「任務跑 5–30 分鐘」**不會**觸發 claim 釋放。
- 會造成「同一任務被重複執行」或「跑完卻回傳失敗」的，是 **processing 逾時**：若**單次執行時間 > 45 分鐘**，bot 每分鐘的 `recoverStaleProcessing()` 會把該任務改回 pending，原 Worker 呼叫 `/processed` 會得到 **409 stale_claim**，其他輪次可能再認領（已用 `last_released_at` 排序減輕）。

**結論**：在 5–30 分鐘預估下，45 分鐘 processing timeout 足以涵蓋；若偶有任務需超過 45 分鐘，可調高 `fsm.js` 的 `PROCESSING_TIMEOUTS` 對應類型。

### 1.7 測試 LINE 各類型任務回傳（模擬指派 → 完成 → 回傳）

**目的**：驗證從 LINE 指派 general / code / podcast / detail / kb_answer / research 各類型任務，直至結果均能正常回傳至 Gun relay（及 LINE）。

**腳本**：`bot/test-line-task-types.mjs`

**前置**：bot 與 my-gun-relay 皆須運行；relay 需已與 bot 完成握手（sharedSecret 存在）；relay 的 LINE webhook 需可從本機或 CI 存取。

**環境變數**（執行前設定，或寫入 `bot/.env` 後 `node --env-file=bot/.env bot/test-line-task-types.mjs`）：

| 變數 | 必填 | 說明 |
|------|------|------|
| `RELAY_LINE_WEBHOOK_URL` | 是 | relay 的 LINE webhook 網址，例：`https://gun-relay-bxdc.onrender.com/api/line-webhook` |
| `LINE_CHANNEL_SECRET` | 是 | 與 relay 的 `.env` 一致，用於簽章驗證（HMAC-SHA256） |
| `LINE_TEST_USER_ID` | 否 | 模擬的 LINE userId，relay 會用此 ID 推回 LINE；預設為測試用 ID |
| `BOT_API` | 否 | 預設 `http://127.0.0.1:3001` |
| `RELAY_API_SECRET` | 否 | relay 的 API_SECRET_KEY，用於測試結束後 GET `/api/replies` 驗證 |

**用法**：

```bash
cd D:\Source\daily-digest-prompt

# 僅發送 6 則 LINE webhook 事件（各類型一則）到 relay
node --env-file=bot/.env bot/test-line-task-types.mjs inject

# 僅對目前 pending 的 line_* 任務模擬 Worker 完成（claim → processing → /processed）
node --env-file=bot/.env bot/test-line-task-types.mjs complete

# 完整流程：inject → 等待 bot 建立 line_* 記錄 → complete → 可選驗證 /api/replies
node --env-file=bot/.env bot/test-line-task-types.mjs full
```

**驗證「回傳至 LINE」**：若 relay 已設定 `LINE_CHANNEL_ACCESS_TOKEN` 且 `LINE_TEST_USER_ID` 為真實 LINE 用戶 ID，完成後該用戶應收到 6 則「任務完畢」推播。若僅驗證 Gun/relay 路徑，可設定 `RELAY_API_SECRET`，腳本會 GET relay 的 `/api/replies` 檢查回覆筆數。

### 1.8 研究型任務出現「WebSearch/WebFetch 被拒絕」

**症狀**：研究報告結果中註明「WebSearch/WebFetch 遭拒絕，未取得外部權威來源」，內容僅依專案內資源與既有知識產出。

**原因**：
- **研究型任務**優先以 Codex（`codex exec --full-auto -m gpt-5.4`）執行，Codex 具內建 Web 搜尋；若 Codex 失敗或不可用，會 **fallback 至 Cursor CLI**（`agent -p ... --trust`）。
- Cursor Agent CLI 在 **print 模式**（無頭/排程）下，**WebFetch** 依專案或全域權限設定（未允許時每次 fetch 需審核，無頭時即被拒絕）；**WebSearch** 在部分 CLI 環境下可能預設關閉。

**已實施修復與優化**：
1. **專案權限**：新增 `.cursor/cli.json`，在 `permissions.allow` 中加入 `WebFetch(*)`，使排程執行時 WebFetch 無需逐次審核即可使用（僅限本專案目錄下執行之 agent）。
2. **研究 fallback 加 --force**：當 Codex 失敗改走 `agent -p` 時，`process_messages.ps1` 已改為傳入 `--force`，讓 print 模式下允許寫檔與工具使用，減少「被拒絕」。
3. **前言說明**：研究工作流前言已改為「若 WebSearch/WebFetch 被拒絕，則依專案內資源與既有知識產出，並於報告中註明『未取得外部網路來源』」，報告產出與註明方式一致。

**若仍出現被拒絕**：
- 確認 **Codex 可用**（研究型會優先使用 Codex 內建 Web 搜尋）：命令列執行 `codex exec --full-auto -m gpt-5.4` 測試。
- 確認本專案根目錄存在 **`.cursor/cli.json`** 且含 `WebFetch(*)`（或至少允許目標網域）。
- Cursor CLI 若仍不提供 WebSearch 給 print 模式，研究報告會持續以專案內資源＋既有知識產出並註明，屬預期降級行為。

**Codex 失敗（exit code 1）與 fallback**：
- 日誌會寫入 **`[Codex 失敗輸出摘要]`** 與 **`[Codex 重試仍失敗輸出摘要]`**（前 600 字），可據此判斷原因。
- 常見原因：**用量上限**（`You've hit your usage limit`）→ 等至提示時間或聯絡管理員；**model refresh 逾時** → 重試或改用 Cursor CLI fallback。
- Fallback 時會改用 **Cursor CLI（agent）**；若排程環境報「agent 不是可辨識的指令」，腳本已改為啟動時解析 `agent` 絕對路徑（`~/.local/bin/agent.exe`、`%APPDATA%\npm\agent.cmd` 等），請確認 Cursor CLI 已安裝且該路徑存在。

**單次測試「八識規矩頌深入研究報告」**（驗證研究型 + Codex/fallback + WebFetch）：
1. 注入一筆研究任務：`node bot/scripts/inject-one-research-task.mjs "提出八識規矩頌的深入研究報告"`
2. 重啟 bot（讓 store 重新載入 `bot/data/records.json`）
3. 執行：`pwsh -ExecutionPolicy Bypass -File bot/process_messages.ps1`（會處理第一筆 pending）
4. 查看 `bot/logs/task_log_<日期>.log`：若有 Codex 失敗會出現 `[Codex 失敗輸出摘要]`（含用量上限等）；fallback 成功會出現「Cursor CLI (composer-1.5, Codex fallback)」與任務完畢。

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
