#!/usr/bin/env python3
"""
Autonomous recovery worker.

消費 autonomous-recovery-queue，將控制面的恢復決策轉為可執行動作：
- restart_agent: 執行安全的重啟命令
- queue_self_heal / rebalance_tasks / scale_down_workload: 寫入暫時 runtime override
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.autonomous_harness import (  # noqa: E402
    CONFIG_PATH,
    AutonomousHarness,
    _load_json,
    _now,
    _write_json,
)


class AutonomousRecoveryWorker:
    def __init__(self, repo_root: Path | None = None, config_path: Path | None = None) -> None:
        self.harness = AutonomousHarness(
            repo_root=repo_root or REPO_ROOT,
            config_path=config_path or CONFIG_PATH,
        )
        self.repo_root = self.harness.repo_root
        self.settings = self.harness.settings
        self.worker_settings = self.harness.recovery_worker

    def _resolve(self, key: str) -> Path:
        return self.repo_root / self.settings[key]

    def _load_queue(self) -> dict[str, Any]:
        return _load_json(self._resolve("recovery_queue_path"), {"version": 1, "items": []})

    def _load_override(self) -> dict[str, Any]:
        return _load_json(
            self._resolve("runtime_override_path"),
            {
                "mode": None,
                "reason": None,
                "expires_at": None,
                "blocked_task_keys": [],
                "blocked_fetch_agents": [],
            },
        )

    def _load_self_heal_requests(self) -> dict[str, Any]:
        return _load_json(self._resolve("self_heal_request_path"), {"version": 1, "items": []})

    def _write_override(self, override: dict[str, Any]) -> None:
        _write_json(self._resolve("runtime_override_path"), override)

    def _append_self_heal_request(self, target: str, reason: str, queued_at: str) -> None:
        payload = self._load_self_heal_requests()
        payload["items"].append(
            {
                "queued_at": queued_at,
                "target": target,
                "reason": reason,
                "status": "pending",
            }
        )
        payload["updated_at"] = queued_at
        _write_json(self._resolve("self_heal_request_path"), payload)

    def _apply_override(self, item: dict[str, Any], now_iso: str) -> dict[str, Any]:
        override = self._load_override()
        mode = "degraded"
        ttl_minutes = int(self.worker_settings.get("default_override_ttl_minutes", 30))
        blocked_task_keys = set(override.get("blocked_task_keys", []))
        blocked_fetch_agents = set(override.get("blocked_fetch_agents", []))
        max_parallel_auto_tasks = override.get("max_parallel_auto_tasks")
        max_parallel_fetch_agents = override.get("max_parallel_fetch_agents")

        if item["action_type"] == "scale_down_workload":
            mode = "recovery" if item["severity"] == "critical" else "degraded"
            ttl_minutes = int(self.worker_settings.get("scale_down_ttl_minutes", ttl_minutes))
            max_parallel_auto_tasks = min(int(max_parallel_auto_tasks or 99), 1 if mode == "recovery" else 2)
            max_parallel_fetch_agents = min(
                int(max_parallel_fetch_agents or 99),
                3 if mode == "recovery" else 4,
            )
        elif item["action_type"] == "rebalance_tasks":
            ttl_minutes = int(self.worker_settings.get("rebalance_ttl_minutes", ttl_minutes))
            max_parallel_auto_tasks = min(int(max_parallel_auto_tasks or 99), 2)
        elif item["action_type"] == "queue_self_heal":
            ttl_minutes = int(self.worker_settings.get("self_heal_ttl_minutes", ttl_minutes))
            mode = "degraded"
            target = item.get("target", "")
            if target and target not in {"scheduler-heartbeat", "global"}:
                blocked_task_keys.add(target)
            if target in {"gmail", "security", "chatroom", "news", "todoist", "hackernews"}:
                blocked_fetch_agents.add(target)
            self._append_self_heal_request(target or "unknown", item["reason"], now_iso)

        expires_at = (_now() + timedelta(minutes=ttl_minutes)).isoformat()
        override.update(
            {
                "mode": mode,
                "reason": item["reason"],
                "expires_at": expires_at,
                "blocked_task_keys": sorted(blocked_task_keys),
                "blocked_fetch_agents": sorted(blocked_fetch_agents),
            }
        )
        if max_parallel_auto_tasks is not None:
            override["max_parallel_auto_tasks"] = max_parallel_auto_tasks
        if max_parallel_fetch_agents is not None:
            override["max_parallel_fetch_agents"] = max_parallel_fetch_agents
        self._write_override(override)
        return {"status": "completed", "effect": "runtime_override_updated", "expires_at": expires_at}

    def _restart_agent(self, item: dict[str, Any]) -> dict[str, Any]:
        command = item.get("command")
        if not command:
            dispatch = self.harness.dispatch.get(item.get("target", ""), {})
            command = dispatch.get("restart_command")
        if not command:
            return {"status": "failed", "error": "missing_restart_command"}

        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=int(self.worker_settings.get("restart_timeout_seconds", 30)),
            check=False,
        )
        return {
            "status": "completed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-500:],
            "stderr": completed.stderr[-500:],
        }

    def process(self, limit: int | None = None) -> dict[str, Any]:
        queue = self._load_queue()
        now_iso = _now().isoformat()
        processed = []
        pending_items = [item for item in queue.get("items", []) if item.get("status") == "pending"]
        for index, item in enumerate(pending_items):
            if limit is not None and index >= limit:
                break
            if item["action_type"] == "restart_agent":
                result = self._restart_agent(item)
            else:
                result = self._apply_override(item, now_iso)
            item["processed_at"] = now_iso
            item["status"] = result["status"]
            item["result"] = result
            processed.append({"target": item.get("target"), "action_type": item["action_type"], **result})

        queue["updated_at"] = now_iso
        _write_json(self._resolve("recovery_queue_path"), queue)

        refreshed_plan = self.harness.build_plan()
        _write_json(self._resolve("output_plan_path"), refreshed_plan)
        _write_json(self._resolve("runtime_state_path"), refreshed_plan["runtime"])

        return {
            "processed_count": len(processed),
            "processed": processed,
            "queue_size": len(queue.get("items", [])),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume autonomous recovery queue")
    parser.add_argument("--limit", type=int, default=None, help="最多處理幾筆 pending item")
    args = parser.parse_args()

    worker = AutonomousRecoveryWorker()
    result = worker.process(limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
