#!/usr/bin/env python3
"""
Checkpoint Manager for Durable Execution with Auto-Recovery.

提供任務執行的 checkpoint 機制，失敗時可從最後成功的 checkpoint 恢復。
受 LangGraph 的 durable execution 啟發（github.com/langchain-ai/langgraph）。

Usage:
    from tools.checkpoint_manager import CheckpointManager

    manager = CheckpointManager(task_id="todoist-auto-research")

    # 載入最後的 checkpoint（若有）
    checkpoint = manager.load_latest()
    start_step = checkpoint["step_index"] + 1 if checkpoint else 0

    # 執行任務
    for i in range(start_step, total_steps):
        execute_step(i)
        manager.save_checkpoint(step_index=i, state={"data": "..."})

    # 完成後清理
    manager.cleanup()
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_DIR = REPO_ROOT / "state" / "checkpoints"
TAIPEI_TZ = timezone(timedelta(hours=8))


class CheckpointManager:
    """管理任務執行的 checkpoint，支援從中斷點恢復。"""

    def __init__(self, task_id: str, max_checkpoints: int = 5):
        """
        初始化 CheckpointManager。

        Args:
            task_id: 任務唯一識別碼（如 "todoist-auto-research"）
            max_checkpoints: 每個任務最多保留幾個 checkpoint（預設 5）
        """
        self.task_id = task_id
        self.max_checkpoints = max_checkpoints
        self.checkpoint_dir = CHECKPOINT_DIR / task_id
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        step_index: int,
        state: dict[str, Any],
        completed_steps: list[str] | None = None,
    ) -> Path:
        """
        儲存 checkpoint。

        Args:
            step_index: 當前步驟索引（從 0 開始）
            state: 任務狀態（任意 JSON-serializable dict）
            completed_steps: 已完成的步驟名稱列表

        Returns:
            checkpoint 檔案路徑
        """
        timestamp = datetime.now(TAIPEI_TZ).isoformat()
        checkpoint_data = {
            "task_id": self.task_id,
            "timestamp": timestamp,
            "step_index": step_index,
            "completed_steps": completed_steps or [],
            "state": state,
        }

        # 檔名：checkpoint-{step_index}-{timestamp_short}.json
        ts_short = timestamp.replace(":", "").replace("-", "")[:15]
        checkpoint_file = self.checkpoint_dir / f"checkpoint-{step_index}-{ts_short}.json"

        checkpoint_file.write_text(
            json.dumps(checkpoint_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 清理舊 checkpoints
        self._cleanup_old_checkpoints()

        return checkpoint_file

    def load_latest(self) -> dict[str, Any] | None:
        """
        載入最新的 checkpoint。

        Returns:
            checkpoint 資料（dict），若無 checkpoint 則回傳 None
        """
        checkpoints = sorted(
            self.checkpoint_dir.glob("checkpoint-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not checkpoints:
            return None

        latest = checkpoints[0]
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """
        列出所有 checkpoints（依時間排序，最新在前）。

        Returns:
            checkpoint 資料列表
        """
        checkpoints = sorted(
            self.checkpoint_dir.glob("checkpoint-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        result = []
        for cp_file in checkpoints:
            try:
                data = json.loads(cp_file.read_text(encoding="utf-8"))
                result.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        return result

    def cleanup(self) -> int:
        """
        清理所有 checkpoints（任務成功完成後呼叫）。

        Returns:
            刪除的檔案數量
        """
        count = 0
        for cp_file in self.checkpoint_dir.glob("checkpoint-*.json"):
            try:
                cp_file.unlink()
                count += 1
            except OSError:
                continue

        # 若目錄空了，刪除目錄
        try:
            self.checkpoint_dir.rmdir()
        except OSError:
            pass

        return count

    def _cleanup_old_checkpoints(self) -> None:
        """保留最近的 N 個 checkpoints，刪除其餘。"""
        checkpoints = sorted(
            self.checkpoint_dir.glob("checkpoint-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old_cp in checkpoints[self.max_checkpoints :]:
            try:
                old_cp.unlink()
            except OSError:
                continue


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Checkpoint Manager CLI")
    parser.add_argument("--task-id", required=True, help="Task ID")
    parser.add_argument("--action", choices=["save", "load", "list", "cleanup"], required=True)
    parser.add_argument("--step-index", type=int, help="Step index (for save)")
    parser.add_argument("--state", help="State JSON string (for save)")

    args = parser.parse_args()
    manager = CheckpointManager(task_id=args.task_id)

    if args.action == "save":
        if args.step_index is None or args.state is None:
            print("❌ --step-index and --state required for save")
            exit(1)
        state_data = json.loads(args.state)
        cp_file = manager.save_checkpoint(step_index=args.step_index, state=state_data)
        print(f"✅ Checkpoint saved: {cp_file}")

    elif args.action == "load":
        checkpoint = manager.load_latest()
        if checkpoint:
            print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        else:
            print("❌ No checkpoint found")

    elif args.action == "list":
        checkpoints = manager.list_checkpoints()
        print(f"Found {len(checkpoints)} checkpoints:")
        for cp in checkpoints:
            print(f"  - Step {cp['step_index']} at {cp['timestamp']}")

    elif args.action == "cleanup":
        count = manager.cleanup()
        print(f"✅ Cleaned up {count} checkpoints")
