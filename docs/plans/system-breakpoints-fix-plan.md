# 系統斷點修補方案與後續優化計畫

> 建立日期：2026-03-15
> 審查範圍：三條系統流程（任務生命週期 / OODA 自癒 / 系統功能進化）+ 模型備援機制
> 斷點總數：39 個（TL-14 + OODA-10 + CE-15）+ 模型備援 6 個

---

## 模型備援機制（已修復）

> 規則：**非 cursor_cli 模型 → cursor_cli 備援；cursor_cli → claude 備援**

### 修復摘要

| 位置 | 修改前 | 修改後 | 狀態 |
|------|--------|--------|------|
| `Get-TaskBackend` codex fallback | `openrouter_research` | `cursor_cli` | ✅ 已修復 |
| `Get-TaskBackend` openrouter fallback | `claude_haiku` | `cursor_cli` | ✅ 已修復 |
| ADR-018 retry：codex timeout | `openrouter → claude_sonnet45` | `cursor_cli → openrouter → claude` | ✅ 已修復 |
| ADR-018 retry：openrouter timeout | 原地重試（無備援） | `cursor_cli → openrouter（原地）` | ✅ 已修復 |
| ADR-018 retry：claude_code timeout | 原地重試（無備援） | `cursor_cli → claude（原地）` | ✅ 已修復 |
| Codex quota fallback | `openrouter → claude_sonnet45` | `cursor_cli → openrouter → claude` | ✅ 已修復 |
| Codex sandbox fallback | 直接 `claude_sonnet45` | `cursor_cli → openrouter → claude` | ✅ 已修復 |
| `all_exhausted_fallback` L1432/1609 | 原本正確 | 保留不變 | ✅ 保留 |
| `cursor_cli` 本身 fallback | `claude_sonnet` | 保留不變 | ✅ 保留 |

### 完整備援鏈（修復後）

```
codex / openrouter / claude
  ↓（不可用或 timeout）
cursor_cli（若有 temp/cursor-cli-task-{key}.md 且 agent CLI 可用）
  ↓（task file 不存在 / agent 不可用）
openrouter_research（若 OPENROUTER_API_KEY 已設定）
  ↓（未設定）
claude_sonnet45（最終兜底）
```

### 已知殘留缺口（P2，不修復）

| 缺口 | 說明 | 風險 |
|------|------|------|
| claude 模型無初始可用性偵測 | `Get-TaskBackend` 對 claude_opus46/sonnet45/haiku 無 API Key 偵測 | 稀有；API 失敗在 Job 層回報 |
| Job.State = "Failed" 無備援 | 非 Completed/Running 狀態缺乏 descriptor 資訊，難以備援 | 稀有；需 Job 啟動時儲存更多 context |

---

## 流程一：任務生命週期（TL）— 14 個斷點

### TL-01 ⬜ Phase 1 計畫格式與 Phase 2 解析不同步
**嚴重度**：P1 | **優先順序**：後期

**症狀**：`tasks[]` 欄位無 JSON schema 定義，Phase 2 解析依賴口頭約定，容易漂移。

**修補方案**：
1. 新建 `config/schemas/todoist-plan.schema.json`（定義 tasks[], auto_tasks[] 結構）
2. Phase 1 輸出前調用 `tools/validate_schema.py results/todoist-plan.json config/schemas/todoist-plan.schema.json`
3. Phase 3 `todoist-assemble.md` 步驟 1 再次驗證，失敗記錄警告但不中斷

---

### TL-02 ⬜ Phase 1 `plan_key` 欄位缺失
**嚴重度**：P1 | **優先順序**：近期

**症狀**：`todoist-query.md` 步驟 3.2 未規範 `plan_key` 來源（是 task_id？是路由 key？）。

**修補方案**：
1. `todoist-query.md` 新增步驟 3.1.5「計算 plan_key」：
   - Tier 1（標籤路由）→ `plan_key = routing.yaml 的對應 key`
   - Tier 2（關鍵字路由）→ `plan_key = 首個匹配 Skill 名稱（底線）`
   - Tier 3（語義）→ `plan_key = 最高優先級 Skill 名稱`
2. 步驟 3.2 輸出 JSON 中必須包含 `plan_key` 欄位

---

### TL-03 ✅ 連字號與底線命名混用（已有保護）
**嚴重度**：P0 | **優先順序**：立即

**症狀**：LLM 易自發將底線轉為連字號，導致 Phase 3 找不到結果檔。

**修補方案**：
1. `todoist-query.md` 步驟 3.2 末尾明確加「⚠️ 結果檔案必須使用底線（_），絕不使用連字號（-）」
2. Phase 3 `todoist-assemble.md` 步驟 1.2 加入路徑正規化：掃描結果目錄，自動將連字號 rename 為底線
3. `hooks/pre_write_guard.py` 新增規則：攔截「todoist-」開頭且含連字號的結果檔寫入

---

### TL-04 ⬜ 結果檔缺失但 Phase 3 無偵測機制
**嚴重度**：P1 | **優先順序**：近期

**症狀**：Phase 2 Agent 超時未產出結果檔，Phase 3 靜默忽略，計數未更新、通知無失敗記錄。

**修補方案**：
1. `todoist-assemble.md` 步驟 1.2 擴展「缺失檔案偵測」：
   - 對每個 selected_tasks，掃描對應 `results/todoist-auto-{key}.json`
   - 不存在 → 立即建立 stub JSON（status=failed, error="Phase 2 未產出結果檔"）
2. Phase 3.3 統計 stub 條目，在通知中列為「失敗任務」

---

### TL-05 ⬜ 快取降級邏輯不完整
**嚴重度**：P2 | **優先順序**：後期

**症狀**：`cache/status.json` 的 valid 欄位預計算責任不清，TTL 計算邏輯未明確定義。

**修補方案**：
1. 新建 `config/schemas/cache-status.schema.json`（含 todoist.valid, cached_at, expires_at）
2. 在 Phase 1 啟動腳本（PowerShell）明確標記「預計算 cache/status.json 是 PowerShell 責任」
3. `todoist-query.md` 步驟 1 明確：「讀取 `cache/status.json`，判斷 `todoist.valid` 欄位」

---

### TL-06 ⬜ Tier 3 語義路由 LLM 決策無約束
**嚴重度**：P2 | **優先順序**：後期

**症狀**：Tier 3 激活條件和 LLM 輸出格式（信心度閾值、JSON vs 自由文字）未定義。

**修補方案**：
1. `config/routing.yaml` 新增 `semantic_routing.activation_condition` 和 `llm_decision_format`
2. LLM 輸出格式標準化：`{processable, confidence, reasoning, suggested_skills}`
3. confidence < 60 → 標記「語義不可判斷」並跳過，不強行執行

---

### TL-07 ⬜ Prompt Injection 檢查缺少通知路徑
**嚴重度**：P1 | **優先順序**：近期

**症狀**：被標記為 `[SUSPICIOUS]` 的任務被靜默跳過，用戶不知道任務被略過。

**修補方案**：
1. 安全關鍵詞清單移至 `config/security-rules.yaml`（正規表達式，大小寫敏感）
2. 計畫 JSON 的 `skipped_tasks` 中記錄 `security_alert: true`
3. Phase 3 通知中若 `security_alert` 存在，加入「⚠️ 安全警告：N 個可疑任務已跳過」

---

### TL-08 ⬜ 跨日邊界 `closed_task_ids` 未明確歸零
**嚴重度**：P2 | **優先順序**：後期

**症狀**：`auto-tasks-today.json` 的 `closed_task_ids` 在跨日時是否清空未被明確說明，可能導致重複關閉防護在新的一天誤觸發。

**修補方案**：
1. `frequency-limits.yaml` 的 `initial_schema` 補充歸零邏輯注釋
2. `todoist-assemble.md` 步驟 3 若今日日期 ≠ JSON 的 date → 重建檔案，`closed_task_ids = []`
3. Phase 3 步驟 2 加防重複關閉邏輯：task_id in closed_task_ids → skip API 呼叫並記錄警告

---

### TL-09 ⬜ ntfy 通知失敗的降級路徑
**嚴重度**：P2 | **優先順序**：後期

**症狀**：`todoist-assemble.md` 步驟 5 的 curl 呼叫失敗時靜默，無記錄。

**修補方案**：
1. 步驟 5 後新增「5.5 發送失敗恢復」：
   - curl 非零退出碼 → 記錄到 `logs/ntfy-failures.jsonl`
   - Fallback：將通知內容寫入 `state/ntfy-draft-{date}.txt` 供手動檢查
2. `on_stop_alert.py` Session 結束時檢查未發送的 ntfy-draft 並告警

---

### TL-10 ⬜ 自動任務輪轉指針競態條件
**嚴重度**：P1 | **優先順序**：近期

**症狀**：多個排程同時觸發時，兩個 Phase 3 同時讀寫 `auto-tasks-today.json`，可能導致輪轉指針回退。

**修補方案**：
1. `todoist-assemble.md` 步驟 3 實現「版本戳樂觀鎖」算法：
   - 步驟 3a：讀取並記錄 `write_version`
   - 步驟 3b：計算新狀態
   - 步驟 3c：寫入前再讀一遍，若版本已變 → 合併（取 count 最大值，保留 next_execution_order）
2. `post_tool_logger.py` 記錄 auto-tasks-today.json 寫入事件（含版本號）

---

### TL-11 ⬜ 自動任務頻率限制無運行時強制
**嚴重度**：P2 | **優先順序**：後期

**症狀**：頻率限制靠 LLM 解讀 YAML，無運行時驗證層，已達上限的任務仍可能被選中。

**修補方案**：
1. 新建 `tools/validate_frequency.py`：驗證 auto_tasks_today 各計數是否超過 frequency-limits.yaml 的 daily_limit
2. Phase 1 完成後呼叫驗證，若違規 → 移除該任務並選下一個

---

### TL-12 ⬜ 聊天室任務佇列集成邊界未標準化
**嚴重度**：P2 | **優先順序**：後期

**症狀**：`todoist-query.md` 步驟 1.5 查詢 bot.js 任務時，健康檢查失敗/認證失敗的結果 JSON 欄位未定義。

**修補方案**：
1. `config/schemas/todoist-plan.schema.json` 新增 `chatroom_status` 欄位
2. `todoist-query.md` 步驟 1.5 明確規範三種狀態（離線/認證失敗/正常）的輸出格式
3. Phase 3 通知中若 `chatroom_status.pending_count > 0` 且未執行 → 加提醒

---

### TL-13 ⬜ Todoist API 版本整合缺乏自動化驗證
**嚴重度**：P1 | **優先順序**：近期

**症狀**：2026-02 遷移至 API v1 後，response 格式（`{results: [...], next_cursor: ...}`）、filter 端點變更等未有自動化驗證。

**修補方案**：
1. 新建 `tests/integration/test_todoist_api.py`：驗證 filter 端點回應格式、close 端點 HTTP code
2. Phase 1 API 呼叫後加「版本驗證」：若 response 無 `.results` 欄位 → 記錄警告並降級使用快取
3. Phase 3 步驟 2.1 關閉任務後驗證 HTTP code（200/204），否則記錄失敗

---

### TL-14 ⬜ 超時配置與實際執行時間的可觀測性不足
**嚴重度**：P2 | **優先順序**：後期

**症狀**：無統計「哪些任務最常超時」的機制，超時配置調整全憑經驗。

**修補方案**：
1. `config/timeouts.yaml` 新增超時計算規則說明注釋
2. Phase 2 Agent prompt 首行加入「⚠️ 本任務預期耗時 {timeout_seconds} 秒，請優先完成核心產出」
3. `check-health.ps1` 新增超時統計：從 structured logs 統計各任務 TIMEOUT 頻率並顯示 Top 5

---

## 流程二：OODA 系統自癒（OODA）— 10 個斷點

### OODA-01 ⬜ Observe / Orient 數據流格式未定義
**嚴重度**：P1 | **優先順序**：立即

**症狀**：system-insight.json（Observe 輸出）→ system-audit（Orient 輸入）的 schema 完全缺失，任何欄位更改都可能無聲失效。

**修補方案**：
1. 新建 `docs/OODA-LOOP.md`，定義四環的輸入/輸出/責任
2. 新建 schema 檔：
   - `config/schemas/system-insight.schema.json`
   - `config/schemas/improvement-backlog.schema.json`
   - `config/schemas/arch-decision.schema.json`
3. 各 Agent prompt 中明確引用對應 schema

---

### OODA-02 ⬜ system-insight.json 冷啟動問題
**嚴重度**：P2 | **優先順序**：近期

**症狀**：首次執行或日誌為空時，system-insight 無法產出合法 JSON，後續 system-audit 失敗。

**修補方案**：
1. `system-insight.md` 步驟 1 新增冷啟動邏輯：數據不足時用預設值，標記 `initialized_from_defaults: true`
2. 新建 `config/system-insight-defaults.yaml`（各指標預設值）
3. system-audit 識別 `initialized_from_defaults: true`，不將其作為改善建議來源

---

### OODA-03 ⬜ improvement-backlog.json 編輯衝突
**嚴重度**：P1 | **優先順序**：立即

**症狀**：system-audit（寫入）與 arch-evolution（修改 decision 欄位）無協調機制，後者可能被前者覆蓋。

**修補方案**：
1. `config/ooda-workflow.yaml` 新增 `file_ownership.improvement-backlog.json`（merge_strategy: union）
2. improvement-backlog.json 每個 item 新增狀態機欄位：`decision_status`（proposed/accepted/deferred/implemented/wontfix）
3. system-audit 再次執行時，保留已決策項的 `decision`、`decided_at`，僅更新「未決策項」

---

### OODA-04 ⬜ arch-decision.json 格式不一致
**嚴重度**：P1 | **優先順序**：立即

**症狀**：arch-evolution 產出 arch-decision.json 的結構未定義，self-heal 讀取時無法確定 action 執行順序。

**修補方案**：
1. 新建 `config/schemas/arch-decision.schema.json`（含 actions[].type/priority/fix_instructions/execution_status）
2. `todoist-auto-arch_evolution.md` 步驟 4 依照 schema 產出
3. self-heal 讀取時先驗證 schema

---

### OODA-05 ⬜ self-heal 多 action 執行順序未定義
**嚴重度**：P2 | **優先順序**：近期

**症狀**：arch-decision 含多個 actions 時，執行順序（優先級/風險/依賴）未定義。

**修補方案**：
1. `config/ooda-workflow.yaml` 新增 `action_execution_order`（P0>P1>P2，safe>moderate>high）
2. self-heal 步驟 2 加入拓撲排序邏輯，跳過 `execution_status=success` 的項目
3. 每次執行一個 action 後更新 arch-decision.json 的 execution_status

---

### OODA-06 ⬜ workflow-state.json 狀態轉移規則缺失
**嚴重度**：P2 | **優先順序**：近期

**症狀**：workflow-state 的狀態轉移圖（observe→orient→decide→act→observe）及失敗時的回退規則未定義。

**修補方案**：
1. 新建 `config/schemas/workflow-state.schema.json`（含 state_transitions 規則）
2. `config/ooda-workflow.yaml` 補充狀態轉移規則（各環節 timeout、失敗回退規則）
3. `max_consecutive_failures: 3` 後自動停止 OODA 並告警

---

### OODA-07 ⬜ 優先級評分可追溯性不足
**嚴重度**：P2 | **優先順序**：後期

**症狀**：improvement-backlog 的 P0/P1/P2 評分來源不明，二次審計無法重現。

**修補方案**：
1. `config/audit-scoring.yaml` 新增 `priority_mapping`（指標 → 優先級 mapping）
2. system-audit 產出時記錄 `priority_reason` 和 `scored_indicators`
3. 已人工調整過 priority 的項目標記 `manually_adjusted: true`，system-audit 不自動重設

---

### OODA-08 ⬜ Act 結果無反饋給下一輪 Observe
**嚴重度**：P1 | **優先順序**：立即

**症狀**：self-heal 執行結果（success/failed）不回饋給 arch-decision.json 和 system-insight，下一輪 OODA 無法感知上一輪的修復結果。

**修補方案**：
1. self-heal 步驟 2.5（每個 action 後）更新 arch-decision.json 的 execution_status/executed_at/failure_reason
2. self-heal 完成後發 ntfy 摘要（成功 N / 失敗 M）
3. system-insight 步驟 1 新增「前次 Act 結果分析」：讀 arch-decision.json 的 failed actions，計入 `recent_act_failures` 欄位

---

### OODA-09 ⬜ 多排程同時觸發的 OODA 協調問題
**嚴重度**：P1 | **優先順序**：近期

**症狀**：run-system-audit-team.ps1 與 run-todoist-agent-team.ps1 的 OODA Act 邏輯可能同時執行，競爭 arch-decision.json。

**修補方案**：
1. 新建 `state/ooda-lock.json`（locked_by, locked_at, expected_release_time）
2. self-heal 執行前獲取鎖，完成後刪除
3. 若鎖超時 > 30 分鐘 → 強制清除（防死鎖）
4. `check-health.ps1` 定期檢查孤立鎖（> 1 小時）並清理

---

### OODA-10 ⬜ self-heal 的「安全邊界」未定義
**嚴重度**：P2 | **優先順序**：近期

**症狀**：`immediate_fix` 的「自動執行」界限模糊，可能刪除重要檔案或修改核心腳本。

**修補方案**：
1. `config/ooda-workflow.yaml` 新增 `safe_boundaries`：
   - 允許：新增檔案、更新 YAML 配置、刪除過期快取、更新 state/*.json
   - 禁止：刪除 .git/.claude/.github、修改核心 .ps1 腳本、修改 hook-rules.yaml、git reset --hard
2. arch-evolution 決策時，僅將 safe_boundaries 內的操作標記為 `immediate_fix`，其餘標記為 `schedule_adr`
3. self-heal 對每個 action 進行權限檢查，不符合則標記 `schedule_adr`，等待人工審核

---

## 流程三：系統功能進化（CE）— 15 個斷點

### CE-01 ⬜ Skill 開創性門檻評估主觀
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. 新建 `tools/originality_check.py`：計算新 Skill 與現有 Skill 的功能覆蓋率（>= 80% → 排除）
2. skill-forge 步驟 2b 改為量化門檻

---

### CE-02 ⬜ KB 研究輸出格式與 Skill 生成輸入不匹配
**嚴重度**：P2 | **優先順序**：近期

**修補方案**：
1. 新建 `config/schemas/kb-research-brief.schema.json`（含 synthesis/confidence_score/gaps）
2. confidence_score < 0.7 → 生成 scaffold + TODO 標記（不拒絕但明確標記不完整）

---

### CE-03 ⬜ Skill 格式驗證規則不完整
**嚴重度**：P2 | **優先順序**：近期

**修補方案**：
1. 新建 `tools/validate_skill_format.py`（frontmatter 完整性、字數、無硬編碼路徑）
2. skill-forge 步驟 5b 呼叫此工具；驗證失敗 → 嘗試自動修復 → 仍失敗 → 寫入 `state/skill-forge-failures.json`

---

### CE-04 ⬜ Skill 自評分標準模糊
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. 新建 `config/skill-quality-rubric.yaml`（5 項評分標準，每項 1-3 分，總分 10，閾值 7）
2. 自評 < 7 → 加入 `state/skill-forge-reviews.json`（人工審核隊列）
3. `check-health.ps1` 提醒「有 N 個 Skill 待人工審核」

---

### CE-05 ⬜ Skill 安全掃描規則集未定義
**嚴重度**：P1 | **優先順序**：立即

**修補方案**：
1. 新建 `config/skill-security-rules.yaml`：
   - `reject`：硬編碼密鑰（TODOIST_API_TOKEN/GROQ_API_KEY 等）
   - `warn`：危險命令（rm -rf、git reset --hard）、unsafe Python（eval/exec/shell=True）
2. skill-scanner 按此規則掃描，產出 `{violations, can_proceed}` JSON
3. skill-forge 根據 `can_proceed` 決定是否繼續

---

### CE-06 ⬜ SKILL_INDEX.md 自動更新機制缺口
**嚴重度**：P2 | **優先順序**：近期

**修補方案**：
1. 新建 `tools/update-skill-index.py`：自動將新 Skill 插入正確分類（按字母序）
2. skill-forge 步驟 6 整合至 SKILL_INDEX.md 時呼叫此工具

---

### CE-07 ⬜ Skill 鑄造失敗後的恢復流程
**嚴重度**：P2 | **優先順序**：近期

**修補方案**：
1. 新建 `config/skill-forge-recovery.yaml`（各步驟失敗的 action：retry/rollback/escalate）
2. 失敗時寫入 `state/skill-forge-failures.json`（含失敗步驟、原因、中間檔路徑）

---

### CE-08 ⬜ 新 Skill 與現有任務的綁定機制
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. skill-forge 步驟 6.5（新增）：掃描 frequency-limits.yaml，推薦哪些任務可使用新 Skill
2. 結果記錄到 `state/skill-adoption-plan.json`，等待人工確認後才更新任務配置

---

### CE-09 ⬜ Skill 版本 breaking change 無自動偵測
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. SKILL.md frontmatter 新增 `breaking_changes` 欄位
2. skill-forge 生成時若含 breaking change → 自動標記 `needs_migration`
3. `check-health.ps1` 顯示「有 N 個 Skill 需要遷移」

---

### CE-10 ⬜ Skill 文件化品質標準缺失
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. 新建 `config/skill-documentation-standard.md`（必填段落、品質清單）
2. skill-forge 步驟 5 生成時依照標準檢查，不符合加 TODO 標記

---

### CE-11 ⬜ improvement-backlog 與 Skill 的雙向關聯缺失
**嚴重度**：P2 | **優先順序**：近期

**修補方案**：
1. improvement-backlog.json 各 item 新增欄位：`resolved_by_skill`、`skill_references`
2. skill-forge 完成後回寫 improvement-backlog.json（resolved_by_skill = skill_name, status = implemented）
3. system-audit 跳過已被 Skill 解決的項目

---

### CE-12 ⬜ skill-forge 與 self-heal 的 Skill 檔案競態
**嚴重度**：P1 | **優先順序**：立即

**症狀**：skill-forge 生成新 Skill 時，self-heal 同時修復同一 Skill，導致版本衝突。

**修補方案**：
1. 新建 `state/skill-write-lock.json`（locked_skill, locked_by, locked_at, expected_release）
2. skill-forge 選定 Skill 後檢查是否被鎖；若被鎖 → 延遲（選次高優先級）或等待（max 10 分鐘）
3. self-heal 完成後刪除鎖

---

### CE-13 ⬜ Skill 試用期機制缺失
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. SKILL.md frontmatter 新增 `status: beta|stable` 和 `beta_until`
2. frequency-limits.yaml 對 beta Skill 任務自動限制執行次數（`beta_max_tasks_per_day: 2`）
3. `check-health.ps1` 統計 beta Skill 成功率；>= 90% → 建議升級；< 70% 且試用期滿 → 建議回滾

---

### CE-14 ⬜ Skill Forge 資源配額未定義
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. 新建 `config/skill-forge.yaml`：`max_total_skills: 60`、`max_skills_per_day: 1`、`max_beta_skills: 5`
2. skill-forge 執行前檢查是否超過配額；若超過 → 改為執行「Skill 審查與淘汰」流程
3. 淘汰規則：最舊的 beta Skill 或過去 7 天無任務使用的 stable Skill

---

### CE-15 ⬜ Skill Forge 成功率追蹤缺失
**嚴重度**：P2 | **優先順序**：後期

**修補方案**：
1. 新建 `state/skill-forge-metrics.json`（generated_skills 陣列，各含 adoption_count/execution_count/success_rate）
2. `check-health.ps1` 每週統計 Skill 成功率趨勢
3. 連續 7 天成功率 < 70% → 自動標記 `needs_improvement`
4. skill-forge 生成時讀取 metrics，參考過往失敗原因

---

## 優先順序總覽

### P0/立即（7 項）

| 斷點 | 動作 |
|------|------|
| TL-03 | `pre_write_guard.py` 攔截規則 + assemble 路徑正規化 |
| OODA-01 | 新建 `docs/OODA-LOOP.md` + 三個 schema 檔 |
| OODA-03 | improvement-backlog 狀態機 + merge 策略 |
| OODA-04 | `config/schemas/arch-decision.schema.json` |
| OODA-08 | self-heal 回寫 arch-decision.json + ntfy 摘要 |
| CE-05 | `config/skill-security-rules.yaml` + skill-scanner 更新 |
| CE-12 | `state/skill-write-lock.json` 競態保護 |

### P1/近期（8 項）

TL-02, TL-04, TL-07, TL-10, TL-13, OODA-09, CE-03, CE-06

### P2/後期（24 項）

TL-01, TL-05, TL-06, TL-08, TL-09, TL-11, TL-12, TL-14,
OODA-02, OODA-05, OODA-06, OODA-07, OODA-10,
CE-01, CE-02, CE-04, CE-07, CE-08, CE-09, CE-10, CE-11, CE-13, CE-14, CE-15

---

## 新建檔案清單（全計畫）

| 檔案 | 用途 | 優先度 |
|------|------|--------|
| `docs/OODA-LOOP.md` | OODA 四環資料流定義 | 立即 |
| `config/schemas/todoist-plan.schema.json` | Phase 1 計畫 JSON schema | 近期 |
| `config/schemas/cache-status.schema.json` | 快取狀態 schema | 後期 |
| `config/schemas/system-insight.schema.json` | Observe 輸出 schema | 立即 |
| `config/schemas/improvement-backlog.schema.json` | Orient 輸出 schema | 立即 |
| `config/schemas/arch-decision.schema.json` | Decide 輸出 schema | 立即 |
| `config/schemas/workflow-state.schema.json` | OODA 狀態機 schema | 近期 |
| `config/schemas/kb-research-brief.schema.json` | KB 研究輸出 schema | 近期 |
| `config/system-insight-defaults.yaml` | Observe 冷啟動預設值 | 近期 |
| `config/security-rules.yaml` | Prompt injection 關鍵詞 | 近期 |
| `config/skill-quality-rubric.yaml` | Skill 自評分標準 | 後期 |
| `config/skill-security-rules.yaml` | Skill 安全掃描規則 | 立即 |
| `config/skill-forge-recovery.yaml` | 鑄造失敗恢復規則 | 近期 |
| `config/skill-documentation-standard.md` | Skill 文件化標準 | 後期 |
| `config/skill-forge.yaml` | Skill 資源配額配置 | 後期 |
| `tools/originality_check.py` | Skill 開創性量化評估 | 後期 |
| `tools/validate_skill_format.py` | SKILL.md 格式驗證 | 近期 |
| `tools/update-skill-index.py` | SKILL_INDEX.md 自動更新 | 近期 |
| `tools/validate_frequency.py` | 頻率限制運行時驗證 | 後期 |
| `tests/integration/test_todoist_api.py` | Todoist API 版本驗證 | 近期 |
| `state/ooda-lock.json` | OODA 互斥鎖 | 近期 |
| `state/skill-write-lock.json` | Skill 編輯互斥鎖 | 立即 |
| `state/skill-forge-reviews.json` | Skill 人工審核隊列 | 後期 |
| `state/skill-forge-failures.json` | 鑄造失敗記錄 | 近期 |
| `state/skill-forge-metrics.json` | Skill 成功率追蹤 | 後期 |
| `state/skill-adoption-plan.json` | Skill 採用候選清單 | 後期 |

---

*文件維護：arch-evolution Skill 在每次 ADR 決策後更新此計畫的完成狀態（⬜→✅）*
