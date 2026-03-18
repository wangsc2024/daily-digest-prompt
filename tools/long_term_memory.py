#!/usr/bin/env python3
"""
長期記憶維護工具。

落地兩個 Daily-Digest-Prompt 的記憶壓縮建議：
1. research-registry.json 超過保留窗格的舊 entries 轉為 archived_summaries
2. auto-task continuity 超過 max_runs 的歷史轉為 compressed_history
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_REGISTRY_PATH = REPO_ROOT / "context" / "research-registry.json"
CONTINUITY_DIR = REPO_ROOT / "context" / "continuity"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_research_findings(entry: dict[str, Any]) -> str | None:
    topic = str(entry.get("topic") or "").strip()
    task_type = str(entry.get("task_type") or "").strip()
    note = str(entry.get("kb_note_title") or "").strip()
    if topic and note:
        return f"{task_type}: {topic} -> {note}"
    if topic:
        return f"{task_type}: {topic}"
    return None


def compress_research_registry(
    registry: dict[str, Any],
    *,
    today: date | None = None,
    keep_days: int = 7,
    max_findings: int = 5,
) -> dict[str, Any]:
    today = today or date.today()
    result = deepcopy(registry)
    entries = list(result.get("entries", []))
    retained: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = list(result.get("archived_summaries", []))
    old_entries: list[dict[str, Any]] = []

    for entry in entries:
        entry_date = _parse_date(str(entry.get("date") or ""))
        if entry_date is None:
            retained.append(entry)
            continue
        if (today - entry_date).days > keep_days:
            old_entries.append(entry)
        else:
            retained.append(entry)

    if old_entries:
        ordered_dates = sorted(
            (_parse_date(str(entry.get("date") or "")) for entry in old_entries),
            key=lambda item: item or today,
        )
        domains = Counter(str(entry.get("task_type") or "unknown") for entry in old_entries)
        findings = []
        for entry in old_entries:
            finding = _extract_research_findings(entry)
            if finding and finding not in findings:
                findings.append(finding)
            if len(findings) >= max_findings:
                break
        summary = {
            "period": f"{ordered_dates[0].isoformat()} to {ordered_dates[-1].isoformat()}",
            "compressed_at": today.isoformat(),
            "total_topics": len(old_entries),
            "domains": dict(sorted(domains.items())),
            "key_findings": findings,
            "source_entry_count": len(old_entries),
        }
        archived.append(summary)

    result["entries"] = retained
    if archived:
        result["archived_summaries"] = archived
    if "summary" in result:
        summary_block = result["summary"]
        summary_block["total"] = len(retained)
        summary_block["last_updated"] = today.isoformat()
        recent_topics = [str(entry.get("topic") or "") for entry in retained[-10:] if entry.get("topic")]
        summary_block["recent_3d_topics"] = recent_topics[::-1]
    return result


def _compact_runs_window(runs: list[dict[str, Any]], window_start: int, window_end: int) -> dict[str, Any]:
    window = runs[window_start:window_end]
    topics = [str(run.get("topic") or "") for run in window if run.get("topic")]
    statuses = [str(run.get("status") or "") for run in window]
    suggested = [str(run.get("next_suggested_angle") or "") for run in window if run.get("next_suggested_angle")]
    keywords = Counter()
    for run in window:
        findings = str(run.get("key_findings") or "")
        for token in findings.replace("（", " ").replace("）", " ").replace("、", " ").split():
            if len(token) >= 4:
                keywords[token] += 1

    completed = sum(status == "completed" for status in statuses)
    return {
        f"runs_{window_start + 1}_to_{window_end}": {
            "topics_covered": topics,
            "success_rate": round(completed / len(window), 4) if window else 0.0,
            "common_angles": [item for item, _ in keywords.most_common(5)],
            "next_suggested_angles": suggested[:3],
        }
    }


def compress_continuity_runs(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    runs = list(result.get("runs", []))
    max_runs = int(result.get("max_runs", 5))
    if len(runs) <= max_runs:
        return result

    overflow = len(runs) - max_runs
    windows = []
    cursor = 0
    while cursor < overflow:
        window_end = min(cursor + max_runs, overflow)
        windows.append(_compact_runs_window(runs, cursor, window_end))
        cursor = window_end

    compressed_history = list(result.get("compressed_history", []))
    compressed_history.extend(windows)
    result["compressed_history"] = compressed_history[-5:]
    result["runs"] = runs[-max_runs:]
    return result


def maintain_long_term_memory(
    *,
    research_registry_path: Path = RESEARCH_REGISTRY_PATH,
    continuity_dir: Path = CONTINUITY_DIR,
    today: date | None = None,
) -> dict[str, int]:
    today = today or date.today()
    stats = {"registry_archives": 0, "continuity_archives": 0}

    if research_registry_path.exists():
        registry = _load_json(research_registry_path)
        updated = compress_research_registry(registry, today=today)
        before = len(registry.get("archived_summaries", []))
        after = len(updated.get("archived_summaries", []))
        _write_json(research_registry_path, updated)
        stats["registry_archives"] = max(0, after - before)

    if continuity_dir.exists():
        for path in continuity_dir.glob("auto-task-*.json"):
            payload = _load_json(path)
            updated = compress_continuity_runs(payload)
            before = len(payload.get("compressed_history", []))
            after = len(updated.get("compressed_history", []))
            if before != after or updated.get("runs") != payload.get("runs"):
                _write_json(path, updated)
            stats["continuity_archives"] += max(0, after - before)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily-Digest 長期記憶維護工具")
    parser.add_argument("--apply", action="store_true", help="實際寫回 research-registry 與 continuity 檔案")
    args = parser.parse_args()

    if args.apply:
        stats = maintain_long_term_memory()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    preview = {
        "research_registry": str(RESEARCH_REGISTRY_PATH),
        "continuity_dir": str(CONTINUITY_DIR),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
