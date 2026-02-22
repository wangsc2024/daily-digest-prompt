#!/usr/bin/env python3
"""Tests for hooks/loop_detector.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'hooks'))

from loop_detector import (
    _hash_entry, check_tool_call_loop, check_content_repetition,
    check_excessive_turns, run_all_checks
)


class TestHashEntry:
    def test_same_input_same_hash(self):
        h1 = _hash_entry("Bash", {"command": "ls -la"})
        h2 = _hash_entry("Bash", {"command": "ls -la"})
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = _hash_entry("Bash", {"command": "ls -la"})
        h2 = _hash_entry("Bash", {"command": "ls -lb"})
        assert h1 != h2

    def test_different_tool_different_hash(self):
        h1 = _hash_entry("Bash", {"command": "ls"})
        h2 = _hash_entry("Read", {"command": "ls"})
        assert h1 != h2

    def test_returns_string(self):
        h = _hash_entry("Bash", {"command": "test"})
        assert isinstance(h, str)
        assert len(h) == 16


class TestToolCallLoop:
    def test_no_loop_under_threshold(self):
        hash_val = _hash_entry("Bash", {"command": "curl api"})
        entries = [{"_tool_hash": hash_val, "tool": "Bash"}] * 3
        new_entry = {"_tool_hash": hash_val, "tool": "Bash"}
        result = check_tool_call_loop(entries, new_entry)
        assert result is None

    def test_detects_loop_at_threshold(self):
        hash_val = _hash_entry("Bash", {"command": "curl api"})
        entries = [{"_tool_hash": hash_val, "tool": "Bash"}] * 5
        new_entry = {"_tool_hash": hash_val, "tool": "Bash"}
        result = check_tool_call_loop(entries, new_entry)
        assert result is not None
        assert result["type"] == "tool_hash"
        assert result["repeat_count"] == 6

    def test_no_loop_with_varied_hashes(self):
        entries = []
        for i in range(10):
            h = _hash_entry("Bash", {"command": f"curl api/{i}"})
            entries.append({"_tool_hash": h, "tool": "Bash"})
        new_entry = {"_tool_hash": _hash_entry("Bash", {"command": "curl api/10"}), "tool": "Bash"}
        result = check_tool_call_loop(entries, new_entry)
        assert result is None

    def test_no_hash_in_entry(self):
        entries = [{"tool": "Bash"}] * 10
        new_entry = {"tool": "Bash"}
        result = check_tool_call_loop(entries, new_entry)
        assert result is None


class TestContentRepetition:
    def test_no_repetition(self):
        entries = [{"summary": f"output {i}"} for i in range(10)]
        result = check_content_repetition(entries)
        assert result is None

    def test_detects_repetition(self):
        entries = [{"summary": "same output content here and more text"}] * 5
        result = check_content_repetition(entries)
        assert result is not None
        assert result["type"] == "content_repetition"

    def test_too_few_entries(self):
        entries = [{"summary": "same"}] * 2
        result = check_content_repetition(entries)
        assert result is None


class TestExcessiveTurns:
    def test_under_threshold(self):
        entries = [{}] * 50
        result = check_excessive_turns(entries, "digest")
        assert result is None

    def test_warning_at_80_percent(self):
        entries = [{}] * 64  # 80% of 80
        result = check_excessive_turns(entries, "digest")
        assert result is not None
        assert result["level"] == "warning"

    def test_block_at_100_percent(self):
        entries = [{}] * 80
        result = check_excessive_turns(entries, "digest")
        assert result is not None
        assert result["level"] == "block"


class TestRunAllChecks:
    def test_returns_none_when_healthy(self):
        entries = [{"_tool_hash": f"hash{i}", "summary": f"output {i}"} for i in range(5)]
        new_entry = {"_tool_hash": "newhash", "tool": "Bash"}
        result = run_all_checks(entries, new_entry, "digest")
        assert result is None
