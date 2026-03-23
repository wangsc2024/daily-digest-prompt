import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.autonomous_harness import AutonomousHarness, _parse_typeperf_value  # noqa: E402


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
            "runtime_override_path": "state/autonomous-runtime-overrides.json",
            "agent_registry_path": "state/autonomous-agent-registry.json",
            "resource_snapshot_path": "state/autonomous-resource-snapshot.json",
            "self_heal_request_path": "state/autonomous-self-heal-requests.json",
            "thresholds": {
                "stale_run_minutes": 45,
                "scheduler_failure_window": 10,
                "scheduler_failure_threshold": 2,
                "failed_auto_task_threshold": 2,
                "api_open_circuit_threshold": 1,
                "starvation_task_threshold": 3,
                "starvation_boost": 2,
                "heartbeat_stale_minutes": 40,
            },
            "discovery": {
                "fetch_agents_glob": "prompts/team/fetch-*.md",
                "auto_tasks_glob": "templates/auto-tasks/*.md",
                "core_fetch_agents": ["todoist", "news", "hackernews"],
                "optional_fetch_agents": ["gmail", "security", "chatroom"],
                "heavy_task_patterns": ["podcast", "research", "shurangama"],
                "research_task_patterns": ["research", "ai_", "shurangama"],
            },
            "resources": {
                "cpu_percent_high": 85,
                "memory_percent_high": 80,
                "gpu_percent_high": 85,
                "gpu_memory_percent_high": 80,
            },
            "dispatch": {
                "daily-digest": {"restart_command": ["pwsh", "-File", "run-agent-team.ps1"]},
                "todoist": {"restart_command": ["pwsh", "-File", "run-todoist-agent-team.ps1"]},
                "gun-bot": {"restart_command": ["pwsh", "-ExecutionPolicy", "Bypass", "-File", "bot/restart-bot.ps1"]},
            },
            "runtime_profiles": {
                "normal": {
                    "max_parallel_auto_tasks": 4,
                    "max_parallel_fetch_agents": 6,
                    "allow_heavy_auto_tasks": True,
                    "allow_research_auto_tasks": True,
                    "daily_digest_assembly_mode": "full",
                    "daily_digest_phase2_retries": 1,
                    "blocked_fetch_agents": [],
                },
                "degraded": {
                    "max_parallel_auto_tasks": 3,
                    "max_parallel_fetch_agents": 4,
                    "allow_heavy_auto_tasks": False,
                    "allow_research_auto_tasks": True,
                    "daily_digest_assembly_mode": "degraded",
                    "daily_digest_phase2_retries": 0,
                    "blocked_fetch_agents": ["security", "chatroom"],
                },
                "recovery": {
                    "max_parallel_auto_tasks": 1,
                    "max_parallel_fetch_agents": 3,
                    "allow_heavy_auto_tasks": False,
                    "allow_research_auto_tasks": False,
                    "daily_digest_assembly_mode": "skip",
                    "daily_digest_phase2_retries": 0,
                    "blocked_fetch_agents": ["gmail", "security", "chatroom"],
                },
            },
            "chatroom_scope_apis": ["gun-bot", "chatroom-scheduler"],
            "recovery_worker": {
                "restart_timeout_seconds": 30,
                "default_override_ttl_minutes": 30,
                "scale_down_ttl_minutes": 45,
                "rebalance_ttl_minutes": 30,
                "self_heal_ttl_minutes": 60,
            },
        }
    }
    config_path = tmp_path / "config" / "autonomous-harness.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    (tmp_path / "prompts" / "team").mkdir(parents=True, exist_ok=True)
    (tmp_path / "templates" / "auto-tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "team" / "fetch-news.md").write_text("news", encoding="utf-8")
    (tmp_path / "prompts" / "team" / "fetch-todoist.md").write_text("todoist", encoding="utf-8")
    (tmp_path / "prompts" / "team" / "fetch-hackernews.md").write_text("hn", encoding="utf-8")
    (tmp_path / "prompts" / "team" / "fetch-gmail.md").write_text("gmail", encoding="utf-8")
    (tmp_path / "prompts" / "team" / "fetch-security.md").write_text("security", encoding="utf-8")
    (tmp_path / "prompts" / "team" / "fetch-chatroom.md").write_text("chatroom", encoding="utf-8")
    (tmp_path / "templates" / "auto-tasks" / "tech-research.md").write_text("research", encoding="utf-8")
    (tmp_path / "templates" / "auto-tasks" / "self-heal.md").write_text("heal", encoding="utf-8")
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
        {"gun-bot": {"state": "open", "failures": 3, "cooldown": None}},
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
        {"timestamp": "2026-03-20T06:50:00+08:00", "status": "running"},  # 10 min ago, within stale threshold
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 42},
        "memory": {"percent": 51, "available_mb": 4096},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["summary"]["pending_actions"] == 6
    action_types = {(item["action_type"], item["target"]) for item in plan["actions"]}
    assert ("restart_agent", "todoist") in action_types
    assert ("queue_self_heal", "self_heal") in action_types
    assert ("restart_agent", "gun-bot") in action_types
    assert ("rebalance_tasks", "todoist") in action_types
    assert ("scale_down_workload", "global") in action_types
    assert plan["runtime"]["mode"] == "recovery"  # stale run → critical severity → recovery mode
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 1
    assert plan["runtime"]["policies"]["daily_digest_assembly_mode"] == "skip"
    assert "tech_research" in plan["runtime"]["policies"]["heavy_task_keys"]
    assert plan["signals"]["agent_registry"]["summary"]["auto_task_count"] == 2


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


def test_build_plan_adds_resource_pressure_actions(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {})
    _write_json(tmp_path / "state" / "auto-task-fairness-hint.json", {"starvation_detected": False, "starvation_count": 0})
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 91},
        "memory": {"percent": 84, "available_mb": 512},
        "gpu": {
            "available": True,
            "devices": [
                {
                    "name": "GPU0",
                    "utilization_percent": 90,
                    "memory_used_mb": 9000,
                    "memory_total_mb": 10000,
                    "memory_percent": 90,
                }
            ],
        },
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    action_types = {(item["action_type"], item["target"]) for item in plan["actions"]}
    assert ("scale_down_workload", "cpu") in action_types
    assert ("scale_down_workload", "memory") in action_types
    assert ("scale_down_workload", "gpu:GPU0") in action_types
    assert ("scale_down_workload", "gpu-memory:GPU0") in action_types


def test_runtime_policy_includes_fetch_agent_limits(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {})
    _write_json(tmp_path / "state" / "auto-task-fairness-hint.json", {"starvation_detected": False, "starvation_count": 0})
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T06:00:00+08:00", "status": "stale"})

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "recovery"
    assert plan["runtime"]["policies"]["max_parallel_fetch_agents"] == 3
    assert plan["runtime"]["policies"]["daily_digest_assembly_mode"] == "skip"
    assert plan["runtime"]["policies"]["core_fetch_agents"] == ["todoist", "news", "hackernews"]
    assert "gmail" in plan["runtime"]["policies"]["blocked_fetch_agents"]
    assert sorted(plan["runtime"]["policies"]["allowed_fetch_agents"]) == ["hackernews", "news", "todoist"]


def test_parse_typeperf_value_extracts_numeric_sample() -> None:
    output = '\n"(PDH-CSV 4.0)","\\\\HOST\\Memory\\Available MBytes"\n"03/20/2026 08:49:47.282","14015.000000"\n'

    assert _parse_typeperf_value(output) == 14015.0


def test_execute_blocks_disallowed_commands(tmp_path: Path) -> None:
    """命令白名單驗證：不在白名單中的命令應被攔截。"""
    config_path = _write_config(tmp_path)
    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    plan = {
        "actions": [
            {
                "action_type": "restart_agent",
                "target": "malicious",
                "reason": "test",
                "severity": "critical",
                "command": ["rm", "-rf", "/"],
            },
        ]
    }

    with patch("tools.autonomous_harness.subprocess.run") as mocked_run:
        executions = harness.execute(plan)

    assert len(executions) == 1
    assert executions[0]["returncode"] == -1
    assert "blocked" in executions[0]["stderr"].lower()
    mocked_run.assert_not_called()


def test_execute_allows_pwsh_and_uv_commands(tmp_path: Path) -> None:
    """命令白名單驗證：pwsh 和 uv run 命令應被允許。"""
    config_path = _write_config(tmp_path)
    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)

    for cmd in [
        ["pwsh", "-File", "run-agent-team.ps1"],
        ["uv", "run", "python", "tools/check.py"],
    ]:
        plan = {
            "actions": [
                {
                    "action_type": "restart_agent",
                    "target": "test",
                    "reason": "test",
                    "severity": "low",
                    "command": cmd,
                },
            ]
        }
        with patch("tools.autonomous_harness.subprocess.run") as mocked_run:
            mocked_run.return_value.returncode = 0
            mocked_run.return_value.stdout = "ok"
            mocked_run.return_value.stderr = ""
            executions = harness.execute(plan)
        assert executions[0]["returncode"] == 0
        mocked_run.assert_called_once()


def test_runtime_override_can_force_more_conservative_mode(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {})
    _write_json(tmp_path / "state" / "auto-task-fairness-hint.json", {"starvation_detected": False, "starvation_count": 0})
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})
    _write_json(
        tmp_path / "state" / "autonomous-runtime-overrides.json",
        {
            "mode": "recovery",
            "reason": "manual override",
            "expires_at": "2026-03-20T08:00:00+08:00",
            "blocked_fetch_agents": ["gmail"],
            "blocked_task_keys": ["tech_research"],
            "max_parallel_auto_tasks": 1,
            "max_parallel_fetch_agents": 2,
        },
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "recovery"
    assert plan["runtime"]["override"]["active"] is True
    assert "tech_research" in plan["runtime"]["policies"]["blocked_task_keys"]
    assert "gmail" in plan["runtime"]["policies"]["blocked_fetch_agents"]
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 1
    assert plan["runtime"]["policies"]["max_parallel_fetch_agents"] == 2


def test_starved_heavy_tasks_are_exempt_from_degraded_block(tmp_path: Path) -> None:
    """飢餓豁免：飢餓偵測不再獨立觸發 degraded（改為 normal + 加速），starved heavy task 不被 blocked。"""
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {})
    _write_json(
        tmp_path / "state" / "auto-task-fairness-hint.json",
        {
            "starvation_detected": True,
            "starvation_count": 5,
            # tech_research 本身是飢餓任務 → 應豁免 blocked
            "zero_count_tasks": ["tech_research"],
        },
    )
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "normal"
    assert plan["runtime"]["gates"]["starvation_detected"] is True
    # 核心斷言：飢餓任務不應出現在 blocked_task_keys
    assert "tech_research" not in plan["runtime"]["policies"]["blocked_task_keys"]
    # 飢餓任務 >= 1 個 → 飢餓加速觸發（normal 的 4，加速至 team_mode+2=5）
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 5


def test_starvation_boost_max_parallel_when_multiple_starved(tmp_path: Path) -> None:
    """飢餓加速：多個任務積壓時保持 normal mode，max_parallel 提升至 team_mode+2=5。
    starvation_detected 不再觸發 degraded；多任務飢餓直接走加速路徑。
    """
    config_path = _write_config(tmp_path)
    # 寫入 frequency-limits.yaml，team_mode=3 以驗證加速邏輯（高於 degraded 的 2）
    freq_yaml = (
        "max_auto_per_run:\n"
        "  single_mode: 1\n"
        "  team_mode: 3\n"
    )
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "frequency-limits.yaml").write_text(freq_yaml, encoding="utf-8")
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {})
    _write_json(
        tmp_path / "state" / "auto-task-fairness-hint.json",
        {
            "starvation_detected": True,
            "starvation_count": 5,
            "zero_count_tasks": ["tech_research", "ai_deep_research", "github_scout"],
        },
    )
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "normal"
    # 飢餓加速：max_parallel 應為 team_mode(3) + 2 = 5
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 5
    # 飢餓任務仍不應被 blocked
    assert "tech_research" not in plan["runtime"]["policies"]["blocked_task_keys"]
    assert "ai_deep_research" not in plan["runtime"]["policies"]["blocked_task_keys"]


def _make_starvation_state(tmp_path: Path, zero_count_tasks: list[str]) -> None:
    """輔助：寫入基本 state 檔案，並設定多個飢餓任務。"""
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(tmp_path / "state" / "api-health.json", {})
    _write_json(
        tmp_path / "state" / "auto-task-fairness-hint.json",
        {"starvation_detected": True, "starvation_count": 5, "zero_count_tasks": zero_count_tasks},
    )
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})


def test_starvation_boost_does_not_apply_in_recovery_mode(tmp_path: Path) -> None:
    """Recovery mode + 多任務飢餓：飢餓加速不應突破 recovery 的並行限制。"""
    config_path = _write_config(tmp_path)
    _make_starvation_state(tmp_path, ["tech_research", "ai_deep_research", "github_scout"])
    # heartbeat stale → recovery mode
    _write_json(
        tmp_path / "state" / "scheduler-heartbeat.json",
        {"timestamp": "2026-03-20T04:00:00+08:00", "status": "stale"},
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "recovery"
    # Recovery mode：飢餓加速不觸發，維持 recovery 的限制值 1
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 1


def test_starvation_boost_in_normal_mode(tmp_path: Path) -> None:
    """Normal mode + 多任務飢餓：max_parallel 從 4 提升至 team_mode+2=5。"""
    config_path = _write_config(tmp_path)
    _make_starvation_state(tmp_path, ["tech_research", "ai_deep_research", "github_scout"])
    _write_json(
        tmp_path / "state" / "scheduler-heartbeat.json",
        {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"},
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }
    # normal mode 需要無 high/critical action：token alert 設為舊日期，無 open circuit
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    # starvation_detected=True 不再觸發 degraded → mode 保持 normal
    # 飢餓加速（>= 1 starved）將 max_parallel 提升至 team_mode+2=5
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 5


def test_starvation_boost_uses_config_value(tmp_path: Path) -> None:
    """starvation_boost 外部化：設 starvation_boost=1 時，加速上限應為 team_mode+1=4（非 hardcode 的 +2）。"""
    config_path = _write_config(tmp_path)
    # 覆寫 starvation_boost=1
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cfg["autonomous_harness"]["thresholds"]["starvation_boost"] = 1
    config_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")

    _make_starvation_state(tmp_path, ["tech_research"])
    _write_json(
        tmp_path / "state" / "scheduler-heartbeat.json",
        {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"},
    )
    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 20},
        "memory": {"percent": 40, "available_mb": 4096},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    # starvation_boost=1 → team_mode(3) + 1 = 4（正常 profile 也是 4，取 max → 4）
    assert plan["runtime"]["policies"]["max_parallel_auto_tasks"] == 4


def test_recovery_mode_sends_ntfy_notification(tmp_path: Path) -> None:
    """Recovery mode 進入時應嘗試發送 ntfy 告警，並寫入冷卻檔。"""
    from unittest.mock import MagicMock, patch

    config_path = _write_config(tmp_path)
    _make_starvation_state(tmp_path, [])
    _write_json(
        tmp_path / "state" / "scheduler-heartbeat.json",
        {"timestamp": "2026-03-20T04:00:00+08:00", "status": "stale"},
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }

    with patch("tools.autonomous_harness.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "recovery"
    # curl 應被呼叫一次
    assert mock_run.call_count == 1
    # 冷卻檔應被寫入
    assert (tmp_path / "state" / "recovery-notified.json").exists()


def test_recovery_mode_ntfy_respects_cooldown(tmp_path: Path) -> None:
    """冷卻期（1 小時）內再次進入 recovery mode 不重複發送通知。"""
    from unittest.mock import MagicMock, patch

    config_path = _write_config(tmp_path)
    _make_starvation_state(tmp_path, [])
    _write_json(
        tmp_path / "state" / "scheduler-heartbeat.json",
        {"timestamp": "2026-03-20T04:00:00+08:00", "status": "stale"},
    )
    # 模擬 30 分鐘前已發過通知
    _write_json(
        tmp_path / "state" / "recovery-notified.json",
        {"notified_at": "2026-03-20T06:30:00+08:00"},
    )

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 35},
        "memory": {"percent": 42, "available_mb": 2048},
        "gpu": {"available": False, "devices": []},
    }

    with patch("tools.autonomous_harness.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    assert plan["runtime"]["mode"] == "recovery"
    # 冷卻期內不應呼叫 curl
    assert mock_run.call_count == 0


def test_chatroom_scope_api_open_does_not_degrade_mode(tmp_path: Path) -> None:
    """gun-bot 熔斷（chatroom scope）不應觸發 degraded mode，只鎖定 chatroom fetch agent。"""
    config_path = _write_config(tmp_path)
    _write_json(tmp_path / "state" / "run-fsm.json", {"runs": {}, "updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "scheduler-state.json", {"runs": []})
    _write_json(tmp_path / "state" / "failure-stats.json", {"updated": "2026-03-20T07:00:00+08:00"})
    _write_json(tmp_path / "state" / "failed-auto-tasks.json", {"entries": []})
    _write_json(
        tmp_path / "state" / "api-health.json",
        {"gun-bot": {"state": "open", "failures": 4, "cooldown": None}},
    )
    _write_json(tmp_path / "state" / "auto-task-fairness-hint.json", {"starvation_detected": False, "starvation_count": 0})
    _write_json(tmp_path / "state" / "token-budget-state.json", {"last_alerted_date": "2026-03-19"})
    _write_json(tmp_path / "state" / "scheduler-heartbeat.json", {"timestamp": "2026-03-20T07:00:00+08:00", "status": "running"})

    harness = AutonomousHarness(repo_root=tmp_path, config_path=config_path)
    harness._collect_resource_snapshot = lambda: {
        "generated_at": "2026-03-20T07:00:00+08:00",
        "cpu": {"percent": 10},
        "memory": {"percent": 30, "available_mb": 8192},
        "gpu": {"available": False, "devices": []},
    }
    plan = harness.build_plan(now=datetime.fromisoformat("2026-03-20T07:00:00+08:00"))

    # chatroom scope API 不計入 open_circuits
    assert plan["summary"]["open_circuits"] == 0
    # 系統保持 normal mode
    assert plan["runtime"]["mode"] == "normal"
    # chatroom fetch agent 被鎖定
    assert "chatroom" in plan["runtime"]["policies"]["blocked_fetch_agents"]
    # 其他 fetch agents 不受影響
    assert "gmail" not in plan["runtime"]["policies"]["blocked_fetch_agents"]
    # gun-bot 有 dispatch 設定 → 產生 restart_agent（非 queue_self_heal）
    action_types = {(item["action_type"], item["target"]) for item in plan["actions"]}
    assert ("restart_agent", "gun-bot") in action_types
    assert ("queue_self_heal", "gun-bot") not in action_types
