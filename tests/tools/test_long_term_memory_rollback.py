import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.long_term_memory_rollback import create_snapshot, restore_snapshot  # noqa: E402


def _make_local_tmp(name: str) -> Path:
    path = REPO_ROOT / "tmp" / "pytest" / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_snapshot_and_restore_roundtrip():
    tmp_path = _make_local_tmp("long_term_memory_rollback")
    source_root = tmp_path / "workspace"
    source_root.mkdir()

    digest = source_root / "context" / "digest-memory.json"
    registry = source_root / "context" / "research-registry.json"
    continuity = source_root / "context" / "continuity" / "auto-task-ai_sysdev.json"
    digest.parent.mkdir(parents=True, exist_ok=True)
    continuity.parent.mkdir(parents=True, exist_ok=True)
    digest.write_text('{"status":"before"}\n', encoding="utf-8")
    registry.write_text('{"entries":[]}\n', encoding="utf-8")
    continuity.write_text('{"runs":[{"topic":"v1"}]}\n', encoding="utf-8")

    snapshot_dir = create_snapshot(label="test", source_root=source_root)

    digest.write_text('{"status":"after"}\n', encoding="utf-8")
    continuity.write_text('{"runs":[{"topic":"v2"}]}\n', encoding="utf-8")

    result = restore_snapshot(snapshot_dir, target_root=source_root)

    assert result["restored_files"] >= 2
    assert result["restored_dirs"] == 1
    assert '"before"' in digest.read_text(encoding="utf-8")
    assert '"v1"' in continuity.read_text(encoding="utf-8")
