#!/usr/bin/env python3
"""
Autonomous harness supervisor.

將既有的 scheduler-state、run-fsm、failure-stats、failed-auto-tasks、api-health
收斂為單一控制面，輸出自治調度決策，必要時可執行安全的重啟派發。
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "autonomous-harness.yaml"
TAIPEI_TZ = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(TAIPEI_TZ)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TAIPEI_TZ)
    return dt.astimezone(TAIPEI_TZ)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class Action:
    action_type: str
    target: str
    reason: str
    severity: str
    command: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "action_type": self.action_type,
            "target": self.target,
            "reason": self.reason,
            "severity": self.severity,
        }
        if self.command:
            payload["command"] = self.command
        return payload


class AutonomousHarness:
    def __init__(self, repo_root: Path = REPO_ROOT, config_path: Path = CONFIG_PATH) -> None:
        self.repo_root = repo_root
        self.config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.settings = self.config["autonomous_harness"]
        self.thresholds = self.settings["thresholds"]
        self.dispatch = self.settings.get("dispatch", {})

    def _resolve(self, key: str) -> Path:
        return self.repo_root / self.settings[key]

    def _recent_scheduler_runs(self, scheduler_state: dict[str, Any]) -> list[dict[str, Any]]:
        runs = scheduler_state.get("runs", [])
        return runs[-self.thresholds["scheduler_failure_window"] :]

    def _stale_run_actions(self, run_fsm: dict[str, Any], now: datetime) -> list[Action]:
        actions: list[Action] = []
        stale_after = timedelta(minutes=self.thresholds["stale_run_minutes"])
        for run_key, run in run_fsm.get("runs", {}).items():
            phases = run.get("phases", {})
            for phase_name, phase in phases.items():
                if phase.get("state") != "running":
                    continue
                updated = _parse_datetime(phase.get("updated"))
                if not updated:
                    continue
                age = now - updated
                if age <= stale_after:
                    continue
                agent_type = run.get("agent_type", "unknown")
                command = self.dispatch.get(agent_type, {}).get("restart_command")
                reason = (
                    f"{run_key}:{phase_name} 持續 running {int(age.total_seconds() // 60)} 分鐘，"
                    "超過自治閾值"
                )
                actions.append(
                    Action(
                        action_type="restart_agent",
                        target=agent_type,
                        reason=reason,
                        severity="critical",
                        command=command,
                    )
                )
        return actions

    def _scheduler_failure_actions(self, scheduler_state: dict[str, Any]) -> list[Action]:
        actions: list[Action] = []
        recent_runs = self._recent_scheduler_runs(scheduler_state)
        failures_by_agent: dict[str, int] = {}
        for run in recent_runs:
            if run.get("status") == "success":
                continue
            agent = run.get("agent", "unknown")
            failures_by_agent[agent] = failures_by_agent.get(agent, 0) + 1

        for agent, failure_count in failures_by_agent.items():
            if failure_count < self.thresholds["scheduler_failure_threshold"]:
                continue
            normalized_agent = "daily-digest" if "daily" in agent else "todoist" if "todoist" in agent else agent
            command = self.dispatch.get(normalized_agent, {}).get("restart_command")
            actions.append(
                Action(
                    action_type="restart_agent",
                    target=normalized_agent,
                    reason=f"最近 {self.thresholds['scheduler_failure_window']} 次排程中失敗 {failure_count} 次",
                    severity="high",
                    command=command,
                )
            )
        return actions

    def _failed_auto_task_actions(self, failed_auto_tasks: dict[str, Any]) -> list[Action]:
        actions: list[Action] = []
        for entry in failed_auto_tasks.get("entries", []):
            count = int(entry.get("consecutive_count", 0))
            if count < self.thresholds["failed_auto_task_threshold"]:
                continue
            task_key = entry.get("task_key", "unknown")
            actions.append(
                Action(
                    action_type="queue_self_heal",
                    target=task_key,
                    reason=f"自動任務已連續失敗 {count} 次，需插入自癒佇列",
                    severity="high",
                )
            )
        return actions

    def _api_health_actions(self, api_health: dict[str, Any]) -> list[Action]:
        actions: list[Action] = []
        for api_name, status in api_health.get("apis", {}).items():
            circuit = status.get("circuit_breaker", {})
            state = circuit.get("state")
            if state != "open":
                continue
            actions.append(
                Action(
                    action_type="queue_self_heal",
                    target=api_name,
                    reason=f"{api_name} circuit breaker 為 open，需自動降級與恢復檢查",
                    severity="medium",
                )
            )
        return actions

    def build_plan(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        run_fsm = _load_json(self._resolve("run_fsm_path"), {"runs": {}, "updated": None})
        scheduler_state = _load_json(self._resolve("scheduler_state_path"), {"runs": []})
        failure_stats = _load_json(self._resolve("failure_stats_path"), {"daily": {}, "total": {}})
        failed_auto_tasks = _load_json(self._resolve("failed_auto_tasks_path"), {"entries": []})
        api_health = _load_json(self._resolve("api_health_path"), {"apis": {}})

        actions = []
        actions.extend(self._stale_run_actions(run_fsm, now))
        actions.extend(self._scheduler_failure_actions(scheduler_state))
        actions.extend(self._failed_auto_task_actions(failed_auto_tasks))
        actions.extend(self._api_health_actions(api_health))

        deduped: list[Action] = []
        seen = set()
        for action in actions:
            key = (action.action_type, action.target, action.reason)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(action)

        plan = {
            "generated_at": now.isoformat(),
            "summary": {
                "scheduler_runs_analyzed": len(self._recent_scheduler_runs(scheduler_state)),
                "open_circuits": sum(
                    1
                    for status in api_health.get("apis", {}).values()
                    if status.get("circuit_breaker", {}).get("state") == "open"
                ),
                "failed_auto_tasks": sum(
                    1
                    for entry in failed_auto_tasks.get("entries", [])
                    if int(entry.get("consecutive_count", 0)) >= self.thresholds["failed_auto_task_threshold"]
                ),
                "pending_actions": len(deduped),
            },
            "signals": {
                "run_fsm_updated": run_fsm.get("updated"),
                "failure_stats_updated": failure_stats.get("updated"),
                "scheduler_state_recent_statuses": [
                    run.get("status") for run in self._recent_scheduler_runs(scheduler_state)
                ],
            },
            "actions": [action.as_dict() for action in deduped],
        }
        return plan

    def enqueue_recovery(self, plan: dict[str, Any]) -> dict[str, Any]:
        queue_path = self._resolve("recovery_queue_path")
        queue = _load_json(queue_path, {"version": 1, "items": []})
        for action in plan["actions"]:
            if action["action_type"] not in {"queue_self_heal", "restart_agent"}:
                continue
            queue["items"].append(
                {
                    "queued_at": plan["generated_at"],
                    "target": action["target"],
                    "action_type": action["action_type"],
                    "reason": action["reason"],
                    "severity": action["severity"],
                    "status": "pending",
                }
            )
        queue["updated_at"] = plan["generated_at"]
        _write_json(queue_path, queue)
        return queue

    def execute(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        executions: list[dict[str, Any]] = []
        for action in plan["actions"]:
            if action["action_type"] != "restart_agent" or not action.get("command"):
                continue
            command = action["command"]
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
            executions.append(
                {
                    "target": action["target"],
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-500:],
                    "stderr": completed.stderr[-500:],
                }
            )
        return executions


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous harness supervisor")
    parser.add_argument("--execute", action="store_true", help="執行 restart_agent 類型動作")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    harness = AutonomousHarness()
    plan = harness.build_plan()
    _write_json(harness._resolve("output_plan_path"), plan)
    queue = harness.enqueue_recovery(plan)
    if args.execute:
        plan["executions"] = harness.execute(plan)
        _write_json(harness._resolve("output_plan_path"), plan)

    if args.format == "json":
        print(json.dumps({"plan": plan, "queue_size": len(queue.get("items", []))}, ensure_ascii=False, indent=2))
        return

    print("[Autonomous Harness]")
    print(f"generated_at: {plan['generated_at']}")
    print(f"pending_actions: {plan['summary']['pending_actions']}")
    for action in plan["actions"]:
        print(f"- {action['severity']} {action['action_type']} {action['target']} :: {action['reason']}")


if __name__ == "__main__":
    main()
