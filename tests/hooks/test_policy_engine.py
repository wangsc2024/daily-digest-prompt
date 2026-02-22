#!/usr/bin/env python3
"""Tests for the tiered policy engine in hooks/hook_utils.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'hooks'))

from hook_utils import resolve_active_rules, PRIORITY_ORDER


# Test rules for policy engine
MOCK_RULES = [
    {"id": "rule-critical", "priority": "critical", "reason": "critical rule"},
    {"id": "rule-high", "priority": "high", "reason": "high rule"},
    {"id": "rule-medium", "priority": "medium", "reason": "medium rule"},
    {"id": "rule-low", "priority": "low", "reason": "low rule"},
]

# Use a non-existent section key to force use of fallback rules in tests
FAKE_SECTION = "_test_rules_nonexistent_section"


class TestPriorityOrder:
    def test_critical_is_highest(self):
        assert PRIORITY_ORDER["critical"] < PRIORITY_ORDER["high"]

    def test_high_before_medium(self):
        assert PRIORITY_ORDER["high"] < PRIORITY_ORDER["medium"]

    def test_medium_before_low(self):
        assert PRIORITY_ORDER["medium"] < PRIORITY_ORDER["low"]


class TestResolveActiveRules:
    def test_strict_mode_returns_all(self):
        """In strict mode, all rules should be active."""
        os.environ["DIGEST_SECURITY_LEVEL"] = "strict"
        rules = resolve_active_rules(FAKE_SECTION, MOCK_RULES)
        assert len(rules) == 4
        os.environ.pop("DIGEST_SECURITY_LEVEL", None)

    def test_default_is_strict(self):
        """Without env var, should default to strict (all rules)."""
        os.environ.pop("DIGEST_SECURITY_LEVEL", None)
        rules = resolve_active_rules(FAKE_SECTION, MOCK_RULES)
        assert len(rules) == 4

    def test_rules_sorted_by_priority(self):
        """Rules should be sorted critical > high > medium > low."""
        rules = resolve_active_rules(FAKE_SECTION, MOCK_RULES)
        ids = [r["id"] for r in rules]
        assert ids[0] == "rule-critical"
        assert ids[-1] == "rule-low"

    def test_rules_without_priority_default_to_high(self):
        """Rules without explicit priority should be treated as 'high'."""
        rules_no_priority = [
            {"id": "no-priority", "reason": "test"},
            {"id": "has-low", "priority": "low", "reason": "test"},
        ]
        sorted_rules = resolve_active_rules(FAKE_SECTION, rules_no_priority)
        ids = [r["id"] for r in sorted_rules]
        assert ids[0] == "no-priority"  # high (default) before low
        assert ids[1] == "has-low"

    def test_real_bash_rules_load_and_sort(self):
        """Test that real bash_rules from YAML are loaded and sorted by priority."""
        os.environ["DIGEST_SECURITY_LEVEL"] = "strict"
        rules = resolve_active_rules("bash_rules", MOCK_RULES)
        # Should load real rules from hook-rules.yaml (6 bash rules)
        assert len(rules) >= 4
        # Verify priority ordering: critical rules first
        priorities = [r.get("priority", "high") for r in rules]
        priority_values = [PRIORITY_ORDER.get(p, 1) for p in priorities]
        assert priority_values == sorted(priority_values)
        os.environ.pop("DIGEST_SECURITY_LEVEL", None)

    def test_permissive_disables_medium_rules(self):
        """In permissive mode, medium priority rules should be disabled."""
        os.environ["DIGEST_SECURITY_LEVEL"] = "permissive"
        rules = resolve_active_rules("bash_rules", MOCK_RULES)
        # sensitive-env (medium) should be removed in permissive
        rule_ids = [r.get("id") for r in rules]
        assert "sensitive-env" not in rule_ids
        # critical rules should still be present
        assert "nul-redirect" in rule_ids
        assert "exfiltration" in rule_ids
        os.environ.pop("DIGEST_SECURITY_LEVEL", None)
