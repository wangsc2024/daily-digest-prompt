---
name: task-manager
version: "1.2.0"
description: |
  標準化新增自動任務、排程任務及單次任務的完整流程。
  消除手動觸碰 6-7 個檔案的遺漏風險，提供自動驗證。
  Use when: 使用者手動要求新增任務、新增自動任務、增加排程、新增排程任務、單次執行、任務管理。
  Note: 此為互動式工具 Skill，由使用者手動觸發，不透過 Todoist 自動路由。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
cache-ttl: N/A
triggers:
  - "新增任務"
  - "新增自動任務"
  - "增加排程"
  - "新增排程任務"
  - "單次執行"
  - "task-manager"
  - "任務管理"
  - "add task"
  - "新增排程"
  - "自動任務管理"
  - "round-robin"
---

# Task Manager Skill — 任務新增標準化

## 使用場景

此 Skill 為**互動式工具**，在以下場景由使用者手動觸發：
- 使用者在 Claude Code 對話中要求新增自動任務（模式 A）
- 使用者要求新增 Windows Task Scheduler 排程（模式 B）
- 使用者要求單次執行某個任務（模式 C）

**不適用場景**：Todoist 自動路由、自動化排程。此 Skill 不在 routing.yaml 中映射。

## 模式判定

根據使用者意圖自動選擇模式：

| 關鍵字 | 模式 | 說明 |
|--------|------|------|
| 「自動任務」「auto-task」「round-robin」「每天執行N次」 | **模式 A** | 自動任務，daily_limit 1-5 |
| 「排程」「定時」「cron」「每小時」「每天」且為循環 | **模式 B** | 排程任務，循環執行 >=2 次 |
| 「單次」「一次」「立即執行」「只跑一次」 | **模式 C** | 單次任務，恰好 1 次 |

模式 C 細分：
- 有指定時間 -> **C-2**（定時單次）
- 無指定時間 -> **C-1**（立即執行）

---

## 三種任務類型定義

| 類型 | 定義 | 執行次數 | 觸發方式 | 需觸碰的核心檔案 |
|------|------|---------|---------|----------------|
| **自動任務** | 無 Todoist 待辦時 round-robin 執行 | 每日 <= 5 次 | Todoist Agent 空閒時自動觸發 | frequency-limits.yaml + 2 模板 + PS1 映射 |
| **排程任務** | Windows Task Scheduler 定時循環觸發 | 循環（>=2 次） | cron 定時 | HEARTBEAT.md + run-*.ps1 + setup-scheduler |
| **單次任務** | 僅執行 1 次即完成 | 恰好 1 次 | 立即或定時單次 | prompt 檔案 + `claude -p` 或 Windows 一次性排程 |

---

## 模式 A：新增自動任務（add-auto-task）

### Step 1：收集任務規格

向使用者收集或從上下文推斷以下資訊：

```yaml
task_key: "新任務的英文 key（snake_case，如 ai_deep_research）"
task_name: "中文名稱（如「AI 深度研究計畫」）"
daily_limit: 數字  # 必填，1-5（硬限制，超過 5 自動截斷並警告）
group: "佛學研究 | AI/技術研究 | 系統優化 | 系統維護 | 遊戲創意 | 專案品質"
skills: ["相關 skill 名稱"]
description: "一句話描述"
template_params: {}  # 可選（如佛學研究的 subject/author/search_terms）
```

**daily_limit 硬限制**：單一自動任務每日最多 5 次。
理由：15+ 任務 round-robin，每任務 5 次已足夠覆蓋，避免單一任務獨佔 slots。

### Step 2：自動計算衍生值

```
counter_field: "{task_key}_count"
execution_order: 現有最大值 + 1（讀取 frequency-limits.yaml 計算）
template_path: "templates/auto-tasks/{task_key 轉 hyphen}.md"
team_prompt_path: "prompts/team/todoist-auto-{task_key 轉 hyphen}.md"
```

### Step 3：前置讀取

執行以下 Read 操作確認現有狀態：

1. `Read config/frequency-limits.yaml`
   - 取得現有 task 清單
   - 確認最大 execution_order 值
   - 確認 counter_field 不與現有重複
2. `Read templates/auto-tasks/` 目錄中任一現有模板
   - 作為格式參考

> **注意**：`run-todoist-agent-team.ps1` 已改為動態掃描（`Get-ChildItem todoist-auto-*.md`），無需讀取或修改 PS1 映射。

### Step 4：依序生成/修改 6 個檔案

#### 4.1 Edit — frequency-limits.yaml 追加 task 定義

在最後一個 task 定義之後、`# ============` 分隔線之前插入：

```yaml
  {task_key}:
    name: "{task_name}"
    daily_limit: {daily_limit}
    counter_field: "{task_key}_count"
    template: "templates/auto-tasks/{task_key_hyphen}.md"
    history_type: "{task_key}"
    execution_order: {next_order}
    skills: [{skills}]
    description: "{description}"
```

#### 4.2 Edit — frequency-limits.yaml 追加 initial_schema counter

在 `initial_schema` 區塊中追加 `"{task_key}_count": 0`。

#### 4.3 Write — 建立單一模式模板

路徑：`templates/auto-tasks/{task_key_hyphen}.md`

**依任務類型選擇基底模板**（讀取 `skills/task-manager/templates/` 中的模板）：
- 研究類 -> 組合 `_base.md` + `_research.md`
- 程式碼類 -> 組合 `_base.md` + `_code.md`
- 維護類 -> 組合 `_base.md` + `_maintenance.md`
- 其他 -> 僅用 `_base.md`

**必備段落**（無論哪種類型）：
- nul 禁令
- Skill-First 規則
- DONE_CERT 輸出格式

**研究類額外必備**：
- 研究註冊表檢查（`context/research-registry.json`）
- KB 去重查詢
- KB 匯入步驟
- 研究註冊表更新

#### 4.4 Write — 建立團隊模式 prompt

路徑：`prompts/team/todoist-auto-{task_key_hyphen}.md`

**必備結構**：
```
你是 {角色描述}，全程使用正體中文。
你的任務是 {任務描述}。
完成後將結果寫入 `results/todoist-auto-{task_key_hyphen}.json`。

## 重要禁令
- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`，改用 `> /dev/null 2>&1`
- 禁止用 Write 工具建立名為 nul 的檔案

## Skill-First 規則
必須先讀取以下 SKILL.md：
- `skills/SKILL_INDEX.md`
- {相關 skills}

---

{任務步驟}

## 輸出結果
用 Write 工具寫入 `results/todoist-auto-{task_key_hyphen}.json`：
{JSON 結構，含 done_cert}
```

#### 4.5 驗證團隊模式 prompt 命名正確

> **注意**：`run-todoist-agent-team.ps1` 已改為動態掃描（`Get-ChildItem todoist-auto-*.md`），
> 不再使用 hardcoded `$dedicatedPrompts` 哈希表。因此**無需手動修改 PS1 映射**。
> 只要 prompt 檔案命名為 `prompts/team/todoist-auto-{task_key_hyphen}.md` 即可被自動發現。

驗證方式：確認 `prompts/team/todoist-auto-{task_key_hyphen}.md` 檔案存在。

#### 4.6 Edit — frequency-limits.yaml 底部摘要

更新 `# 每日上限摘要` 區塊，加入新群組/任務的計數。
更新合計數字。

### Step 5：驗證矩陣（6 項全過才算完成）

依序執行以下驗證：

```bash
# 5.1 YAML 語法檢查
python -c "import yaml; yaml.safe_load(open('config/frequency-limits.yaml', encoding='utf-8'))"

# 5.2 模板結構檢查
```
用 Grep 確認：
- `templates/auto-tasks/{key}.md` 含 `DONE_CERT`
- 研究類模板含 `research-registry`
- `prompts/team/todoist-auto-{key}.md` 含 `results/`

```bash
# 5.3 團隊 prompt 命名檢查（動態掃描，無需 PS1 映射）
```
確認 `prompts/team/todoist-auto-{task_key_hyphen}.md` 存在且命名正確（動態掃描靠檔名匹配）

```bash
# 5.4 counter_field 一致性
```
用 Grep 確認 `frequency-limits.yaml` 的 `counter_field` 值出現在 `initial_schema` 中

```bash
# 5.5 execution_order 無重複
```
用 Grep 確認 `execution_order: {N}` 只出現一次

```bash
# 5.6 團隊 prompt 檔案存在
```
確認 `prompts/team/todoist-auto-{key}.md` 檔案存在

### Step 6：輸出變更摘要

```
新增自動任務完成：
  - 任務: {task_name} (key: {task_key})
  - 每日上限: {daily_limit}
  - 執行順序: {execution_order}
  - 群組: {group}
  - 模板: templates/auto-tasks/{key}.md
  - 團隊 prompt: prompts/team/todoist-auto-{key}.md
  - 動態掃描: 檔名符合 todoist-auto-*.md 規範
  - 驗證: 6/6 通過

需人工確認：
  - CLAUDE.md 架構段落（自動任務數量已變更）
  - SKILL_INDEX.md（若涉及新 Skill）
```

---

## 模式 B：新增排程任務（add-scheduled-task）

排程任務是**循環觸發**的，會執行 2 次以上（每日、每小時等）。

### Step 1：收集排程規格

```yaml
schedule_name: "排程名稱（英文 kebab-case，如 daily-digest-am）"
cron: "cron 表達式（如 0 8 * * *）"
script: "run-*.ps1 腳本名稱（現有或新建）"
timeout: 秒數
description: "中文描述"
interval: "可選，如 60m（表示重複間隔）"
retry: 0 或 1  # 失敗是否自動重試
```

### Step 2：生成/修改檔案

#### 2.1 Edit — HEARTBEAT.md 追加 YAML frontmatter

在 `---` 結束標記前、最後一個 schedule 之後追加：

```yaml
  {schedule_name}:
    cron: "{cron}"
    script: {script}
    timeout: {timeout}
    retry: {retry}
    description: "{description}"
```

若有 interval，加入 `interval: {interval}`。

#### 2.2 若需新腳本 -> Write 建立 run-{name}.ps1

基於現有 `run-agent-team.ps1` 或 `run-todoist-agent-team.ps1` 結構：
- 設定 `$AgentDir`、`$LogDir`
- 確保建立 `logs\structured\` 目錄
- 讀取 prompt -> `claude -p` 執行
- 記錄狀態到 `scheduler-state.json`

#### 2.3 若需新 prompt -> Write 建立

基於 `skills/task-manager/templates/_base.md` 組合。

### Step 3：驗證 + 指令輸出

```
排程任務已定義：
  - 名稱: {schedule_name}
  - Cron: {cron}
  - 腳本: {script}

執行以下指令註冊排程：
  .\setup-scheduler.ps1 -FromHeartbeat

驗證排程已建立：
  schtasks /query /tn "Claude_{schedule_name}" /v
```

---

## 模式 C：單次執行任務（run-once-task）

### C-1：立即執行

| 步驟 | 操作 | 說明 |
|------|------|------|
| 1 | 收集規格 | task_description、allowed_tools、skills、output_file（可選） |
| 2 | Write 建立 prompt | `task_prompt_once.md`（組合 _base.md + 任務指引） |
| 3 | Bash 執行 | `cat task_prompt_once.md \| claude -p --allowedTools "..."` |
| 4 | 清理 | `rm task_prompt_once.md` |

### C-2：定時單次執行

| 步驟 | 操作 | 說明 |
|------|------|------|
| 1 | 收集規格 | task_description、allowed_tools、skills、**scheduled_time** |
| 2 | Write 建立 prompt | `task_prompt_once.md` |
| 3 | Write 建立 PS1 腳本 | `run-once-{name}.ps1`（見下方模板） |
| 4 | Bash 建立排程 | `schtasks /create /tn "Claude_Once_{name}" /tr "pwsh -File run-once-{name}.ps1" /sc once /st {time} /sd {date}` |
| 5 | 輸出確認 | 排程名稱 + 觸發時間 + 手動刪除指令 |

**一次性排程腳本模板**：
```powershell
# 自動產生的一次性執行腳本
$AgentDir = "D:\Source\daily-digest-prompt"
$prompt = Get-Content "$AgentDir\task_prompt_once.md" -Raw -Encoding UTF8
$prompt | claude -p --allowedTools "{tools}" 2>&1 | ForEach-Object { Write-Host $_ }
# 清理排程（排程本身可被刪除）
schtasks /delete /tn "Claude_Once_{name}" /f
# 注意：不在此腳本內刪除自身（Windows file lock 問題）
# 殘留的 run-once-*.ps1 和 task_prompt_once.md 由 log-audit 自動任務定期清理
```

---

## 內建模板庫

模板位於 `skills/task-manager/templates/`，按任務類型組合：

| 模板 | 用途 | 關鍵段落 |
|------|------|---------|
| `_base.md` | 所有模板的共用基底 | 禁令 + Skill-First + DONE_CERT |
| `_research.md` | 研究類任務擴充 | + 去重 + KB 查詢 + 註冊表 + WebSearch |
| `_code.md` | 程式開發類擴充 | + Plan-Then-Execute + 測試驗證 |
| `_maintenance.md` | 系統維護類擴充 | + 日誌分析 + 狀態更新 |

**組合規則**：
- 研究類（群組含「研究」）-> `_base.md` + `_research.md`
- 程式碼類（群組含「系統優化」「專案品質」或 skills 含 code 相關）-> `_base.md` + `_code.md`
- 維護類（群組含「系統維護」）-> `_base.md` + `_maintenance.md`
- 其他 -> 僅 `_base.md`

---

## 錯誤處理與降級

| 錯誤情境 | 處理方式 |
|----------|---------|
| frequency-limits.yaml 無法解析 | 中止操作，輸出 YAML 錯誤訊息，不寫入任何檔案 |
| execution_order 計算衝突 | 自動遞增至下一個可用值 |
| 模板目錄不存在 | 自動建立目錄，並用 _base.md 作為最小模板 |
| 團隊 prompt 命名不符規範 | 輸出警告，提示正確格式 `todoist-auto-{key}.md` |
| YAML 驗證失敗 | 回復原始內容，輸出差異比對，標記為 PARTIAL |

---

## 安全機制

1. **YAML 驗證**：frequency-limits.yaml 修改後 `python -c "import yaml; ..."` 驗證
3. **execution_order 不重複**：Grep 確認唯一性
4. **counter_field 自動標準化**：`{task_key}_count` 格式
5. **daily_limit 硬限制**：1-5，超過自動截斷
