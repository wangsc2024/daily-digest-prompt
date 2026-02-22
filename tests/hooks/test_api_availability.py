#!/usr/bin/env python3
"""Tests for hooks/api_availability.py"""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'hooks'))

from api_availability import (
    load_health, save_health, check_circuit, record_success, record_failure,
    get_health_summary, API_SOURCES, _default_source_state, _state_file_path
)


class TestDefaultState:
    def test_default_state_structure(self):
        state = _default_source_state()
        assert state["circuit_state"] == "closed"
        assert state["consecutive_failures"] == 0
        assert state["last_success"] is None
        assert state["cooldown_until"] is None


class TestLoadHealth:
    def test_initializes_all_sources(self, tmp_path, monkeypatch):
        """When no state file exists, all sources should start as closed."""
        monkeypatch.setattr(
            "api_availability._state_file_path",
            lambda: str(tmp_path / "api-health.json"),
        )
        health = load_health()
        for source in API_SOURCES:
            assert source in health
            assert health[source]["circuit_state"] == "closed"


class TestCheckCircuit:
    def test_closed_circuit_allows(self):
        health = {"todoist": _default_source_state()}
        result = check_circuit("todoist", health)
        assert result["should_skip"] is False
        assert result["circuit_state"] == "closed"

    def test_open_circuit_skips(self):
        health = {
            "todoist": {
                "circuit_state": "open",
                "cooldown_until": "2099-01-01T00:00:00",
                "consecutive_failures": 3,
                "last_success": None,
                "last_failure": None,
            }
        }
        result = check_circuit("todoist", health)
        assert result["should_skip"] is True
        assert result["circuit_state"] == "open"

    def test_unknown_source_allows(self):
        result = check_circuit("nonexistent", {})
        assert result["should_skip"] is False


class TestRecordSuccess:
    def test_resets_failures(self):
        health = {
            "todoist": {
                "consecutive_failures": 5,
                "circuit_state": "open",
                "cooldown_until": "2099-01-01T00:00:00",
                "last_success": None,
                "last_failure": None,
            }
        }
        health = record_success("todoist", health)
        assert health["todoist"]["consecutive_failures"] == 0
        assert health["todoist"]["circuit_state"] == "closed"
        assert health["todoist"]["cooldown_until"] is None
        assert health["todoist"]["last_success"] is not None


class TestRecordFailure:
    def test_increments_failures(self):
        health = {"todoist": _default_source_state()}
        health = record_failure("todoist", health)
        assert health["todoist"]["consecutive_failures"] == 1
        assert health["todoist"]["circuit_state"] == "closed"

    def test_opens_circuit_at_threshold(self):
        health = {
            "todoist": {
                "consecutive_failures": 2,
                "circuit_state": "closed",
                "cooldown_until": None,
                "last_success": None,
                "last_failure": None,
            }
        }
        health = record_failure("todoist", health, failure_threshold=3)
        assert health["todoist"]["consecutive_failures"] == 3
        assert health["todoist"]["circuit_state"] == "open"
        assert health["todoist"]["cooldown_until"] is not None

    def test_half_open_failure_reopens(self):
        health = {
            "todoist": {
                "consecutive_failures": 3,
                "circuit_state": "half_open",
                "cooldown_until": None,
                "last_success": None,
                "last_failure": None,
            }
        }
        health = record_failure("todoist", health)
        assert health["todoist"]["circuit_state"] == "open"


class TestHealthSummary:
    def test_returns_all_sources(self):
        summary = get_health_summary()
        for source in API_SOURCES:
            assert source in summary
            assert "circuit_state" in summary[source]
