# 計畫：程式碼文件、變更日誌智能化工作流（持續改善整合版）

**計畫 ID**：twinkling-soaring-seahorse
**建立日期**：2026-03-23
**版本**：v4（schema 精確對齊 + 安全邊界修正）
**狀態**：已審查，待批准

---

## Context

### 問題
系統擁有 47 個工具、12 個 Hooks、58 個 Skills，但沒有任何自動化的文件生成工作流：
- `CHANGELOG.md` 完全手動維護，容易漏記或格式不一致
- `tools/` 和 `hooks/` 的 Python 程式碼缺乏系統性 docstring 追蹤，文件債務不可見
- Agent 對系統自身結構的理解靠逐一讀檔，無統一索引入口

### KB 知識基礎（兩篇筆記）

| 筆記 ID | 標題 | 階段 | 關鍵洞察 |
|---------|------|------|---------|
| 27f25242 | AI 文件生成與自動化完整指南（2026） | foundation | LLM 節省 85-90% 文件維護時間；4 個本專案應用場景 |
| 524c2011 | AI 活文件管線實作（2026-03-12） | application | docs-as-code 概念；`llms.txt` 讓 agent 快速理解系統；`results/*.json` 可延伸為 weekly digest |

### KB 識別的 4 個本專案應用場景 → 本計畫落實

| 場景 | 本計畫交付物 |
|------|-----------|
| CHANGELOG 自動生成 | `tools/changelog_generator.py` + auto-task |
| 程式碼文件覆蓋率追蹤 | `tools/doc_scanner.py` |
| Hook 規則文件化 | doc_scanner 含 `hooks/` 目錄掃描 |
| Agent 可讀文件索引 | `docs/llms.txt` + `tools/llms_txt_generator.py` |

### OODA 閉環整合策略

`doc_generation` 不孤立運行，而是融入 OODA 閉環：

```
[doc_generation]（每日凌晨）
     │
     ├── changelog_generator.py  →  CHANGELOG.md
     ├── doc_scanner.py          →  覆蓋率報告
     ├── llms_txt_generator.py   →  docs/llms.txt
     │
     └── coverage < 60% OR debt > 20?
            │ Yes
            ▼
    improvement-backlog.json 新增條目
    （source_pattern: "doc_coverage_deficit"）
            │
            ▼
    [arch_evolution]（下一次 OODA 循環）
    讀取 backlog → 安全邊界判斷：
    ├── tools/*.py docstring → immediate_fix（安全邊界外）
    └── hooks/*.py docstring → schedule_adr（安全邊界內，需人工確認）
```

---

## 交付物清單（依實作順序）

> `tests/tools/__init__.py` 已存在（已驗證），不在清單中。

| # | 檔案 | 類型 | 說明 |
|---|------|------|------|
| 1 | `config/doc-generation.yaml` | 新建 | 所有參數的唯一定義處 |
| 2 | `tests/tools/test_changelog_generator.py` | 新建 | TDD 先寫測試（紅燈） |
| 3 | `tools/changelog_generator.py` | 新建 | Git commits → CHANGELOG.md（綠燈） |
| 4 | `tests/tools/test_doc_scanner.py` | 新建 | TDD 先寫測試（紅燈） |
| 5 | `tools/doc_scanner.py` | 新建 | Docstring 覆蓋率掃描（綠燈） |
| 6 | `tools/llms_txt_generator.py` | 新建 | 生成/更新 `docs/llms.txt` |
| 7 | `docs/llms.txt` | 新建 | Agent 可讀系統索引（首次由工具生成） |
| 8 | `prompts/team/todoist-auto-doc_generation.md` | 新建 | Auto-task prompt（7 步驟） |
| 9 | `config/frequency-limits.yaml` | 修改 | 新增 `doc_generation` 任務 + `initial_schema` 計數欄位 |

---

## 詳細設計

### 1. `config/doc-generation.yaml`（先建，所有工具引用）

```yaml
# 文件生成工作流配置（唯一真相來源）
# 引用者：tools/changelog_generator.py, doc_scanner.py,
#         llms_txt_generator.py, todoist-auto-doc_generation.md
version: 1

changelog:
  output_file: CHANGELOG.md
  unreleased_section: "[Unreleased]"
  insert_after: "### Added"        # 在此小節標題下方第一行插入新條目
  commit_type_mapping:
    feat: Added
    fix: Fixed
    refactor: Changed
    docs: Changed
    chore: Changed
    perf: Changed
    test: Changed
  breaking_label: "Breaking Changes"
  ignored_prefixes:
    - "Merge"
    - "merge"
    - "wip"
  default_lookback_days: 7
  dedup_strategy: "hash"           # 以 git 7-char short-hash 去重

doc_scanner:
  scan_dirs:
    - hooks
    - tools
  exclude_patterns:
    - "__init__.py"
    - "query_logs.py"
    - "generate_*.py"
    - "concat_audio.py"
    - "compose_video.py"
    - "trip_plan_outline.py"
    - "resolve_podcast_series.py"
    - "run_podcast_create.py"
  count_module_doc: true
  count_class_doc: true
  count_function_doc: true         # 非 `_` 開頭；dunder（__init__ 等）不計
  min_coverage_pct: 60
  debt_threshold: 20               # 超過此數觸發 improvement-backlog 寫入

llms_txt:
  output_file: docs/llms.txt
  site_name: "Daily Digest Prompt"
  site_description: >
    AI 自動化研究與知識庫系統。提供 Skills、研究模板、自動任務、
    Hook 機器層、OODA 閉環自癒機制。
  sections:
    - title: "Core Rules"
      paths:
        - templates/shared/preamble.md
        - CLAUDE.md
    - title: "Skill Map"
      paths:
        - skills/SKILL_INDEX.md
    - title: "Architecture"
      paths:
        - docs/ARCHITECTURE.md
        - docs/OPERATIONS.md
    - title: "Config"
      paths:
        - config/frequency-limits.yaml
        - config/hook-rules.yaml
        - config/doc-generation.yaml
  optional_paths:
    - context/research-registry.json
    - state/autonomous-harness-plan.json

auto_task:
  result_file: results/todoist-auto-doc_generation.json
  kb_tag: "文件生成"
  improvement_backlog_source_pattern: "doc_coverage_deficit"   # arch_evolution 去重 key
  improvement_backlog_priority: "medium"
  improvement_backlog_effort: "medium"
```

---

### 2. `tools/changelog_generator.py`

**目的**：解析 git log Conventional Commits → 去重後插入 CHANGELOG.md。

**CLI**：
```bash
uv run python tools/changelog_generator.py --since 7d --dry-run
uv run python tools/changelog_generator.py --since 7d --update-changelog
uv run python tools/changelog_generator.py --since 2026-03-01 --until 2026-03-23 --format json
uv run python tools/changelog_generator.py --last-n 20 --dry-run
```

**參數**：

| 參數 | 說明 | 預設 |
|------|------|------|
| `--since 7d \| YYYY-MM-DD` | 起始（相對天數或 ISO 日期） | `7d` |
| `--until YYYY-MM-DD` | 截止日期 | 今日 |
| `--last-n N` | 最近 N 筆（與 since/until 互斥） | — |
| `--format markdown\|json` | 輸出格式 | `markdown` |
| `--dry-run` | 只列印，不修改任何檔案 | false |
| `--update-changelog` | 寫入 CHANGELOG.md（含去重） | false |

**JSON 輸出**：
```json
{
  "generated_at": "2026-03-23T10:00:00+08:00",
  "since": "2026-03-16",
  "until": "2026-03-23",
  "commit_count": 12,
  "new_entries_count": 8,
  "skipped_duplicates": 4,
  "grouped": {
    "Added": [{"hash": "220a108", "message": "feat: AI 架構治理方案"}],
    "Changed": [{"hash": "7337e40", "message": "refactor: hook-rules v2→v3"}],
    "Fixed": [],
    "Breaking Changes": [],
    "Other": [{"hash": "35b6950", "message": "解決飢餓問題"}]
  },
  "markdown_block": "### Added\n- feat: AI 架構治理方案 (`220a108`)\n"
}
```

**關鍵實作**：
- `subprocess.run(["git", "log", "--format=%h %s", f"--since={since}"])` — 純 stdlib
- 正規表達式 `r'^(\w+)(?:\(([^)]+)\))?!?: (.+)$'` 解析 Conventional Commits
- 去重：讀 CHANGELOG.md 提取所有 7-char hash（`\(`([0-9a-f]{7})`\)` 模式），跳過已存在的 commit
- 插入：找 `## [Unreleased]` → 找 `### Added` → 在其下一行插入；若不存在則自動建立小節

---

### 3. `tools/doc_scanner.py`

**目的**：用 `ast` 模組量化 Python 程式碼 docstring 覆蓋率，識別文件債務。

**「公開項目」定義**：名稱不以 `_` 開頭的函式、方法、類別；dunder 方法（`__init__` 等）不計。

**CLI**：
```bash
uv run python tools/doc_scanner.py                    # JSON 輸出（預設）
uv run python tools/doc_scanner.py --format text      # 人類可讀報告
uv run python tools/doc_scanner.py --min-coverage 70  # 只顯示低於門檻的檔案
```

**JSON 輸出**：
```json
{
  "scanned_at": "2026-03-23T10:00:00+08:00",
  "config_used": "config/doc-generation.yaml",
  "summary": {
    "total_files": 20,
    "total_items": 87,
    "documented_items": 52,
    "coverage_pct": 59.8,
    "debt_items": 35
  },
  "by_file": {
    "hooks/pre_bash_guard.py": {
      "module_doc": true,
      "public_functions": {
        "total": 3,
        "documented": 2,
        "missing": ["check_dangerous_cmd"]
      },
      "public_classes": {"total": 0, "documented": 0, "missing": []},
      "coverage_pct": 83.3
    }
  },
  "debt_report": [
    {"file": "tools/autonomous_harness.py", "item": "run_analysis", "type": "function"},
    {"file": "hooks/pre_bash_guard.py", "item": "check_dangerous_cmd", "type": "function"}
  ]
}
```

**文字報告**（`--format text`）：
```
=== Doc Scanner (2026-03-23) ===
Coverage: 52/87 (59.8%)  Debt: 35 items

BELOW 60%:
  tools/autonomous_harness.py  31.2%  missing: run_analysis, plan_recovery...
  hooks/agent_guardian.py      40.0%  missing: classify_error, reset_circuit

TOP 5 DEBT FILES:
  tools/autonomous_harness.py — 11 missing
  hooks/post_tool_logger.py   —  6 missing
```

---

### 4. `tools/llms_txt_generator.py`

**目的**：依 `config/doc-generation.yaml` 的 `llms_txt` 區段，生成/更新 `docs/llms.txt`，讓 agent 快速理解系統結構（KB 524c2011 核心建議）。

**CLI**：
```bash
uv run python tools/llms_txt_generator.py            # 更新 docs/llms.txt
uv run python tools/llms_txt_generator.py --dry-run  # 只印出，不寫檔
```

**輸出格式**（符合 llmstxt.org 規格）：
```markdown
# Daily Digest Prompt

> AI 自動化研究與知識庫系統。提供 Skills、研究模板、自動任務、Hook 機器層、OODA 閉環自癒機制。

## Core Rules
- [templates/shared/preamble.md](templates/shared/preamble.md): 所有 agent 共同規則（Skill-First + nul 禁令）
- [CLAUDE.md](CLAUDE.md): 專案完整指引、架構決策、慣例

## Skill Map
- [skills/SKILL_INDEX.md](skills/SKILL_INDEX.md): 58 個 Skills 完整索引

## Architecture
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): 系統架構圖與決策
- [docs/OPERATIONS.md](docs/OPERATIONS.md): 執行流程與 Hooks 詳解

## Config
- [config/frequency-limits.yaml](config/frequency-limits.yaml): 自動任務頻率（唯一真相來源）
- [config/hook-rules.yaml](config/hook-rules.yaml): Hook 攔截規則
- [config/doc-generation.yaml](config/doc-generation.yaml): 文件生成工作流配置

## Optional
- [context/research-registry.json](context/research-registry.json): 近期研究索引（7天滾動）
- [state/autonomous-harness-plan.json](state/autonomous-harness-plan.json): 自主改善計畫狀態

---
*Generated by tools/llms_txt_generator.py — 2026-03-23T10:00:00+08:00*
```

---

### 5. `prompts/team/todoist-auto-doc_generation.md`

**Front-matter**：
```yaml
---
name: "todoist-auto-doc_generation"
template_type: "team_prompt"
version: "1.0.0"
released_at: "2026-03-23"
---
```

**完整步驟**：

```markdown
你是文件維護助手，全程使用正體中文。
任務：自動更新 CHANGELOG.md、掃描程式碼文件覆蓋率、維護 docs/llms.txt。
完成後將結果寫入 results/todoist-auto-doc_generation.json。

## 共用規則
先讀取 templates/shared/preamble.md，遵守 Skill-First + nul 禁令。

## 立即行動：Fail-Safe 結果寫入（最高優先）
用 Write 工具建立 results/todoist-auto-doc_generation.json：
{"agent":"todoist-auto-doc_generation","status":"failed","type":"doc_generation",
 "error":"task_did_not_complete_or_timeout","completed":false}

## 步驟 1：CHANGELOG 自動更新
1a. 讀取 config/doc-generation.yaml
1b. 執行：uv run python tools/changelog_generator.py --since 7d --format json
1c. 讀取輸出，記錄 new_entries_count 與 skipped_duplicates
1d. 若 new_entries_count > 0：
    執行：uv run python tools/changelog_generator.py --since 7d --update-changelog

## 步驟 2：文件覆蓋率掃描
2a. 執行：uv run python tools/doc_scanner.py
2b. 讀取輸出 JSON，記錄 summary.coverage_pct 和 summary.debt_items
2c. 找出 debt_report 中 debt 最多的前 3 個檔案

## 步驟 3：維護 llms.txt
3a. 執行：uv run python tools/llms_txt_generator.py
3b. 確認 docs/llms.txt 已成功更新（讀取最後一行確認時間戳）

## 步驟 4：OODA 整合（條件觸發）
條件：summary.coverage_pct < 60 OR summary.debt_items > 20

若觸發：
  4a. 讀取 context/improvement-backlog.json（若不存在初始化為 {"version":1,"items":[]}）
  4b. 檢查 items 中是否已有 source_pattern = "doc_coverage_deficit" 且 status = "Proposed"
      若已存在 → 更新該條目的 context 欄位，跳過新增
      若不存在 → 新增以下格式的條目：

  {
    "id": "backlog_doc_coverage_<YYYYMMDD>",
    "source": "doc_generation",
    "source_pattern": "doc_coverage_deficit",
    "title": "程式碼文件覆蓋率低於門檻（<X>%）",
    "priority": "medium",
    "effort": "medium",
    "context": "文件覆蓋率 <X>%，低於 60% 門檻；債務 <N> 項。tools/*.py 可 immediate_fix；hooks/*.py 需 schedule_adr（安全邊界內）",
    "decision": "",
    "consequences": "文件債務持續累積，降低系統可維護性",
    "related_files": [<top 3 debt file paths>],
    "status": "Proposed",
    "implementation_status": "pending",
    "created_at": "<ISO 時間>"
  }

  4c. 用 Write 工具更新 context/improvement-backlog.json

## 步驟 5：LLM 分析（條件觸發，僅在 coverage < 60%）
為 top 3 債務檔案中缺失的公開函式，建議符合現有風格的 docstring 範本，
寫入 docs/doc-suggestions-<YYYYMMDD>.md。

## 步驟 6：寫入知識庫
讀取 skills/knowledge-query/SKILL.md，將本次掃描摘要匯入 KB：
tag: ["文件生成", "doc-coverage", "changelog"]

## 步驟 7：最終結果 JSON（覆寫 Fail-Safe 佔位符）
用 Write 工具覆寫 results/todoist-auto-doc_generation.json：
{
  "agent": "todoist-auto-doc_generation",
  "status": "success",
  "type": "doc_generation",
  "changelog_entries_added": <數字>,
  "changelog_skipped_duplicates": <數字>,
  "doc_coverage_pct": <數字>,
  "debt_items": <數字>,
  "top_debt_files": [<前3個路徑>],
  "llms_txt_updated": true,
  "ooda_backlog_written": <true/false>,
  "llm_suggestions_generated": <true/false>,
  "kb_imported": <true/false>,
  "done_cert": {"status": "DONE", "quality_score": 4, "remaining_issues": []},
  "summary": "CHANGELOG 新增 N 條；文件覆蓋率 X%，債務 Y 項；llms.txt 已更新",
  "completed": true,
  "error": null
}
```

---

### 6. `config/frequency-limits.yaml` 修改

**修改 1**：在 `tasks:` 末尾（qa_optimize，execution_order: 35 之後）新增：

```yaml
  doc_generation:
    name: "程式碼文件生成"
    daily_limit: 1
    counter_field: "doc_generation_count"
    template: "prompts/team/todoist-auto-doc_generation.md"
    template_version: 1
    history_type: "doc_generation"
    execution_order: 36           # 現有最大值 35（qa_optimize）；跳號 27/33 為歷史預留
    allowed_hours: [3, 4]         # 凌晨低峰
    timeout_seconds: 900          # 15 分鐘上限
    result_suffix: "json"
    backend: claude_sonnet45
    skills: [knowledge-query]
```

**修改 2**：在 `initial_schema:` 的計數器欄位區段（所有 `_count: 0` 行之列）新增：
```yaml
    "doc_generation_count": 0,
```

> **注意**：本專案無頂層 `daily_limit` 欄位；各任務各自定義 `daily_limit`。

---

## 測試設計

### `tests/tools/test_changelog_generator.py`（14 個測試）

仿照 `tests/tools/test_compute_log_audit_trend.py` 慣例：`tmp_path` fixture、UTF-8、`ensure_ascii=False`。

| 測試函式 | 驗證點 |
|---------|-------|
| `test_parse_feat_commit()` | `feat: msg` → grouped["Added"] |
| `test_parse_fix_commit()` | `fix: msg` → grouped["Fixed"] |
| `test_parse_breaking_commit()` | `feat!: msg` → grouped["Breaking Changes"] |
| `test_parse_scoped_commit()` | `fix(hooks): msg` → grouped["Fixed"] |
| `test_parse_non_conventional()` | `解決飢餓問題` → grouped["Other"] |
| `test_ignored_prefix_skipped()` | `Merge branch ...` → 不出現在任何分組 |
| `test_group_by_type_all_keys()` | 輸出 dict 含所有分類 key |
| `test_json_output_schema()` | JSON 含 generated_at/since/until/new_entries_count/grouped |
| `test_markdown_output_format()` | markdown 含 `### Added` 與 `- ` 列表 |
| `test_dedup_skips_existing_hash(tmp_path)` | CHANGELOG 已有同 hash → skipped_duplicates+1 |
| `test_update_changelog_inserts_below_added(tmp_path)` | 條目插入在 `### Added` 下方第一行 |
| `test_dry_run_no_file_modification(tmp_path)` | dry-run 不寫入任何檔案 |
| `test_since_relative_days()` | `--since 7d` 轉換為正確日期範圍 |
| `test_empty_range_returns_zero(tmp_path)` | 無提交時 new_entries_count=0 |

### `tests/tools/test_doc_scanner.py`（11 個測試）

| 測試函式 | 驗證點 |
|---------|-------|
| `test_module_docstring_detected(tmp_path)` | 頂層 `"""..."""` → module_doc=true |
| `test_missing_module_docstring(tmp_path)` | 無頂層 docstring → module_doc=false |
| `test_public_function_documented(tmp_path)` | `def foo(): """..."""` → documented+1 |
| `test_private_function_excluded(tmp_path)` | `def _bar():` → 不計入任何數字 |
| `test_dunder_excluded(tmp_path)` | `def __init__():` → 不計入 |
| `test_coverage_pct_calculation(tmp_path)` | 3 文件化 / 4 項 = 75.0% |
| `test_exclude_patterns_applied(tmp_path)` | `query_logs.py` 不出現在 by_file |
| `test_debt_report_only_missing(tmp_path)` | debt_report 只含未文件化的公開項目 |
| `test_json_output_schema(tmp_path)` | 輸出含 summary/by_file/debt_report |
| `test_text_format_contains_coverage(tmp_path)` | text 格式含 `Coverage:` 與百分比 |
| `test_scan_empty_dir(tmp_path)` | 空目錄 → coverage_pct=100.0, total_items=0 |

---

## 關鍵依賴

| 依賴 | 說明 | 狀態 |
|------|------|------|
| `subprocess` | 呼叫 `git log` | stdlib，已有 |
| `ast` | 解析 Python docstring | stdlib，已有 |
| `pathlib` | 路徑操作 | stdlib，已有 |
| `pyyaml` | 讀取 doc-generation.yaml | pyproject.toml 已有 |
| `git`（系統） | changelog_generator 外部依賴 | 系統已有 |

**不引入任何新 pip 套件**。

---

## 驗證方式（端對端）

```bash
# 1. TDD — 先跑測試（紅燈，工具尚不存在）
uv run pytest tests/tools/test_changelog_generator.py -v
uv run pytest tests/tools/test_doc_scanner.py -v

# 2. 實作後再跑（應全部綠燈）
uv run pytest tests/tools/test_changelog_generator.py tests/tools/test_doc_scanner.py -v

# 3. 手動驗證工具（dry-run，不修改任何檔案）
uv run python tools/changelog_generator.py --since 7d --dry-run
uv run python tools/doc_scanner.py --format text
uv run python tools/llms_txt_generator.py --dry-run

# 4. 驗證 frequency-limits.yaml 一致性
uv run python hooks/validate_config.py --check-auto-tasks

# 5. 全套件測試不退步
uv run pytest tests/ -v --tb=short

# 6. 端對端模擬（更新實際檔案）
uv run python tools/changelog_generator.py --since 7d --update-changelog
uv run python tools/doc_scanner.py
uv run python tools/llms_txt_generator.py
cat results/todoist-auto-doc_generation.json | python -m json.tool
```

---

## 審查記錄

| 版本 | 主要修正 |
|------|---------|
| v1 | 初版 |
| v2 | execution_order 34→33；補 `__init__.py`；修正 private function 矛盾；補 front-matter；CHANGELOG 去重策略；text 格式定義 |
| v3 | execution_order 33→36（確認 max=35）；刪除錯誤「47→48 daily_limit」；加 `llms.txt` + `llms_txt_generator`；加 OODA 閉環圖；7 步驟 auto-task prompt |
| v4 | **移除已存在的 `tests/tools/__init__.py`**（已驗證存在）；**修正 improvement-backlog 條目 schema**（`source_pattern`/`priority`/`context`/`status`/`implementation_status` 對齊實際 arch_evolution 消費格式）；**加安全邊界說明**（hooks/*.py → schedule_adr；tools/*.py → immediate_fix）；**修正 `initial_schema` 計數欄位說明**；`improvement_backlog_type` 改名為 `improvement_backlog_source_pattern` |
