# Config 一致性驗證清單

> **版本**: 1.0.0
> **建立日期**: 2026-03-22
> **適用對象**: config/*.yaml 維護者、Prompt 開發者
> **驗證頻率**: 每次修改 config 或新增自動任務時

## 概述

本清單確保 `config/*.yaml` 中定義的路徑、task_key、skills 等欄位與實際檔案系統、`SKILL_INDEX.md`、prompt 模板保持一致，避免執行時錯誤與配置膨脹風險。

---

## 1. frequency-limits.yaml 一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **1a. task_key 與檔名一致** | Glob `prompts/team/todoist-auto-*.md`，比對 `frequency-limits.yaml` tasks 鍵 | 每個 task_key 對應的 `prompts/team/todoist-auto-{task_key}.md` 檔案存在（底線命名） |
| **1b. counter_field 一致** | 檢查 `initial_schema` 是否包含 `{task_key}_count` 欄位 | 每個任務的 `counter_field` 值與 `initial_schema` 中的欄位名稱完全一致 |
| **1c. template 路徑存在** | Read 每個任務的 `template` 路徑 | 所有 template 檔案確實存在，無 404 |
| **1d. execution_order 唯一** | 提取所有 `execution_order` 值，檢查重複 | 無重複值，範圍 1-35（含已停用任務） |
| **1e. allowed_days 合法** | 檢查 `allowed_days` 陣列的所有值 | 值在 0-6 範圍內（Mon=0, Sun=6），未設定則略過 |
| **1f. skills 存在性** | 提取 `skills` 陣列，比對 `skills/SKILL_INDEX.md` 速查表 | 所有 Skill 名稱在 SKILL_INDEX.md 中存在（忽略大小寫、連字號/底線） |
| **1g. prompt_file 存在** | 若任務有 `prompt_file` 欄位，Read 該路徑 | prompt_file 檔案存在（如 `prompts/team/todoist-auto-arch_evolution.md`） |

---

## 2. cache-policy.yaml 一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **2a. cache 檔案路徑** | 檢查每個 source 的 `file` 路徑父目錄 | `cache/` 目錄存在，檔案可建立 |
| **2b. volatility 一致** | 比對 `adaptive_ttl.volatility` 與 `sources` 的 key | 兩者的 key 集合完全一致（todoist, pingtung-news, hackernews, knowledge, gmail, chatroom） |
| **2c. tracking 路徑** | 檢查 `tracking.write_to` 指向的檔案 | `context/digest-memory.json` 存在或父目錄存在 |

---

## 3. routing.yaml 一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **3a. skills 存在性** | 提取 `label_routing.mappings` 的所有 `skills` 陣列，比對 SKILL_INDEX.md | 所有 Skill 名稱在 SKILL_INDEX.md 中存在 |
| **3b. template 路徑** | Read 每個 mapping 的 `template` 路徑 | 所有 template 檔案存在（templates/sub-agent/*.md） |
| **3c. skill_aliases 模板** | 檢查 `skill_aliases` 中 `type: template_driven` 的 template 路徑 | template 檔案存在，如 `templates/sub-agent/code-task.md` |
| **3d. chatroom template** | Read `chatroom_task_source.template` 路徑 | template 檔案存在（templates/sub-agent/chatroom-task.md） |

---

## 4. pipeline.yaml 一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **4a. skill_files 路徑** | Read 每個 step 的 `skill_files` 路徑 | 所有 SKILL.md 檔案存在（如 `skills/todoist/SKILL.md`） |
| **4b. cache_key 對應** | 比對 step 的 `cache_key` 與 `cache-policy.yaml` sources | 每個 cache_key 在 cache-policy.yaml 的 sources 中有對應 source |
| **4c. format_file 存在** | Read `finalize.compile_digest.format_file` 路徑 | `config/digest-format.md` 存在 |
| **4d. skills 存在性** | 提取每個 step 的 `skills` 陣列，比對 SKILL_INDEX.md | 所有 Skill 名稱在 SKILL_INDEX.md 中存在 |

---

## 5. ooda-workflow.yaml 一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **5a. prompt_file 路徑** | 若 `trigger_mode` 非 `ps_script`，Read `prompt_file` 路徑 | prompt_file 檔案存在（如 `prompts/team/todoist-auto-system_insight.md`） |
| **5b. auto_task_key 一致** | 比對每個 step 的 `auto_task_key` 與 `frequency-limits.yaml` tasks | auto_task_key 在 frequency-limits.yaml 中存在 |
| **5c. state_file 路徑** | 檢查 `state_file` 父目錄 | `context/` 目錄存在，可建立 workflow-state.json |
| **5d. history_file 路徑** | 檢查 `history_file` 父目錄 | `logs/structured/` 目錄存在，可建立 ooda-transitions.jsonl |

---

## 6. 結果檔案命名一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **6a. 結果路徑底線** | Grep `'Write.*results/todoist-auto-'` 在所有 `prompts/team/todoist-auto-*.md` | 檔名使用底線（`todoist-auto-{task_key}.json`），與 task_key 一致 |
| **6b. agent 欄位格式** | 抽樣 Read 3-5 個 `results/todoist-auto-*.json`，檢查 `agent` 欄位 | agent 欄位格式為 `todoist-auto-{task_key}`（底線） |
| **6c. task_key 一致** | 檢查結果 JSON 的 `task_key` 欄位 | task_key 與 frequency-limits.yaml 的 task_key 完全一致 |

**底線命名規則（黃金規則）**：
- `frequency-limits.yaml` 的 task_key 是**唯一真相來源**
- prompt 檔名：`todoist-auto-{task_key}.md`（底線）
- 結果檔名：`todoist-auto-{task_key}.json`（底線）
- `agent` 欄位：`todoist-auto-{task_key}`（底線）

**反例**：~~`todoist-auto-ai-github-research.json`~~（連字號錯誤）
**正例**：`todoist-auto-ai_github_research.json`（底線正確）

---

## 7. SKILL.md 引用一致性

| 檢查項目 | 驗證方法 | 通過標準 |
|---------|---------|---------|
| **7a. config Skill 引用** | 提取 `config/*.yaml` 所有 `skills` 陣列，比對 SKILL_INDEX.md | 所有 Skill 名稱在 SKILL_INDEX.md 速查表中存在 |
| **7b. prompt SKILL.md 路徑** | Grep `'skills/.*SKILL.md'` 在 `prompts/team/*.md`，Read 路徑 | 所有引用的 SKILL.md 檔案存在 |
| **7c. skill_aliases 豁免** | 檢查 `routing.yaml` 的 `skill_aliases` | 標記為 `no_skill_file: true` 的項目無需檢查 SKILL.md（如「程式開發（Plan-Then-Execute）」） |

---

## 驗證方法

### 手動驗證（推薦）

1. 開啟 config/*.yaml 與對應的檔案系統視窗
2. 逐一核對上述 7 個 section 的檢查項目
3. 記錄不一致項目於 `logs/validation/config-consistency-YYYYMMDD.md`

### 自動驗證（可選）

執行現有驗證腳本：
```powershell
# 已有驗證腳本
uv run python hooks/validate_config.py --check-auto-tasks
```

或開發新腳本（未來工作）：
```powershell
# 可選：建立專用驗證工具
uv run python tools/validate_config_consistency.py
```

---

## 整合指引

### 新增自動任務時

1. 在 `config/frequency-limits.yaml` 新增任務定義（使用底線）
2. 建立 `prompts/team/todoist-auto-{task_key}.md`（底線）
3. 執行本清單「1. frequency-limits.yaml 一致性」section
4. 執行本清單「6. 結果檔案命名一致性」section

### 修改 config 時

1. 修改 config/*.yaml
2. 執行對應 section 的驗證項目
3. 若涉及 Skill 引用，執行「7. SKILL.md 引用一致性」

### 整合至 CI/CD（未來工作）

將本清單轉化為 pre-commit hook 或 GitHub Actions workflow，自動驗證每次 config 變更。

---

## 參考資料

- [config/frequency-limits.yaml](../config/frequency-limits.yaml)
- [config/cache-policy.yaml](../config/cache-policy.yaml)
- [config/routing.yaml](../config/routing.yaml)
- [config/pipeline.yaml](../config/pipeline.yaml)
- [config/ooda-workflow.yaml](../config/ooda-workflow.yaml)
- [skills/SKILL_INDEX.md](../skills/SKILL_INDEX.md)
- [CLAUDE.md 自動任務命名規範](../CLAUDE.md#自動任務命名規範嚴禁使用連字號)

---

**Generated by workflow-forge** | v1.0.0 | 2026-03-22
