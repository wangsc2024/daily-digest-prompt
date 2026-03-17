"""Demo for daily -> digest -> vectorize -> cross-session retrieval."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from digest_scheduler import DigestTriggerState, should_trigger_digest
from memory.long_term_memory import DigestLevel, LongTermMemoryConfig, LongTermMemoryManager


def main() -> None:
    manager = LongTermMemoryManager(
        LongTermMemoryConfig(
            storage_path=Path("tmp/demo_long_term_memory.json"),
            backup_path=Path("tmp/demo_long_term_memory_expired.jsonl"),
            retrieval_similarity_threshold=0.4,
        ),
        now_provider=lambda: datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
    )

    messages = [
        "使用者要求優化 long term memory，並加入 daily weekly monthly digest 與 scheduler backup。",
        "決定先保留現有 knowledge-base-search，相容既有 digest sync 與 multi stage retrieval。",
        "待辦：建立 scheduler、Prompt 樣板、過期清理與備份流程。",
    ]
    record = manager.add_digest(
        level=DigestLevel.DAILY,
        topic="Long-Term Memory",
        messages=messages,
        session_id="demo-session-001",
        tags=["demo", "memory"],
    )
    print(f"[1] 已新增摘要: {record.id} / {record.summary}")

    state = DigestTriggerState(
        last_digest_at={
            DigestLevel.DAILY: "2026-03-16T08:00:00+00:00",
            DigestLevel.WEEKLY: "2026-03-10T08:00:00+00:00",
            DigestLevel.MONTHLY: "2026-02-01T08:00:00+00:00",
        },
        message_count_since={
            DigestLevel.DAILY: 1200,
            DigestLevel.WEEKLY: 1200,
            DigestLevel.MONTHLY: 1200,
        },
    )
    should_trigger, reason = should_trigger_digest(DigestLevel.DAILY, state)
    print(f"[2] 每日摘要觸發: {should_trigger} ({reason})")

    results = manager.multi_stage_search(
        "daily weekly monthly digest scheduler backup",
        top_k=3,
    )
    print("[3] 跨會話檢索結果:")
    if not results:
        print("  - 無命中結果")
    for item in results:
        print(f"  - score={item.score:.3f} level={item.record.level.value} topic={item.record.topic}")
        print(f"    retrieval_path={item.retrieval_path}")


if __name__ == "__main__":
    main()
