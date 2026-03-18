#!/usr/bin/env python3
"""
Daily Digest 長期記憶同步工具。

讀取 context/digest-memory.json，建立可檢索的長期記憶筆記，並以重試機制
寫入 knowledge-base-search API。
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIGEST_MEMORY_PATH = REPO_ROOT / "context" / "digest-memory.json"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "long_term_memory.yaml"
DEFAULT_QUEUE_PATH = REPO_ROOT / "state" / "long_term_memory_sync_queue.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _load_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _write_queue(path: Path, items: list[dict[str, Any]]) -> None:
    _write_json(path, {"items": items, "updated_at": datetime.now(timezone.utc).isoformat()})


def _iso_date(value: str | None) -> str:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _infer_topic(payload: dict[str, Any]) -> str:
    knowledge = payload.get("knowledge", {})
    top_tags = knowledge.get("top_tags", [])
    if isinstance(top_tags, list) and top_tags:
        return str(top_tags[0])
    digest_summary = str(payload.get("digest_summary", "")).strip()
    return digest_summary[:24] if digest_summary else "daily-digest"


def build_digest_note(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    last_run = str(payload.get("last_run") or now.isoformat())
    digest_date = _iso_date(last_run)
    retention_days = int(payload.get("long_term_memory", {}).get("retention_days", 30) or 30)
    expires_at = (now + timedelta(days=retention_days)).isoformat()
    insights = payload.get("insights") or []
    if not isinstance(insights, list):
        insights = [str(insights)]
    knowledge = payload.get("knowledge", {})
    top_tags = knowledge.get("top_tags") if isinstance(knowledge, dict) else []
    if not isinstance(top_tags, list):
        top_tags = []
    topic = _infer_topic(payload)
    task_type = str(
        payload.get("task_type")
        or payload.get("long_term_memory", {}).get("task_type")
        or payload.get("metadata", {}).get("task_type")
        or ""
    ).strip()
    insight_lines = [f"- {item}" for item in insights[:5]] if insights else ["- （無）"]
    retrieval_hints = [str(tag) for tag in top_tags[:5]]

    content = "\n".join(
        [
            f"# Daily Digest {digest_date}",
            "",
            "## 摘要",
            str(payload.get("digest_summary") or "（無摘要）"),
            "",
            "## 洞察",
            *insight_lines,
            "",
            "## 記憶指標",
            f"- 執行時間：{last_run}",
            f"- 執行次數：{payload.get('run_count', 0)}",
            f"- 知識庫筆記數：{knowledge.get('total_notes', 0) if isinstance(knowledge, dict) else 0}",
            f"- 主題：{topic}",
            f"- 標籤：{', '.join(map(str, top_tags[:5])) if top_tags else 'daily-digest'}",
        ]
    )

    importance = 0.85 if any("重大" in str(item) for item in insights) else 0.7
    return {
        "title": f"Daily Digest Memory - {digest_date}",
        "contentText": content,
        "tags": ["Daily-Digest-Prompt", "long-term-memory", "daily-digest", *map(str, top_tags[:3])],
        "source": "import",
        "summary": str(payload.get("digest_summary") or "Daily digest memory"),
        "kind": "digest",
        "topic": topic,
        "taskType": task_type or None,
        "retrievalHints": retrieval_hints,
        "digestDate": digest_date,
        "memoryLayer": "recent",
        "importance": importance,
        "expiresAt": expires_at,
        "updatedAt": now.isoformat(),
    }


@dataclass
class SyncResult:
    success: bool
    attempts: int
    note_id: str | None = None
    message: str = ""
    queued: bool = False
    queue_size: int = 0


def update_digest_memory_state(
    payload: dict[str, Any],
    result: SyncResult,
    *,
    synced_at: datetime | None = None,
) -> dict[str, Any]:
    synced_at = synced_at or datetime.now(timezone.utc)
    updated = dict(payload)
    long_term_memory = dict(updated.get("long_term_memory") or {})
    long_term_memory.update(
        {
            "last_sync_at": synced_at.isoformat(),
            "last_note_id": result.note_id,
            "sync_status": "success" if result.success else "failed",
            "memory_layer": "knowledge-base",
            "retention_days": int(long_term_memory.get("retention_days", 30) or 30),
            "queue_size": result.queue_size,
        }
    )
    if result.queued:
        long_term_memory["sync_status"] = "queued"
    updated["long_term_memory"] = long_term_memory
    return updated


def load_sync_settings(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = _load_yaml(config_path)
    queue = config.get("sync_queue", {}) if isinstance(config.get("sync_queue"), dict) else {}
    sync = config.get("sync", {}) if isinstance(config.get("sync"), dict) else {}
    return {
        "queue_path": REPO_ROOT / str(queue.get("path", "state/long_term_memory_sync_queue.json")),
        "max_queue_size": int(queue.get("max_items", 2000) or 2000),
        "flush_batch_size": int(queue.get("flush_batch_size", 20) or 20),
        "timeout": int(sync.get("timeout_seconds", 10) or 10),
        "max_retries": int(sync.get("max_retries", 3) or 3),
    }


def sync_note(
    base_url: str,
    note: dict[str, Any],
    *,
    max_retries: int = 3,
    timeout: int = 10,
    session: requests.Session | None = None,
    sleep_seconds: float = 0.5,
) -> SyncResult:
    session = session or requests.Session()
    title_query = note["title"]
    attempts = 0
    last_error = ""
    for attempt in range(1, max_retries + 1):
        attempts = attempt
        try:
            health = session.get(f"{base_url}/api/health", timeout=timeout)
            health.raise_for_status()

            dedup = session.post(
                f"{base_url}/api/search/hybrid",
                json={"query": title_query, "topK": 3, "topic": note.get("topic")},
                timeout=timeout,
            )
            dedup.raise_for_status()
            items = dedup.json().get("items", [])
            for item in items:
                metadata = item.get("metadata", {})
                if metadata.get("digestDate") == note.get("digestDate"):
                    note["id"] = item.get("id")
                    break

            imported = session.post(
                f"{base_url}/api/import",
                json={"notes": [note], "autoSync": True},
                timeout=timeout,
            )
            imported.raise_for_status()
            body = imported.json()
            note_ids = body.get("result", {}).get("noteIds", [])
            return SyncResult(
                success=True,
                attempts=attempts,
                note_id=note_ids[0] if note_ids else note.get("id"),
                message=body.get("message", "ok"),
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < max_retries:
                time.sleep(sleep_seconds * (2 ** (attempt - 1)))
    return SyncResult(success=False, attempts=attempts, message=last_error)


def enqueue_note(note: dict[str, Any], *, queue_path: Path, max_queue_size: int) -> int:
    queue = _load_queue(queue_path)
    dedup_key = (note.get("digestDate"), note.get("topic"), note.get("title"))
    queue = [
        item
        for item in queue
        if (item.get("digestDate"), item.get("topic"), item.get("title")) != dedup_key
    ]
    queue.append(note)
    if len(queue) > max_queue_size:
        queue = queue[-max_queue_size:]
    _write_queue(queue_path, queue)
    return len(queue)


def flush_sync_queue(
    base_url: str,
    *,
    queue_path: Path,
    max_retries: int,
    timeout: int,
    session: requests.Session | None = None,
    sleep_seconds: float = 0.5,
    batch_size: int = 20,
) -> list[SyncResult]:
    queue = _load_queue(queue_path)
    if not queue:
        return []

    session = session or requests.Session()
    remaining: list[dict[str, Any]] = []
    results: list[SyncResult] = []
    for index, note in enumerate(queue):
        if index >= batch_size:
            remaining.extend(queue[index:])
            break
        result = sync_note(
            base_url,
            note,
            max_retries=max_retries,
            timeout=timeout,
            session=session,
            sleep_seconds=sleep_seconds,
        )
        results.append(result)
        if not result.success:
            remaining.append(note)
    _write_queue(queue_path, remaining)
    return results


def sync_digest_memory(
    digest_memory_path: Path,
    *,
    base_url: str,
    max_retries: int = 3,
    timeout: int = 10,
    session: requests.Session | None = None,
    sleep_seconds: float = 0.5,
    now: datetime | None = None,
    queue_path: Path | None = None,
    queue_max_items: int | None = None,
    flush_batch_size: int | None = None,
) -> tuple[dict[str, Any], SyncResult]:
    settings = load_sync_settings()
    queue_path = queue_path or settings["queue_path"]
    queue_max_items = queue_max_items or settings["max_queue_size"]
    flush_batch_size = flush_batch_size or settings["flush_batch_size"]
    flush_sync_queue(
        base_url,
        queue_path=queue_path,
        max_retries=max_retries,
        timeout=timeout,
        session=session,
        sleep_seconds=sleep_seconds,
        batch_size=flush_batch_size,
    )
    payload = _load_json(digest_memory_path)
    note = build_digest_note(payload, now=now)
    result = sync_note(
        base_url,
        note,
        max_retries=max_retries,
        timeout=timeout,
        session=session,
        sleep_seconds=sleep_seconds,
    )
    if not result.success:
        queue_size = enqueue_note(note, queue_path=queue_path, max_queue_size=queue_max_items)
        result = SyncResult(
            success=False,
            attempts=result.attempts,
            note_id=result.note_id,
            message=result.message,
            queued=True,
            queue_size=queue_size,
        )
    else:
        result.queue_size = len(_load_queue(queue_path))
    updated_payload = update_digest_memory_state(payload, result, synced_at=now)
    _write_json(digest_memory_path, updated_payload)
    return updated_payload, result


def search_digest_notes(
    base_url: str,
    *,
    query: str,
    top_k: int = 5,
    topic: str | None = None,
    task_type: str | None = None,
    task_tags: list[str] | None = None,
    keyword: str | None = None,
    memory_layer: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    recency_half_life_days: int | None = None,
    timeout: int = 10,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    session = session or requests.Session()
    response = session.post(
        f"{base_url}/api/search/retrieve",
        json={
            "query": query,
            "topK": top_k,
            "topic": topic,
            "taskType": task_type,
            "taskTags": task_tags,
            "keyword": keyword,
            "memoryLayer": memory_layer,
            "startDate": start_date,
            "endDate": end_date,
            "recencyHalfLifeDays": recency_half_life_days,
            "tags": ["daily-digest"],
            "kind": "digest",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="同步 Daily Digest 至長期記憶")
    parser.add_argument("--digest-memory", default=str(DEFAULT_DIGEST_MEMORY_PATH))
    parser.add_argument("--base-url", default="http://localhost:3000")
    settings = load_sync_settings()
    parser.add_argument("--max-retries", type=int, default=settings["max_retries"])
    parser.add_argument("--timeout", type=int, default=settings["timeout"])
    parser.add_argument("--queue-path", default=str(settings["queue_path"]))
    parser.add_argument("--flush-queue", action="store_true", help="只嘗試沖刷待同步佇列")
    parser.add_argument("--query", help="改為執行摘要檢索，而非同步")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--topic")
    parser.add_argument("--task-type")
    parser.add_argument("--task-tags", nargs="*")
    parser.add_argument("--keyword")
    parser.add_argument("--memory-layer")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--recency-half-life-days", type=int)
    args = parser.parse_args()

    if args.query:
        result = search_digest_notes(
            args.base_url,
            query=args.query,
            top_k=args.top_k,
            topic=args.topic,
            task_type=args.task_type,
            task_tags=args.task_tags,
            keyword=args.keyword,
            memory_layer=args.memory_layer,
            start_date=args.start_date,
            end_date=args.end_date,
            recency_half_life_days=args.recency_half_life_days,
            timeout=args.timeout,
        )
    elif args.flush_queue:
        flushed = flush_sync_queue(
            args.base_url,
            queue_path=Path(args.queue_path),
            max_retries=args.max_retries,
            timeout=args.timeout,
        )
        result = {
            "flushed": len(flushed),
            "succeeded": sum(1 for item in flushed if item.success),
            "failed": sum(1 for item in flushed if not item.success),
            "queue_size": len(_load_queue(Path(args.queue_path))),
        }
    else:
        _, sync_result = sync_digest_memory(
            Path(args.digest_memory),
            base_url=args.base_url,
            max_retries=args.max_retries,
            timeout=args.timeout,
            queue_path=Path(args.queue_path),
        )
        result = {
            "success": sync_result.success,
            "attempts": sync_result.attempts,
            "note_id": sync_result.note_id,
            "message": sync_result.message,
            "queued": sync_result.queued,
            "queue_size": sync_result.queue_size,
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
