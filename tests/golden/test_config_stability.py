#!/usr/bin/env python3
"""Golden tests for configuration file stability and cross-references."""
import os
import sys

# Project root
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')

sys.path.insert(0, os.path.join(PROJECT_ROOT, 'hooks'))


def _load_yaml(filename):
    """Load a YAML config file."""
    try:
        import yaml
    except ImportError:
        return None
    filepath = os.path.join(CONFIG_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestHookRulesStability:
    def test_all_rule_ids_unique(self):
        """All rule IDs across all sections must be unique."""
        data = _load_yaml("hook-rules.yaml")
        if data is None:
            return
        all_ids = []
        for section in ["bash_rules", "write_rules", "read_rules"]:
            rules = data.get(section, [])
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict):
                        all_ids.append(rule.get("id", ""))
        # Check for duplicates
        seen = set()
        for rid in all_ids:
            assert rid not in seen, f"Duplicate rule ID: {rid}"
            seen.add(rid)

    def test_all_rules_have_guard_tag(self):
        """All rules must have a guard_tag."""
        data = _load_yaml("hook-rules.yaml")
        if data is None:
            return
        for section in ["bash_rules", "write_rules", "read_rules"]:
            rules = data.get(section, [])
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict):
                        assert "guard_tag" in rule, \
                            f"Rule '{rule.get('id')}' in {section} missing guard_tag"

    def test_presets_exist(self):
        """hook-rules.yaml v2+ should have presets."""
        data = _load_yaml("hook-rules.yaml")
        if data is None:
            return
        if data.get("version", 1) >= 2:
            assert "presets" in data
            assert "strict" in data["presets"]

    def test_all_rules_have_priority(self):
        """v2+ rules should have priority field."""
        data = _load_yaml("hook-rules.yaml")
        if data is None:
            return
        if data.get("version", 1) < 2:
            return
        for section in ["bash_rules", "write_rules", "read_rules"]:
            rules = data.get(section, [])
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict):
                        assert "priority" in rule, \
                            f"Rule '{rule.get('id')}' in {section} missing priority"


class TestCachePolicyStability:
    def test_all_expected_sources(self):
        """Cache policy should define all expected API sources."""
        data = _load_yaml("cache-policy.yaml")
        if data is None:
            return
        sources = data.get("sources", {})
        expected = ["todoist", "pingtung-news", "hackernews", "knowledge", "gmail"]
        for src in expected:
            assert src in sources, f"Missing cache source: {src}"

    def test_all_sources_have_ttl(self):
        """Each source should have a ttl_minutes value."""
        data = _load_yaml("cache-policy.yaml")
        if data is None:
            return
        for name, config in data.get("sources", {}).items():
            assert "ttl_minutes" in config, f"Source '{name}' missing ttl_minutes"


class TestErrorPatternsStability:
    def test_has_common_status_codes(self):
        """Error patterns should cover common HTTP error codes."""
        data = _load_yaml("error-patterns.yaml")
        if data is None:
            return
        status_map = data.get("http_status_map", {})
        for code in [401, 403, 404, 429, 500, 502, 503]:
            assert code in status_map or str(code) in status_map, \
                f"Missing HTTP status code: {code}"

    def test_backoff_config_complete(self):
        """Backoff config should have all required fields."""
        data = _load_yaml("error-patterns.yaml")
        if data is None:
            return
        backoff = data.get("backoff", {})
        for field in ["base_seconds", "max_seconds", "multiplier"]:
            assert field in backoff, f"Missing backoff field: {field}"


class TestTimeoutsStability:
    def test_has_required_sections(self):
        """Timeouts should define key execution sections."""
        data = _load_yaml("timeouts.yaml")
        if data is None:
            return
        assert "daily_digest_team" in data or "version" in data


class TestConfigFilesExist:
    """Verify that all expected config files exist."""

    EXPECTED_CONFIGS = [
        "hook-rules.yaml",
        "cache-policy.yaml",
        "error-patterns.yaml",
        "timeouts.yaml",
    ]

    def test_required_configs_exist(self):
        for filename in self.EXPECTED_CONFIGS:
            filepath = os.path.join(CONFIG_DIR, filename)
            assert os.path.exists(filepath), f"Missing config: {filename}"
