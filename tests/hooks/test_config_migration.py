#!/usr/bin/env python3
"""Tests for hooks/config_migration.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'hooks'))

from config_migration import (
    migrate_hook_rules_v1_to_v2,
    migrate_timeouts_v1_to_v2,
    migrate_cache_policy_v1_to_v2,
    check_migrations,
    MIGRATIONS,
)


class TestMigrateHookRulesV1ToV2:
    def test_adds_presets(self):
        data = {"version": 1, "bash_rules": [], "write_rules": []}
        result = migrate_hook_rules_v1_to_v2(data)
        assert "presets" in result
        assert "strict" in result["presets"]
        assert "standard" in result["presets"]
        assert "permissive" in result["presets"]

    def test_bumps_version(self):
        data = {"version": 1, "bash_rules": [], "write_rules": []}
        result = migrate_hook_rules_v1_to_v2(data)
        assert result["version"] == 2

    def test_adds_priority_to_rules(self):
        data = {
            "version": 1,
            "bash_rules": [{"id": "nul-redirect", "reason": "test", "guard_tag": "nul"}],
            "write_rules": [],
        }
        result = migrate_hook_rules_v1_to_v2(data)
        assert result["bash_rules"][0]["priority"] == "critical"

    def test_preserves_existing_priority(self):
        data = {
            "version": 1,
            "bash_rules": [{"id": "test", "priority": "low", "reason": "test"}],
            "write_rules": [],
        }
        # First set priority, then migrate
        result = migrate_hook_rules_v1_to_v2(data)
        # Should keep "low" since it already has priority
        assert result["bash_rules"][0]["priority"] == "low"


class TestMigrateTimeoutsV1ToV2:
    def test_adds_loop_detection(self):
        data = {"version": 1}
        result = migrate_timeouts_v1_to_v2(data)
        assert "loop_detection" in result
        assert result["loop_detection"]["tool_hash_threshold"] == 5

    def test_bumps_version(self):
        data = {"version": 1}
        result = migrate_timeouts_v1_to_v2(data)
        assert result["version"] == 2


class TestMigrateCachePolicyV1ToV2:
    def test_adds_circuit_breaker(self):
        data = {"version": 1}
        result = migrate_cache_policy_v1_to_v2(data)
        assert "circuit_breaker" in result
        assert result["circuit_breaker"]["failure_threshold"] == 3

    def test_bumps_version(self):
        data = {"version": 1}
        result = migrate_cache_policy_v1_to_v2(data)
        assert result["version"] == 2


class TestCheckMigrations:
    def test_registry_has_expected_files(self):
        assert "hook-rules.yaml" in MIGRATIONS
        assert "timeouts.yaml" in MIGRATIONS
        assert "cache-policy.yaml" in MIGRATIONS
