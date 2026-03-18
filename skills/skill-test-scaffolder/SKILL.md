---
name: skill-test-scaffolder
version: "0.5.0"
description: |
  自動分析 SKILL.md 結構（frontmatter + 步驟），生成對應的 pytest 測試骨架檔案。
  解析 triggers、depends-on、allowed-tools、步驟編號與 I/O 描述，
  產出包含 frontmatter 驗證、觸發詞覆蓋、依賴 mock fixture、步驟行為測試的完整測試檔案。
  Use when: 為 Skill 生成測試、提升 Skills 測試覆蓋率、新建 Skill 後自動補測試、批次生成測試骨架。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "skill-test-scaffolder"
  - "生成 Skill 測試"
  - "Skill 測試骨架"
  - "自動生成測試"
  - "測試覆蓋擴充"
  - "補測試"
  - "scaffold test"
depends-on:
  - knowledge-query
  - "config/dependencies.yaml"
---

# Skill Test Scaffolder — SKILL.md → pytest 測試骨架自動生成

> **端點來源**：`config/dependencies.yaml`（deps key: `knowledge_query`）— ADR-001 Phase 3

## 設計哲學

本 Skill 讀取目標 SKILL.md 的結構化資訊（frontmatter + 步驟描述），
自動生成一份 pytest 測試骨架，涵蓋 frontmatter 驗證、觸發詞測試、依賴 mock、步驟行為測試四大類。
生成的測試檔可直接執行（紅燈），開發者只需填入實際邏輯讓測試綠燈。

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（了解現有 Skills 總覽）

---

## 步驟 1：選擇目標 Skill

**互動模式**：詢問使用者要為哪個 Skill 生成測試。
**自動模式**（由 skill-forge 或排程呼叫時）：從參數接收目標 Skill 名稱。

確認目標：
```bash
ls skills/{target_skill}/SKILL.md
```

若不存在 → 報錯並終止，記錄 `status: "failed"`。

---

## 步驟 2：解析 SKILL.md 結構

用 Python 解析目標 SKILL.md，提取結構化資訊：

```bash
uv run python -X utf8 -c "
import yaml, json, re, sys

fname = 'skills/{target_skill}/SKILL.md'
content = open(fname, encoding='utf-8').read()
parts = content.split('---')

# Frontmatter 解析
fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
body = '---'.join(parts[2:]) if len(parts) >= 3 else ''

# 步驟提取（匹配 '## 步驟 N' 或 '## Step N'）
steps = re.findall(r'##\s+(?:步驟|Step)\s+(\d+[\w.]*)[：:]\s*(.+)', body)

# depends-on 解析
deps = fm.get('depends-on', [])
skill_deps = [d for d in deps if not d.startswith('config/')]

result = {
    'name': fm.get('name', ''),
    'version': fm.get('version', ''),
    'triggers': fm.get('triggers', []),
    'allowed_tools': fm.get('allowed-tools', []),
    'depends_on': deps,
    'skill_deps': skill_deps,
    'cache_ttl': fm.get('cache-ttl', 'N/A'),
    'has_use_when': 'Use when' in fm.get('description', ''),
    'steps': [{'id': s[0], 'title': s[1].strip()} for s in steps],
    'body_chars': len(body.strip()),
    'has_degradation': bool(re.search(r'(?:降級|錯誤處理|fallback|degradation)', body, re.I))
}
print(json.dumps(result, ensure_ascii=False, indent=2))
" > temp_skill_analysis.json
```

讀取 `temp_skill_analysis.json`，確認解析成功。

---

## 步驟 3：掃描現有測試（避免覆蓋）

```bash
ls tests/skills/{target_skill}/ 2>/dev/null || echo "NO_EXISTING_TESTS"
```

- 已有測試檔 → 生成的檔名加 `_scaffolded` 後綴，避免覆蓋
- 無現有測試 → 建立目錄 `tests/skills/{target_skill}/`

---

## 步驟 4：生成 pytest 測試骨架

依步驟 2 的解析結果，用 Write 工具生成測試檔案。

**輸出路徑**：`tests/skills/{target_skill}/test_{target_skill}_scaffolded.py`

**測試骨架結構**（四大類）：

### 4a. Frontmatter 驗證測試

```python
class TestFrontmatter:
    """SKILL.md frontmatter 完整性驗證。"""

    def test_required_fields_present(self):
        """frontmatter 必須包含 name, version, description, triggers, allowed-tools。"""
        # 讀取並解析 SKILL.md frontmatter
        # assert all required fields present

    def test_description_contains_use_when(self):
        """description 必須包含 'Use when' 段落。"""

    def test_triggers_minimum_count(self):
        """triggers 至少 3 個。"""

    def test_version_format(self):
        """version 格式為 semver（X.Y.Z）。"""
```

### 4b. 觸發詞覆蓋測試

為每個 trigger 生成一個參數化測試：

```python
import pytest

TRIGGERS = {triggers_from_analysis}

class TestTriggers:
    """觸發關鍵字覆蓋測試。"""

    @pytest.mark.parametrize("trigger", TRIGGERS)
    def test_trigger_is_non_empty(self, trigger):
        """每個 trigger 必須非空。"""
        assert trigger.strip()

    @pytest.mark.parametrize("trigger", TRIGGERS)
    def test_trigger_max_length(self, trigger):
        """trigger 不超過 50 字元。"""
        assert len(trigger) <= 50
```

### 4c. 依賴 Mock Fixture

為每個 skill_deps 生成 mock fixture：

```python
@pytest.fixture
def mock_{dep_name}(monkeypatch):
    """Mock {dep_name} 依賴。"""
    # monkeypatch 或 responses 模擬
    yield
```

### 4d. 步驟行為測試骨架

為解析出的每個步驟生成一個測試類別：

```python
class TestStep{step_id}_{step_title_slug}:
    """步驟 {step_id}：{step_title} 的行為測試。"""

    def test_step_{step_id}_happy_path(self):
        """步驟 {step_id} 正常路徑。"""
        pytest.skip("TODO: 實作正常路徑測試")

    def test_step_{step_id}_error_handling(self):
        """步驟 {step_id} 錯誤處理。"""
        pytest.skip("TODO: 實作錯誤處理測試")
```

若 `has_degradation` 為 True，額外生成：

```python
class TestDegradation:
    """降級處理測試。"""

    def test_degradation_fallback(self):
        """外部依賴不可用時應正確降級。"""
        pytest.skip("TODO: 實作降級測試")
```

---

## 步驟 5：驗證生成的測試檔案

```bash
uv run python -X utf8 -c "
import ast, sys
try:
    ast.parse(open('tests/skills/{target_skill}/test_{target_skill}_scaffolded.py', encoding='utf-8').read())
    print('SYNTAX_OK: True')
except SyntaxError as e:
    print(f'SYNTAX_OK: False — {e}')
"
```

- `SYNTAX_OK: True` → 繼續
- `SYNTAX_OK: False` → 用 Edit 修正語法錯誤，最多重試 2 次

接著執行 pytest 確認可收集（不需通過，骨架測試用 `pytest.skip`）：

```bash
uv run python -m pytest tests/skills/{target_skill}/test_{target_skill}_scaffolded.py --collect-only -q 2>&1 | head -20
```

---

## 步驟 6：生成測試覆蓋報告

統計生成的測試數量與覆蓋範圍：

```bash
uv run python -X utf8 -c "
import ast, json
tree = ast.parse(open('tests/skills/{target_skill}/test_{target_skill}_scaffolded.py', encoding='utf-8').read())
classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
fixtures = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and any(
    d.attr == 'fixture' if hasattr(d, 'attr') else d.id == 'fixture'
    for d in getattr(n, 'decorator_list', []) if hasattr(d, 'attr') or hasattr(d, 'id')
)]
print(json.dumps({
    'test_classes': len(classes),
    'test_methods': len(methods),
    'fixtures': len(fixtures),
    'categories': {
        'frontmatter': len([m for m in methods if 'frontmatter' in m.name.lower() or 'required' in m.name.lower()]),
        'triggers': len([m for m in methods if 'trigger' in m.name.lower()]),
        'steps': len([m for m in methods if 'step' in m.name.lower()]),
        'degradation': len([m for m in methods if 'degrad' in m.name.lower() or 'fallback' in m.name.lower()])
    }
}))
"
```

---

## 步驟 7：匯入知識庫（可選）

若 KB 可用（`curl -s http://localhost:3000/api/health` 成功），
將生成報告匯入 KB：

用 Write 建立 `import_scaffolder_note.json`：
```json
{
  "notes": [{
    "title": "skill-test-scaffolder 生成報告：{target_skill}（{YYYY-MM-DD}）",
    "contentText": "## 測試骨架生成摘要\n目標 Skill：{target_skill}\n生成類別數：{test_classes}\n生成方法數：{test_methods}\nMock Fixtures：{fixtures}\n\n## 覆蓋範圍\n- Frontmatter 驗證：{frontmatter_count} 項\n- 觸發詞測試：{triggers_count} 項\n- 步驟行為測試：{steps_count} 項\n- 降級測試：{degradation_count} 項",
    "tags": ["skill-test-scaffolder", "測試", "pytest", "{target_skill}"],
    "source": "import"
  }],
  "autoSync": true
}
```

```bash
curl -s -X POST "http://localhost:3000/api/import" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @import_scaffolder_note.json
rm import_scaffolder_note.json
```

KB 不可用 → 跳過，記錄 `kb_imported: false`。

---

## 步驟 8：輸出結果

生成結果摘要，格式：

```
測試骨架生成完成：
- 目標 Skill：{target_skill}
- 測試檔案：tests/skills/{target_skill}/test_{target_skill}_scaffolded.py
- 測試類別：{test_classes} 個
- 測試方法：{test_methods} 個
- Mock Fixtures：{fixtures} 個
- 語法驗證：通過
- pytest 收集：通過
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| SKILL.md 不存在 | 報錯終止，status=failed |
| frontmatter 解析失敗 | 僅生成基礎測試（觸發詞 + 檔案存在性），標記 partial |
| 已有同名測試檔 | 加 `_scaffolded` 後綴，不覆蓋現有測試 |
| 生成檔案語法錯誤 | 最多重試 2 次修正，仍失敗則 status=failed |
| KB 不可用 | 跳過 KB 匯入，繼續其他步驟 |
| pytest 收集失敗 | 檢查 import 路徑，嘗試修正 conftest.py |

---

## 批次模式

支援一次為多個 Skills 生成測試骨架：

```bash
# 列出所有無測試的 Skills
uv run python -X utf8 -c "
import os, json
skills_dir = 'skills'
tests_dir = 'tests/skills'
no_test = []
for d in sorted(os.listdir(skills_dir)):
    skill_path = os.path.join(skills_dir, d, 'SKILL.md')
    test_path = os.path.join(tests_dir, d)
    if os.path.isfile(skill_path) and not os.path.isdir(test_path):
        no_test.append(d)
print(json.dumps({'skills_without_tests': no_test, 'count': len(no_test)}))
"
```

逐一對每個無測試 Skill 執行步驟 2-6，批次結束後統一匯入 KB。

---

## 注意事項

- 生成的測試使用 `pytest.skip("TODO: ...")` 標記未實作部分，確保可收集但不假通過
- Windows 環境下所有 `uv run python` 呼叫加 `-X utf8` 確保編碼正確
- 不直接修改 SKILL.md，只讀取分析
- 生成檔案必須通過 `ast.parse` 語法驗證
- 建立 `__init__.py` 確保 pytest 可發現測試目錄
