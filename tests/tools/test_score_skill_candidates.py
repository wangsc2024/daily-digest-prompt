"""
tests/tools/test_score_skill_candidates.py
TDD 紅燈測試 — 對應 ADR-20260323-044 複雜度維度修復

執行：uv run pytest tests/tools/test_score_skill_candidates.py -v
"""
import sys
from pathlib import Path

# 確保 tools/ 在 import path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.score_skill_candidates import _is_complexity_excluded, _score_complexity


# ── _is_complexity_excluded 測試 ──────────────────────────────────────


def test_is_complexity_excluded_simple_date():
    """date 命令應被排除（簡單 Bash，無業務邏輯）"""
    p = {"tool": "Bash", "summary_sample": "date -u +%Y-%m-%dT%H:%M:%SZ"}
    assert _is_complexity_excluded(p) is True


def test_is_complexity_excluded_health_check():
    """curl health-check 應被排除（固定格式，無業務邏輯）"""
    p = {"tool": "Bash", "summary_sample": "curl -s --max-time 5 http://localhost:3001/api/health"}
    assert _is_complexity_excluded(p) is True


def test_is_complexity_excluded_pwsh_multiline():
    """pwsh 多行命令不應被排除（有業務邏輯）"""
    p = {"tool": "Bash", "summary_sample": "pwsh -Command '\\n$t = if ($env:TODOIST) { ... } else { ... }'"}
    assert _is_complexity_excluded(p) is False


def test_is_complexity_excluded_non_bash_ignored():
    """非 Bash 工具不應被複雜度排除（由其他機制處理）"""
    p = {"tool": "Read", "summary_sample": "date -u +%Y-%m-%dT%H:%M:%SZ"}
    assert _is_complexity_excluded(p) is False


def test_is_complexity_excluded_rm_command():
    """rm 簡單命令應被排除"""
    p = {"tool": "Bash", "summary_sample": "rm temp.json"}
    assert _is_complexity_excluded(p) is True


# ── _score_complexity 測試 ────────────────────────────────────────────


def test_score_complexity_short_returns_zero():
    """極短命令得 0 分"""
    p = {"tool": "Bash", "summary_sample": "rm temp.json"}
    assert _score_complexity(p) == 0.0


def test_score_complexity_multiline_returns_high():
    """含換行符的 pwsh 命令應得高分（≥ 2.0）"""
    p = {"tool": "Bash", "summary_sample": "pwsh -Command '\\nif ($x) { Write-Host ok } else { exit 1 }'"}
    assert _score_complexity(p) >= 2.0


def test_score_complexity_pipeline_returns_mid():
    """含管道的命令應得中等分數（≥ 1.0）"""
    p = {"tool": "Bash", "summary_sample": "cat logs/structured/*.jsonl | grep ERROR | wc -l"}
    assert _score_complexity(p) >= 1.0


def test_score_complexity_long_command_returns_nonzero():
    """長命令（> 50 字元）應得到分數"""
    p = {"tool": "Bash", "summary_sample": "uv run python tools/score_skill_candidates.py --top 10 --min-score 5.0"}
    assert _score_complexity(p) >= 1.0
