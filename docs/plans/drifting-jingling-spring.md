# 計畫：workflow_forge 產出自動引用機制

## Context

**問題**：`docs/workflows/` 有 2 個驗證清單，但 Grep 確認 29 個 `todoist-auto-*.md` 中零引用這些檔案。workflow-forge 每次產出都是靜態孤本，任何任務都不讀，也沒有索引。

**目標**：一個固定設定檔 + preamble 一行規則，讓任務「自動引用」新 workflow；workflow_forge 每次產出後自動維護 index，形成閉環。

**約束**：
- 不改 `frequency-limits.yaml` tasks 區塊
- 不刪既有 config 鍵
- PS pipeline 改動用 `enabled: false` flag 隔離風險

---

## 實施方案

### Step 0：遷移現有 `docs/workflows/` → `workflows/`（移動）

現有 2 個檔案從 `docs/workflows/` 移至專案根目錄 `workflows/`：

```
docs/workflows/prompt-output-validation-checklist.md  →  workflows/prompt-output-validation-checklist.md
docs/workflows/results-validation-checklist.md        →  workflows/results-validation-checklist.md
```

遷移後 `docs/workflows/` 目錄可移除（無其他檔案）。

同步更新 `context/workflow-forge-registry.json` 中 entries 的 `artifact_path` 欄位，將 `docs/workflows/...` 改為 `workflows/...`。

---

### Step 1：建立 `workflows/index.yaml`（新建）

Forge 維護的 workflow 目錄，Agent 按 `task_types` 篩選並按需讀取。

```yaml
version: "1.0.0"
updated_at: "2026-03-21"
description: "workflow-forge 產出物索引，Agent 執行前依 task_type 篩選適用 workflow"

entries:
  - id: "wf-20260321-prompt-output-validation"
    path: "workflows/prompt-output-validation-checklist.md"
    type: "validation_checklist"
    title: "Prompt 輸出規範驗證清單"
    version: "1.0.0"
    created_at: "2026-03-21"
    task_types: ["workflow_forge", "skill_forge"]
    priority: "P0"
    summary: "29 個自動任務 prompt 的輸出 JSON 規範統一驗證清單"
    read_when: "developing_or_reviewing_prompt"

  - id: "wf-20260319-results-validation"
    path: "workflows/results-validation-checklist.md"
    type: "validation_checklist"
    title: "結果檔案格式驗證清單"
    version: "1.0.0"
    created_at: "2026-03-19"
    task_types: ["all"]
    priority: "P0"
    summary: "確保 results/todoist-auto-*.json 符合 Schema 的驗證步驟清單"
    read_when: "producing_results_json"
```

---

### Step 2：建立 `config/agent-extra-reads.yaml`（新建）

PS Phase 0 注入用的靜態映射；`enabled: false` 為全局開關（預設關閉，不影響現有流程）。

```yaml
version: 1
enabled: false  # Phase 0 機器注入開關；false=Agent 靠 preamble 自律讀取

global_reads:
  - path: "workflows/index.yaml"
    purpose: "workflow 索引，Agent 依 task_type 篩選適用 workflow"
    required: false

task_type_mapping:
  workflow_forge:
    reads:
      - path: "workflows/prompt-output-validation-checklist.md"
        purpose: "prompt 輸出格式驗證清單"
        when: "always"
    enabled: true
  # workflow-forge 自動 append 新 entry 的位置
```

---

### Step 3：修改 `templates/shared/preamble.md`

在「Skill-First 核心規則」段落後（第 10-11 行間）插入：

```markdown
## Workflow 自動引用規則

若你是 `todoist-auto-*` 自動任務，在執行主要步驟**之前**：
1. 讀取 `workflows/index.yaml`（不存在則略過）
2. 找出 `task_types` 包含你的 task_key 或 `"all"` 的 entries
3. 用 Read 工具讀取匹配的 workflow 文件，遵守其規範
4. 無匹配或 index 不存在 → 略過，繼續主任務
```

**影響範圍**：所有讀 preamble.md 的 Agent（29 個自動任務）。

---

### Step 4：修改 `skills/workflow-forge/SKILL.md`

**步驟 4 末尾**（產出實體檔案後）插入強制動作：

> 產出後必須執行：
> 1. 讀取 `workflows/index.yaml`（不存在則建立初始結構）
> 2. 在 `entries[]` 開頭 append 新 entry（含 id/path/type/task_types/priority/summary/read_when）
> 3. 更新頂層 `updated_at` 為今日日期
> 4. 用 Write 工具完整覆寫 `workflows/index.yaml`
> 5. **所有新產出的 workflow 檔案一律寫入 `workflows/`（不再寫 `docs/workflows/`）**

**步驟 6 末尾**（整合登記後）插入：

> 同步更新 `config/agent-extra-reads.yaml`：在 `task_type_mapping` 下 append 對應 task_key 的 reads 項目（若 task_types=all 則跳過）。

---

### Step 5：修改 `hooks/validate_config.py`

**5a. SCHEMAS dict 新增**（`insight-briefing-workflow.yaml` 後）：

```python
"agent-extra-reads.yaml": {
    "required_keys": ["version", "enabled", "global_reads", "task_type_mapping"],
    "list_fields": {
        "global_reads": ["path", "purpose"],
    },
},
```

> 注意：現有 `validate_config()` 對不存在的檔案已是 `warnings`（非 `errors`），不需要 `_optional` 標記。

**5b. 新增函數 `validate_workflow_index(base_dir=".")`**（位置：`check_auto_tasks_consistency` 後）：

```python
def validate_workflow_index(base_dir: str = ".") -> tuple:
    """驗證 workflows/index.yaml 結構。
    Returns: (errors, warnings)
    """
    errors, warnings = [], []
    index_path = os.path.join(base_dir, "workflows", "index.yaml")

    if not os.path.exists(index_path):
        warnings.append("workflows/index.yaml 不存在（forge 尚未產出 workflow）")
        return errors, warnings

    data = _load_yaml(index_path)
    if data is None:
        errors.append("workflows/index.yaml: YAML 解析失敗")
        return errors, warnings

    for key in ["version", "entries"]:
        if key not in data:
            errors.append(f"workflows/index.yaml: 缺少必要鍵 '{key}'")

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        errors.append("workflows/index.yaml: 'entries' 應為 list")
        return errors, warnings

    seen_ids = set()
    required_entry_keys = ["id", "path", "type", "task_types", "priority"]
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"workflows/index.yaml: entries[{i}] 應為 dict")
            continue
        for key in required_entry_keys:
            if key not in entry:
                errors.append(f"workflows/index.yaml: entries[{i}] 缺少 '{key}'")
        entry_id = entry.get("id", "")
        if entry_id in seen_ids:
            errors.append(f"workflows/index.yaml: id '{entry_id}' 重複")
        elif entry_id:
            seen_ids.add(entry_id)
        entry_path = entry.get("path", "")
        if entry_path and not os.path.exists(os.path.join(base_dir, entry_path)):
            warnings.append(f"workflows/index.yaml: entries[{i}] path '{entry_path}' 不存在")
        if not isinstance(entry.get("task_types", []), list):
            errors.append(f"workflows/index.yaml: entries[{i}].task_types 應為 list")

    return errors, warnings
```

**5c. CLI 旗標 `--check-workflows`**（main() 函數中，`--check-auto-tasks` 後加入），並在 `--all` 分支中也呼叫。

---

### Step 6：修改 `run-todoist-agent-team.ps1`（Phase 0d，選配）

在 Phase 0c（fairness-hint）後、Phase 1 前，插入 **Phase 0d** 區塊：

```powershell
# Phase 0d: Workflow 前置注入（agent-extra-reads.yaml, enabled: false）
$script:WorkflowInjectPrefix = ""
$extraReadsPath = Join-Path $AgentDir "config\agent-extra-reads.yaml"
if (Test-Path $extraReadsPath) {
    # 讀取 enabled 旗標；若 true，組裝 WorkflowInjectPrefix
    # 失敗時 catch 並 Write-Log WARN，不中斷 Phase 1
}
```

在 Phase 2 的 `$promptContent = Strip-Frontmatter ...` 後，插入：

```powershell
if ($script:WorkflowInjectPrefix) {
    $promptContent = $script:WorkflowInjectPrefix + $promptContent
}
```

**啟用方式**：`config/agent-extra-reads.yaml` 的 `enabled: false` 改為 `true`。

---

## 正確性驗證

### 端對端執行路徑（enabled: false 預設）

```
Phase 0d → WorkflowInjectPrefix="" → 不注入
Phase 2: todoist-auto-workflow_forge.md
  ├─ 讀 preamble.md（含 Workflow 自動引用規則）
  ├─ 讀 workflows/index.yaml
  ├─ 找到 task_types=["workflow_forge"] 的 entry
  ├─ 讀 workflows/prompt-output-validation-checklist.md
  ├─ 執行主要任務
  ├─ 產出新 artifact（寫入 workflows/）
  ├─ [Step 4 強制] append entry 到 workflows/index.yaml
  └─ [Step 6 強制] append 到 config/agent-extra-reads.yaml
```

### 失效模式與防護

| 失效點 | 影響 | 防護 |
|--------|------|------|
| index.yaml 不存在 | Agent 略過 | preamble 已明寫「不存在則略過」 |
| index.yaml 格式損壞 | Agent 解析失敗 | forge 步驟 5 有 2 輪 YAML 格式驗證 |
| forge 自身讀 index（循環） | 讀到自己上次的 entries | 串行讀寫無競爭；讀舊狀態用於去重，正確 |
| task_types 無匹配 | 找不到對應 workflow | 正常降級：繼續主任務 |
| validate_config 現有測試 | SCHEMAS 新增 key | 檔案不存在 → warnings（非 errors），不影響 37 個現有測試 |

---

## 關鍵檔案

| 動作 | 檔案 | 說明 |
|------|------|------|
| 移動 | `docs/workflows/*.md` → `workflows/` | 遷移現有 2 個驗證清單 |
| 更新 | `context/workflow-forge-registry.json` | artifact_path 由 docs/workflows/ 改為 workflows/ |
| 新建 | `workflows/index.yaml` | Forge 維護的 workflow 目錄 |
| 新建 | `config/agent-extra-reads.yaml` | PS Phase 0 注入用映射（enabled: false）|
| 修改 | `templates/shared/preamble.md` | +10 行 Workflow 自動引用規則 |
| 修改 | `skills/workflow-forge/SKILL.md` | 步驟 4+6 強制更新 index 與映射；產出路徑改 workflows/ |
| 修改 | `hooks/validate_config.py` | +SCHEMAS entry + validate_workflow_index() + --check-workflows |
| 修改 | `run-todoist-agent-team.ps1` | Phase 0d + Phase 2 注入（enabled: false 隔離）|

---

## 驗證指令

```powershell
# 1. 驗證 agent-extra-reads.yaml schema
uv run python hooks/validate_config.py

# 2. 驗證 workflows/index.yaml
uv run python hooks/validate_config.py --check-workflows

# 3. 全套驗證（含 workflow index）
uv run python hooks/validate_config.py --all

# 4. 確認 preamble 修改
uv run python -c "c=open('templates/shared/preamble.md',encoding='utf-8').read(); assert 'workflows/index.yaml' in c; print('preamble OK')"

# 5. 確認 index.yaml YAML 格式合法
uv run python -c "import yaml; d=yaml.safe_load(open('workflows/index.yaml',encoding='utf-8')); print(f'OK, {len(d[\"entries\"])} entries')"

# 6. 確認舊路徑已清理
uv run python -c "import os; assert not os.path.exists('docs/workflows/prompt-output-validation-checklist.md'), 'old path still exists'; print('migration OK')"
```
