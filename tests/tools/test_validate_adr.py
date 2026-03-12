"""
tests/tools/test_validate_adr.py — ADR 驗證工具（P0-A）TDD

覆蓋重點（15 個測試）：
  - validate_record：必填欄位、非法 status、id 格式、consequences 空字串
  - calc_tech_debt_score：pending+Accepted、age>365、age>180、P0 bonus
  - find_stale：Accepted+pending 且 age>=90、未達閾值不列出、非 Accepted 不列出
  - age_days：ISO 格式解析
  - run_check：通過/失敗、JSON report 結構
"""
import json
import sys
from pathlib import Path
from datetime import date, timedelta

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validate_adr import (  # noqa: E402
    REQUIRED_FIELDS,
    VALID_STATUSES,
    age_days,
    calc_tech_debt_score,
    find_stale,
    validate_record,
    run_check,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_record(**kwargs) -> dict:
    """最小合法 ADR 記錄"""
    base = {
        "id": "ADR-20260101-001",
        "title": "測試 ADR",
        "status": "Proposed",
        "created_at": "2026-01-01",
        "context": "背景說明（10 字以上）",
        "decision": "決策內容",
        "consequences": ["後果 A", "後果 B"],
        "implementation_status": "pending",
    }
    base.update(kwargs)
    return base


# ── validate_record ───────────────────────────────────────────────────────────

class TestValidateRecord:
    def test_valid_record_no_errors(self):
        rec = _make_record()
        assert validate_record(rec, 0) == []

    def test_missing_required_field(self):
        rec = _make_record()
        del rec["title"]
        errors = validate_record(rec, 0)
        assert any("title" in e for e in errors)

    def test_all_required_fields_missing(self):
        """若記錄為空，所有必填欄位均報錯"""
        errors = validate_record({}, 0)
        # 至少回報 REQUIRED_FIELDS 數量的錯誤
        assert len(errors) >= len(REQUIRED_FIELDS)

    def test_invalid_status(self):
        rec = _make_record(status="Unknown")
        errors = validate_record(rec, 0)
        assert any("status" in e or "Unknown" in e for e in errors)

    def test_valid_statuses_accepted(self):
        for status in VALID_STATUSES:
            rec = _make_record(status=status)
            errors = [e for e in validate_record(rec, 0) if "status" in e.lower() or "非法" in e]
            assert errors == [], f"status={status} 不應回報 status 錯誤"

    def test_invalid_id_format(self):
        rec = _make_record(id="ADR-001")
        errors = validate_record(rec, 0)
        assert any("id" in e or "格式" in e for e in errors)

    def test_valid_id_format(self):
        rec = _make_record(id="ADR-20260311-099")
        errors = [e for e in validate_record(rec, 0) if "格式" in e]
        assert errors == []

    def test_empty_string_consequences(self):
        rec = _make_record(consequences="")
        errors = validate_record(rec, 0)
        assert any("consequences" in e for e in errors)

    def test_list_consequences_ok(self):
        rec = _make_record(consequences=["後果 A"])
        errors = [e for e in validate_record(rec, 0) if "consequences" in e]
        assert errors == []


# ── calc_tech_debt_score ──────────────────────────────────────────────────────

class TestCalcTechDebtScore:
    def test_pending_accepted_adds_5(self):
        rec = _make_record(status="Accepted", implementation_status="pending")
        score = calc_tech_debt_score(rec)
        assert score >= 5.0

    def test_non_pending_no_base_score(self):
        rec = _make_record(status="Accepted", implementation_status="completed")
        score = calc_tech_debt_score(rec)
        assert score < 5.0

    def test_age_over_365_adds_3(self):
        old_date = (date.today() - timedelta(days=400)).isoformat()
        rec = _make_record(status="Proposed", implementation_status="pending",
                           created_at=old_date)
        score = calc_tech_debt_score(rec)
        # 僅年齡加分（非 Accepted，不加 5）
        assert score >= 3.0

    def test_age_180_to_365_adds_2(self):
        mid_date = (date.today() - timedelta(days=200)).isoformat()
        rec = _make_record(status="Proposed", implementation_status="pending",
                           created_at=mid_date)
        score = calc_tech_debt_score(rec)
        assert score >= 2.0

    def test_p0_pending_adds_2(self):
        rec = _make_record(status="Proposed", implementation_status="pending", priority="P0")
        score = calc_tech_debt_score(rec)
        # P0 bonus = +2（無 age bonus，無 Accepted base）
        assert score >= 2.0

    def test_score_capped_at_10(self):
        old_date = (date.today() - timedelta(days=500)).isoformat()
        rec = _make_record(status="Accepted", implementation_status="pending",
                           created_at=old_date, priority="P0")
        score = calc_tech_debt_score(rec)
        assert score <= 10.0


# ── find_stale ────────────────────────────────────────────────────────────────

class TestFindStale:
    def test_stale_accepted_pending_over_90_days(self):
        old_date = (date.today() - timedelta(days=100)).isoformat()
        rec = _make_record(status="Accepted", implementation_status="pending",
                           created_at=old_date)
        stale = find_stale([rec])
        assert len(stale) == 1
        assert stale[0]["_stale_days"] >= 90

    def test_fresh_accepted_not_stale(self):
        rec = _make_record(status="Accepted", implementation_status="pending",
                           created_at=date.today().isoformat())
        assert find_stale([rec]) == []

    def test_non_accepted_not_stale(self):
        old_date = (date.today() - timedelta(days=200)).isoformat()
        rec = _make_record(status="Proposed", implementation_status="pending",
                           created_at=old_date)
        assert find_stale([rec]) == []

    def test_completed_not_stale(self):
        old_date = (date.today() - timedelta(days=200)).isoformat()
        rec = _make_record(status="Accepted", implementation_status="completed",
                           created_at=old_date)
        assert find_stale([rec]) == []


# ── age_days ──────────────────────────────────────────────────────────────────

class TestAgeDays:
    def test_today_zero_days(self):
        assert age_days(date.today().isoformat()) == 0

    def test_past_date(self):
        past = (date.today() - timedelta(days=30)).isoformat()
        assert age_days(past) == 30


# ── run_check ─────────────────────────────────────────────────────────────────

class TestRunCheck:
    def _write_registry(self, tmp_path: Path, records: list) -> Path:
        f = tmp_path / "adr-registry.json"
        f.write_text(json.dumps({"records": records}), encoding="utf-8")
        return f

    def test_valid_records_returns_true(self, tmp_path):
        registry = self._write_registry(tmp_path, [_make_record()])
        assert run_check(registry) is True

    def test_invalid_records_returns_false(self, tmp_path):
        bad = _make_record(status="INVALID_STATUS")
        registry = self._write_registry(tmp_path, [bad])
        assert run_check(registry) is False

    def test_json_report_structure(self, tmp_path, capsys):
        registry = self._write_registry(tmp_path, [_make_record()])
        run_check(registry, report_json=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total_adrs" in data
        assert "passed" in data
        assert "errors" in data
        assert "stale_adrs" in data
        assert "tech_debt_scores" in data
