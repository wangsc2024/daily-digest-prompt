from datetime import datetime, timezone

from digest_scheduler import DigestTriggerState, build_scheduler_snapshot, should_trigger_digest
from memory.long_term_memory import DigestLevel, LongTermMemoryConfig


def test_should_trigger_when_message_threshold_reached():
    state = DigestTriggerState(
        last_digest_at={level: "2026-03-17T00:00:00+00:00" for level in DigestLevel},
        message_count_since={DigestLevel.DAILY: 1000, DigestLevel.WEEKLY: 10, DigestLevel.MONTHLY: 10},
    )

    should_trigger, reason = should_trigger_digest(
        DigestLevel.DAILY,
        state,
        config=LongTermMemoryConfig(),
        now=datetime(2026, 3, 17, 8, tzinfo=timezone.utc),
    )

    assert should_trigger is True
    assert reason == "message_count>=1000"


def test_build_scheduler_snapshot_reports_all_levels():
    state = DigestTriggerState(
        last_digest_at={level: None for level in DigestLevel},
        message_count_since={level: 0 for level in DigestLevel},
    )

    snapshot = build_scheduler_snapshot(
        state=state,
        now=datetime(2026, 3, 17, 8, tzinfo=timezone.utc),
    )

    assert set(snapshot["levels"]) == {"daily", "weekly", "monthly"}
    assert snapshot["levels"]["daily"]["should_trigger"] is True
