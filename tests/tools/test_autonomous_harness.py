import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.autonomous_harness import AutonomousHarness  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_config(tmp_path: Path) -> Path:
    config = {
        "autonomous_harness": {
            "run_fsm_path": "state/run-fsm.json",
            "scheduler_state_path": "state/scheduler-state.json",
            "failure_stats_path": "state/failure-stats.json",
            "failed_auto_tasks_path": "state/failed-auto-tasks.json",
            "api_health_path": "state/api-health.json",
            "auto_task_fairness_path": "state/auto-task-fairness-hint.json",
            "token_budget_state_path": "state/token-budget-state.json",
            "scheduler_heartbeat_path": "state/scheduler-heartbeat.json",
            "output_plan_path": "state/autonomous-harness-plan.json",
            "recovery_queue_path": "state/autonomous-recovery-queue.json",
            "runtime_state_path": "state/autonomous-runtime.json",
            "thresholds": {
                "stale_run_minutes": 45,
                "scheduler_failure_window": 10,
                "scheduler_failure_threshold": 2,
                "failed_auto_task_threshold": 2,
                "api_open_circuit_threshold": 1,
                "starvation_task_threshold": 3,
                "heartbeat_stale_minutes": 20,
            },
            "dispatch": {
                "daily-digest": {"restart_command": ["pwsh", "-File", "run-agent-team.ps1"]},
                "todoist": {"restart_command": ["pwsh", "-File", "run-todoist-agent-team.ps1"]},
            },
            "runtime_profiles": {
                "normal": {"max_parallel_auto_tasks": 4, "allow_heavy_auto_tasks": True, "allow_research_auto_tasks": True},
                "degraded": {"max_parallel_auto_tasks": 2, "allow_heavy_auto_tasks": False, "allow_research_auto_tasks": True},
                "recovery": {"max_parallel_auto_tasks": 1, "allow_heavy_auto_tasks": False, "allow_research_auto_tasks": False},
            },
        }
    }
    config_path = tmp_path / "config" / "autonomous-harness.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return config_path


def test_build_plan_detects_stale_run_and_failed_tasks(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(
        tmp_path / "state" / "run-fsm.json",
        {
            "runs": {
                "todoist_deadbeef": {
                    "agent_type": "todoist",
                    "phases": {
                        "phase2": {"state": "running", "updated": "2026-03-20T06:00:00+08:00"}
                    },
                }
            },
            "updated": "2026-03-20T06:00:00+08:00",
        },
    )
    _write_json(
        tmp_path / "state" / "scheduler-state.json",
        {
            "runs": [
                {"agent": "todoist-team", "status": "failed"},
                {"agent": "todoist-team", "status": "failed"},
                {"agent": "daily-digest-team", "status": "success"},
            ]
        },
    )
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(
        tmp_path / "state" / "failed-auto-tasks.json",
        {"entries": [{"task_key": "self_heal", "consecutive_count": 2}]},
    )
    _write_json(
        tmp_path / "state" / "api-health.json",
        {"apis": {"gun-bot": {"circuit_breaker": {"state": "open"}}}},
    )
    _write_json(
        tmp_path / "state" / "auto-task-fairness-hint.json",
        {"starvation_detected": True, "starvation_count": 5},
    )
    _write_json(
        tmp_path / "state" / "token-budget-state.json",
        {"last_alerted_date": "2026-03-20"},
    )
    _write_json(
        tmp_path / "state" / "scheduler-heartbeat.json",
        {"timestamp": "2026-03-20T06:20:00+08:00", "status": "running"},
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["summary"]["pending_actions"] == 6
    action_types = {(item["action_type"], item["target"]) for item in plan["actions"]}
    assert ("restart_agent", "todoist") in action_types
    assert ("queue_self_heal", "self_heal") in action_types
    assert ("queue_self_heal", "gun-bot") in action_types
    assert ("rebalance_tasks", "todoist") in action_types
    assert ("scale_down_workload", "global") in action_types
    assert plan["runtime"]["mode"] == "degraded"
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 2


def test_enqueue_recovery_writes_pending_items(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    plan = {
        "generated_at": "2026-03-20T07:10:00+08:00",
        "actions": [
            {
                "action_type": "queue_self_heal",
                "target": "self_heal",
                "reason": "auto task failed twice",
                "severity": "high",
            }
        ],
    }

    queue = harness.enqueue_recovery(plan)

    assert queue["items"][0]["target"] == "self_heal"
    assert queue["items"][0]["status"] == "pending"


def test_enqueue_recovery_dedupes_existing_pending_items(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(
        tmp_path / "state" / "autonomous-recovery-queue.json",
        {
            "version": 1,
            "items": [
                {
                    "queued_at": "2026-03-20T07:00:00+08:00",
                    "target": "self_heal",
                    "action_type": "queue_self_heal",
                    "reason": "auto task failed twice",
                    "severity": "high",
                    "status": "pending",
                }
            ],
        },
    )
    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    plan = {
        "generated_at": "2026-03-20T07:10:00+08:00",
        "actions": [
            {
                "action_type": "queue_self_heal",
                "target": "self_heal",
                "reason": "auto task failed twice",
                "severity": "high",
            }
        ],
    }

    queue = harness.enqueue_recovery(plan)

    assert len(queue["items"]) == 1


def test_execute_runs_restart_commands_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    plan = {
        "actions": [
            {
                "action_type": "restart_agent",
                "target": "todoist",
                "reason": "stale",
                "severity": "critical",
                "command": ["pwsh", "-File", "run-todoist-agent-team.ps1"],
            },
            {
                "action_type": "queue_self_heal",
                "target": "self_heal",
                "reason": "failed",
                "severity": "high",
            },
        ]
    }

    with patch("tools.autonomous_harness.subprocess.run") as mocked_run:
        mocked_run.return_value.returncode = 0
        mocked_run.return_value.stdout = "ok"
        mocked_run.return_value.stderr = ""
        executions = harness.execute(plan)

    assert len(executions) == 1
    assert executions[0]["target"] == "todoist"
    mocked_run.assert_called_once()
