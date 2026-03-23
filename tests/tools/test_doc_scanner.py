"""Tests for tools/doc_scanner.py — TDD red phase."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.doc_scanner import DocScanner, scan_file, ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# scan_file — module docstring
# ---------------------------------------------------------------------------

def test_module_docstring_detected(tmp_path: Path):
    p = _write_py(tmp_path, "mod.py", '"""Module docstring."""\n\ndef foo():\n    """Foo."""\n    pass\n')
    result = scan_file(p)
    assert result.module_doc is True


def test_missing_module_docstring(tmp_path: Path):
    p = _write_py(tmp_path, "mod.py", "def foo():\n    pass\n")
    result = scan_file(p)
    assert result.module_doc is False


# ---------------------------------------------------------------------------
# scan_file — public functions
# ---------------------------------------------------------------------------

def test_public_function_documented(tmp_path: Path):
    src = '"""Module."""\ndef foo():\n    """Foo docstring."""\n    pass\n'
    p = _write_py(tmp_path, "mod.py", src)
    result = scan_file(p)
    assert result.public_functions["documented"] == 1
    assert result.public_functions["total"] == 1
    assert "foo" not in result.public_functions["missing"]


def test_private_function_excluded(tmp_path: Path):
    src = '"""Module."""\ndef _bar():\n    pass\n'
    p = _write_py(tmp_path, "mod.py", src)
    result = scan_file(p)
    assert result.public_functions["total"] == 0


def test_dunder_excluded(tmp_path: Path):
    src = '"""Module."""\nclass Cls:\n    def __init__(self):\n        pass\n'
    p = _write_py(tmp_path, "mod.py", src)
    result = scan_file(p)
    assert result.public_functions["total"] == 0


# ---------------------------------------------------------------------------
# coverage_pct calculation
# ---------------------------------------------------------------------------

def test_coverage_pct_calculation(tmp_path: Path):
    # 3 documented out of 4 items (module_doc + 3 funcs, 2 have docstring)
    src = (
        '"""Module."""\n'
        "def foo():\n    \"\"\"Foo.\"\"\"\n    pass\n"
        "def bar():\n    \"\"\"Bar.\"\"\"\n    pass\n"
        "def baz():\n    pass\n"
    )
    p = _write_py(tmp_path, "mod.py", src)
    result = scan_file(p)
    # module_doc(1) + foo(1) + bar(1) = 3 documented; baz(0); total = 4 items
    assert result.coverage_pct == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# DocScanner — exclude_patterns
# ---------------------------------------------------------------------------

def test_exclude_patterns_applied(tmp_path: Path):
    # Create query_logs.py — should be excluded
    _write_py(tmp_path, "query_logs.py", "def foo():\n    pass\n")
    _write_py(tmp_path, "real_tool.py", '"""Module."""\ndef bar():\n    """Bar."""\n    pass\n')
    scanner = DocScanner(scan_dirs=[tmp_path], exclude_patterns=["query_logs.py"])
    report = scanner.scan()
    assert "query_logs.py" not in str(report["by_file"])


def test_debt_report_only_missing(tmp_path: Path):
    src = '"""Module."""\ndef foo():\n    \"\"\"Foo.\"\"\"\n    pass\ndef bar():\n    pass\n'
    p = _write_py(tmp_path, "mod.py", src)
    scanner = DocScanner(scan_dirs=[tmp_path], exclude_patterns=[])
    report = scanner.scan()
    debt = report["debt_report"]
    items = [d["item"] for d in debt]
    assert "bar" in items
    assert "foo" not in items


# ---------------------------------------------------------------------------
# JSON output schema
# ---------------------------------------------------------------------------

def test_json_output_schema(tmp_path: Path):
    _write_py(tmp_path, "mod.py", '"""Module."""\ndef foo():\n    pass\n')
    scanner = DocScanner(scan_dirs=[tmp_path], exclude_patterns=[])
    report = scanner.scan()
    for key in ("summary", "by_file", "debt_report"):
        assert key in report, f"Missing key: {key}"
    for key in ("total_files", "total_items", "documented_items", "coverage_pct", "debt_items"):
        assert key in report["summary"], f"Missing summary key: {key}"


# ---------------------------------------------------------------------------
# text format
# ---------------------------------------------------------------------------

def test_text_format_contains_coverage(tmp_path: Path):
    _write_py(tmp_path, "mod.py", '"""Module."""\ndef foo():\n    \"\"\"Foo.\"\"\"\n    pass\n')
    scanner = DocScanner(scan_dirs=[tmp_path], exclude_patterns=[])
    report = scanner.scan()
    text = scanner.format_text(report)
    assert "Coverage:" in text
    assert "%" in text


# ---------------------------------------------------------------------------
# scan_empty_dir
# ---------------------------------------------------------------------------

def test_scan_empty_dir(tmp_path: Path):
    scanner = DocScanner(scan_dirs=[tmp_path], exclude_patterns=[])
    report = scanner.scan()
    assert report["summary"]["total_items"] == 0
    assert report["summary"]["coverage_pct"] == 100.0
