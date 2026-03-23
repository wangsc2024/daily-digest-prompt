# 計畫：程式碼註解、API 文件、變更日誌智能化工作流

**計畫 ID**：twinkling-soaring-seahorse
**建立日期**：2026-03-23
**狀態**：已審查優化 v2

---

## Context

**問題**：系統擁有 47 個工具、12 個 Hooks、58 個 Skills，但沒有任何自動化的文件生成工作流：
- `CHANGELOG.md` 完全手動維護，容易漏記或格式不一致
- `tools/` 和 `hooks/` 下的 Python 檔案缺乏系統性 docstring 追蹤
- 無法量化「文件債務」（未加 docstring 的公開函式佔比）

**來源**：KB 筆記「AI 文件生成與自動化完整指南 — 程式碼註解、API 文件、變更日誌的智能化工作流（2026）」（ID: 27f25242）識別了本專案 4 個具體應用場景，本計畫落實其中最高價值的 3 個：

| 場景 | 本計畫交付 |
|------|-----------|
| CHANGELOG 自動生成 | `tools/changelog_generator.py` + auto-task |
| 程式碼文件覆蓋率 | `tools/doc_scanner.py` |
| Hook 規則文件化 | doc_scanner 含 `hooks/` 目錄掃描 |
| 系統審查報告 | 已由 system-audit Skill 覆蓋，本計畫不重複 |

**預期效果**：依 KB 筆記數據，CHANGELOG 維護時間節省 90%；docstring 覆蓋率可量化追蹤，文件債務可視化。

---

## 交付物清單

| # | 檔案 | 類型 | 說明 |
|---|------|------|------|
| 1 | `config/doc-generation.yaml` | 新建 | 文件生成工作流配置（所有參數的唯一定義處） |
| 2 | `tools/changelog_generator.py` | 新建 | Git commits → CHANGELOG.md 條目 |
| 3 | `tools/doc_scanner.py` | 新建 | Python 檔案 docstring 覆蓋率掃描 |
| 4 | `prompts/team/todoist-auto-doc_generation.md` | 新建 | Auto-task prompt（CHANGELOG + doc scan） |
| 5 | `config/frequency-limits.yaml` | 修改 | 新增 `doc_generation` 任務條目（execution_order: 33） |
| 6 | `tests/tools/__init__.py` | 新建（若不存在） | 空檔，讓 pytest 發現 tests/tools/ |
| 7 | `tests/tools/test_changelog_generator.py` | 新建 | changelog_generator 單元測試（≥12 個） |
| 8 | `tests/tools/test_doc_scanner.py` | 新建 | doc_scanner 單元測試（≥10 個） |

---

## 詳細設計

### 1. `config/doc-generation.yaml`（先建，其他工具引用）

```yaml
# 文件生成工作流配置（唯一真相來源）
version: 1

changelog:
  output_file: CHANGELOG.md          # 相對專案根目錄
  unreleased_section: "[Unreleased]" # 目標插入區段標題
  insert_marker: "### Added"         # 在此標題下一行插入（避免覆蓋手動條目）
  commit_type_mapping:               # Conventional Commit type → CHANGELOG 分類
    feat: Added
    fix: Fixed
    refactor: Changed
    docs: Changed
    chore: Changed
    perf: Changed
    test: Changed
  breaking_label: "Breaking Changes" # BREAKING CHANGE! 提交的分類
  ignored_prefixes:                  # 符合這些前綴的提交直接略過
    - "Merge"
    - "merge"
    - "wip"
  default_lookback_days: 7
  # 防重複：掃描 CHANGELOG.md 現有條目，若相同 commit hash 或描述已存在則略過
  dedup_strategy: "hash"             # 以 git short-hash 比對（7碼）

doc_scanner:
  scan_dirs:
    - hooks
    - tools
  exclude_patterns:
    - "__init__.py"
    - "query_logs.py"        # 互動式查詢工具
    - "generate_*.py"        # 多媒體生成腳本（格式不同）
    - "concat_audio.py"
    - "compose_video.py"
    - "trip_plan_outline.py"
  count_module_doc: true     # 模組頂層 docstring 計入分母
  count_class_doc: true      # 公開類別 docstring 計入
  count_function_doc: true   # 非 `_` 開頭的函式/方法 docstring 計入
  min_coverage_pct: 60       # 低於此值在 auto-task 中警告
  debt_threshold: 20         # debt_items 超過此數觸發 LLM 建議

auto_task:
  kb_tag: "文件生成"
  result_key: "doc_generation"
  result_file: "results/todoist-auto-doc_generation.json"
```

---

### 2. `tools/changelog_generator.py`

**目的**：從 git log 解析 Conventional Commits，生成結構化 CHANGELOG 條目，支援去重（不重複插入同一 commit）。

**CLI 介面**：

```bash
# 最近 7 天 dry-run（只印，不寫檔）
uv run python tools/changelog_generator.py --since 7d --dry-run

# 自動更新 CHANGELOG.md（插入 [Unreleased] → ### Added 下方）
uv run python tools/changelog_generator.py --since 7d --update-changelog

# 指定日期範圍，JSON 輸出
uv run python tools/changelog_generator.py --since 2026-03-01 --until 2026-03-23 --format json

# 最近 N 筆提交
uv run python tools/changelog_generator.py --last-n 20 --dry-run
```

**參數規格**：

| 參數 | 說明 | 預設 |
|------|------|------|
| `--since 7d` / `--since 2026-03-01` | 起始時間（相對天數或 ISO 日期） | `7d` |
| `--until 2026-03-23` | 截止日期（ISO 日期） | 今日 |
| `--last-n N` | 最近 N 筆提交（與 since/until 互斥） | — |
| `--format markdown\|json` | 輸出格式 | `markdown` |
| `--dry-run` | 只列印，不修改任何檔案 | false |
| `--update-changelog` | 寫入 CHANGELOG.md（含去重） | false |

**輸出 JSON 格式**：
```json
{
  "generated_at": "2026-03-23T10:00:00+08:00",
  "since": "2026-03-16",
  "until": "2026-03-23",
  "commit_count": 12,
  "new_entries_count": 8,
  "skipped_duplicates": 4,
  "grouped": {
    "Added": [
      {"hash": "220a108", "message": "feat: AI 架構治理方案完整實施"},
      {"hash": "02cb253", "message": "feat: kb-research-strategist Skill"}
    ],
    "Changed": [
      {"hash": "7337e40", "message": "refactor: hook-rules.yaml v2→v3"}
    ],
    "Fixed": [],
    "Breaking Changes": [],
    "Other": [
      {"hash": "35b6950", "message": "解決飢餓問題"}
    ]
  },
  "markdown_block": "### Added\n- feat: AI 架構治理方案完整實施 (`220a108`)\n..."
}
```

**關鍵實作細節**：
- 使用 `subprocess.run(["git", "log", "--oneline", "--format=%h %s", f"--since={since}"])` 呼叫 git（stdlib，不依賴額外套件）
- 正規表達式：`r'^(\w+)(?:\(([^)]+)\))?!?: (.+)$'` 解析 Conventional Commits
- `BREAKING CHANGE!` 或 `!:` 提交 → `Breaking Changes` 分類
- 無法解析的提交（無類型前綴）→ `Other` 分類
- **去重策略**：插入前讀取 CHANGELOG.md，提取現有 7 碼 hash，跳過已存在的提交
- **插入位置**：找到 `## [Unreleased]` 後再找 `### Added`，在其下方第一行插入新條目（保留既有手動條目）
- 若 `### Added` 不存在，自動建立此小節

---

### 3. `tools/doc_scanner.py`

**目的**：用 `ast` 模組解析 Python 源碼，量化 docstring 覆蓋率，識別文件債務（僅計算**公開**項目）。

**「公開」定義**：名稱不以 `_` 開頭的函式、方法、類別（`__init__` 等 dunder 方法不計）。

**CLI 介面**：

```bash
# 完整掃描，JSON 輸出（機器可讀）
uv run python tools/doc_scanner.py

# 只列出低於 70% 覆蓋率的檔案
uv run python tools/doc_scanner.py --min-coverage 70

# 人類可讀的文字報告
uv run python tools/doc_scanner.py --format text

# 指定掃描目錄（覆蓋 config）
uv run python tools/doc_scanner.py --dirs hooks tools/agent_pool
```

**輸出 JSON 格式**（`--format json`，預設）：
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
      "public_functions": {"total": 3, "documented": 2, "missing": ["check_dangerous_cmd"]},
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

**輸出文字報告**（`--format text`）：
```
=== Doc Scanner Report (2026-03-23) ===
Coverage: 52/87 items (59.8%)  Debt: 35 items

FILES BELOW 60%:
  tools/autonomous_harness.py    31.2%  (5/16)  missing: run_analysis, plan_recovery, ...
  hooks/agent_guardian.py        40.0%  (2/5)   missing: classify_error, reset_circuit

DEBT TOP 5:
  tools/autonomous_harness.py — 11 missing
  hooks/post_tool_logger.py   — 6 missing
  ...
```

---

### 4. `prompts/team/todoist-auto-doc_generation.md`

**格式**：仿照 `todoist-auto-log_audit.md`（YAML front-matter + 共用規則 + 步驟）。

**Front-matter**：
```yaml
---
name: "todoist-auto-doc_generation"
template_type: "team_prompt"
version: "1.0.0"
released_at: "2026-03-23"
---
```

**完整步驟結構**：

```markdown
你是文件維護助手，全程使用正體中文。
任務：自動更新 CHANGELOG.md 並掃描程式碼文件覆蓋率。
完成後將結果寫入 `results/todoist-auto-doc_generation.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守 Skill-First + nul 禁令。

## 立即行動：寫入 Fail-Safe 結果（最高優先）
用 Write 工具建立 `results/todoist-auto-doc_generation.json`：
{"agent":"todoist-auto-doc_generation","status":"failed","type":"doc_generation",
 "error":"task_did_not_complete_or_timeout","summary":"任務啟動但未完成","completed":false}

## 步驟 1：CHANGELOG 生成
1a. 執行：`uv run python tools/changelog_generator.py --since 7d --format json`
1b. 讀取輸出，若 new_entries_count > 0 → 執行：
    `uv run python tools/changelog_generator.py --since 7d --update-changelog`
1c. 記錄：changelog_entries_added = new_entries_count

## 步驟 2：文件覆蓋率掃描
2a. 執行：`uv run python tools/doc_scanner.py`
2b. 讀取輸出 JSON，提取 summary.coverage_pct 和 debt_report
2c. 找出 debt_items 最多的前 3 個檔案

## 步驟 3：LLM 分析（條件觸發）
僅在以下任一條件成立時執行：
- summary.coverage_pct < 60（低於 config 門檻）
- summary.debt_items > 20

若觸發：為 debt top 3 檔案中每個缺失的公開函式，產生符合現有風格的 docstring 建議範本，
以 Write 工具寫入 docs/doc-suggestions-<YYYYMMDD>.md。

## 步驟 4：寫入知識庫
讀取 `skills/knowledge-query/SKILL.md`，將本次掃描摘要（覆蓋率、債務趨勢、changelog 摘要）
匯入知識庫，tag: ["文件生成", "doc-coverage", "changelog"]。

## 步驟 5：最終結果 JSON
用 Write 工具覆寫 `results/todoist-auto-doc_generation.json`：
{
  "agent": "todoist-auto-doc_generation",
  "status": "success",
  "type": "doc_generation",
  "changelog_entries_added": <數字>,
  "doc_coverage_pct": <數字>,
  "debt_items": <數字>,
  "top_debt_files": [<前3個檔案名>],
  "llm_suggestions_generated": <true/false>,
  "kb_imported": <true/false>,
  "done_cert": {"status": "DONE", "quality_score": 4, "remaining_issues": []},
  "summary": "CHANGELOG 新增 N 條；文件覆蓋率 X%，債務 Y 項",
  "completed": true,
  "error": null
}
```

---

### 5. `config/frequency-limits.yaml` 修改

在 `tasks:` 區段末尾（kb_system_optimize 之後）新增：

```yaml
  doc_generation:
    name: "程式碼文件生成"
    daily_limit: 1
    counter_field: "doc_generation_count"
    template: "prompts/team/todoist-auto-doc_generation.md"
    template_version: 1
    history_type: "doc_generation"
    execution_order: 33           # 現有最大值為 32（kb_system_optimize）
    allowed_hours: [3, 4]         # 凌晨低峰，避開業務高峰
    timeout_seconds: 900          # 15 分鐘上限（git log + ast 解析均快速）
    result_suffix: "json"
    backend: claude_sonnet45
    skills: [knowledge-query]
```

同時將頂層 `daily_limit:` 從 `47` 改為 `48`。

---

### 6. 測試設計

**前置條件**：確認 `tests/tools/__init__.py` 存在（空檔，讓 pytest 發現此目錄）。

#### `tests/tools/test_changelog_generator.py`（≥12 個測試）

測試模式遵循 `test_compute_log_audit_trend.py` 慣例（`tmp_path` fixture、UTF-8、`ensure_ascii=False`）：

| 測試函式 | 驗證點 |
|---------|-------|
| `test_parse_feat_commit()` | `feat: msg` → `Added` 分類 |
| `test_parse_fix_commit()` | `fix: msg` → `Fixed` 分類 |
| `test_parse_breaking_commit()` | `feat!: msg` → `Breaking Changes` |
| `test_parse_scoped_commit()` | `fix(hooks): msg` → `Fixed`，scope 保留 |
| `test_parse_non_conventional()` | `解決飢餓問題` → `Other` 分類 |
| `test_ignored_prefix_skipped()` | `Merge branch ...` → 不出現在輸出 |
| `test_group_by_type_structure()` | 分組 dict 包含所有 key |
| `test_json_output_schema()` | JSON 包含 generated_at/since/until/new_entries_count/grouped |
| `test_markdown_output_format()` | markdown 含 `### Added` 標題與 `- ` 列表 |
| `test_dedup_skips_existing_hash()` | 現有 CHANGELOG 含 short-hash，跳過重複 |
| `test_update_changelog_inserts_below_added(tmp_path)` | 插入在 `### Added` 下方第一行 |
| `test_dry_run_no_file_modification(tmp_path)` | dry-run 不寫入任何檔案 |
| `test_since_relative_days()` | `--since 7d` 轉換為正確日期範圍 |
| `test_empty_range_returns_zero_entries()` | 無提交時 new_entries_count=0 |

#### `tests/tools/test_doc_scanner.py`（≥10 個測試）

| 測試函式 | 驗證點 |
|---------|-------|
| `test_module_docstring_detected(tmp_path)` | `"""..."""` 在頂層 → module_doc=true |
| `test_missing_module_docstring(tmp_path)` | 無頂層 docstring → module_doc=false |
| `test_public_function_documented(tmp_path)` | `def foo(): """..."""` → documented |
| `test_private_function_excluded(tmp_path)` | `def _bar():` → 不計入任何計數 |
| `test_dunder_excluded(tmp_path)` | `def __init__():` → 不計入 |
| `test_coverage_pct_calculation(tmp_path)` | 3 項文件化 / 4 項 = 75.0% |
| `test_exclude_patterns_applied(tmp_path)` | `query_logs.py` 不出現在結果 |
| `test_debt_report_only_missing(tmp_path)` | debt_report 只含缺失項目 |
| `test_json_output_schema(tmp_path)` | 輸出 dict 含 summary/by_file/debt_report |
| `test_text_format_contains_coverage(tmp_path)` | text 格式含 `Coverage:` 與百分比 |
| `test_scan_empty_dir(tmp_path)` | 空目錄返回 coverage_pct=100.0, total_items=0 |

---

## 關鍵依賴

| 依賴 | 說明 | 狀態 |
|------|------|------|
| `subprocess` | 呼叫 `git log` | stdlib，已有 |
| `ast` | 解析 Python 源碼 docstring | stdlib，已有 |
| `pathlib` | 路徑操作 | stdlib，已有 |
| `pyyaml` | 讀取 doc-generation.yaml | pyproject.toml 已有 |
| `git`（系統） | changelog_generator 的外部依賴 | 系統已有 |

**不引入新 pip 套件**。

---

## 驗證方式（端對端）

```bash
# 1. 確認 tests/tools/__init__.py 存在
ls tests/tools/__init__.py

# 2. 執行新增的單元測試
uv run pytest tests/tools/test_changelog_generator.py -v
uv run pytest tests/tools/test_doc_scanner.py -v

# 3. 手動驗證 changelog_generator（dry-run 不修改任何檔案）
uv run python tools/changelog_generator.py --since 7d --dry-run

# 4. 手動驗證 doc_scanner（文字報告）
uv run python tools/doc_scanner.py --format text

# 5. 驗證 frequency-limits.yaml 一致性（auto-task 完整性檢查）
uv run python hooks/validate_config.py --check-auto-tasks

# 6. 模擬完整 auto-task 執行
uv run python tools/changelog_generator.py --since 7d --update-changelog
uv run python tools/doc_scanner.py
cat results/todoist-auto-doc_generation.json | python -m json.tool

# 7. 全套件測試不退步
uv run pytest tests/ -v --tb=short
```

---

## 實作順序（依依賴關係）

1. `tests/tools/__init__.py`（空檔，最先確認）
2. `config/doc-generation.yaml`（無依賴，定義配置）
3. `tests/tools/test_changelog_generator.py` → **紅燈**
4. `tools/changelog_generator.py` → **綠燈**
5. `tests/tools/test_doc_scanner.py` → **紅燈**
6. `tools/doc_scanner.py` → **綠燈**
7. `prompts/team/todoist-auto-doc_generation.md`（依賴步驟 4、6）
8. `config/frequency-limits.yaml` 修改（最後，確保整合正確）

---

## 審查記錄（v1 → v2 修正項目）

| 問題 | 修正 |
|------|------|
| `execution_order: 34`（誤）| 改為 `33`（現有最大值 32） |
| `missing` 陣列含 `_` 開頭私有函式（自相矛盾）| 修正為只列公開函式，並澄清「公開」定義 |
| 缺少 `tests/tools/__init__.py` 交付物 | 加入交付物清單（#6） |
| auto-task prompt 無 YAML front-matter 規範 | 補充完整格式 |
| CHANGELOG 插入策略對現有手動條目處理不清 | 新增 `dedup_strategy: hash` + 插入位置精確說明 |
| `--format text` 輸出格式未定義 | 補充文字報告範例 |
| `daily_limit` 更新數值來源未確認 | 確認現有值 47，更新為 48 |
