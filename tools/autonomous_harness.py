#!/usr/bin/env python3
"""
Autonomous harness supervisor.

將既有的 scheduler-state、run-fsm、failure-stats、failed-auto-tasks、api-health
收斂為單一控制面，輸出自治調度決策，必要時可執行安全的重啟派發。
"""
from __future__ import annotations

import argparse
import json
import os
import re
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


def _parse_typeperf_value(output: str) -> float | None:
    for line in reversed(output.splitlines()):
        match = re.search(r'"([-+]?\d+(?:\.\d+)?)"\s*$', line.strip())
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


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
        self.runtime_profiles = self.settings.get("runtime_profiles", {})
        self.discovery = self.settings.get("discovery", {})
        self.resources = self.settings.get("resources", {})
        self.recovery_worker = self.settings.get("recovery_worker", {})

    def _resolve(self, key: str) -> Path:
        return self.repo_root / self.settings[key]

    def _recent_scheduler_runs(self, scheduler_state: dict[str, Any]) -> list[dict[str, Any]]:
        runs = scheduler_state.get("runs", [])
        return runs[-self.thresholds["scheduler_failure_window"] :]

    def _classify_auto_task(self, task_key: str) -> dict[str, bool]:
        heavy_patterns = self.discovery.get("heavy_task_patterns", [])
        research_patterns = self.discovery.get("research_task_patterns", [])
        is_heavy = any(pattern in task_key for pattern in heavy_patterns)
        is_research = any(pattern in task_key for pattern in research_patterns)
        return {"is_heavy": is_heavy, "is_research": is_research}

    def _discover_agent_registry(
        self, run_fsm: dict[str, Any], scheduler_state: dict[str, Any]
    ) -> dict[str, Any]:
        fetch_agents: list[dict[str, Any]] = []
        auto_tasks: list[dict[str, Any]] = []

        for prompt_path in sorted(self.repo_root.glob(self.discovery.get("fetch_agents_glob", ""))):
            name = prompt_path.stem.replace("fetch-", "")
            fetch_agents.append(
                {
                    "key": name,
                    "path": str(prompt_path.relative_to(self.repo_root)).replace("\\", "/"),
                    "source": "prompt",
                }
            )

        for task_path in sorted(self.repo_root.glob(self.discovery.get("auto_tasks_glob", ""))):
            key = task_path.stem.replace("-", "_")
            classification = self._classify_auto_task(key)
            auto_tasks.append(
                {
                    "key": key,
                    "path": str(task_path.relative_to(self.repo_root)).replace("\\", "/"),
                    "source": "template",
                    **classification,
                }
            )

        runtime_agents = sorted(
            {
                run.get("agent_type", "unknown")
                for run in run_fsm.get("runs", {}).values()
                if run.get("agent_type")
            }
            | {
                "daily-digest" if "daily" in str(item.get("agent")) else "todoist"
                if "todoist" in str(item.get("agent"))
                else str(item.get("agent"))
                for item in scheduler_state.get("runs", [])
                if item.get("agent")
            }
            | set(self.dispatch.keys())
        )

        registry = {
            "generated_at": _now().isoformat(),
            "managed_agents": runtime_agents,
            "fetch_agents": fetch_agents,
            "auto_tasks": auto_tasks,
            "summary": {
                "managed_agent_count": len(runtime_agents),
                "fetch_agent_count": len(fetch_agents),
                "auto_task_count": len(auto_tasks),
                "heavy_auto_task_count": sum(1 for item in auto_tasks if item["is_heavy"]),
                "research_auto_task_count": sum(1 for item in auto_tasks if item["is_research"]),
            },
        }
        return registry

    def _run_powershell_json(self, script: str) -> dict[str, Any] | None:
        command = ["powershell", "-NoProfile", "-Command", script]
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None

    def _run_typeperf(self, counter: str) -> float | None:
        """執行 typeperf 取得單一效能計數器值，失敗回傳 None。"""
        try:
            result = subprocess.run(
                ["typeperf", counter, "-sc", "1"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return _parse_typeperf_value(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def _collect_resource_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "generated_at": _now().isoformat(),
            "cpu": {"percent": None},
            "memory": {"percent": None, "available_mb": None},
            "gpu": {"available": False, "devices": []},
        }

        if os.name == "nt":
            system_stats = self._run_powershell_json(
                """
$cpu = (Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
  cpu_percent = [math]::Round($cpu, 2)
  memory_percent = [math]::Round((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize) * 100, 2)
  available_mb = [math]::Round($os.FreePhysicalMemory / 1024, 2)
} | ConvertTo-Json -Compress
""".strip()
            )
            if system_stats:
                snapshot["cpu"]["percent"] = system_stats.get("cpu_percent")
                snapshot["memory"]["percent"] = system_stats.get("memory_percent")
                snapshot["memory"]["available_mb"] = system_stats.get("available_mb")

            if snapshot["cpu"]["percent"] is None:
                snapshot["cpu"]["percent"] = self._run_typeperf(
                    r"\Processor(_Total)\% Processor Time"
                )
            if snapshot["memory"]["available_mb"] is None:
                snapshot["memory"]["available_mb"] = self._run_typeperf(
                    r"\Memory\Available MBytes"
                )
            if snapshot["memory"]["percent"] is None:
                snapshot["memory"]["percent"] = self._run_typeperf(
                    r"\Memory\% Committed Bytes In Use"
                )

        try:
            gpu_result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,name",
                    "--format=csv,noheader,nounits",
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
                check=False,
            )
            if gpu_result.returncode == 0 and gpu_result.stdout.strip():
                devices = []
                for raw_line in gpu_result.stdout.strip().splitlines():
                    util_str, used_str, total_str, name = [part.strip() for part in raw_line.split(",", 3)]
                    used = float(used_str)
                    total = float(total_str)
                    devices.append(
                        {
                            "name": name,
                            "utilization_percent": float(util_str),
                            "memory_used_mb": used,
                            "memory_total_mb": total,
                            "memory_percent": round((used / total) * 100, 2) if total else None,
                        }
                    )
                snapshot["gpu"] = {"available": True, "devices": devices}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return snapshot

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
                dispatch_entry = self.dispatch.get(agent_type) or {}
                command = dispatch_entry.get("restart_command") or []
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

    def _fairness_actions(self, fairness_hint: dict[str, Any]) -> list[Action]:
        if not fairness_hint.get("starvation_detected"):
            return []
        starvation_count = int(fairness_hint.get("starvation_count", 0))
        if starvation_count < self.thresholds["starvation_task_threshold"]:
            return []
        return [
            Action(
                action_type="rebalance_tasks",
                target="todoist",
                reason=f"偵測到 {starvation_count} 個任務飢餓，需降低並行並優先補跑低頻任務",
                severity="high",
            )
        ]

    def _token_budget_actions(self, token_budget_state: dict[str, Any], now: datetime) -> list[Action]:
        last_alerted_date = token_budget_state.get("last_alerted_date")
        if last_alerted_date != now.date().isoformat():
            return []
        return [
            Action(
                action_type="scale_down_workload",
                target="global",
                reason="今日已觸發 token budget 告警，需暫停高成本自動任務",
                severity="medium",
            )
        ]

    def _heartbeat_actions(self, scheduler_heartbeat: dict[str, Any], now: datetime) -> list[Action]:
        status = scheduler_heartbeat.get("status")
        ts = _parse_datetime(scheduler_heartbeat.get("timestamp"))
        stale_after = timedelta(minutes=self.thresholds["heartbeat_stale_minutes"])
        if status == "running" and ts and now - ts <= stale_after:
            return []
        reason = "scheduler heartbeat 遺失或逾時，需進入恢復模式"
        if ts:
            reason = f"scheduler heartbeat 最後更新於 {ts.isoformat()}，超過自治閾值"
        return [
            Action(
                action_type="queue_self_heal",
                target="scheduler-heartbeat",
                reason=reason,
                severity="critical",
            )
        ]

    def _resource_actions(self, resource_snapshot: dict[str, Any]) -> list[Action]:
        actions: list[Action] = []
        cpu_percent = resource_snapshot.get("cpu", {}).get("percent")
        memory_percent = resource_snapshot.get("memory", {}).get("percent")
        gpu_devices = resource_snapshot.get("gpu", {}).get("devices", [])

        if cpu_percent is not None and cpu_percent >= self.resources.get("cpu_percent_high", 85):
            actions.append(
                Action(
                    action_type="scale_down_workload",
                    target="cpu",
                    reason=f"CPU 使用率 {cpu_percent}% 已超過閾值",
                    severity="high",
                )
            )
        if memory_percent is not None and memory_percent >= self.resources.get("memory_percent_high", 80):
            actions.append(
                Action(
                    action_type="scale_down_workload",
                    target="memory",
                    reason=f"記憶體使用率 {memory_percent}% 已超過閾值",
                    severity="high",
                )
            )
        for device in gpu_devices:
            gpu_percent = device.get("utilization_percent")
            gpu_memory_percent = device.get("memory_percent")
            if gpu_percent is not None and gpu_percent >= self.resources.get("gpu_percent_high", 85):
                actions.append(
                    Action(
                        action_type="scale_down_workload",
                        target=f"gpu:{device['name']}",
                        reason=f"GPU 使用率 {gpu_percent}% 已超過閾值",
                        severity="medium",
                    )
                )
            if (
                gpu_memory_percent is not None
                and gpu_memory_percent >= self.resources.get("gpu_memory_percent_high", 80)
            ):
                actions.append(
                    Action(
                        action_type="scale_down_workload",
                        target=f"gpu-memory:{device['name']}",
                        reason=f"GPU 記憶體使用率 {gpu_memory_percent}% 已超過閾值",
                        severity="medium",
                    )
                )
        return actions

    def _derive_runtime_state(
        self,
        plan: dict[str, Any],
        fairness_hint: dict[str, Any],
        token_budget_state: dict[str, Any],
        scheduler_heartbeat: dict[str, Any],
        resource_snapshot: dict[str, Any],
        agent_registry: dict[str, Any],
        runtime_override: dict[str, Any],
    ) -> dict[str, Any]:
        has_critical = any(action["severity"] == "critical" for action in plan["actions"])
        has_high = any(action["severity"] == "high" for action in plan["actions"])
        token_alert = token_budget_state.get("last_alerted_date") == plan["generated_at"][:10]
        starvation_detected = bool(fairness_hint.get("starvation_detected"))
        heartbeat_stale = any(action["target"] == "scheduler-heartbeat" for action in plan["actions"])

        if has_critical or heartbeat_stale:
            mode = "recovery"
        elif has_high or token_alert or starvation_detected or plan["summary"]["open_circuits"] > 0:
            mode = "degraded"
        else:
            mode = "normal"

        override_active = False
        override_reason = None
        override_mode = runtime_override.get("mode")
        override_until = _parse_datetime(runtime_override.get("expires_at"))
        if override_mode and override_until and override_until >= _parse_datetime(plan["generated_at"]):
            mode_order = {"normal": 0, "degraded": 1, "recovery": 2}
            if mode_order.get(override_mode, -1) > mode_order.get(mode, -1):
                mode = override_mode
            override_active = True
            override_reason = runtime_override.get("reason")

        profile = self.runtime_profiles.get(mode, {})
        core_fetch_agents = self.discovery.get("core_fetch_agents", [])
        optional_fetch_agents = self.discovery.get("optional_fetch_agents", [])
        blocked_fetch_agents = list(profile.get("blocked_fetch_agents", []))
        fetch_agent_keys = [item["key"] for item in agent_registry.get("fetch_agents", [])]
        allowed_fetch_agents = [
            key for key in fetch_agent_keys if key not in blocked_fetch_agents
        ]
        heavy_task_keys = [
            item["key"] for item in agent_registry.get("auto_tasks", []) if item.get("is_heavy")
        ]
        research_task_keys = [
            item["key"] for item in agent_registry.get("auto_tasks", []) if item.get("is_research")
        ]
        # 飢餓豁免：在飢餓清單內的任務，即使屬於 heavy/research 也不阻擋
        # 原因：降速的目的是讓輕量任務補跑，但若 heavy task 本身就是飢餓任務，
        #       繼續阻擋反而讓它更飢餓（悖論），故豁免以允許其補跑。
        starved_task_keys = set(fairness_hint.get("zero_count_tasks", []))
        blocked_task_keys: list[str] = []
        if not profile.get("allow_heavy_auto_tasks", True):
            blocked_task_keys.extend(k for k in heavy_task_keys if k not in starved_task_keys)
        if not profile.get("allow_research_auto_tasks", True):
            blocked_task_keys.extend(k for k in research_task_keys if k not in starved_task_keys)
        blocked_fetch_agents.extend(runtime_override.get("blocked_fetch_agents", []))
        blocked_task_keys.extend(runtime_override.get("blocked_task_keys", []))
        max_parallel_auto_tasks = profile.get("max_parallel_auto_tasks", 4)
        if runtime_override.get("max_parallel_auto_tasks") is not None:
            max_parallel_auto_tasks = min(
                max_parallel_auto_tasks,
                int(runtime_override["max_parallel_auto_tasks"]),
            )
        max_parallel_fetch_agents = profile.get("max_parallel_fetch_agents", len(fetch_agent_keys))
        if runtime_override.get("max_parallel_fetch_agents") is not None:
            max_parallel_fetch_agents = min(
                max_parallel_fetch_agents,
                int(runtime_override["max_parallel_fetch_agents"]),
            )
        allowed_fetch_agents = [
            key for key in fetch_agent_keys if key not in sorted(set(blocked_fetch_agents))
        ]
        reasons = [action["reason"] for action in plan["actions"][:5]]
        if override_reason:
            reasons.append(f"override: {override_reason}")
        return {
            "generated_at": plan["generated_at"],
            "mode": mode,
            "reasons": reasons,
            "override": {
                "active": override_active,
                "reason": override_reason,
                "expires_at": runtime_override.get("expires_at"),
            },
            "gates": {
                "heartbeat_stale": heartbeat_stale,
                "starvation_detected": starvation_detected,
                "token_budget_alert": token_alert,
                "open_circuits": plan["summary"]["open_circuits"],
            },
            "policies": {
                "max_parallel_auto_tasks": max_parallel_auto_tasks,
                "max_parallel_fetch_agents": max_parallel_fetch_agents,
                "allow_heavy_auto_tasks": profile.get("allow_heavy_auto_tasks", True),
                "allow_research_auto_tasks": profile.get("allow_research_auto_tasks", True),
                "daily_digest_assembly_mode": profile.get("daily_digest_assembly_mode", "full"),
                "daily_digest_phase2_retries": profile.get("daily_digest_phase2_retries", 1),
                "core_fetch_agents": core_fetch_agents,
                "optional_fetch_agents": optional_fetch_agents,
                "blocked_fetch_agents": sorted(set(blocked_fetch_agents)),
                "allowed_fetch_agents": allowed_fetch_agents,
                "heavy_task_keys": heavy_task_keys,
                "research_task_keys": research_task_keys,
                "blocked_task_keys": sorted(set(blocked_task_keys)),
                "priority_recovery_targets": [
                    action["target"]
                    for action in plan["actions"]
                    if action["action_type"] in {"queue_self_heal", "rebalance_tasks"}
                ],
            },
            "resource_snapshot": resource_snapshot,
            "agent_registry_summary": agent_registry.get("summary", {}),
            "scheduler_heartbeat": scheduler_heartbeat,
        }

    def build_plan(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        run_fsm = _load_json(self._resolve("run_fsm_path"), {"runs": {}, "updated": None})
        scheduler_state = _load_json(self._resolve("scheduler_state_path"), {"runs": []})
        failure_stats = _load_json(self._resolve("failure_stats_path"), {"daily": {}, "total": {}})
        failed_auto_tasks = _load_json(self._resolve("failed_auto_tasks_path"), {"entries": []})
        api_health = _load_json(self._resolve("api_health_path"), {"apis": {}})
        fairness_hint = _load_json(self._resolve("auto_task_fairness_path"), {})
        token_budget_state = _load_json(self._resolve("token_budget_state_path"), {})
        scheduler_heartbeat = _load_json(self._resolve("scheduler_heartbeat_path"), {})
        runtime_override = _load_json(
            self._resolve("runtime_override_path"),
            {"mode": None, "reason": None, "expires_at": None},
        )
        agent_registry = self._discover_agent_registry(run_fsm, scheduler_state)
        resource_snapshot = self._collect_resource_snapshot()

        actions = []
        actions.extend(self._stale_run_actions(run_fsm, now))
        actions.extend(self._scheduler_failure_actions(scheduler_state))
        actions.extend(self._failed_auto_task_actions(failed_auto_tasks))
        actions.extend(self._api_health_actions(api_health))
        actions.extend(self._fairness_actions(fairness_hint))
        actions.extend(self._token_budget_actions(token_budget_state, now))
        actions.extend(self._heartbeat_actions(scheduler_heartbeat, now))
        actions.extend(self._resource_actions(resource_snapshot))

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
                "fairness_hint": fairness_hint,
                "token_budget_state": token_budget_state,
                "scheduler_heartbeat": scheduler_heartbeat,
                "runtime_override": runtime_override,
                "resource_snapshot": resource_snapshot,
                "agent_registry": agent_registry,
                "scheduler_state_recent_statuses": [
                    run.get("status") for run in self._recent_scheduler_runs(scheduler_state)
                ],
            },
            "actions": [action.as_dict() for action in deduped],
        }
        plan["runtime"] = self._derive_runtime_state(
            plan,
            fairness_hint,
            token_budget_state,
            scheduler_heartbeat,
            resource_snapshot,
            agent_registry,
            runtime_override,
        )
        return plan

    def enqueue_recovery(self, plan: dict[str, Any]) -> dict[str, Any]:
        queue_path = self._resolve("recovery_queue_path")
        queue = _load_json(queue_path, {"version": 1, "items": []})
        existing_pending = {
            (item.get("action_type"), item.get("target"), item.get("reason"))
            for item in queue.get("items", [])
            if item.get("status") == "pending"
        }
        for action in plan["actions"]:
            if action["action_type"] not in {
                "queue_self_heal",
                "restart_agent",
                "rebalance_tasks",
                "scale_down_workload",
            }:
                continue
            dedupe_key = (action["action_type"], action["target"], action["reason"])
            if dedupe_key in existing_pending:
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
            existing_pending.add(dedupe_key)
        queue["updated_at"] = plan["generated_at"]
        _write_json(queue_path, queue)
        return queue

    # 允許執行的命令白名單前綴（防止任意命令注入）
    ALLOWED_COMMAND_PREFIXES = (
        "pwsh",
        "powershell",
        "uv run",
    )

    def _validate_command(self, command: list[str] | str) -> bool:
        """驗證命令是否在白名單中。僅允許已知安全的命令前綴。"""
        if isinstance(command, list):
            cmd_str = " ".join(command)
        else:
            cmd_str = str(command)
        cmd_lower = cmd_str.strip().lower()
        return any(cmd_lower.startswith(prefix) for prefix in self.ALLOWED_COMMAND_PREFIXES)

    def execute(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        executions: list[dict[str, Any]] = []
        for action in plan["actions"]:
            if action["action_type"] != "restart_agent" or not action.get("command"):
                continue
            command = action["command"]
            if not self._validate_command(command):
                executions.append(
                    {
                        "target": action["target"],
                        "returncode": -1,
                        "stdout": "",
                        "stderr": "Command blocked: not in allowed prefix whitelist",
                    }
                )
                continue
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
    _write_json(harness._resolve("runtime_state_path"), plan["runtime"])
    _write_json(harness._resolve("agent_registry_path"), plan["signals"]["agent_registry"])
    _write_json(harness._resolve("resource_snapshot_path"), plan["signals"]["resource_snapshot"])
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
