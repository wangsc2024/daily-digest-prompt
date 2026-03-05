# Daily Digest Prompt - 運維手冊

> 本文件由 `docs/OPERATIONS.md` 維護，對應 CLAUDE.md 的「執行流程」與「Hooks 機器強制層」引用。

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
2. **Phase 0**：PS 預計算快取狀態，生成 `cache/status.json`（LLM 直接讀 valid 欄位，不計算時間差）
3. **Phase 1**：用 `Start-Job` 同時啟動 5 個 `claude -p`（Todoist + 新聞 + HN + Gmail + 安全審查）
4. 各 Agent 讀取 `cache/status.json` 判斷是否命中快取；結果寫入 `results/*.json`
5. 等待全部完成（timeout 300s），收集各 Agent 狀態；完成後 PS 回寫快取
6. **Phase 2**：啟動組裝 Agent 讀取 `results/*.json`（timeout 420s）
7. 組裝 Agent 加上政策解讀、習慣提示、學習技巧、知識庫查詢、禪語
8. 整理完整摘要 → ntfy 推播 → 更新記憶/狀態 → 清理 results/
9. Phase 2 失敗可自動重試一次（間隔 60 秒）
10. 預期耗時約 1 分鐘（快取命中）～ 2 分鐘（全部 API 呼叫）

### Todoist 任務規劃 - 單一模式（run-todoist-agent.ps1）
1. Windows Task Scheduler 觸發 `run-todoist-agent.ps1`（timeout 2100s）
2. Agent 載入共用前言 + Skill 索引（~140 行薄層調度器）
3. 讀取 `config/routing.yaml` 取得三層路由規則 + `config/frequency-limits.yaml` 取得頻率限制
4. 查詢 Todoist → 依 routing.yaml 路由 → 按 `config/scoring.yaml` 計分排序
5. 子 Agent 模板從 `templates/sub-agent/` 按需載入（不預載）
6. 無可處理項目或全部完成時，自動任務 prompt 從 `templates/auto-tasks/` 按需載入
7. 品質驗證依 `templates/shared/quality-gate.md` + `templates/shared/done-cert.md`
8. 通知格式依 `config/notification.yaml`
9. **自動任務頻率限制**（config/frequency-limits.yaml）：19 個任務，合計 47 次/日上限，round-robin 輪轉
10. **研究任務 KB 去重**（templates/sub-agent/research-task.md）：研究前先查詢知識庫避免重複

### Todoist 任務規劃 - 團隊並行模式（run-todoist-agent-team.ps1，推薦）
1. Windows Task Scheduler 觸發 `run-todoist-agent-team.ps1`
2. **Phase 1**：1 個查詢 Agent（Todoist 查詢 + 過濾 + 路由 + 規劃，timeout 420s）
3. 輸出計畫類型：`tasks`（有待辦）/ `auto`（觸發自動任務）/ `idle`（跳過）
4. **Phase 2**：N 個並行執行 Agent（依計畫分配，動態 timeout 按任務類型計算）
   - research: 600s、code: 900s、skill/general: 300s、auto: 600s、gitpush: 360s
5. **Phase 3**：1 個組裝 Agent（關閉任務 + 更新狀態 + 推播通知，timeout 180s）
6. Phase 3 失敗可自動重試一次（間隔 60 秒）

### 每日系統審查 - 團隊並行模式（run-system-audit-team.ps1，推薦）

每日 00:40 自動執行，使用 `system-audit` Skill 評估 7 個維度、38 個子項：

1. Windows Task Scheduler 觸發 `run-system-audit-team.ps1`
2. **Phase 0**：PS 預計算快取狀態，生成 `cache/status.json`
3. **Phase 1**：用 `Start-Job` 同時啟動 4 個 `claude -p` 並行審查
   - Agent 1: 評估維度 1（資訊安全）+ 維度 5（技術棧），輸出 `results/audit-dim1-5.json`
   - Agent 2: 評估維度 2（系統架構）+ 維度 6（系統文件），輸出 `results/audit-dim2-6.json`
   - Agent 3: 評估維度 3（系統品質）+ 維度 7（系統完成度），輸出 `results/audit-dim3-7.json`
   - Agent 4: 評估維度 4（系統工作流），輸出 `results/audit-dim4.json`
4. 等待全部完成（timeout 600s），收集各 Agent 狀態
5. **Phase 2**：啟動組裝 Agent 讀取 Phase 1 的 4 個 JSON（timeout 1200s）
6. 組裝 Agent 計算加權總分 → 識別問題 → 自動修正（最多 5 項）→ 生成報告 → 寫入 RAG → 更新狀態
7. Phase 2 失敗可自動重試一次（間隔 60 秒）
8. 預期耗時約 15-20 分鐘（單一模式需 25-30 分鐘）

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

---

## Hooks 機器強制層（Harness Enforcement）

從「Agent 自律」升級到「機器強制」。透過 Claude Code Hooks 在 runtime 攔截工具呼叫，違規操作在執行前就被阻斷。

### 設定檔
`.claude/settings.json`（專案級，commit 到 repo，所有開發者共享）
Hook 命令格式：`uv run --project D:/Source/daily-digest-prompt python D:/Source/daily-digest-prompt/hooks/<hook>.py`

### Hook 清單

| Hook | 類型 | Matcher | 用途 |
|------|------|---------|------|
| `pre_bash_guard.py` | PreToolUse | Bash | 攔截 nul 重導向、scheduler-state 寫入、危險刪除、force push、敏感環境變數讀取、機密外洩 |
| `pre_write_guard.py` | PreToolUse | Write, Edit | 攔截 nul 檔案建立、scheduler-state 寫入、敏感檔案寫入、路徑遍歷攻擊 |
| `pre_read_guard.py` | PreToolUse | Read | 攔截敏感系統路徑（.ssh/.gnupg）、敏感檔案（.env/credentials）、Windows 憑據路徑 |
| `post_tool_logger.py` | PostToolUse | *（所有工具） | 結構化 JSONL 日誌，自動標籤分類，50MB 緊急輪轉 |
| `cjk_guard.py post-fix` | PostToolUse | Write, Edit | CJK 字元守衛（日文 Unicode 變體修正） |
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
| `skill-modified` | Write/Edit SKILL.md | SKILL.md 修改追蹤 |

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
| SKILL.md 修改 | skill-modified > 0 | info（附修改路徑清單） |
| 全部正常 | 無上述問題 | 不告警（靜默記錄 session-summary） |

告警透過 ntfy 推送到 `wangsc2025`，含：呼叫統計、攔截詳情、錯誤摘要。

### 查詢結構化日誌

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

# JSON 輸出（供程式處理）
uv run python hooks/query_logs.py --format json
```

### 前置需求
- Python 3.11+（由 uv 管理，`uv sync` 安裝所有依賴）
- uv（`pip install uv` 或 `winget install astral-sh.uv`）
- 依賴宣告於 `pyproject.toml`，`requirements.txt` 已廢棄
- Windows 環境使用 `uv run python`（非裸 `python`，因 Windows Store 的 `python3` 空殼會靜默失敗）

---

## Hook 規則外部化

規則定義在 `config/hook-rules.yaml`（v3，20 條規則）：
- Bash 守衛規則：13 條（nul重導向、scheduler-state、危險刪除、force push、環境變數、外洩防護等）
- Write 守衛規則：4 條（nul寫入、scheduler-state、敏感檔案、路徑遍歷）
- Read 守衛規則：3 條（敏感路徑、Windows 憑據）
- 三個 preset（strict/normal/permissive），Hook 執行時載入 YAML，失敗回退硬編碼規則
