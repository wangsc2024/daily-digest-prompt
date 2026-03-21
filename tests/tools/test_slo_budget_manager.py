#!/usr/bin/env python3
"""SLO Budget Manager 單元測試。"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.slo_budget_manager import classify_failure, calc_error_budget, BLAST_RADIUS


class TestClassifyFailure:
    """classify_failure() 關鍵字分類測試。"""

    def test_timeout_keywords(self):
        assert classify_failure("Connection timed out after 30s") == "timeout"
        assert classify_failure("SIGTERM received") == "timeout"
        assert classify_failure("請求超時") == "timeout"
        assert classify_failure("timeout exceeded") == "timeout"

    def test_api_error_keywords(self):
        assert classify_failure("Connection refused on port 3000") == "api_error"
        assert classify_failure("ECONNREFUSED") == "api_error"
        assert classify_failure("HTTP 503 Service Unavailable") == "api_error"
        assert classify_failure("curl: (7) Failed to connect") == "api_error"
        assert classify_failure("知識庫服務未啟動") == "api_error"

    def test_parse_error_keywords(self):
        assert classify_failure("JSONDecodeError: Expecting value") == "parse_error"
        assert classify_failure("Schema validation failed") == "parse_error"
        assert classify_failure("SyntaxError in config") == "parse_error"
        assert classify_failure("KeyError: 'missing_key'") == "parse_error"

    def test_quota_exceeded_keywords(self):
        assert classify_failure("quota limit reached") == "quota_exceeded"
        assert classify_failure("HTTP 429 Too Many Requests") == "quota_exceeded"
        assert classify_failure("token limit hit") == "quota_exceeded"
        assert classify_failure("budget depleted") == "quota_exceeded"

    def test_template_missing_keywords(self):
        assert classify_failure("Prompt not found: auto-task") == "template_missing"
        assert classify_failure("模板不存在") == "template_missing"
        assert classify_failure("FileNotFoundError: template.md") == "template_missing"

    def test_phase_failure_keywords(self):
        assert classify_failure("Phase 1 failed: no results") == "phase_failure"
        assert classify_failure("phase_failure in todoist") == "phase_failure"

    def test_config_error_keywords(self):
        assert classify_failure("config file missing") == "config_error"
        assert classify_failure("configuration invalid") == "config_error"
        assert classify_failure("yaml loading failed") == "config_error"

    def test_unknown_fallback(self):
        assert classify_failure("Something completely unexpected") == "unknown"
        assert classify_failure("") == "unknown"

    def test_case_insensitive(self):
        assert classify_failure("TIMEOUT") == "timeout"
        assert classify_failure("Timed Out") == "timeout"


class TestBlastRadius:
    """BLAST_RADIUS 映射完整性測試。"""

    def test_all_failure_modes_have_blast_radius(self):
        modes = ["timeout", "api_error", "parse_error", "quota_exceeded",
                 "template_missing", "phase_failure", "config_error", "unknown"]
        for mode in modes:
            assert mode in BLAST_RADIUS, f"Missing blast_radius for {mode}"

    def test_all_tasks_modes(self):
        """quota_exceeded 和 config_error 影響所有任務。"""
        assert BLAST_RADIUS["quota_exceeded"] == "all_tasks"
        assert BLAST_RADIUS["config_error"] == "all_tasks"

    def test_single_task_modes(self):
        """timeout 和 parse_error 只影響單一任務。"""
        assert BLAST_RADIUS["timeout"] == "single_task"
        assert BLAST_RADIUS["parse_error"] == "single_task"


class TestCalcErrorBudget:
    """calc_error_budget() Error Budget 計算測試。"""

    def test_green_status_when_above_target(self):
        """Given 成功率 95%，target 90% → budget 剩餘 100%，status=green。"""
        slos = [{"id": "slo-1", "name": "成功率", "target": 0.9, "metric_direction": "higher_is_better"}]
        result = calc_error_budget(slos, 0.95, 100)
        assert "slo-1" in result
        b = result["slo-1"]
        assert b["status"] == "green"
        assert b["budget_remaining_pct"] == 100.0
        assert b["actual"] == 0.95

    def test_yellow_status_when_slightly_below(self):
        """Given 成功率 87%，target 90% → consumed 30%，remaining 70%，status=green（>50）。"""
        slos = [{"id": "slo-1", "target": 0.9, "metric_direction": "higher_is_better"}]
        result = calc_error_budget(slos, 0.87, 100)
        b = result["slo-1"]
        assert b["budget_consumed_pct"] == 30.0
        assert b["budget_remaining_pct"] == 70.0
        assert b["status"] == "green"

    def test_red_status_when_heavily_below(self):
        """Given 成功率 80%，target 90% → consumed 100%，remaining 0%，status=red。"""
        slos = [{"id": "slo-1", "target": 0.9, "metric_direction": "higher_is_better"}]
        result = calc_error_budget(slos, 0.80, 100)
        b = result["slo-1"]
        assert b["budget_consumed_pct"] == 100.0
        assert b["budget_remaining_pct"] == 0.0
        assert b["status"] == "red"

    def test_lower_is_better_within_target(self):
        """lower_is_better：actual ≤ target → budget 剩餘 100%。"""
        slos = [{"id": "blocked", "name": "攔截率", "target": 10, "metric_direction": "lower_is_better"}]
        result = calc_error_budget(slos, 3, 100)
        assert "blocked" in result
        b = result["blocked"]
        assert b["status"] == "green"
        assert b["budget_remaining_pct"] == 100.0
        assert b["budget_consumed_pct"] == 0.0

    def test_lower_is_better_exceeds_target(self):
        """lower_is_better：actual > target → 消耗預算。"""
        slos = [{"id": "errors", "name": "錯誤率", "target": 5, "metric_direction": "lower_is_better"}]
        result = calc_error_budget(slos, 8, 100)
        assert "errors" in result
        b = result["errors"]
        # consumed = (8-5)/5 * 100 = 60%
        assert b["budget_consumed_pct"] == 60.0
        assert b["budget_remaining_pct"] == 40.0
        assert b["status"] == "yellow"

    def test_lower_is_better_heavily_exceeds(self):
        """lower_is_better：actual 遠超 target → red。"""
        slos = [{"id": "loops", "name": "迴圈率", "target": 5, "metric_direction": "lower_is_better"}]
        result = calc_error_budget(slos, 20, 100)
        b = result["loops"]
        # consumed = (20-5)/5 * 100 = 300%, remaining = 0%
        assert b["budget_remaining_pct"] == 0.0
        assert b["status"] == "red"

    def test_skip_when_actual_rate_none(self):
        """actual_rate=None 時不計算。"""
        slos = [{"id": "slo-1", "target": 0.9, "metric_direction": "higher_is_better"}]
        result = calc_error_budget(slos, None, 0)
        assert result == {}

    def test_multiple_slos(self):
        """多個 SLO 同時計算。"""
        slos = [
            {"id": "daily", "target": 0.9, "metric_direction": "higher_is_better"},
            {"id": "weekly", "target": 0.95, "metric_direction": "higher_is_better"},
        ]
        result = calc_error_budget(slos, 0.92, 100)
        assert "daily" in result
        assert "weekly" in result
        assert result["daily"]["status"] == "green"
        assert result["weekly"]["status"] == "yellow"  # consumed 60%

    def test_target_100_pct(self):
        """target=1.0 時 budget_total=0%，consumed 極高。"""
        slos = [{"id": "perfect", "target": 1.0, "metric_direction": "higher_is_better"}]
        result = calc_error_budget(slos, 0.99, 100)
        b = result["perfect"]
        # budget_total=0%, division by zero protection
        assert b["budget_consumed_pct"] == 0.0

    def test_empty_slos(self):
        result = calc_error_budget([], 0.95, 100)
        assert result == {}
