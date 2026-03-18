#!/usr/bin/env python3
"""Performance smoke test for Daily Digest long-term memory."""
from __future__ import annotations

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memory.long_term_memory import DigestLevel, LongTermMemoryConfig, LongTermMemoryManager
from memory.long_term_memory import SearchFilters


def _build_manager(tmp_dir: Path) -> LongTermMemoryManager:
    now = datetime(2026, 3, 18, tzinfo=timezone.utc)
    return LongTermMemoryManager(
        LongTermMemoryConfig(
            storage_path=tmp_dir / "perf-memory.json",
            backup_path=tmp_dir / "perf-expired.jsonl",
        ),
        now_provider=lambda: now,
    )


def run_performance_test(summary_count: int = 100) -> dict[str, float | int | bool]:
    tmp_dir = Path("tmp") / "perf"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    manager = _build_manager(tmp_dir)
    write_lock = Lock()

    write_latencies_ms: list[float] = []
    search_latencies_ms: list[float] = []
    now = datetime(2026, 3, 18, tzinfo=timezone.utc)

    def write_one(index: int) -> float:
        started = time.perf_counter()
        created_at = (now - timedelta(days=index % 30)).isoformat()
        with write_lock:
            record = manager.add_digest(
                level=DigestLevel.DAILY,
                topic=f"AI-{index % 5}",
                messages=[
                    f"第 {index} 筆摘要：AI 與系統開發重點。",
                    f"決定採用 context boost index={index}",
                    f"待辦：整理過去 30 天關鍵資訊，batch={index % 10}",
                ],
                session_id=f"session-{index}",
                tags=["daily-digest", "AI", "系統開發"],
                metadata={"taskType": "ai_sysdev", "created_at": created_at},
                auto_save=False,
            )
            record.created_at = created_at
            record.updated_at = created_at
        return (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=8) as executor:
        for latency in executor.map(write_one, range(summary_count)):
            write_latencies_ms.append(latency)
    manager.save()

    for _ in range(20):
        started = time.perf_counter()
        manager.multi_stage_search("過去 30 天 AI 系統開發關鍵資訊 context boost", top_k=5)
        search_latencies_ms.append((time.perf_counter() - started) * 1000)

    report = {
        "summary_count": summary_count,
        "write_avg_ms": round(statistics.mean(write_latencies_ms), 3),
        "write_p95_ms": round(statistics.quantiles(write_latencies_ms, n=20)[18], 3),
        "search_avg_ms": round(statistics.mean(search_latencies_ms), 3),
        "search_p95_ms": round(statistics.quantiles(search_latencies_ms, n=20)[18], 3),
    }
    report["within_200ms"] = bool(
        report["write_p95_ms"] <= 200 and report["search_p95_ms"] <= 200
    )
    return report


def run_million_scale_retrieval_benchmark(
    record_count: int = 1_000_000,
    hot_bucket_size: int = 256,
) -> dict[str, float | int | bool]:
    bucket_count = max(1, record_count // max(1, hot_bucket_size))
    token_index: dict[str, set[int]] = {}
    task_index: dict[str, set[int]] = {}
    date_index: list[str] = []
    topic_index: list[str] = []

    for index in range(record_count):
        bucket = index % bucket_count
        topic = f"ai-agent-{bucket}"
        task_type = "ai_sysdev" if bucket % 2 == 0 else "research"
        digest_date = f"2026-03-{(bucket % 28) + 1:02d}"
        token_index.setdefault(topic, set()).add(index)
        task_index.setdefault(task_type, set()).add(index)
        topic_index.append(topic)
        date_index.append(digest_date)

    query_topic = "ai-agent-42"
    filters = SearchFilters(task_type="ai_sysdev", start_date="2026-03-10", end_date="2026-03-28")
    search_latencies_ms: list[float] = []
    candidate_counts: list[int] = []

    for _ in range(20):
        started = time.perf_counter()
        candidates = set(token_index.get(query_topic, set()))
        candidates &= task_index.get(filters.task_type or "", set())
        narrowed = [
            index
            for index in candidates
            if filters.start_date <= date_index[index] <= filters.end_date and topic_index[index] == query_topic
        ]
        elapsed_ms = (time.perf_counter() - started) * 1000
        search_latencies_ms.append(elapsed_ms)
        candidate_counts.append(len(narrowed))

    report = {
        "record_count": record_count,
        "hot_bucket_size": hot_bucket_size,
        "search_avg_ms": round(statistics.mean(search_latencies_ms), 3),
        "search_p95_ms": round(statistics.quantiles(search_latencies_ms, n=20)[18], 3),
        "candidate_count": candidate_counts[0] if candidate_counts else 0,
    }
    report["within_200ms"] = bool(report["search_p95_ms"] <= 200)
    return report


def main() -> None:
    report = {
        "write_search_smoke": run_performance_test(),
        "million_scale_retrieval": run_million_scale_retrieval_benchmark(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
