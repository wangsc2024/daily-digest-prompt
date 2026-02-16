"""Tests for hooks/validate_config.py — YAML 配置 Schema 驗證。"""
import os
import sys
import json
import pytest

# Add hooks dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "hooks"))

from validate_config import validate_config, SCHEMAS, _check_required_keys, _check_list_fields


# ---------------------------------------------------------------------------
# Real config validation (integration)
# ---------------------------------------------------------------------------
class TestRealConfigs:
    """Integration test: validate actual project config files."""

    def test_all_configs_valid(self):
        """All project YAML configs should pass validation."""
        config_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "config")
        errors, warnings = validate_config(config_dir)
        assert errors == [], f"Config validation errors: {errors}"

    def test_all_config_files_exist(self):
        """All expected config files should exist."""
        config_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "config")
        for filename in SCHEMAS:
            filepath = os.path.join(config_dir, filename)
            assert os.path.exists(filepath), f"Missing config: {filename}"


# ---------------------------------------------------------------------------
# _check_required_keys
# ---------------------------------------------------------------------------
class TestCheckRequiredKeys:

    def test_all_keys_present(self):
        data = {"a": 1, "b": 2, "c": 3}
        errors = _check_required_keys(data, ["a", "b"], "test.yaml")
        assert errors == []

    def test_missing_key(self):
        data = {"a": 1}
        errors = _check_required_keys(data, ["a", "missing"], "test.yaml")
        assert len(errors) == 1
        assert "missing" in errors[0]

    def test_empty_data(self):
        errors = _check_required_keys({}, ["a"], "test.yaml")
        assert len(errors) == 1

    def test_no_required(self):
        errors = _check_required_keys({"a": 1}, [], "test.yaml")
        assert errors == []


# ---------------------------------------------------------------------------
# _check_list_fields
# ---------------------------------------------------------------------------
class TestCheckListFields:

    def test_valid_list(self):
        data = {"rules": [
            {"id": "r1", "reason": "test", "guard_tag": "g1"},
        ]}
        errors = _check_list_fields(
            data, {"rules": ["id", "reason", "guard_tag"]}, "test.yaml")
        assert errors == []

    def test_missing_subkey(self):
        data = {"rules": [{"id": "r1"}]}
        errors = _check_list_fields(
            data, {"rules": ["id", "reason"]}, "test.yaml")
        assert len(errors) == 1
        assert "reason" in errors[0]

    def test_not_a_list(self):
        data = {"rules": "not_a_list"}
        errors = _check_list_fields(
            data, {"rules": ["id"]}, "test.yaml")
        assert len(errors) == 1
        assert "list" in errors[0]

    def test_item_not_dict(self):
        data = {"rules": ["string_item"]}
        errors = _check_list_fields(
            data, {"rules": ["id"]}, "test.yaml")
        assert len(errors) == 1
        assert "dict" in errors[0]

    def test_alternative_keys(self):
        """Support 'key_a|key_b' syntax (either one present is OK)."""
        data = {"rules": [
            {"id": "r1", "reason_template": "test"},
        ]}
        errors = _check_list_fields(
            data, {"rules": ["id", "reason|reason_template"]}, "test.yaml")
        assert errors == []

    def test_alternative_keys_both_missing(self):
        data = {"rules": [{"id": "r1"}]}
        errors = _check_list_fields(
            data, {"rules": ["id", "reason|reason_template"]}, "test.yaml")
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# validate_config with synthetic configs
# ---------------------------------------------------------------------------
class TestSyntheticConfigs:

    def test_missing_directory(self, tmp_path):
        """Non-existent config dir should yield warnings."""
        fake_dir = str(tmp_path / "nonexistent")
        errors, warnings = validate_config(fake_dir)
        assert len(warnings) == len(SCHEMAS)

    def test_empty_yaml(self, tmp_path):
        """Empty YAML files should report missing keys."""
        config_dir = str(tmp_path)
        for filename in SCHEMAS:
            with open(os.path.join(config_dir, filename), "w") as f:
                f.write("")  # empty
        errors, warnings = validate_config(config_dir)
        # All files with required_keys should have errors
        assert len(errors) > 0

    def test_valid_minimal_config(self, tmp_path):
        """Minimal valid configs should pass."""
        import yaml
        config_dir = str(tmp_path)

        # Create minimal valid configs
        configs = {
            "hook-rules.yaml": {
                "bash_rules": [{"id": "r1", "reason": "test", "guard_tag": "g1"}],
                "write_rules": [{"id": "w1", "check": "nul", "reason": "test", "guard_tag": "g1"}],
            },
            "routing.yaml": {"pre_filter": {}, "label_routing": {}},
            "cache-policy.yaml": {"version": 1},
            "frequency-limits.yaml": {
                "version": 1,
                "tasks": {
                    "test_task": {
                        "name": "Test",
                        "daily_limit": 1,
                        "counter_field": "test_count",
                        "execution_order": 1,
                    }
                },
            },
            "scoring.yaml": {"version": 1},
            "notification.yaml": {
                "version": 1,
                "default_topic": "test",
                "service_url": "https://ntfy.sh",
            },
            "dedup-policy.yaml": {"version": 1},
        }

        for filename, data in configs.items():
            with open(os.path.join(config_dir, filename), "w",
                      encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True)

        errors, warnings = validate_config(config_dir)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_json_output(self, tmp_path):
        """Validate JSON output format."""
        config_dir = str(tmp_path)
        # Create one empty config to trigger errors
        with open(os.path.join(config_dir, "hook-rules.yaml"), "w") as f:
            f.write("version: 1\n")

        errors, warnings = validate_config(config_dir)
        result = {"errors": errors, "warnings": warnings,
                  "valid": len(errors) == 0}
        # Should be JSON-serializable
        output = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(output)
        assert isinstance(parsed["errors"], list)
        assert isinstance(parsed["valid"], bool)


# ---------------------------------------------------------------------------
# Schema coverage
# ---------------------------------------------------------------------------
class TestSchemaCoverage:
    """Verify that SCHEMAS covers critical config files."""

    def test_hook_rules_covered(self):
        assert "hook-rules.yaml" in SCHEMAS

    def test_frequency_limits_covered(self):
        assert "frequency-limits.yaml" in SCHEMAS

    def test_routing_covered(self):
        assert "routing.yaml" in SCHEMAS

    def test_notification_covered(self):
        assert "notification.yaml" in SCHEMAS

    def test_all_schemas_have_required_keys(self):
        for name, schema in SCHEMAS.items():
            assert "required_keys" in schema, f"{name} missing required_keys"
