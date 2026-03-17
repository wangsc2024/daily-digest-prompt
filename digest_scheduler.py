"""Digest scheduling for daily, weekly, and monthly long-term memory summarization."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from memory.long_term_memory import DigestLevel, LongTermMemoryConfig


@dataclass
class DigestTriggerState:
    last_digest_at: dict[DigestLevel, str | None]
    message_count_since: dict[DigestLevel, int]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def should_trigger_digest(
    level: DigestLevel,
    state: DigestTriggerState,
    *,
    config: LongTermMemoryConfig | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    config = config or LongTermMemoryConfig()
    now = now or datetime.now(timezone.utc)
    rule = config.trigger_rules[level]
    last_digest = _parse_iso(state.last_digest_at.get(level))
    message_count = state.message_count_since.get(level, 0)
    if message_count >= rule["max_messages"]:
        return True, f"message_count>={rule['max_messages']}"
    if last_digest is None:
        return True, "missing_last_digest"
    elapsed_hours = (now - last_digest).total_seconds() / 3600
    if elapsed_hours >= rule["hours"]:
        return True, f"elapsed_hours>={rule['hours']}"
    return False, "within_window"


def build_scheduler_snapshot(
    *,
    state: DigestTriggerState,
    config: LongTermMemoryConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"generated_at": (now or datetime.now(timezone.utc)).isoformat(), "levels": {}}
    for level in DigestLevel:
        should_trigger, reason = should_trigger_digest(level, state, config=config, now=now)
        snapshot["levels"][level.value] = {"should_trigger": should_trigger, "reason": reason}
    return snapshot
