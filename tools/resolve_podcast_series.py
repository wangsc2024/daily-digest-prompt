#!/usr/bin/env python3
"""從 config/podcast.yaml 解析 ntfy 標題用的節目顯示名（名實相符，非 KB 查詢關鍵字）。"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CFG = ROOT / "config" / "podcast.yaml"


def resolve(*, task: str, slug: str, cfg_path: Path) -> str:
    data: dict = {}
    if cfg_path.is_file():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    n = data.get("notification") or {}
    by_task = n.get("series_by_task") or {}
    default = (n.get("series_default") or "知識電台").strip()
    if task and task in by_task:
        return str(by_task[task]).strip()
    s = slug or ""
    if s.startswith("jiaoguang-"):
        return str(by_task.get("podcast_jiaoguangzong") or "淨土學苑").strip()
    return default


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", default="", help="task_key，如 podcast_jiaoguangzong、podcast_create")
    ap.add_argument("--slug", default="", help="本集 slug（例如 jiaoguang-ep1-20260322）")
    ap.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CFG,
        help="podcast.yaml 路徑",
    )
    args = ap.parse_args()
    cfg = args.config if args.config.is_absolute() else ROOT / args.config
    print(resolve(task=args.task.strip(), slug=args.slug.strip(), cfg_path=cfg))


if __name__ == "__main__":
    main()
