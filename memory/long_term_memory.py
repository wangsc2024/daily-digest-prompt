"""Long-term memory primitives for multi-level digest storage and retrieval."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class DigestLevel(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if token]


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(left[token] * right.get(token, 0.0) for token in left)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def redact_sensitive_text(text: str) -> str:
    patterns = [
        (r"\b09\d{8}\b", "[REDACTED_PHONE]"),
        (r"\b\d{3,4}-\d{6,8}\b", "[REDACTED_PHONE]"),
        (r"\b[A-Z][12]\d{8}\b", "[REDACTED_TW_ID]"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_ID]"),
    ]
    sanitized = text
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


class LocalEmbeddingModel:
    """Deterministic local embedder for tests and offline execution."""

    def __init__(self, model_name: str = "local-token-v1") -> None:
        self.model_name = model_name

    def embed(self, text: str) -> dict[str, float]:
        tokens = _tokenize(text)
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        return {token: count / total for token, count in counts.items()}


@dataclass
class EmbeddingProviderConfig:
    provider: str = "local"
    model: str = "local-token-v1"
    dimension: int = 0
    api_base: str | None = None
    api_key_env: str | None = None
    estimated_cost_per_1k_tokens_usd: float = 0.0
    monthly_cost_limit_usd: float = 15.0
    current_month_cost_usd: float = 0.0


@dataclass
class LongTermMemoryConfig:
    storage_path: Path = Path("data/long_term_memory_optimized.json")
    backup_path: Path = Path("backups/long_term_memory_expired.jsonl")
    summary_prompt_path: Path = Path("prompt_templates/daily_digest_prompt.txt")
    embedding: EmbeddingProviderConfig = field(default_factory=EmbeddingProviderConfig)
    retention_days: dict[DigestLevel, int | None] = field(
        default_factory=lambda: {
            DigestLevel.DAILY: 30,
            DigestLevel.WEEKLY: 90,
            DigestLevel.MONTHLY: None,
        }
    )
    trigger_rules: dict[DigestLevel, dict[str, int]] = field(
        default_factory=lambda: {
            DigestLevel.DAILY: {"hours": 24, "max_messages": 1000},
            DigestLevel.WEEKLY: {"hours": 24 * 7, "max_messages": 7000},
            DigestLevel.MONTHLY: {"hours": 24 * 30, "max_messages": 30000},
        }
    )
    retrieval_similarity_threshold: float = 0.78


@dataclass
class MemoryRecord:
    id: str
    level: DigestLevel
    title: str
    topic: str
    summary: str
    key_events: list[str]
    decisions: list[str]
    open_questions: list[str]
    source_session_ids: list[str]
    raw_messages: list[str]
    tags: list[str]
    language: str
    created_at: str
    updated_at: str
    expires_at: str | None
    embedding_text: str
    embedding: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    record: MemoryRecord
    score: float
    retrieval_path: list[str]


@dataclass
class SearchFilters:
    topic: str | None = None
    task_type: str | None = None
    tags: list[str] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None


class LongTermMemoryManager:
    def __init__(
        self,
        config: LongTermMemoryConfig | None = None,
        *,
        embedder: LocalEmbeddingModel | None = None,
        now_provider=utc_now,
    ) -> None:
        self.config = config or LongTermMemoryConfig()
        self.embedder = embedder or LocalEmbeddingModel(self.config.embedding.model)
        self.now_provider = now_provider
        self.records: list[MemoryRecord] = []
        self._token_index: dict[str, set[int]] = {}
        self._topic_index: dict[str, set[int]] = {}
        self._task_type_index: dict[str, set[int]] = {}
        self._tag_index: dict[str, set[int]] = {}
        self._date_index: list[datetime | None] = []
        self._load()

    def _load(self) -> None:
        if not self.config.storage_path.exists():
            self.records = []
            return
        payload = json.loads(self.config.storage_path.read_text(encoding="utf-8"))
        self.records = [
            MemoryRecord(
                id=item["id"],
                level=DigestLevel(item["level"]),
                title=item["title"],
                topic=item["topic"],
                summary=item["summary"],
                key_events=list(item.get("key_events", [])),
                decisions=list(item.get("decisions", [])),
                open_questions=list(item.get("open_questions", [])),
                source_session_ids=list(item.get("source_session_ids", [])),
                raw_messages=list(item.get("raw_messages", [])),
                tags=list(item.get("tags", [])),
                language=item.get("language", "zh-TW"),
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                expires_at=item.get("expires_at"),
                embedding_text=item["embedding_text"],
                embedding=dict(item.get("embedding", {})),
                metadata=dict(item.get("metadata", {})),
            )
            for item in payload.get("records", [])
        ]
        self._rebuild_indexes()

    def save(self) -> None:
        self.config.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "records": [asdict(record) | {"level": record.level.value} for record in self.records],
            "embedding": asdict(self.config.embedding),
        }
        self.config.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _rebuild_indexes(self) -> None:
        self._token_index = {}
        self._topic_index = {}
        self._task_type_index = {}
        self._tag_index = {}
        self._date_index = []
        for index, record in enumerate(self.records):
            self._index_record(index, record)

    def _index_bucket(self, mapping: dict[str, set[int]], key: str | None, index: int) -> None:
        normalized = str(key or "").strip().lower()
        if not normalized:
            return
        mapping.setdefault(normalized, set()).add(index)

    def _record_datetime(self, record: MemoryRecord) -> datetime | None:
        candidates = [
            record.metadata.get("digestDate"),
            record.metadata.get("created_at"),
            record.created_at,
            record.updated_at,
        ]
        for value in candidates:
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
        return None

    def _index_record(self, index: int, record: MemoryRecord) -> None:
        for token in set(_tokenize(record.embedding_text)):
            self._token_index.setdefault(token, set()).add(index)
        self._index_bucket(self._topic_index, record.topic, index)
        self._index_bucket(self._task_type_index, record.metadata.get("taskType"), index)
        for tag in record.tags:
            self._index_bucket(self._tag_index, tag, index)
        self._date_index.append(self._record_datetime(record))

    def _parse_filter_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _match_filters(self, index: int, filters: SearchFilters) -> bool:
        record = self.records[index]
        if filters.topic and record.topic.lower() != filters.topic.strip().lower():
            return False
        record_task_type = str(record.metadata.get("taskType") or "").strip().lower()
        if filters.task_type and record_task_type != filters.task_type.strip().lower():
            return False
        if filters.tags:
            record_tags = {tag.lower() for tag in record.tags}
            if not set(tag.strip().lower() for tag in filters.tags).issubset(record_tags):
                return False
        record_dt = self._date_index[index]
        start_dt = self._parse_filter_date(filters.start_date)
        end_dt = self._parse_filter_date(filters.end_date)
        if start_dt and (record_dt is None or record_dt < start_dt):
            return False
        if end_dt and (record_dt is None or record_dt > end_dt.replace(hour=23, minute=59, second=59)):
            return False
        return True

    def _candidate_indexes(self, query: str, filters: SearchFilters) -> set[int]:
        candidates: set[int] = set()
        query_tokens = set(_tokenize(redact_sensitive_text(query)))
        for token in query_tokens:
            candidates.update(self._token_index.get(token, set()))
        if filters.topic:
            topic_matches = self._topic_index.get(filters.topic.strip().lower(), set())
            candidates = topic_matches if not candidates else candidates & topic_matches
        if filters.task_type:
            task_matches = self._task_type_index.get(filters.task_type.strip().lower(), set())
            candidates = task_matches if not candidates else candidates & task_matches
        for tag in filters.tags:
            tag_matches = self._tag_index.get(tag.strip().lower(), set())
            candidates = tag_matches if not candidates else candidates & tag_matches
        if not candidates:
            candidates = set(range(len(self.records)))
        return {index for index in candidates if self._match_filters(index, filters)}

    def _expiry_for(self, level: DigestLevel, now: datetime) -> str | None:
        retention = self.config.retention_days[level]
        if retention is None:
            return None
        return (now + timedelta(days=retention)).isoformat()

    def _build_embedding_text(
        self,
        topic: str,
        summary: str,
        key_events: list[str],
        decisions: list[str],
        open_questions: list[str],
    ) -> str:
        parts = [topic, summary, " ".join(key_events), " ".join(decisions), " ".join(open_questions)]
        return redact_sensitive_text("\n".join(part for part in parts if part).strip())

    def _generate_summary(
        self,
        *,
        level: DigestLevel,
        topic: str,
        messages: list[str],
        language: str,
    ) -> dict[str, Any]:
        sanitized = [redact_sensitive_text(item.strip()) for item in messages if item.strip()]
        condensed = sanitized[:12]
        summary = "；".join(condensed[:3]) if condensed else "無對話內容"
        key_events = condensed[:4]
        decisions = [item for item in condensed if "決定" in item or "採用" in item][:3]
        open_questions = [item for item in condensed if "待辦" in item or "未解" in item or "TODO" in item][:3]
        return {
            "title": f"{level.value.title()} Digest - {topic}",
            "summary": summary,
            "key_events": key_events,
            "decisions": decisions,
            "open_questions": open_questions,
            "language": language,
        }

    def add_digest(
        self,
        *,
        level: DigestLevel,
        topic: str,
        messages: list[str],
        session_id: str,
        language: str = "zh-TW",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        auto_save: bool = True,
    ) -> MemoryRecord:
        now = self.now_provider()
        generated = self._generate_summary(level=level, topic=topic, messages=messages, language=language)
        embedding_text = self._build_embedding_text(
            topic,
            generated["summary"],
            generated["key_events"],
            generated["decisions"],
            generated["open_questions"],
        )
        record = MemoryRecord(
            id=f"{level.value}-{int(now.timestamp())}-{len(self.records) + 1}",
            level=level,
            title=generated["title"],
            topic=topic,
            summary=generated["summary"],
            key_events=generated["key_events"],
            decisions=generated["decisions"],
            open_questions=generated["open_questions"],
            source_session_ids=[session_id],
            raw_messages=[redact_sensitive_text(item) for item in messages],
            tags=list(dict.fromkeys((tags or []) + [level.value, topic])),
            language=language,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            expires_at=self._expiry_for(level, now),
            embedding_text=embedding_text,
            embedding=self.embedder.embed(embedding_text),
            metadata=metadata or {},
        )
        self.records.append(record)
        self._index_record(len(self.records) - 1, record)
        if auto_save:
            self.save()
        return record

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_score: float | None = None,
        levels: list[DigestLevel] | None = None,
        filters: SearchFilters | None = None,
    ) -> list[SearchResult]:
        self.expire_records()
        query_embedding = self.embedder.embed(redact_sensitive_text(query))
        min_score = self.config.retrieval_similarity_threshold if min_score is None else min_score
        coarse: list[SearchResult] = []
        allowed = set(levels or list(DigestLevel))
        filters = filters or SearchFilters()
        for index in self._candidate_indexes(query, filters):
            record = self.records[index]
            if record.level not in allowed:
                continue
            score = _cosine_similarity(query_embedding, record.embedding)
            if score >= min_score:
                coarse.append(SearchResult(record=record, score=score, retrieval_path=[record.level.value]))
        coarse.sort(key=lambda item: item.score, reverse=True)
        return coarse[:top_k]

    def multi_stage_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> list[SearchResult]:
        coarse = self.search(
            query,
            top_k=top_k,
            levels=[DigestLevel.MONTHLY, DigestLevel.WEEKLY, DigestLevel.DAILY],
            filters=filters,
        )
        enriched: list[SearchResult] = []
        for item in coarse:
            retrieval_path = ["summary-index"]
            if filters and any([filters.task_type, filters.topic, filters.tags, filters.start_date, filters.end_date]):
                retrieval_path.append("metadata-filter")
            retrieval_path.extend([item.record.level.value, "raw-messages"])
            enriched.append(SearchResult(record=item.record, score=item.score, retrieval_path=retrieval_path))
        return enriched

    def expire_records(self, *, now: datetime | None = None) -> list[MemoryRecord]:
        now = now or self.now_provider()
        kept: list[MemoryRecord] = []
        expired: list[MemoryRecord] = []
        for record in self.records:
            if record.expires_at and datetime.fromisoformat(record.expires_at) <= now:
                expired.append(record)
            else:
                kept.append(record)
        if expired:
            self._backup_expired(expired)
            self.records = kept
            self._rebuild_indexes()
            self.save()
        return expired

    def _backup_expired(self, records: list[MemoryRecord]) -> None:
        self.config.backup_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.backup_path.open("a", encoding="utf-8") as handle:
            for record in records:
                payload = asdict(record) | {"level": record.level.value, "backup_reason": "expired"}
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def estimate_embedding_cost(self, token_count: int) -> float:
        return (token_count / 1000) * self.config.embedding.estimated_cost_per_1k_tokens_usd

    def can_embed(self, token_count: int) -> bool:
        projected = self.config.embedding.current_month_cost_usd + self.estimate_embedding_cost(token_count)
        return projected <= self.config.embedding.monthly_cost_limit_usd

    def export_records(self) -> list[dict[str, Any]]:
        return [asdict(record) | {"level": record.level.value} for record in self.records]
