# 實作計畫：Daily Digest Prompt 專案優化

## 概要
- **目標**：提升專案的測試覆蓋率、程式碼品質、安全性與可維護性
- **預估任務數**：9 個
- **相關文件**：CLAUDE.md、SKILLS_INDEX.md

## 架構說明
本專案是 Skill-First 架構的自動化每日摘要系統，主要包含：
- PowerShell 排程腳本（run-agent.ps1、run-agent-team.ps1）
- Python CLI 工具（todoist.py）
- Skill 模組（11 個核心 Skills）
- 持久化檔案（context/、cache/、state/、results/）

## 技術棧
- 語言：PowerShell 5.1+、Python 3.x
- 測試：pytest（Python）、Pester（PowerShell，可選）
- Lint：ruff（Python）

## 執行方式
使用 `executing-plans` skill 執行此計畫

---

## 優化項目識別

### 🔴 Critical（必須修復）
1. **無測試覆蓋**：todoist.py 是核心 Python 工具，目前沒有任何測試
2. **Git 尚未提交**：專案有 untracked files 但沒有 commit 歷史

### 🟡 High（建議修復）
3. **Token 硬編碼**：API token 直接寫在 SKILL.md 和程式碼中，有安全風險
4. **Python 工具缺少 requirements.txt**：todoist.py 依賴 requests 但未宣告

### 🟢 Medium（程式碼品質）
5. **PowerShell 腳本缺少錯誤處理**：部分邊界情況未處理
6. **check-health.ps1 的日期解析可能失敗**：使用 `[datetime]::Parse` 但無 try-catch
7. **todoist.py 異常處理可改進**：bare except 應改為具體 exception type

### 🔵 Low（改善體驗）
8. **缺少 .editorconfig**：確保協作者使用一致的編碼格式
9. **缺少 pyproject.toml**：現代 Python 專案標準配置

---

## Task 1: 初始化 Git 提交

### 目標
建立初始 commit，確保版本控制正常運作

### 步驟

#### 1.1 檢查 .gitignore
檔案：`.gitignore`
確認已排除敏感檔案和暫存目錄。

#### 1.2 執行初始提交
```bash
cd D:/Source/daily-digest-prompt
git add .
git commit -m "chore: initial commit - daily digest prompt system"
```

#### 1.3 驗證
```bash
git log --oneline
# 預期：看到初始 commit
```

---

## Task 2: 建立 Python 專案配置

### 目標
建立標準的 Python 專案結構，宣告依賴

### 步驟

#### 2.1 建立 pyproject.toml
檔案：`pyproject.toml`

```toml
[project]
name = "daily-digest-prompt"
version = "0.1.0"
description = "Automated daily digest system with Claude Code"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N"]
ignore = ["E501"]
```

#### 2.2 驗證
```bash
cd D:/Source/daily-digest-prompt
cat pyproject.toml
# 預期：顯示完整的 pyproject.toml 內容
```

#### 2.3 Commit
```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml with dependencies and tool configs"
```

---

## Task 3: 建立測試目錄結構

### 目標
建立測試目錄和基礎設施

### 步驟

#### 3.1 建立測試目錄
```bash
mkdir -p D:/Source/daily-digest-prompt/tests/skills/todoist
```

#### 3.2 建立 conftest.py
檔案：`tests/conftest.py`

```python
"""Pytest fixtures for daily-digest-prompt tests."""
import os
import sys
import pytest

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "skills", "todoist", "scripts"))


@pytest.fixture
def mock_api_token():
    """Provide a mock API token for testing."""
    return "test_token_12345"


@pytest.fixture
def sample_task():
    """Provide a sample Todoist task."""
    return {
        "id": "12345",
        "content": "測試任務",
        "description": "",
        "priority": 4,
        "due": {
            "date": "2026-02-12",
            "string": "today"
        },
        "labels": ["work"]
    }


@pytest.fixture
def sample_tasks(sample_task):
    """Provide a list of sample tasks."""
    return [
        sample_task,
        {
            "id": "12346",
            "content": "低優先級任務",
            "priority": 1,
            "due": None,
            "labels": []
        },
        {
            "id": "12347",
            "content": "中優先級任務",
            "priority": 2,
            "due": {
                "date": "2026-02-20",
                "string": "next week"
            },
            "labels": ["personal"]
        }
    ]
```

#### 3.3 建立 __init__.py
檔案：`tests/__init__.py`

```python
"""Tests for daily-digest-prompt."""
```

檔案：`tests/skills/__init__.py`

```python
"""Tests for skills."""
```

檔案：`tests/skills/todoist/__init__.py`

```python
"""Tests for todoist skill."""
```

#### 3.4 驗證目錄結構
```bash
ls -la D:/Source/daily-digest-prompt/tests/
# 預期：看到 conftest.py 和 skills/ 目錄
```

#### 3.5 Commit
```bash
git add tests/
git commit -m "test: add test directory structure and fixtures"
```

---

## Task 4: 為 TodoistAPI 撰寫單元測試（格式化方法）

### 目標
測試 todoist.py 中的 format_task 和 format_tasks 方法

### 步驟

#### 4.1 寫測試
檔案：`tests/skills/todoist/test_todoist_format.py`

```python
"""Tests for TodoistAPI formatting methods."""
import pytest
from datetime import datetime, timedelta
from todoist import TodoistAPI


class TestFormatTask:
    """Tests for format_task method."""

    def test_format_task_with_high_priority(self, mock_api_token, sample_task, monkeypatch):
        """High priority task should show red emoji."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_task(sample_task)

        assert "🔴" in result  # p1 = priority 4
        assert "測試任務" in result

    def test_format_task_with_low_priority(self, mock_api_token, monkeypatch):
        """Low priority task should show white emoji."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        task = {"content": "低優先級", "priority": 1}

        result = api.format_task(task)

        assert "⚪" in result
        assert "低優先級" in result

    def test_format_task_with_overdue(self, mock_api_token, monkeypatch):
        """Overdue task should show overdue indicator."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        task = {
            "content": "過期任務",
            "priority": 2,
            "due": {"date": yesterday}
        }

        result = api.format_task(task)

        assert "過期" in result

    def test_format_task_with_today_due(self, mock_api_token, monkeypatch):
        """Task due today should show today indicator."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        today = datetime.now().strftime("%Y-%m-%d")
        task = {
            "content": "今日任務",
            "priority": 3,
            "due": {"date": today}
        }

        result = api.format_task(task)

        assert "今日" in result

    def test_format_task_with_labels(self, mock_api_token, monkeypatch):
        """Task with labels should show them."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()
        task = {
            "content": "有標籤",
            "priority": 1,
            "labels": ["work", "urgent"]
        }

        result = api.format_task(task)

        assert "@work" in result
        assert "@urgent" in result

    def test_format_task_with_id(self, mock_api_token, sample_task, monkeypatch):
        """Task formatted with show_id should include ID."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_task(sample_task, show_id=True)

        assert "[ID:12345]" in result


class TestFormatTasks:
    """Tests for format_tasks method."""

    def test_format_empty_tasks(self, mock_api_token, monkeypatch):
        """Empty task list should return specific message."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks([])

        assert "無任務" in result

    def test_format_tasks_sorted_by_priority(self, mock_api_token, sample_tasks, monkeypatch):
        """Tasks should be sorted by priority (high first)."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks(sample_tasks)
        lines = result.strip().split("\n")

        # First line should be high priority (🔴)
        assert "🔴" in lines[0]


class TestFormatTasksGrouped:
    """Tests for format_tasks_grouped method."""

    def test_format_grouped_empty(self, mock_api_token, monkeypatch):
        """Empty task list should return specific message."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks_grouped([])

        assert "無任務" in result

    def test_format_grouped_shows_priority_headers(self, mock_api_token, sample_tasks, monkeypatch):
        """Grouped format should show priority headers."""
        monkeypatch.setenv("TODOIST_API_TOKEN", mock_api_token)
        api = TodoistAPI()

        result = api.format_tasks_grouped(sample_tasks)

        assert "P1" in result.upper()  # Should have P1 header
```

#### 4.2 驗證測試失敗
```bash
cd D:/Source/daily-digest-prompt
python -m pytest tests/skills/todoist/test_todoist_format.py -v
# 預期：測試可執行（可能因 import 而失敗，這是正常的紅燈階段）
```

#### 4.3 確認測試通過
由於 todoist.py 已存在，測試應該通過。執行：
```bash
python -m pytest tests/skills/todoist/test_todoist_format.py -v
# 預期：所有測試通過
```

#### 4.4 Commit
```bash
git add tests/
git commit -m "test: add unit tests for TodoistAPI formatting methods"
```

---

## Task 5: 為 TodoistAPI 撰寫單元測試（API 方法 - Mock）

### 目標
使用 mock 測試 TodoistAPI 的 API 呼叫方法

### 步驟

#### 5.1 寫測試
檔案：`tests/skills/todoist/test_todoist_api.py`

```python
"""Tests for TodoistAPI request methods using mocks."""
import pytest
from unittest.mock import Mock, patch
from todoist import TodoistAPI


class TestTodoistAPIInit:
    """Tests for TodoistAPI initialization."""

    def test_init_with_token_param(self):
        """API should accept token as parameter."""
        api = TodoistAPI(api_token="test_token")
        assert api.api_token == "test_token"

    def test_init_with_env_var(self, monkeypatch):
        """API should read token from environment variable."""
        monkeypatch.setenv("TODOIST_API_TOKEN", "env_token")
        api = TodoistAPI()
        assert api.api_token == "env_token"

    def test_init_without_token_raises(self, monkeypatch):
        """API should raise ValueError without token."""
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        with pytest.raises(ValueError):
            TodoistAPI()


class TestGetTasks:
    """Tests for get_tasks method."""

    @patch("todoist.requests.request")
    def test_get_tasks_success(self, mock_request, mock_api_token):
        """Successful API call should return task list."""
        mock_response = Mock()
        mock_response.text = '[{"id": "1", "content": "Task 1"}]'
        mock_response.json.return_value = [{"id": "1", "content": "Task 1"}]
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        tasks = api.get_tasks()

        assert len(tasks) == 1
        assert tasks[0]["id"] == "1"
        mock_request.assert_called_once()

    @patch("todoist.requests.request")
    def test_get_tasks_with_filter(self, mock_request, mock_api_token):
        """Filter parameter should be passed to API."""
        mock_response = Mock()
        mock_response.text = "[]"
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.get_tasks(filter_query="today")

        call_args = mock_request.call_args
        assert call_args[1]["params"]["filter"] == "today"


class TestCreateTask:
    """Tests for create_task method."""

    @patch("todoist.requests.request")
    def test_create_task_success(self, mock_request, mock_api_token):
        """Successful task creation should return task object."""
        mock_response = Mock()
        mock_response.text = '{"id": "new_task", "content": "New Task"}'
        mock_response.json.return_value = {"id": "new_task", "content": "New Task"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        task = api.create_task(content="New Task")

        assert task["id"] == "new_task"
        call_args = mock_request.call_args
        assert call_args[1]["json"]["content"] == "New Task"

    @patch("todoist.requests.request")
    def test_create_task_with_all_options(self, mock_request, mock_api_token):
        """Task creation should accept all optional parameters."""
        mock_response = Mock()
        mock_response.text = '{"id": "1"}'
        mock_response.json.return_value = {"id": "1"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        api.create_task(
            content="Task",
            description="Description",
            due_string="tomorrow",
            priority=4,
            labels=["work"]
        )

        call_args = mock_request.call_args
        data = call_args[1]["json"]
        assert data["content"] == "Task"
        assert data["description"] == "Description"
        assert data["due_string"] == "tomorrow"
        assert data["priority"] == 4
        assert data["labels"] == ["work"]


class TestCompleteTask:
    """Tests for complete_task method."""

    @patch("todoist.requests.request")
    def test_complete_task_success(self, mock_request, mock_api_token):
        """Successful completion should return True."""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        api = TodoistAPI(api_token=mock_api_token)
        result = api.complete_task("12345")

        assert result is True
        call_args = mock_request.call_args
        assert "12345/close" in call_args[1]["url"]


class TestErrorHandling:
    """Tests for error handling."""

    @patch("todoist.requests.request")
    def test_http_error_returns_none(self, mock_request, mock_api_token, capsys):
        """HTTP errors should return None and print error."""
        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.json.side_effect = ValueError()

        error = HTTPError(response=mock_response)
        mock_request.return_value.raise_for_status.side_effect = error

        api = TodoistAPI(api_token=mock_api_token)
        result = api.get_tasks()

        assert result == []  # get_tasks returns [] on error

    @patch("todoist.requests.request")
    def test_network_error_returns_none(self, mock_request, mock_api_token, capsys):
        """Network errors should return None and print error."""
        from requests.exceptions import ConnectionError

        mock_request.side_effect = ConnectionError("Network error")

        api = TodoistAPI(api_token=mock_api_token)
        result = api.get_tasks()

        assert result == []  # get_tasks returns [] on error
```

#### 5.2 驗證測試
```bash
cd D:/Source/daily-digest-prompt
python -m pytest tests/skills/todoist/test_todoist_api.py -v
# 預期：測試通過
```

#### 5.3 Commit
```bash
git add tests/
git commit -m "test: add API method tests with mocks for TodoistAPI"
```

---

## Task 6: 改善 todoist.py 異常處理

### 目標
將 bare except 改為具體的 exception type

### 步驟

#### 6.1 寫測試（驗證異常類型）
這個改動是重構，現有測試已覆蓋行為，只需確保測試仍通過。

#### 6.2 實作
檔案：`skills/todoist/scripts/todoist.py`

修改第 63-64 行的 bare except：
```python
# 原本
except:
    error_msg += f": {e.response.text}"

# 改為
except (ValueError, KeyError):
    error_msg += f": {e.response.text}"
```

#### 6.3 驗證測試通過
```bash
python -m pytest tests/skills/todoist/ -v
# 預期：所有測試仍通過
```

#### 6.4 Commit
```bash
git add skills/todoist/scripts/todoist.py
git commit -m "refactor: replace bare except with specific exception types in todoist.py"
```

---

## Task 7: 改善 check-health.ps1 日期解析錯誤處理

### 目標
為日期解析加入 try-catch 防護

### 步驟

#### 7.1 實作
檔案：`check-health.ps1`

修改第 40-42 行，將 `[datetime]::Parse` 包裝在 try-catch 中：
```powershell
# 原本
$recentRuns = $runs | Where-Object {
    [datetime]::Parse($_.timestamp) -gt $sevenDaysAgo
}

# 改為
$recentRuns = $runs | Where-Object {
    try {
        [datetime]::Parse($_.timestamp) -gt $sevenDaysAgo
    }
    catch {
        $false  # 無法解析的記錄視為不在範圍內
    }
}
```

#### 7.2 驗證
```bash
powershell -ExecutionPolicy Bypass -File D:/Source/daily-digest-prompt/check-health.ps1
# 預期：正常執行，無錯誤
```

#### 7.3 Commit
```bash
git add check-health.ps1
git commit -m "fix: add error handling for date parsing in check-health.ps1"
```

---

## Task 8: 建立 .editorconfig

### 目標
確保協作者使用一致的編碼格式

### 步驟

#### 8.1 建立 .editorconfig
檔案：`.editorconfig`

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.md]
trim_trailing_whitespace = false

[*.{json,yml,yaml}]
indent_size = 2

[*.ps1]
indent_size = 4
end_of_line = crlf

[Makefile]
indent_style = tab
```

#### 8.2 驗證
```bash
cat D:/Source/daily-digest-prompt/.editorconfig
# 預期：顯示完整內容
```

#### 8.3 Commit
```bash
git add .editorconfig
git commit -m "chore: add .editorconfig for consistent formatting"
```

---

## Task 9: 建立安全性文件提示

### 目標
建立 SECURITY.md 提醒 Token 管理最佳實踐（不修改現有 Token 配置）

### 步驟

#### 9.1 建立 SECURITY.md
檔案：`SECURITY.md`

```markdown
# Security Policy

## API Token 管理

本專案使用以下外部服務 API：
- Todoist API
- ntfy.sh

### 建議做法

1. **環境變數**（推薦）
   ```bash
   export TODOIST_API_TOKEN="your_token_here"
   ```

2. **本地配置檔**（.gitignore 已排除）
   - 將敏感配置放在 `.env` 或 `secrets/` 目錄
   - 確保這些檔案已加入 .gitignore

### 目前配置說明

為了簡化部署，部分 Token 目前直接寫在 SKILL.md 中。
若需要更高安全性，請：
1. 將 Token 移至環境變數
2. 修改 SKILL.md 引用環境變數

## 報告漏洞

如發現安全問題，請直接聯繫專案維護者。
```

#### 9.2 更新 .gitignore
確認 `.gitignore` 已包含敏感檔案排除：
```bash
grep -E "\.env|secrets" D:/Source/daily-digest-prompt/.gitignore || echo "需要添加"
```

若未包含，加入：
```
.env
.env.*
secrets/
```

#### 9.3 Commit
```bash
git add SECURITY.md .gitignore
git commit -m "docs: add SECURITY.md with token management guidelines"
```

---

## 驗證清單

執行完所有任務後，確認：

- [ ] `git log --oneline` 顯示 9 個 commits
- [ ] `python -m pytest tests/ -v` 所有測試通過
- [ ] `python -m pytest tests/ --cov=skills/todoist/scripts --cov-report=term` 覆蓋率 ≥ 60%
- [ ] `powershell -ExecutionPolicy Bypass -File check-health.ps1` 正常執行
- [ ] 目錄結構完整：
  - `tests/conftest.py`
  - `tests/skills/todoist/test_todoist_format.py`
  - `tests/skills/todoist/test_todoist_api.py`
  - `pyproject.toml`
  - `.editorconfig`
  - `SECURITY.md`

---

## 下一步建議

完成本計畫後，可考慮：

1. **CI/CD 設定**：加入 GitHub Actions 自動執行測試
2. **PowerShell 測試**：使用 Pester 框架測試 .ps1 腳本
3. **Token 遷移**：將硬編碼 Token 遷移至環境變數
4. **更多測試**：為其他 Skill 建立整合測試
