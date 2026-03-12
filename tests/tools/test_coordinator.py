"""
tests/tools/test_coordinator.py — Coordinator TDD（P5-A）

覆蓋重點：
  - PLAN_KEY_WORKER_MAP 精確映射
  - label 推斷回退（未命中 PLAN_KEY_WORKER_MAP）
  - build_coordination_plan 輸出結構
  - prompt_file / result_file 路徑格式
  - max_concurrent 繼承自 pool_config
  - done_cert_required 欄位
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.agent_pool.coordinator import (  # noqa: E402
    PLAN_KEY_WORKER_MAP,
    build_coordination_plan,
    infer_worker_type,
)

MINIMAL_POOL_CONFIG = {
    "worker_pool": {
        "web_search":   {"max_concurrent": 3},
        "kb_import":    {"max_concurrent": 5},
        "file_sync":    {"max_concurrent": 2},
        "notification": {"max_concurrent": 10},
    },
    "done_cert": {"enabled": True},
}


# ─── infer_worker_type ───────────────────────────────────────────────────────

class TestInferWorkerType:
    @pytest.mark.parametrize("plan_key,expected", [
        ("ai_research",         "web_search"),
        ("tech_research",       "web_search"),
        ("hackernews",          "web_search"),
        ("kb_content_score",    "kb_import"),
        ("shurangama",          "kb_import"),
        ("system_insight",      "file_sync"),
        ("log_audit",           "file_sync"),
        ("podcast_create",      "notification"),
        ("podcast_jiaoguangzong", "notification"),
    ])
    def test_plan_key_map_exact_match(self, plan_key, expected):
        task = {"plan_key": plan_key, "labels": []}
        assert infer_worker_type(task) == expected

    def test_label_fallback_研究(self):
        task = {"plan_key": "unknown_key", "labels": ["研究"]}
        assert infer_worker_type(task) == "web_search"

    def test_label_fallback_知識庫(self):
        task = {"plan_key": "unknown_key", "labels": ["知識庫"]}
        assert infer_worker_type(task) == "kb_import"

    def test_label_fallback_通知(self):
        task = {"plan_key": "unknown_key", "labels": ["通知"]}
        assert infer_worker_type(task) == "notification"

    def test_unknown_key_and_no_matching_label_defaults_to_web_search(self):
        task = {"plan_key": "totally_unknown", "labels": ["雜項"]}
        assert infer_worker_type(task) == "web_search"

    def test_plan_key_takes_priority_over_labels(self):
        """plan_key 精確映射優先於 label 推斷"""
        task = {"plan_key": "system_insight", "labels": ["研究"]}  # label 指向 web_search
        assert infer_worker_type(task) == "file_sync"  # plan_key 應優先


# ─── build_coordination_plan ─────────────────────────────────────────────────

class TestBuildCoordinationPlan:
    def test_empty_tasks_returns_empty_plan(self):
        plan = build_coordination_plan([], MINIMAL_POOL_CONFIG)
        assert plan["tasks"] == []
        assert "generated_at" in plan

    def test_single_task_output_structure(self):
        tasks = [{"id": "task-001", "plan_key": "ai_research", "labels": []}]
        plan = build_coordination_plan(tasks, MINIMAL_POOL_CONFIG)

        assert len(plan["tasks"]) == 1
        t = plan["tasks"][0]
        assert t["task_id"] == "task-001"
        assert t["plan_key"] == "ai_research"
        assert t["worker_type"] == "web_search"
        assert t["max_concurrent"] == 3
        assert t["done_cert_required"] is True

    def test_prompt_file_follows_naming_convention(self):
        tasks = [{"id": "t1", "plan_key": "system_insight", "labels": []}]
        plan = build_coordination_plan(tasks, MINIMAL_POOL_CONFIG)

        assert plan["tasks"][0]["prompt_file"] == "prompts/team/todoist-auto-system_insight.md"

    def test_result_file_follows_naming_convention(self):
        tasks = [{"id": "t1", "plan_key": "podcast_create", "labels": []}]
        plan = build_coordination_plan(tasks, MINIMAL_POOL_CONFIG)

        assert plan["tasks"][0]["result_file"] == "results/todoist-auto-podcast_create.json"

    def test_max_concurrent_from_pool_config(self):
        tasks = [
            {"id": "t1", "plan_key": "ai_research", "labels": []},  # web_search → 3
            {"id": "t2", "plan_key": "shurangama", "labels": []},   # kb_import → 5
        ]
        plan = build_coordination_plan(tasks, MINIMAL_POOL_CONFIG)

        concurrents = {t["worker_type"]: t["max_concurrent"] for t in plan["tasks"]}
        assert concurrents["web_search"] == 3
        assert concurrents["kb_import"] == 5

    def test_done_cert_disabled_when_config_false(self):
        config = dict(MINIMAL_POOL_CONFIG, done_cert={"enabled": False})
        tasks = [{"id": "t1", "plan_key": "ai_research", "labels": []}]
        plan = build_coordination_plan(tasks, config)

        assert plan["tasks"][0]["done_cert_required"] is False

    def test_multiple_tasks_all_included(self):
        tasks = [
            {"id": f"t{i}", "plan_key": "ai_research", "labels": []}
            for i in range(5)
        ]
        plan = build_coordination_plan(tasks, MINIMAL_POOL_CONFIG)
        assert len(plan["tasks"]) == 5

    def test_task_without_id_uses_plan_key(self):
        tasks = [{"plan_key": "system_insight", "labels": []}]  # 無 id 欄位
        plan = build_coordination_plan(tasks, MINIMAL_POOL_CONFIG)
        assert plan["tasks"][0]["task_id"] == "system_insight"

    def test_plan_key_worker_map_completeness(self):
        """PLAN_KEY_WORKER_MAP 所有 key 都應能正確映射到已知 worker_type"""
        valid_types = {"web_search", "kb_import", "file_sync", "notification"}
        for plan_key, worker_type in PLAN_KEY_WORKER_MAP.items():
            assert worker_type in valid_types, (
                f"PLAN_KEY_WORKER_MAP['{plan_key}'] = '{worker_type}' 不在 valid_types 中"
            )
