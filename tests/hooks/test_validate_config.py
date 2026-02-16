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
            "pipeline.yaml": {
                "version": 1,
                "init": [],
                "steps": [{"id": "s1", "name": "Step 1"}],
                "finalize": [],
            },
            "topic-rotation.yaml": {
                "version": 1,
                "strategy": "no_repeat_until_all_used",
                "habits_topics": ["topic1"],
                "learning_topics": ["topic1"],
            },
            "health-scoring.yaml": {
                "version": 1,
                "ranges": [{"min": 0, "label": "test"}],
                "dimensions": {"test": {"weight": 100}},
            },
            "audit-scoring.yaml": {
                "version": 1,
                "weight_profiles": {"balanced": {}},
                "grade_thresholds": {"A": {"min": 80}},
                "dimensions": {"security": {}},
            },
            "benchmark.yaml": {
                "version": 1,
                "metrics": [
                    {"name": "m1", "target": ">= 90%", "weight": 100},
                ],
            },
            "timeouts.yaml": {"version": 1},
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

    def test_schema_count_matches_config_files(self):
        """SCHEMAS should cover all 13 config YAML files."""
        assert len(SCHEMAS) == 13

    def test_pipeline_covered(self):
        assert "pipeline.yaml" in SCHEMAS

    def test_topic_rotation_covered(self):
        assert "topic-rotation.yaml" in SCHEMAS

    def test_health_scoring_covered(self):
        assert "health-scoring.yaml" in SCHEMAS

    def test_audit_scoring_covered(self):
        assert "audit-scoring.yaml" in SCHEMAS

    def test_benchmark_covered(self):
        assert "benchmark.yaml" in SCHEMAS

    def test_timeouts_covered(self):
        assert "timeouts.yaml" in SCHEMAS


# ---------------------------------------------------------------------------
# New schema-specific validation tests
# ---------------------------------------------------------------------------
class TestPipelineSchema:
    """Tests specific to pipeline.yaml schema validation."""

    def test_pipeline_missing_steps(self, tmp_path):
        """pipeline.yaml without 'steps' should fail."""
        import yaml
        config_dir = str(tmp_path)
        # Only create pipeline.yaml with missing keys
        data = {"version": 1, "init": []}
        with open(os.path.join(config_dir, "pipeline.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        pipeline_errors = [e for e in errors if "pipeline" in e]
        assert any("steps" in e for e in pipeline_errors)

    def test_pipeline_steps_missing_id(self, tmp_path):
        """pipeline.yaml steps without 'id' should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "init": [],
            "steps": [{"name": "No ID step"}],
            "finalize": [],
        }
        with open(os.path.join(config_dir, "pipeline.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        pipeline_errors = [e for e in errors if "pipeline" in e]
        assert any("id" in e for e in pipeline_errors)


class TestBenchmarkSchema:
    """Tests specific to benchmark.yaml schema validation."""

    def test_benchmark_metrics_missing_weight(self, tmp_path):
        """benchmark.yaml metrics without 'weight' should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "metrics": [{"name": "m1", "target": ">= 90%"}],
        }
        with open(os.path.join(config_dir, "benchmark.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        benchmark_errors = [e for e in errors if "benchmark" in e]
        assert any("weight" in e for e in benchmark_errors)

    def test_benchmark_metrics_missing_name(self, tmp_path):
        """benchmark.yaml metrics without 'name' should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "metrics": [{"target": ">= 90%", "weight": 10}],
        }
        with open(os.path.join(config_dir, "benchmark.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        benchmark_errors = [e for e in errors if "benchmark" in e]
        assert any("name" in e for e in benchmark_errors)


class TestTopicRotationSchema:
    """Tests specific to topic-rotation.yaml schema validation."""

    def test_topic_rotation_missing_habits(self, tmp_path):
        """topic-rotation.yaml without habits_topics should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "strategy": "no_repeat",
            "learning_topics": ["topic1"],
        }
        with open(os.path.join(config_dir, "topic-rotation.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        rotation_errors = [e for e in errors if "topic-rotation" in e]
        assert any("habits_topics" in e for e in rotation_errors)


class TestAuditScoringSchema:
    """Tests specific to audit-scoring.yaml schema validation."""

    def test_audit_missing_dimensions(self, tmp_path):
        """audit-scoring.yaml without dimensions should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "weight_profiles": {"balanced": {}},
            "grade_thresholds": {"A": {"min": 80}},
        }
        with open(os.path.join(config_dir, "audit-scoring.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        audit_errors = [e for e in errors if "audit" in e]
        assert any("dimensions" in e for e in audit_errors)

    def test_audit_missing_weight_profiles(self, tmp_path):
        """audit-scoring.yaml without weight_profiles should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "grade_thresholds": {"A": {"min": 80}},
            "dimensions": {"security": {}},
        }
        with open(os.path.join(config_dir, "audit-scoring.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        audit_errors = [e for e in errors if "audit" in e]
        assert any("weight_profiles" in e for e in audit_errors)


class TestHealthScoringSchema:
    """Tests specific to health-scoring.yaml schema validation."""

    def test_health_missing_ranges(self, tmp_path):
        """health-scoring.yaml without ranges should fail."""
        import yaml
        config_dir = str(tmp_path)
        data = {
            "version": 1,
            "dimensions": {"test": {"weight": 100}},
        }
        with open(os.path.join(config_dir, "health-scoring.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.dump(data, f)
        errors, warnings = validate_config(config_dir)
        health_errors = [e for e in errors if "health" in e]
        assert any("ranges" in e for e in health_errors)
