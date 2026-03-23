---
name: "new-asset-onboard"
template_type: "auto_task_template"
version: "1.0.0"
released_at: "2026-03-23"
---
# 近三天新增資產系統整合 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 new_asset_onboard_count < daily_limit
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

```
你是系統資產整合工程師，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/SKILL_INDEX.md
- skills/knowledge-query/SKILL.md
- skills/system-insight/SKILL.md

## 任務目標
自動偵測近 3 天新增或修改的 Skill、自動任務模板、工具腳本，
確認每項資產已正確整合進系統運作，讓新功能實際發揮功效。

## 第一步：偵測近三天的新增資產

```bash
# 偵測近 3 天新增（A=Added）的相關檔案
git log --since="3 days ago" --diff-filter=A --name-only --format="" \
  -- "skills/*/SKILL.md" "templates/auto-tasks/*.md" "tools/*.py" \
  "skills/*/SKILL.md" "workflows/*.yaml" "prompts/team/todoist-auto-*.md" \
  | sort -u | grep -v "^$"
```

將結果分類：
- **新增 Skill**：`skills/*/SKILL.md`
- **新增自動任務模板**：`templates/auto-tasks/*.md` 或 `prompts/team/todoist-auto-*.md`
- **新增工具腳本**：`tools/*.py`
- **新增 Workflow**：`workflows/*.yaml` 或 `config/*.yaml`

若無任何新增資產 → 輸出「近三天無新增資產，任務完成」並輸出 DONE_CERT。

## 第二步：整合新增 Skill

對每個新增的 `skills/*/SKILL.md`：

### 2.1 SKILL_INDEX.md 登錄檢查
讀取 `skills/SKILL_INDEX.md`，確認該 Skill 是否已登錄。

**若未登錄**，依以下格式加入適當分類：
```
| skill-name | 一行描述 | 觸發關鍵字1, 觸發關鍵字2 |
```

### 2.2 自動任務 skills 欄位掛載
讀取 `config/frequency-limits.yaml`，找出功能上最相關的任務（依 Skill 的 description 判斷）。
若該 Skill 適合在某任務中使用（如：新增的研究 Skill 應掛到研究任務），
在該任務的 `skills:` 陣列中加入此 Skill 名稱。

### 2.3 驗證
- 讀取修改後的 SKILL_INDEX.md 確認格式正確
- Skill key 拼寫與目錄名一致

## 第三步：整合新增自動任務模板

對每個新增的自動任務模板（`templates/auto-tasks/*.md` 或 `prompts/team/todoist-auto-*.md`）：

### 3.1 frequency-limits.yaml 登錄檢查
讀取 `config/frequency-limits.yaml` 的 `tasks:` 段落，
確認是否已有對應的任務定義（以模板檔名去掉副檔名比對 key）。

**若未定義**，依照 `allowed_hours` 指引加入任務配置：
```yaml
  task_key:
    name: "任務顯示名稱"
    daily_limit: 1
    counter_field: "task_key_count"
    template: "模板路徑"
    template_version: 1
    history_type: "task_key"
    execution_order: <選擇未使用的號碼>
    allowed_hours: [<依類型選擇>, 23]
    timeout_seconds: 720
    result_suffix: "json"
    skills: []
```

### 3.2 initial_schema 同步
在 `config/frequency-limits.yaml` 的 `initial_schema` 中加入：
```
"task_key_count": 0,
```

### 3.3 execution_order 衝突檢查
確認選用的 execution_order 未被其他任務使用：
```bash
grep "execution_order:" config/frequency-limits.yaml | grep -v "^#"
```

## 第四步：整合新增工具腳本

對每個新增的 `tools/*.py`：

### 4.1 功能識別
讀取工具的 docstring 或前 30 行，理解其功能與 CLI 介面。

### 4.2 整合檢查清單
- [ ] `docs/OPERATIONS.md` 或 `CLAUDE.md` 是否有說明此工具的用途與指令
- [ ] 若工具有 `--help` 或 CLI 入口，確認 `check-health.ps1` 中是否需要引用
- [ ] 若工具是 Hook 輔助：確認 `.claude/settings.json` 正確配置
- [ ] 若工具有 `main()` 且可獨立執行：在 `docs/OPERATIONS.md` 的「常用操作」區段加入範例指令

**若有缺漏**：補充相關文件，確保工具有完整的使用說明。

## 第五步：整合品質驗證

逐項確認：
1. 所有新增 Skill 均在 SKILL_INDEX.md 中登錄 ✓/✗
2. 所有新增自動任務模板均在 frequency-limits.yaml 中有定義 ✓/✗
3. 所有新增工具均有文件說明 ✓/✗
4. 無 execution_order 衝突 ✓/✗
5. initial_schema 中有新任務的計數欄位 ✓/✗

若有未完成項目：立即補完，最多 2 輪修正。

## 第六步：寫入知識庫

依 knowledge-query SKILL.md 匯入整合報告：
- tags: ["系統整合", "資產管理", "Skill", "自動任務", "工具"]
- contentText: 完整整合報告（含偵測到的資產、執行的整合動作、驗證結果）
- source: "import"

## 品質自評
1. 偵測到的每項新資產是否都有對應的整合動作？
2. 修改後的配置檔案是否語法正確？
3. 整合報告是否超過 300 字？
若未通過：補充 → 修正（最多 2 次）。

## 輸出 DONE 認證
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["修改的檔案列表"],"tests_passed":true/false,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[]}
===DONE_CERT_END===
```

## 執行方式

> ⚡ **【立即】用 Bash tool 執行（不得只輸出命令文字）**

```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,Edit,Glob,Grep"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`new_asset_onboard_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=new_asset_onboard 記錄
3. 清理：`rm task_prompt.md`
