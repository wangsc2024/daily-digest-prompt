import shutil
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.long_term_memory import (  # noqa: E402
    compress_continuity_runs,
    compress_research_registry,
    maintain_long_term_memory,
)


def _make_local_tmp(name: str) -> Path:
    path = REPO_ROOT / "tmp" / "pytest" / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_compress_research_registry_archives_old_entries():
    registry = {
        "entries": [
            {
                "date": "2026-03-01",
                "task_type": "ai_sysdev",
                "topic": "Old topic A",
                "kb_note_title": "A note",
            },
            {
                "date": "2026-03-05",
                "task_type": "tech_research",
                "topic": "Old topic B",
                "kb_note_title": "B note",
            },
            {
                "date": "2026-03-16",
                "task_type": "ai_sysdev",
                "topic": "Fresh topic",
                "kb_note_title": "Fresh note",
            },
        ],
        "summary": {"total": 3, "last_updated": "2026-03-16", "recent_3d_topics": []},
    }

    updated = compress_research_registry(registry, today=date(2026, 3, 17), keep_days=7)

    assert len(updated["entries"]) == 1
    assert updated["entries"][0]["topic"] == "Fresh topic"
    assert len(updated["archived_summaries"]) == 1
    archived = updated["archived_summaries"][0]
    assert archived["total_topics"] == 2
    assert archived["domains"] == {"ai_sysdev": 1, "tech_research": 1}
    assert updated["summary"]["total"] == 1


def test_compress_continuity_runs_keeps_recent_window():
    payload = {
        "task_key": "ai_sysdev",
        "max_runs": 5,
        "runs": [
            {
                "topic": f"topic-{index}",
                "status": "completed" if index != 1 else "failed",
                "key_findings": f"finding-{index} keyword-{index}",
                "next_suggested_angle": f"angle-{index}",
            }
            for index in range(8)
        ],
    }

    updated = compress_continuity_runs(payload)

    assert len(updated["runs"]) == 5
    assert updated["runs"][0]["topic"] == "topic-3"
    assert len(updated["compressed_history"]) == 1
    summary = updated["compressed_history"][0]["runs_1_to_3"]
    assert summary["topics_covered"] == ["topic-0", "topic-1", "topic-2"]
    assert summary["success_rate"] == round(2 / 3, 4)


def test_maintain_long_term_memory_writes_back_files():
    tmp_path = _make_local_tmp("long_term_memory")
    registry_path = tmp_path / "research-registry.json"
    continuity_dir = tmp_path / "continuity"
    continuity_dir.mkdir()

    registry_path.write_text(
        """
{
  "entries": [
    {"date": "2026-03-01", "task_type": "ai_sysdev", "topic": "old"},
    {"date": "2026-03-17", "task_type": "ai_sysdev", "topic": "new"}
  ],
  "summary": {"total": 2, "last_updated": "2026-03-17", "recent_3d_topics": []}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (continuity_dir / "auto-task-ai_sysdev.json").write_text(
        """
{
  "task_key": "ai_sysdev",
  "max_runs": 2,
  "runs": [
    {"topic": "a", "status": "completed", "key_findings": "alpha beta gamma"},
    {"topic": "b", "status": "completed", "key_findings": "beta gamma delta"},
    {"topic": "c", "status": "failed", "key_findings": "delta epsilon zeta"}
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    stats = maintain_long_term_memory(
        research_registry_path=registry_path,
        continuity_dir=continuity_dir,
        today=date(2026, 3, 17),
    )

    assert stats["registry_archives"] == 1
    assert stats["continuity_archives"] == 1
    registry = registry_path.read_text(encoding="utf-8")
    continuity = (continuity_dir / "auto-task-ai_sysdev.json").read_text(encoding="utf-8")
    assert "archived_summaries" in registry
    assert "compressed_history" in continuity
