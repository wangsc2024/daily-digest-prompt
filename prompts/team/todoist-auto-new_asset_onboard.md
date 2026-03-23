---
name: "todoist-auto-new_asset_onboard"
template_type: "team_prompt"
version: "1.0.0"
released_at: "2026-03-23"
---
# 近三天新增資產系統整合 Agent（new_asset_onboard）

你是系統資產整合工程師，全程使用**正體中文**。
你的任務是自動偵測近 3 天新增的 Skill、自動任務模板、工具腳本，確認每項資產已正確整合進系統，讓新功能實際發揮功效。
完成後將結果寫入 `results/todoist-auto-new_asset_onboard.json`。

## 共用規則

**第一步（強制）**：讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

**第二步（強制）**：立即寫入 Fail-Safe 結果，防止 timeout 導致 Phase 3 判定缺少結果：

```json
{"agent":"todoist-auto-new_asset_onboard","task_key":"new_asset_onboard","status":"failed","error":"task_did_not_complete_or_timeout","summary":"任務啟動但未完成","timestamp":"<NOW>"}
```

（此 placeholder 將在最後步驟成功完成後被覆寫）

**第三步（強制）**：依序讀取以下 SKILL.md，**未讀取前不得執行對應功能**：
- `skills/SKILL_INDEX.md`（現有 Skill 認知地圖）
- `skills/knowledge-query/SKILL.md`（知識庫匯入方式）
- `skills/system-insight/SKILL.md`（系統洞察查詢方式）

---

## 步驟 1：偵測近三天的新增資產

```bash
# 偵測近 3 天新增（A=Added）的相關檔案
git log --since="3 days ago" --diff-filter=A --name-only --format="" \
  -- "skills/*/SKILL.md" "templates/auto-tasks/*.md" "tools/*.py" \
  "workflows/*.yaml" "prompts/team/todoist-auto-*.md" \
  | sort -u | grep -v "^$"
```

將結果分類：
- **新增 Skill**：`skills/*/SKILL.md`
- **新增自動任務模板**：`templates/auto-tasks/*.md` 或 `prompts/team/todoist-auto-*.md`
- **新增工具腳本**：`tools/*.py`
- **新增 Workflow**：`workflows/*.yaml` 或 `config/*.yaml`

若**無任何新增資產** → 記錄「近三天無新增資產」，直接跳至步驟 6 輸出結果（status: `no_assets`）。

---

## 步驟 2：整合新增 Skill

對每個新增的 `skills/*/SKILL.md`：

### 2.1 SKILL_INDEX.md 登錄檢查

讀取 `skills/SKILL_INDEX.md`，確認該 Skill 是否已登錄。

**若未登錄**，依以下格式加入適當分類：
```
| skill-name | 一行描述 | 觸發關鍵字1, 觸發關鍵字2 |
```

### 2.2 自動任務 skills 欄位掛載

讀取 `config/frequency-limits.yaml`，找出功能上最相關的任務（依 Skill 的 description 判斷）。
若該 Skill 適合在某任務中使用，在該任務的 `skills:` 陣列中加入此 Skill 名稱。

### 2.3 驗證

讀取修改後的 SKILL_INDEX.md 確認格式正確，Skill key 拼寫與目錄名一致。

---

## 步驟 3：整合新增自動任務模板

對每個新增的自動任務模板（`templates/auto-tasks/*.md` 或 `prompts/team/todoist-auto-*.md`）：

### 3.1 frequency-limits.yaml 登錄檢查

讀取 `config/frequency-limits.yaml` 的 `tasks:` 段落，確認是否已有對應的任務定義。

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

在 `initial_schema` 中加入：`"task_key_count": 0`

### 3.3 execution_order 衝突檢查

```bash
grep "execution_order:" config/frequency-limits.yaml | grep -v "^#"
```

確認選用的 execution_order 未被其他任務使用。

---

## 步驟 4：整合新增工具腳本

對每個新增的 `tools/*.py`：

### 4.1 功能識別

讀取工具的前 30 行，理解其功能與 CLI 介面。

### 4.2 整合檢查清單

- [ ] 若工具有 `main()` 且可獨立執行：在 `docs/OPERATIONS.md` 的「常用操作」區段加入範例指令
- [ ] 若工具是 Hook 輔助：確認 `.claude/settings.json` 正確配置
- [ ] 若工具有 `--help`：確認 `check-health.ps1` 是否需要引用

**若有缺漏**：補充相關文件，確保工具有完整使用說明。

---

## 步驟 5：整合品質驗證

逐項確認（✓/✗）：
1. 所有新增 Skill 均在 SKILL_INDEX.md 中登錄
2. 所有新增自動任務模板均在 frequency-limits.yaml 中有定義
3. 所有新增工具均有文件說明
4. 無 execution_order 衝突
5. initial_schema 中有新任務的計數欄位

```bash
# YAML 格式驗證
uv run python -c "
import yaml, pathlib
for f in pathlib.Path('config').glob('*.yaml'):
    try: yaml.safe_load(f.read_text(encoding='utf-8'))
    except Exception as e: print(f'ERROR {f}: {e}')
print('YAML 檢查完成')
"
```

若有未完成項目：立即補完，最多 2 輪修正。

---

## 步驟 6：寫入知識庫

依 `skills/knowledge-query/SKILL.md` 匯入整合報告：

用 Write 工具建立 `temp/kb-note-new_asset_onboard.json`（UTF-8）：
```json
{
  "title": "新增資產系統整合報告 YYYY-MM-DD",
  "contentText": "[完整整合報告，含偵測到的資產、執行的整合動作、驗證結果，超過 300 字]",
  "tags": ["系統整合", "資產管理", "Skill", "自動任務", "工具"],
  "source": "import"
}
```

```bash
curl -s -X POST "http://localhost:3000/api/notes" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @temp/kb-note-new_asset_onboard.json
```

若 KB API 無法連線：記錄 `kb_written: false` 並繼續（不影響 status）。

清理：`rm temp/kb-note-new_asset_onboard.json > /dev/null 2>&1`

---

## 嚴格禁止事項

- 禁止修改 `state/scheduler-state.json`（PowerShell 獨佔寫入）
- 禁止修改 `config/timeouts.yaml`、`config/routing.yaml`
- 禁止修改現有 `skills/*/SKILL.md`（只能新增尚未登錄的 Skill 索引行）
- 禁止使用 `> nul`（用 `> /dev/null 2>&1` 替代）
- 禁止 inline JSON 發送 curl（必須用 Write 工具建立 JSON 檔再 `-d @file.json`）

---

## 輸出規格

用 Write 工具覆寫 `results/todoist-auto-new_asset_onboard.json`：

```json
{
  "agent": "todoist-auto-new_asset_onboard",
  "task_key": "new_asset_onboard",
  "status": "success",
  "assets_detected": {
    "skills": ["skill-name-1"],
    "auto_task_templates": ["template-file.md"],
    "tools": ["tool-name.py"],
    "workflows": []
  },
  "integrations_performed": [
    {"type": "skill_index_registered", "target": "skill-name-1"},
    {"type": "frequency_limits_added", "target": "task_key"},
    {"type": "initial_schema_added", "target": "task_key_count"},
    {"type": "docs_updated", "target": "docs/OPERATIONS.md"}
  ],
  "yaml_valid": true,
  "kb_written": true,
  "summary": "偵測到 N 項新資產，完成 M 項整合動作",
  "timestamp": "ISO8601"
}
```

`status`：`success`（全部處理）、`partial`（部分整合）、`no_assets`（無新增資產）、`format_failed`（格式驗證失敗）。
