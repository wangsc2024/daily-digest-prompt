"""tests/tools/test_classify_failure.py — classify_failure.py 單元測試"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# 確保 tools/ 可被匯入
TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import classify_failure as cf


# ---------------------------------------------------------------------------
# load_taxonomy
# ---------------------------------------------------------------------------


class TestLoadTaxonomy:
    """測試 YAML taxonomy 載入邏輯。"""

    def test_load_real_taxonomy(self):
        """若 failure-taxonomy.yaml 存在，能成功載入 4 個分類。"""
        if not cf.TAXONOMY_PATH.exists():
            pytest.skip("failure-taxonomy.yaml 不存在")
        result = cf.load_taxonomy()
        assert isinstance(result, dict)
        # 預期至少包含 4 個已知分類
        expected_cats = {"external_dependency", "resource_contention",
                         "schema_mismatch", "logic_error"}
        assert expected_cats.issubset(result.keys()), f"缺少分類：{expected_cats - result.keys()}"
        # 每個分類都有 keywords 列表
        for cat, info in result.items():
            assert "keywords" in info
            assert isinstance(info["keywords"], list)
            assert len(info["keywords"]) > 0, f"{cat} 的 keywords 為空"

    def test_load_taxonomy_missing_file(self, tmp_path):
        """taxonomy 檔不存在時回傳空 dict。"""
        with patch.object(cf, "TAXONOMY_PATH", tmp_path / "nonexistent.yaml"):
            result = cf.load_taxonomy()
            assert result == {}


# ---------------------------------------------------------------------------
# classify_record
# ---------------------------------------------------------------------------


class TestClassifyRecord:
    """測試單一記錄分類。"""

    @pytest.fixture
    def categories(self):
        return {
            "external_dependency": {"keywords": ["api-call", "timeout", "connection", "500"]},
            "resource_contention": {"keywords": ["context", "token", "budget", "OOM"]},
            "schema_mismatch": {"keywords": ["schema", "validate", "JSON"]},
            "logic_error": {"keywords": ["assertion", "unexpected", "logic"]},
        }

    def test_classify_api_error(self, categories):
        record = {"tags": ["api-call", "error"], "error_category": "timeout", "message": ""}
        result = cf.classify_record(record, categories)
        assert result == "external_dependency"

    def test_classify_token_budget(self, categories):
        record = {"tags": ["warn"], "error_category": "", "message": "token budget exceeded"}
        result = cf.classify_record(record, categories)
        assert result == "resource_contention"

    def test_classify_schema_error(self, categories):
        record = {"tags": ["error"], "error_category": "", "message": "JSON schema validate failed"}
        result = cf.classify_record(record, categories)
        assert result == "schema_mismatch"

    def test_classify_logic_error(self, categories):
        record = {"tags": ["error"], "error_category": "", "message": "unexpected assertion failure"}
        result = cf.classify_record(record, categories)
        assert result == "logic_error"

    def test_classify_unclassified(self, categories):
        record = {"tags": [], "error_category": "", "message": "everything is fine"}
        result = cf.classify_record(record, categories)
        assert result == "unclassified"

    def test_classify_highest_score_wins(self, categories):
        """多個分類匹配時，分數最高的獲勝。"""
        record = {"tags": ["api-call", "error"], "error_category": "timeout connection",
                  "message": "500 error"}
        result = cf.classify_record(record, categories)
        assert result == "external_dependency"  # 4 個 keyword 匹配

    def test_empty_categories(self):
        record = {"tags": ["error"], "error_category": "", "message": "something"}
        result = cf.classify_record(record, {})
        assert result == "unclassified"


# ---------------------------------------------------------------------------
# scan_failures
# ---------------------------------------------------------------------------


class TestScanFailures:
    """測試日誌掃描與分類。"""

    @pytest.fixture
    def logs_dir(self, tmp_path):
        """建立模擬日誌目錄。"""
        logs = tmp_path / "logs" / "structured"
        logs.mkdir(parents=True)
        return logs

    @pytest.fixture
    def categories(self):
        return {
            "external_dependency": {"keywords": ["api-call", "timeout"]},
            "resource_contention": {"keywords": ["token", "budget"]},
        }

    def test_scan_finds_failures(self, logs_dir, categories):
        today = datetime.now().date()
        log_file = logs_dir / f"{today.isoformat()}.jsonl"
        records = [
            {"ts": "2026-03-23T10:00:00", "tool": "Bash", "tags": ["error", "api-call"],
             "error_category": "timeout", "message": "API timeout"},
            {"ts": "2026-03-23T10:01:00", "tool": "Read", "tags": ["info"],
             "message": "normal operation"},
            {"ts": "2026-03-23T10:02:00", "tool": "Bash", "tags": ["blocked"],
             "error_category": "", "message": "token budget exceeded"},
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        with patch.object(cf, "LOGS_DIR", logs_dir):
            failures = cf.scan_failures(1, categories)

        assert len(failures) == 2
        assert failures[0]["classified_as"] == "external_dependency"
        assert failures[1]["classified_as"] == "resource_contention"

    def test_scan_empty_dir(self, logs_dir, categories):
        with patch.object(cf, "LOGS_DIR", logs_dir):
            failures = cf.scan_failures(7, categories)
        assert failures == []

    def test_scan_skips_malformed_json(self, logs_dir, categories):
        today = datetime.now().date()
        log_file = logs_dir / f"{today.isoformat()}.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
            f.write(json.dumps({"ts": "t", "tool": "X", "tags": ["error"],
                                "error_category": "timeout", "message": ""}) + "\n")

        with patch.object(cf, "LOGS_DIR", logs_dir):
            failures = cf.scan_failures(1, categories)
        assert len(failures) == 1

    def test_scan_multi_day(self, logs_dir, categories):
        today = datetime.now().date()
        for d in range(3):
            date = today - timedelta(days=d)
            log_file = logs_dir / f"{date.isoformat()}.jsonl"
            record = {"ts": f"2026-03-{23-d}T10:00:00", "tool": "Bash",
                      "tags": ["warn"], "error_category": "api-call", "message": ""}
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

        with patch.object(cf, "LOGS_DIR", logs_dir):
            failures = cf.scan_failures(3, categories)
        assert len(failures) == 3


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """測試報告產生邏輯。"""

    def test_report_structure(self):
        failures = [
            {"classified_as": "external_dependency"},
            {"classified_as": "external_dependency"},
            {"classified_as": "schema_mismatch"},
        ]
        report = cf.generate_report(failures, 7)
        assert report["period_days"] == 7
        assert report["total_failures"] == 3
        assert report["failure_breakdown"]["external_dependency"] == 2
        assert report["failure_breakdown"]["schema_mismatch"] == 1
        assert report["top_category"] == "external_dependency"
        assert "generated_at" in report
        assert "details" in report

    def test_report_empty_failures(self):
        report = cf.generate_report([], 7)
        assert report["total_failures"] == 0
        assert report["failure_breakdown"] == {}
        assert report["top_category"] == "none"

    def test_report_details_capped(self):
        """details 最多 50 筆。"""
        failures = [{"classified_as": "x"} for _ in range(100)]
        report = cf.generate_report(failures, 7)
        assert len(report["details"]) == 50


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    """測試 CLI 入口。"""

    def test_no_args_prints_usage(self, capsys):
        with patch.object(sys, "argv", ["classify_failure.py"]):
            rc = cf.main()
        assert rc == 0
        assert "用法" in capsys.readouterr().out

    def test_report_dry_run(self, tmp_path):
        """--report --dry-run 不寫入檔案。"""
        taxonomy = {
            "external_dependency": {"keywords": ["timeout"]},
        }
        with patch.object(sys, "argv", ["classify_failure.py", "--report", "--dry-run"]), \
             patch.object(cf, "load_taxonomy", return_value=taxonomy), \
             patch.object(cf, "scan_failures", return_value=[]), \
             patch.object(cf, "OUTPUT_PATH", tmp_path / "out.json"):
            rc = cf.main()
        assert rc == 0
        assert not (tmp_path / "out.json").exists()

    def test_report_writes_file(self, tmp_path):
        """--report 寫入結果檔案。"""
        taxonomy = {
            "external_dependency": {"keywords": ["timeout"]},
        }
        output = tmp_path / "analysis" / "report.json"
        with patch.object(sys, "argv", ["classify_failure.py", "--report"]), \
             patch.object(cf, "load_taxonomy", return_value=taxonomy), \
             patch.object(cf, "scan_failures", return_value=[]), \
             patch.object(cf, "OUTPUT_PATH", output):
            rc = cf.main()
        assert rc == 0
        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["total_failures"] == 0

    def test_report_fails_without_taxonomy(self):
        with patch.object(sys, "argv", ["classify_failure.py", "--report"]), \
             patch.object(cf, "load_taxonomy", return_value={}):
            rc = cf.main()
        assert rc == 1
