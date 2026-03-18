import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path
import json as jsonlib

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.digest_sync import (  # noqa: E402
    SyncResult,
    build_digest_note,
    flush_sync_queue,
    main,
    search_digest_notes,
    sync_digest_memory,
    sync_note,
    update_digest_memory_state,
)


def _make_local_tmp(name: str) -> Path:
    path = REPO_ROOT / "tmp" / "pytest" / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *, fail_import_times=0):
        self.fail_import_times = fail_import_times
        self.import_calls = 0
        self.search_payload = None

    def get(self, url, timeout):
        return FakeResponse({"status": "ok"})

    def post(self, url, json, timeout):
        if url.endswith("/api/search/retrieve"):
            self.search_payload = json
            return FakeResponse({"items": [{"id": "digest-1"}], "formattedContext": "摘要：test"})
        if url.endswith("/api/search/hybrid"):
            return FakeResponse(
                {
                    "items": [
                        {
                            "id": "existing-note",
                            "metadata": {"digestDate": json.get("query", "").split(" - ")[-1]},
                        }
                    ]
                }
            )
        if url.endswith("/api/import"):
            self.import_calls += 1
            if self.import_calls <= self.fail_import_times:
                return FakeResponse(status_code=500)
            note_id = json["notes"][0].get("id", "new-note")
            return FakeResponse({"message": "Imported 1 notes, 0 failed", "result": {"noteIds": [note_id]}})
        raise AssertionError(url)


def test_build_digest_note_includes_layer_and_topic():
    payload = {
        "last_run": "2026-03-17T08:00:00+08:00",
        "run_count": 12,
        "digest_summary": "今日 AI 與政策摘要",
        "task_type": "ai_sysdev",
        "knowledge": {"total_notes": 42, "top_tags": ["AI", "政策"]},
        "insights": ["重大政策進展"],
        "long_term_memory": {"retention_days": 30},
    }

    note = build_digest_note(payload, now=datetime(2026, 3, 17, tzinfo=timezone.utc))

    assert note["memoryLayer"] == "recent"
    assert note["topic"] == "AI"
    assert note["taskType"] == "ai_sysdev"
    assert note["retrievalHints"] == ["AI", "政策"]
    assert note["digestDate"] == "2026-03-17"
    assert note["importance"] == 0.85
    assert "## 洞察" in note["contentText"]


def test_sync_note_retries_and_updates_existing_note_id():
    session = FakeSession(fail_import_times=1)
    note = {
        "title": "Daily Digest Memory - 2026-03-17",
        "digestDate": "2026-03-17",
        "topic": "AI",
        "contentText": "summary",
    }

    result = sync_note(
        "http://localhost:3000",
        note,
        max_retries=3,
        session=session,
        sleep_seconds=0,
    )

    assert isinstance(result, SyncResult)
    assert result.success is True
    assert result.attempts == 2
    assert result.note_id == "existing-note"


def test_update_digest_memory_state_marks_sync_result():
    payload = {"long_term_memory": {"retention_days": 14}}
    updated = update_digest_memory_state(
        payload,
        SyncResult(success=True, attempts=1, note_id="note-123"),
        synced_at=datetime(2026, 3, 17, tzinfo=timezone.utc),
    )

    assert updated["long_term_memory"]["sync_status"] == "success"
    assert updated["long_term_memory"]["last_note_id"] == "note-123"
    assert updated["long_term_memory"]["retention_days"] == 14


def test_sync_digest_memory_writes_back_state():
    tmp_path = _make_local_tmp("digest_sync")
    digest_path = tmp_path / "digest-memory.json"
    digest_path.write_text(
        """
{
  "last_run": "2026-03-17T08:00:00+08:00",
  "digest_summary": "今日摘要",
  "knowledge": {"top_tags": ["AI"]}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    updated, result = sync_digest_memory(
        digest_path,
        base_url="http://localhost:3000",
        session=FakeSession(),
        sleep_seconds=0,
        now=datetime(2026, 3, 17, tzinfo=timezone.utc),
    )

    assert result.success is True
    assert updated["long_term_memory"]["sync_status"] == "success"
    saved = digest_path.read_text(encoding="utf-8")
    assert "\"last_note_id\": \"existing-note\"" in saved


def test_sync_digest_memory_queues_failed_note():
    tmp_path = _make_local_tmp("digest_sync_queue")
    digest_path = tmp_path / "digest-memory.json"
    queue_path = tmp_path / "queue.json"
    digest_path.write_text(
        """
{
  "last_run": "2026-03-17T08:00:00+08:00",
  "digest_summary": "今日摘要",
  "knowledge": {"top_tags": ["AI"]}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    class AlwaysFailSession(FakeSession):
        def get(self, url, timeout):
            return FakeResponse(status_code=500)

    updated, result = sync_digest_memory(
        digest_path,
        base_url="http://localhost:3000",
        session=AlwaysFailSession(),
        sleep_seconds=0,
        now=datetime(2026, 3, 17, tzinfo=timezone.utc),
        queue_path=queue_path,
        queue_max_items=5,
        flush_batch_size=5,
    )

    assert result.success is False
    assert result.queued is True
    assert result.queue_size == 1
    assert updated["long_term_memory"]["sync_status"] == "queued"
    assert queue_path.exists()


def test_flush_sync_queue_removes_succeeded_items():
    tmp_path = _make_local_tmp("digest_sync_flush")
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        jsonlib.dumps(
            {
                "items": [
                    {"title": "Daily Digest Memory - 2026-03-17", "digestDate": "2026-03-17", "topic": "AI"},
                    {"title": "Daily Digest Memory - 2026-03-18", "digestDate": "2026-03-18", "topic": "AI"},
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    flushed = flush_sync_queue(
        "http://localhost:3000",
        queue_path=queue_path,
        max_retries=2,
        timeout=10,
        session=FakeSession(),
        sleep_seconds=0,
        batch_size=10,
    )

    assert len(flushed) == 2
    assert all(item.success for item in flushed)
    queue_payload = jsonlib.loads(queue_path.read_text(encoding="utf-8"))
    assert queue_payload["items"] == []


def test_search_digest_notes_passes_filters():
    session = FakeSession()

    result = search_digest_notes(
        "http://localhost:3000",
        query="AI 摘要",
        top_k=3,
        topic="AI",
        task_type="ai_sysdev",
        task_tags=["AI", "系統開發"],
        keyword="Claude",
        memory_layer="recent",
        start_date="2026-03-01",
        end_date="2026-03-31",
        recency_half_life_days=45,
        session=session,
    )

    assert result["items"][0]["id"] == "digest-1"
    assert session.search_payload["kind"] == "digest"
    assert session.search_payload["tags"] == ["daily-digest"]
    assert session.search_payload["taskType"] == "ai_sysdev"
    assert session.search_payload["taskTags"] == ["AI", "系統開發"]
    assert session.search_payload["recencyHalfLifeDays"] == 45
    assert session.search_payload["memoryLayer"] == "recent"


def test_build_digest_note_handles_invalid_date_and_missing_tags():
    payload = {
        "last_run": "not-a-date",
        "digest_summary": "",
        "knowledge": {"top_tags": "invalid"},
        "insights": "單一洞察",
        "metadata": {"task_type": "ops"},
    }

    note = build_digest_note(payload, now=datetime(2026, 3, 18, tzinfo=timezone.utc))

    assert len(note["digestDate"]) == 10
    assert note["topic"] == "daily-digest"
    assert note["taskType"] == "ops"
    assert note["retrievalHints"] == []
    assert "（無摘要）" in note["contentText"]


def test_sync_note_returns_failure_after_retries():
    class AlwaysFailSession(FakeSession):
        def get(self, url, timeout):
            return FakeResponse(status_code=500)

    result = sync_note(
        "http://localhost:3000",
        {"title": "Daily Digest Memory - 2026-03-17", "digestDate": "2026-03-17"},
        max_retries=2,
        session=AlwaysFailSession(),
        sleep_seconds=0,
    )

    assert result.success is False
    assert result.attempts == 2
    assert "status=500" in result.message


def test_main_query_mode_prints_json(monkeypatch, capsys):
    def _fake_search(*args, **kwargs):
        return {"items": [{"id": "digest-1"}], "formattedContext": "摘要"}

    monkeypatch.setattr("tools.digest_sync.search_digest_notes", _fake_search)
    monkeypatch.setattr(
        sys,
        "argv",
        ["digest_sync.py", "--query", "AI 摘要", "--task-type", "ai_sysdev", "--task-tags", "AI"],
    )

    main()

    output = jsonlib.loads(capsys.readouterr().out)
    assert output["items"][0]["id"] == "digest-1"


def test_main_sync_mode_prints_sync_result(monkeypatch, capsys):
    tmp_dir = _make_local_tmp("digest-sync-main")
    digest_path = tmp_dir / "digest-memory.json"
    digest_path.write_text("{\"digest_summary\":\"今日摘要\"}\n", encoding="utf-8")

    def _fake_sync(path, *, base_url, max_retries, timeout, queue_path):
        assert path == digest_path
        return (
            {"long_term_memory": {"sync_status": "success"}},
            SyncResult(success=True, attempts=1, note_id="note-1", message="ok"),
        )

    monkeypatch.setattr("tools.digest_sync.sync_digest_memory", _fake_sync)
    monkeypatch.setattr(
        sys,
        "argv",
        ["digest_sync.py", "--digest-memory", str(digest_path), "--base-url", "http://localhost:3000"],
    )

    main()

    output = jsonlib.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["note_id"] == "note-1"
