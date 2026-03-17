from datetime import datetime, timedelta, timezone
from pathlib import Path

from memory.long_term_memory import DigestLevel, LongTermMemoryConfig, LongTermMemoryManager, SearchFilters


def _local_tmp(name: str) -> Path:
    path = Path("tmp") / "pytest" / name
    if path.exists():
        for item in sorted(path.rglob("*"), reverse=True):
            if item.is_file():
                item.unlink()
            else:
                item.rmdir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_add_digest_generates_structured_summary():
    tmp_path = _local_tmp("memory-summary")
    manager = LongTermMemoryManager(
        LongTermMemoryConfig(
            storage_path=tmp_path / "memory.json",
            backup_path=tmp_path / "expired.jsonl",
        ),
        now_provider=lambda: datetime(2026, 3, 17, tzinfo=timezone.utc),
    )

    record = manager.add_digest(
        level=DigestLevel.DAILY,
        topic="AI Agent",
        messages=[
            "決定採用 Qdrant 作為向量資料庫。",
            "待辦：補上 weekly 摘要與過期清理。",
            "新增每日摘要排程。",
        ],
        session_id="session-1",
    )

    assert record.topic == "AI Agent"
    assert "Qdrant" in record.summary
    assert any("決定" in item or "採用" in item for item in record.decisions)
    assert any("待辦" in item for item in record.open_questions)


def test_similarity_search_meets_threshold():
    tmp_path = _local_tmp("memory-search")
    manager = LongTermMemoryManager(
        LongTermMemoryConfig(storage_path=tmp_path / "memory.json", backup_path=tmp_path / "expired.jsonl"),
        now_provider=lambda: datetime(2026, 3, 17, tzinfo=timezone.utc),
    )
    manager.add_digest(
        level=DigestLevel.DAILY,
        topic="向量檢索",
        messages=[
            "採用 qdrant vector retrieval threshold 作為 long term memory 核心查詢。",
            "qdrant vector retrieval threshold 需支援 multi stage retrieval 與 similarity threshold。",
        ],
        session_id="session-2",
    )

    results = manager.multi_stage_search(
        "qdrant vector retrieval threshold long term memory",
        top_k=3,
    )

    assert results
    assert results[0].score > 0.78
    assert results[0].retrieval_path == ["summary-index", "daily", "raw-messages"]


def test_multi_stage_search_supports_metadata_filters():
    tmp_path = _local_tmp("memory-search-filters")
    manager = LongTermMemoryManager(
        LongTermMemoryConfig(storage_path=tmp_path / "memory.json", backup_path=tmp_path / "expired.jsonl"),
        now_provider=lambda: datetime(2026, 3, 18, tzinfo=timezone.utc),
    )
    manager.add_digest(
        level=DigestLevel.DAILY,
        topic="AI Agent",
        messages=["決定採用 recent memory layer。"],
        session_id="session-keep",
        tags=["daily-digest", "AI"],
        metadata={"taskType": "ai_sysdev", "digestDate": "2026-03-18T08:00:00+00:00"},
    )
    manager.add_digest(
        level=DigestLevel.DAILY,
        topic="AI Agent",
        messages=["這是一筆舊資料。"],
        session_id="session-skip",
        tags=["daily-digest", "AI"],
        metadata={"taskType": "research", "digestDate": "2026-02-01T08:00:00+00:00"},
    )

    results = manager.multi_stage_search(
        "AI Agent recent memory layer",
        top_k=5,
        filters=SearchFilters(
            topic="AI Agent",
            task_type="ai_sysdev",
            tags=["AI"],
            start_date="2026-03-01",
            end_date="2026-03-31",
        ),
    )

    assert len(results) == 1
    assert results[0].record.metadata["taskType"] == "ai_sysdev"
    assert results[0].retrieval_path == ["summary-index", "metadata-filter", "daily", "raw-messages"]


def test_expire_records_removes_outdated_daily_and_keeps_monthly():
    tmp_path = _local_tmp("memory-expiry")
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    manager = LongTermMemoryManager(
        LongTermMemoryConfig(storage_path=tmp_path / "memory.json", backup_path=tmp_path / "expired.jsonl"),
        now_provider=lambda: now,
    )
    daily = manager.add_digest(
        level=DigestLevel.DAILY,
        topic="Daily",
        messages=["daily digest"],
        session_id="session-daily",
    )
    monthly = manager.add_digest(
        level=DigestLevel.MONTHLY,
        topic="Monthly",
        messages=["monthly digest"],
        session_id="session-monthly",
    )
    daily.expires_at = (now - timedelta(days=1)).isoformat()
    monthly.expires_at = None
    manager.save()

    expired = manager.expire_records(now=now)

    assert [item.id for item in expired] == [daily.id]
    assert [item.id for item in manager.records] == [monthly.id]
    backup_text = (tmp_path / "expired.jsonl").read_text(encoding="utf-8")
    assert daily.id in backup_text
