#!/usr/bin/env python3
"""Snapshot and restore long-term memory related files."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_ROOT = REPO_ROOT / "backups" / "long_term_memory_snapshots"
TARGETS = [
    "context/digest-memory.json",
    "context/research-registry.json",
    "data/long_term_memory_optimized.json",
    "state/long_term_memory_sync_queue.json",
]
TARGET_DIRS = [
    "context/continuity",
]


def _safe_label(label: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in label).strip("-") or "snapshot"


def create_snapshot(*, label: str | None = None, source_root: Path = REPO_ROOT) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_name = f"{timestamp}-{_safe_label(label or 'manual')}"
    snapshot_dir = SNAPSHOT_ROOT / snapshot_name
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label": label or "manual",
        "files": [],
        "directories": [],
    }

    for relative in TARGETS:
        source = source_root / relative
        if not source.exists():
            continue
        destination = snapshot_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest["files"].append(relative)

    for relative in TARGET_DIRS:
        source = source_root / relative
        if not source.exists():
            continue
        destination = snapshot_dir / relative
        shutil.copytree(source, destination, dirs_exist_ok=True)
        manifest["directories"].append(relative)

    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot_dir


def restore_snapshot(snapshot_dir: Path, *, target_root: Path = REPO_ROOT) -> dict[str, int]:
    restored_files = 0
    restored_dirs = 0

    manifest_path = snapshot_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files", [])
        directories = manifest.get("directories", [])
    else:
        files = TARGETS
        directories = TARGET_DIRS

    for relative in files:
        source = snapshot_dir / str(relative)
        if not source.exists():
            continue
        destination = target_root / str(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        restored_files += 1

    for relative in directories:
        source = snapshot_dir / str(relative)
        if not source.exists():
            continue
        destination = target_root / str(relative)
        shutil.copytree(source, destination, dirs_exist_ok=True)
        restored_dirs += 1

    return {"restored_files": restored_files, "restored_dirs": restored_dirs}


def main() -> None:
    parser = argparse.ArgumentParser(description="長期記憶快照與回退工具")
    subcommands = parser.add_subparsers(dest="command", required=True)

    snapshot_cmd = subcommands.add_parser("snapshot")
    snapshot_cmd.add_argument("--label")

    restore_cmd = subcommands.add_parser("restore")
    restore_cmd.add_argument("--snapshot", required=True)

    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot_dir = create_snapshot(label=args.label)
        print(json.dumps({"snapshot": str(snapshot_dir)}, ensure_ascii=False, indent=2))
        return

    result = restore_snapshot(Path(args.snapshot))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
