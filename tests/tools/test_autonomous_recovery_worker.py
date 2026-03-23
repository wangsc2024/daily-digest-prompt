import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.tools.test_autonomous_harness import _write_config, _write_json  # noqa: E402
from tools.autonomous_recovery_worker import AutonomousRecoveryWorker  # noqa: E402


def test_recovery_worker_applies_runtime_override_for_self_heal(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {"apis": {}})
    _write_json(tmp_path / "state" / "auto-task-fairness-hint.json", {"starvation_detected": False, "starvation_count": 0})
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})
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

    worker = AutonomousRecoveryWorker(repo_root=tmp_path, config_path=config_path)
    worker.harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 20},
        "memory": {"percent": 30, "available_mb": 4096},
        "gpu": {"available": False, "devices": []},
    }
    result = worker.process()

    override = json.loads((tmp_path / "state" / "autonomous-runtime-overrides.json").read_text(encoding="utf-8"))
    requests = json.loads((tmp_path / "state" / "autonomous-self-heal-requests.json").read_text(encoding="utf-8"))
    queue = json.loads((tmp_path / "state" / "autonomous-recovery-queue.json").read_text(encoding="utf-8"))

    assert result["processed_count"] == 1
    assert override["mode"] == "degraded"
    assert "self_heal" in override["blocked_task_keys"]
    assert requests["items"][0]["target"] == "self_heal"
    assert queue["items"][0]["status"] == "completed"


def test_recovery_worker_executes_restart_command(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {"apis": {}})
    _write_json(tmp_path / "state" / "auto-task-fairness-hint.json", {"starvation_detected": False, "starvation_count": 0})
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})
    _write_json(
        tmp_path / "state" / "autonomous-recovery-queue.json",
        {
            "version": 1,
            "items": [
                {
                    "queued_at": "2026-03-20T07:00:00+08:00",
                    "target": "todoist",
                    "action_type": "restart_agent",
                    "reason": "stale phase2",
                    "severity": "critical",
                    "status": "pending",
                    "command": ["pwsh", "-File", "run-todoist-agent-team.ps1"],
                }
            ],
        },
    )

    worker = AutonomousRecoveryWorker(repo_root=tmp_path, config_path=config_path)
    worker.harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 20},
        "memory": {"percent": 30, "available_mb": 4096},
        "gpu": {"available": False, "devices": []},
    }
    with patch("tools.autonomous_recovery_worker.subprocess.run") as mocked_run:
        mocked_run.return_value.returncode = 0
        mocked_run.return_value.stdout = "ok"
        mocked_run.return_value.stderr = ""
        result = worker.process()

    queue = json.loads((tmp_path / "state" / "autonomous-recovery-queue.json").read_text(encoding="utf-8"))
    assert result["processed_count"] == 1
    assert result["processed"][0]["status"] == "completed"
    assert queue["items"][0]["status"] == "completed"
    # Verify restart command was called (may also call subprocess for ntfy notifications)
    assert mocked_run.call_count >= 1
    restart_called = any(
        call.args and call.args[0] == ["pwsh", "-File", "run-todoist-agent-team.ps1"]
        for call in mocked_run.call_args_list
    )
    assert restart_called, f"Restart command not found in calls: {[c.args for c in mocked_run.call_args_list]}"
