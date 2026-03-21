"""
tests/tools/test_trip_plan_outline.py — 行程規劃大綱工具測試

覆蓋重點：
  - 日期格式驗證（YYYY-MM-DD）
  - 時間格式驗證（HH:MM）
  - 限制條件解析
  - 目標推斷
  - 排除項目完整性
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.trip_plan_outline import (  # noqa: E402
    EXCLUSIONS,
    validate_date,
    validate_time,
    parse_constraints,
    infer_goal,
    get_suggestions,
    format_outline,
)


class TestValidateDate:
    def test_valid_iso_date(self):
        r = validate_date("2026-03-21")
        assert r.valid is True
        assert r.errors == []

    def test_invalid_format_slash(self):
        r = validate_date("2026/03/21")
        assert r.valid is False
        assert "YYYY-MM-DD" in r.errors[0]

    def test_invalid_format_short(self):
        r = validate_date("26-03-21")
        assert r.valid is False

    def test_invalid_month(self):
        r = validate_date("2026-13-01")
        assert r.valid is False


class TestValidateTime:
    def test_valid_24h(self):
        r = validate_time("09:00")
        assert r.valid is True

    def test_valid_midnight(self):
        r = validate_time("00:00")
        assert r.valid is True

    def test_invalid_hour(self):
        r = validate_time("25:00")
        assert r.valid is False
        assert "數值無效" in r.errors[0]

    def test_invalid_format(self):
        r = validate_time("9:00")
        assert r.valid is False


class TestParseConstraints:
    def test_extracts_days(self):
        c = parse_constraints("3天兩夜、台北")
        assert c.get("days") == "3"

    def test_extracts_region(self):
        c = parse_constraints("三天兩夜、台北、大眾運輸")
        assert c.get("region") == "台北"

    def test_extracts_transport(self):
        c = parse_constraints("大眾運輸、預算中等")
        assert c.get("transport") == "大眾運輸"

    def test_extracts_budget_low(self):
        c = parse_constraints("預算低、省錢")
        assert c.get("budget") == "低"


class TestInferGoal:
    def test_includes_region_and_transport(self):
        c = {"days": "3", "region": "台北", "transport": "大眾運輸"}
        g = infer_goal(c, "")
        assert "台北" in g
        assert "大眾運輸" in g


class TestExclusions:
    def test_exclusions_complete(self):
        assert "溫泉" in EXCLUSIONS
        assert "夜市" in EXCLUSIONS
        assert "寺廟" in EXCLUSIONS


class TestFormatOutline:
    def test_includes_all_sections(self):
        goal = "深度體驗台北"
        suggestions = {
            "market": ["南門市場"],
            "cultural": ["故宮"],
            "attraction": ["陽明山"],
        }
        out = format_outline(goal, suggestions, EXCLUSIONS)
        assert "行程目標" in out
        assert "必訪地點類型" in out
        assert "市場" in out
        assert "文化" in out
        assert "景點" in out
        assert "排除項目" in out
        assert "溫泉" in out
        assert "夜市" in out
        assert "寺廟" in out
        assert "南門市場" in out
        assert "故宮" in out
        assert "陽明山" in out
