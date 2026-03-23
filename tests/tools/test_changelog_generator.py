"""Tests for tools/changelog_generator.py — TDD red phase."""
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.changelog_generator import (
    ChangelogGenerator,
    CommitEntry,
    parse_commit_line,
    group_commits,
    load_existing_hashes,
    build_markdown_block,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_changelog(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "CHANGELOG.md"
    p.write_text(content, encoding="utf-8")
    return p


def _fake_git_log(lines: list[str]):
    """Return a mock for subprocess.run that simulates git log output."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = "\n".join(lines) + "\n"
    return result


# ---------------------------------------------------------------------------
# parse_commit_line
# ---------------------------------------------------------------------------

def test_parse_feat_commit():
    entry = parse_commit_line("abc1234 feat: AI 架構治理方案")
    assert entry is not None
    assert entry.commit_type == "feat"
    assert entry.category == "Added"
    assert entry.hash == "abc1234"
    assert "AI 架構治理方案" in entry.message


def test_parse_fix_commit():
    entry = parse_commit_line("bcd2345 fix: Phase 2 結果檔案命名統一")
    assert entry is not None
    assert entry.commit_type == "fix"
    assert entry.category == "Fixed"


def test_parse_breaking_commit():
    entry = parse_commit_line("cde3456 feat!: 破壞性變更說明")
    assert entry is not None
    assert entry.category == "Breaking Changes"


def test_parse_scoped_commit():
    entry = parse_commit_line("def4567 fix(hooks): 修正 CWD 漂移問題")
    assert entry is not None
    assert entry.category == "Fixed"
    assert entry.scope == "hooks"


def test_parse_non_conventional():
    entry = parse_commit_line("efa5678 解決飢餓問題")
    assert entry is not None
    assert entry.category == "Other"
    assert entry.commit_type is None


def test_ignored_prefix_skipped():
    entry = parse_commit_line("fab6789 Merge branch 'main' into feature")
    assert entry is None


# ---------------------------------------------------------------------------
# group_commits
# ---------------------------------------------------------------------------

def test_group_by_type_all_keys():
    entries = [
        parse_commit_line("aaa1111 feat: 新功能"),
        parse_commit_line("bbb2222 fix: 修正問題"),
    ]
    entries = [e for e in entries if e is not None]
    grouped = group_commits(entries)
    assert "Added" in grouped
    assert "Fixed" in grouped
    assert "Changed" in grouped
    assert "Breaking Changes" in grouped
    assert "Other" in grouped


# ---------------------------------------------------------------------------
# load_existing_hashes
# ---------------------------------------------------------------------------

def test_dedup_skips_existing_hash(tmp_path: Path):
    changelog = _make_changelog(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- feat: 舊功能 (`abc1234`)\n",
    )
    hashes = load_existing_hashes(changelog)
    assert "abc1234" in hashes


# ---------------------------------------------------------------------------
# JSON output schema
# ---------------------------------------------------------------------------

def test_json_output_schema(tmp_path: Path):
    gen = ChangelogGenerator(project_root=tmp_path)
    fake_log = ["abc1234 feat: 新功能 A", "bcd2345 fix: 修正 B"]
    with patch("subprocess.run", return_value=_fake_git_log(fake_log)):
        result = gen.generate(since="7d", output_format="json")
    data = json.loads(result)
    for key in ("generated_at", "since", "until", "new_entries_count", "skipped_duplicates", "grouped"):
        assert key in data, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# markdown output
# ---------------------------------------------------------------------------

def test_markdown_output_format(tmp_path: Path):
    gen = ChangelogGenerator(project_root=tmp_path)
    fake_log = ["abc1234 feat: 新功能 A"]
    with patch("subprocess.run", return_value=_fake_git_log(fake_log)):
        result = gen.generate(since="7d", output_format="markdown")
    assert "### Added" in result
    assert "- " in result


def test_build_markdown_block():
    grouped = {
        "Added": [CommitEntry("abc1234", "feat", None, "新功能", "Added")],
        "Fixed": [],
        "Changed": [],
        "Breaking Changes": [],
        "Other": [],
    }
    block = build_markdown_block(grouped)
    assert "### Added" in block
    assert "abc1234" in block
    assert "新功能" in block


# ---------------------------------------------------------------------------
# update_changelog
# ---------------------------------------------------------------------------

def test_update_changelog_inserts_below_added(tmp_path: Path):
    changelog = _make_changelog(
        tmp_path,
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- 舊條目\n",
    )
    gen = ChangelogGenerator(project_root=tmp_path)
    fake_log = ["xyz9999 feat: 全新功能"]
    with patch("subprocess.run", return_value=_fake_git_log(fake_log)):
        gen.update_changelog(since="7d", changelog_path=changelog)
    content = changelog.read_text(encoding="utf-8")
    lines = content.splitlines()
    added_idx = next(i for i, l in enumerate(lines) if l.strip() == "### Added")
    # 新條目應在 ### Added 之後、舊條目之前
    new_idx = next(i for i, l in enumerate(lines) if "全新功能" in l)
    old_idx = next(i for i, l in enumerate(lines) if "舊條目" in l)
    assert added_idx < new_idx < old_idx


def test_dry_run_no_file_modification(tmp_path: Path):
    changelog = _make_changelog(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- 舊條目\n",
    )
    original = changelog.read_text(encoding="utf-8")
    gen = ChangelogGenerator(project_root=tmp_path)
    fake_log = ["xyz9999 feat: 新功能（不應寫入）"]
    with patch("subprocess.run", return_value=_fake_git_log(fake_log)):
        gen.update_changelog(since="7d", changelog_path=changelog, dry_run=True)
    assert changelog.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# since filter
# ---------------------------------------------------------------------------

def test_since_relative_days():
    gen = ChangelogGenerator(project_root=Path("."))
    since_date = gen._resolve_since("7d")
    expected = date.today() - timedelta(days=7)
    assert since_date == expected


# ---------------------------------------------------------------------------
# empty range
# ---------------------------------------------------------------------------

def test_empty_range_returns_zero(tmp_path: Path):
    gen = ChangelogGenerator(project_root=tmp_path)
    with patch("subprocess.run", return_value=_fake_git_log([])):
        result = gen.generate(since="7d", output_format="json")
    data = json.loads(result)
    assert data["new_entries_count"] == 0
    assert data["commit_count"] == 0
