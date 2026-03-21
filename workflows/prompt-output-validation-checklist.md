# Prompt 輸出規範驗證清單

> **版本**：1.0.0
> **建立日期**：2026-03-21
> **用途**：確保所有 `prompts/team/todoist-auto-*.md` 輸出格式一致，對齊 `config/schemas/results-auto-task-schema.json`
> **適用對象**：新增或修改自動任務 prompts 時使用

---

## 背景

**問題**：29 個自動任務 prompts 的輸出 JSON 規範不一致：
- 部分有詳細「關鍵欄位確認清單」，部分僅有基本範例
- 命名不一致（`task_type` vs `agent`）
- 缺少統一的必填欄位檢查列表

**影響**：
- Phase 3 組裝時可能因欄位缺失失敗
- `avg_io_per_call` 超標 5.3 倍（system-insight 告警），部分原因是 prompt 需重複說明輸出格式

**目標**：
- 結果 JSON 格式一致性提升至 95% 以上
- Phase 3 組裝失敗率下降
- `avg_io_per_call` 下降 10-15%

---

## 驗證清單

### 1. Frontmatter 驗證

**檢查項目**：
- [ ] prompt 檔案開頭必須有 YAML frontmatter（`---`包裹）
- [ ] frontmatter 必須含 `name`、`template_type`、`version`、`released_at` 四個欄位
- [ ] `name` 欄位格式：`todoist-auto-{task_key}`（與 `task_key` 一致）
- [ ] `template_type` 固定為 `team_prompt`
- [ ] `version` 遵循 semver（如 `1.0.0`）
- [ ] `released_at` 為 `YYYY-MM-DD` 格式

**良好範例**：
```yaml
---
name: "todoist-auto-skill_forge"
template_type: "team_prompt"
version: "1.0.0"
released_at: "2026-03-20"
---
```

---

### 2. 結果 JSON 路徑驗證

**檢查項目**：
- [ ] prompt 必須明確指定結果檔案路徑：`results/todoist-auto-{task_key}.json`
- [ ] `task_key` 必須使用**底線**（`_`），**禁用連字號**（`-`）
- [ ] 結果檔案路徑在 prompt 中至少出現 **2 次**（共用規則區塊 + 輸出規格區塊）

**良好範例**：
```markdown
完成後將結果寫入 `results/todoist-auto-workflow_forge.json`。

## 輸出規格
用 Write 工具建立 `results/todoist-auto-workflow_forge.json`，...
```

**錯誤範例**（避免）：
```markdown
# ❌ 使用連字號
results/todoist-auto-workflow-forge.json

# ❌ 只出現一次
完成後將結果寫入 results/xxx.json（輸出規格未重複）
```

---

### 3. 必填欄位檢查列表

**檢查項目**：
- [ ] prompt 必須明確列出「關鍵欄位確認清單」或「必填欄位」區塊
- [ ] 必填欄位最少包含：`agent`（或 `task_type`）、`task_key`、`status`
- [ ] `agent` 欄位格式：`todoist-auto-{task_key}`（與檔名、結果路徑一致）
- [ ] `task_key` 欄位值：與 `config/frequency-limits.yaml` 中的 `tasks` 鍵名完全一致（底線）
- [ ] `status` 欄位值域：必須明確列出允許值（`success`/`partial`/`failed`/`format_failed`）

**良好範例**（todoist-auto-skill_forge.md）：
```markdown
## 輸出規格
關鍵欄位確認清單：
- `"agent"` 欄位必須完全等於 `"todoist-auto-skill_forge"`
- `"task_key"` 欄位必須完全等於 `"skill_forge"`
- `"status"` 必須是以下其一：`success`、`partial`、`quality_rejected`、`format_failed`
```

**待改善範例**（todoist-auto-system_insight.md）：
```markdown
# ❌ 僅有 JSON 範例，缺少明確必填欄位清單
{
  "task_type": "auto",
  "task_key": "system_insight",
  "status": "success"
}
```

**修正建議**：補充「關鍵欄位確認清單」區塊，明確列出 3 個必填欄位與允許值。

---

### 4. 欄位命名一致性

**檢查項目**：
- [ ] 優先使用 `agent` 欄位（推薦），避免混用 `task_type`
- [ ] 若使用 `agent` 欄位，格式必須為 `todoist-auto-{task_key}`
- [ ] 所有欄位名稱必須與 `config/schemas/results-auto-task-schema.json` 定義一致

**推薦格式**：
```json
{
  "agent": "todoist-auto-workflow_forge",
  "task_key": "workflow_forge",
  "status": "success"
}
```

**向後相容格式**（舊 prompts 可用，但不推薦新增）：
```json
{
  "task_type": "auto",
  "task_key": "system_insight",
  "status": "success"
}
```

**注意**：Schema 定義為 `anyOf: [{"required": ["agent"]}, {"required": ["task_type"]}]`，但新 prompts 應統一使用 `agent` 欄位。

---

### 5. Schema 對齊驗證

**檢查項目**：
- [ ] prompt 輸出規格必須參考 `config/schemas/results-auto-task-schema.json`
- [ ] 所有選填欄位（如 `artifact`、`integration_status`、`kb_imported`）若使用，必須符合 Schema 定義
- [ ] `artifact.type` 若使用，必須是 Schema 允許的 enum 值之一：
  - `workflow_yaml`
  - `output_schema`
  - `validation_checklist`
  - `report`
  - `code`
  - `config`
  - `documentation`

**良好範例**：
```json
{
  "agent": "todoist-auto-workflow_forge",
  "task_key": "workflow_forge",
  "status": "success",
  "artifact": {
    "path": "workflows/prompt-output-validation-checklist.md",
    "type": "validation_checklist",
    "gap_addressed": "解決 29 個自動任務 prompts 的輸出格式不一致問題"
  },
  "integration_status": "integrated",
  "kb_imported": true
}
```

**錯誤範例**（避免）：
```json
{
  "artifact": {
    "path": "...",
    "type": "checklist"  // ❌ 無效的 type，應為 validation_checklist
  }
}
```

**驗證方式**：
```bash
# 讀取 Schema 確認欄位定義
cat config/schemas/results-auto-task-schema.json | grep -A 10 '"artifact"'
```

---

### 6. 執行流程完整性

**檢查項目**：
- [ ] prompt 必須包含「共用規則」區塊，引用 `templates/shared/preamble.md`
- [ ] prompt 必須包含「Skill-First」區塊，明確列出需讀取的 SKILL.md 檔案
- [ ] prompt 必須包含「嚴格禁止事項」區塊，列出至少 3 項禁止操作
- [ ] prompt 必須包含「輸出規格」區塊，明確定義結果 JSON 的欄位與格式

**良好範例結構**：
```markdown
# Workflow 鑄造 Agent（workflow-forge）

...

## 共用規則

**第一步（強制）**：讀取 `templates/shared/preamble.md`，...

**第二步（強制）**：依序讀取以下 SKILL.md：
- `skills/SKILL_INDEX.md`
- `skills/workflow-forge/SKILL.md`
- ...

## 執行

依 `skills/workflow-forge/SKILL.md` 的完整步驟執行（步驟 0 → 8）。

## 嚴格禁止事項

- 禁止修改 `state/scheduler-state.json`
- 禁止使用 `> nul`
- ...

## 輸出規格

用 Write 工具建立 `results/todoist-auto-workflow_forge.json`，
欄位格式詳見 `skills/workflow-forge/SKILL.md` 步驟 8b。

關鍵欄位確認清單：
- `"agent"` 欄位必須完全等於 `"todoist-auto-workflow_forge"`
- ...
```

---

## 驗證方式

### 人工審查

1. 開啟待驗證的 `prompts/team/todoist-auto-{task_key}.md`
2. 對照本清單逐條檢查（6 大類共 28 項檢查點）
3. 發現缺失時，依「良好範例」修正

### 自動化驗證（可選）

建立 `tools/validate_prompt_output.py` 腳本，自動掃描 `prompts/team/` 目錄並驗證上述規則：

```python
# 示例腳本（待實作）
import re, yaml, glob

def validate_prompt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Frontmatter 驗證
    if not re.match(r'^---\n.*?\n---', content, re.DOTALL):
        print(f"❌ {file_path}: 缺少 frontmatter")

    # 2. 結果 JSON 路徑驗證
    if content.count('results/todoist-auto-') < 2:
        print(f"⚠️ {file_path}: 結果路徑出現次數 < 2")

    # 3. 必填欄位檢查清單
    if '關鍵欄位確認清單' not in content and '必填欄位' not in content:
        print(f"❌ {file_path}: 缺少必填欄位檢查清單")

    # ...其他檢查

for prompt_file in glob.glob('prompts/team/todoist-auto-*.md'):
    validate_prompt(prompt_file)
```

---

## 整合說明

### 文件引用

- **docs/ARCHITECTURE.md**：配置文件速查表新增一行：
  ```
  | workflows/prompt-output-validation-checklist.md | Prompt 輸出格式驗證 | 所有 todoist-auto-*.md |
  ```

- **CLAUDE.md**：文件驅動架構設計原則新增驗證清單說明：
  ```
  新增/修改自動任務 prompts 時，必須通過 workflows/prompt-output-validation-checklist.md 驗證。
  ```

### 對齊檔案

- **Schema 檔案**：`config/schemas/results-auto-task-schema.json`（v1.1.0）
- **良好範例**：`prompts/team/todoist-auto-skill_forge.md`
- **待改善範例**：`prompts/team/todoist-auto-system_insight.md`

---

## 預期成果

### 即時成果
- 所有 prompt 開發者有明確檢查列表
- 新增/修改 prompt 時可自我驗證

### 中期成果（2-4 週）
- 結果 JSON 格式一致性提升至 **95% 以上**（目前約 70%）
- Phase 3 組裝失敗率下降

### 長期成果（2-3 個月）
- `avg_io_per_call` 因減少重複格式說明而下降 **10-15%**
- 系統輸出穩定度顯著提升

---

## 附錄：快速參考表

| 檢查類別 | 檢查點數量 | 關鍵驗證項 |
|---------|-----------|----------|
| Frontmatter | 6 | frontmatter 存在、4 個必填欄位、格式正確 |
| 結果路徑 | 3 | 路徑格式、底線命名、出現 ≥ 2 次 |
| 必填欄位 | 5 | 3 個必填欄位、格式一致、值域明確 |
| 命名一致性 | 3 | 優先 agent、格式正確、對齊 Schema |
| Schema 對齊 | 3 | 參考 Schema、選填欄位符合定義、type 值有效 |
| 執行流程 | 4 | 4 個必備區塊（共用規則、Skill-First、禁止事項、輸出規格）|
| **總計** | **24** | - |

---

**版本記錄**：
- **v1.0.0（2026-03-21）**：初版，統一 29 個自動任務 prompts 輸出格式驗證規則
