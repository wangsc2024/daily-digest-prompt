#!/usr/bin/env python3
"""
從 git log 解析 Conventional Commits，生成結構化 CHANGELOG 條目。

支援去重（以 7-char short-hash 比對），可直接插入 CHANGELOG.md 的 [Unreleased] 段落。

CLI 用法：
    uv run python tools/changelog_generator.py --since 7d --dry-run
    uv run python tools/changelog_generator.py --since 7d --update-changelog
    uv run python tools/changelog_generator.py --since 2026-03-01 --format json
    uv run python tools/changelog_generator.py --last-n 20 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_COMMIT_TYPE_MAP: dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "docs": "Changed",
    "chore": "Changed",
    "perf": "Changed",
    "test": "Changed",
    "style": "Changed",
    "ci": "Changed",
    "build": "Changed",
}

_IGNORED_PREFIXES = ("Merge", "merge", "wip")

_CATEGORY_ORDER = ["Added", "Changed", "Fixed", "Breaking Changes", "Other"]

# Pattern: <hash> <type>[(<scope>)][!]: <description>
_CONVENTIONAL_RE = re.compile(r"^(\w+)(?:\(([^)]+)\))?(!)?: (.+)$")

# Pattern to extract 7-char hashes already in CHANGELOG: (`abc1234`)
_HASH_IN_CHANGELOG_RE = re.compile(r"`([0-9a-f]{7})`")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CommitEntry:
    hash: str
    commit_type: Optional[str]
    scope: Optional[str]
    description: str
    category: str

    @property
    def message(self) -> str:
        """Full subject: '<type>(<scope>): <description>' or just description."""
        if self.commit_type:
            scope_str = f"({self.scope})" if self.scope else ""
            return f"{self.commit_type}{scope_str}: {self.description}"
        return self.description


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_commit_line(line: str) -> Optional[CommitEntry]:
    """Parse a single git log line into a CommitEntry, or None if ignored."""
    line = line.strip()
    if not line:
        return None

    # Split off hash (first token)
    parts = line.split(" ", 1)
    if len(parts) < 2:
        return None
    commit_hash, subject = parts[0], parts[1]

    # Check ignored prefixes
    for prefix in _IGNORED_PREFIXES:
        if subject.startswith(prefix):
            return None

    # Try Conventional Commit
    m = _CONVENTIONAL_RE.match(subject)
    if m:
        ctype, scope, breaking, desc = m.group(1), m.group(2), m.group(3), m.group(4)
        if breaking:
            category = "Breaking Changes"
        else:
            category = _COMMIT_TYPE_MAP.get(ctype, "Other")
        return CommitEntry(
            hash=commit_hash,
            commit_type=ctype,
            scope=scope,
            description=desc,
            category=category,
        )

    # Non-conventional
    return CommitEntry(
        hash=commit_hash,
        commit_type=None,
        scope=None,
        description=subject,
        category="Other",
    )


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def group_commits(entries: list[CommitEntry]) -> dict[str, list[CommitEntry]]:
    """Group CommitEntry list by category."""
    grouped: dict[str, list[CommitEntry]] = {cat: [] for cat in _CATEGORY_ORDER}
    for entry in entries:
        cat = entry.category if entry.category in grouped else "Other"
        grouped[cat].append(entry)
    return grouped


# ---------------------------------------------------------------------------
# CHANGELOG helpers
# ---------------------------------------------------------------------------

def load_existing_hashes(changelog_path: Path) -> set[str]:
    """Extract all 7-char commit hashes already present in CHANGELOG."""
    if not changelog_path.exists():
        return set()
    content = changelog_path.read_text(encoding="utf-8")
    return set(_HASH_IN_CHANGELOG_RE.findall(content))


def build_markdown_block(grouped: dict[str, list[CommitEntry]]) -> str:
    """Build a markdown string from grouped commits (only non-empty categories)."""
    lines: list[str] = []
    for cat in _CATEGORY_ORDER:
        entries = grouped.get(cat, [])
        if not entries:
            continue
        lines.append(f"### {cat}")
        for e in entries:
            scope_str = f"({e.scope})" if e.scope else ""
            type_str = f"{e.commit_type}{scope_str}: " if e.commit_type else ""
            lines.append(f"- {type_str}{e.description} (`{e.hash}`)")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

class ChangelogGenerator:
    def __init__(self, project_root: Path = _PROJECT_ROOT) -> None:
        self.project_root = project_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        last_n: Optional[int] = None,
        output_format: str = "markdown",
    ) -> str:
        """Generate changelog content and return as string (no file I/O)."""
        raw_lines = self._run_git_log(since=since, until=until, last_n=last_n)
        entries = [e for line in raw_lines if (e := parse_commit_line(line)) is not None]

        since_date = self._resolve_since(since) if since else None
        until_date = self._resolve_until(until) if until else date.today()

        grouped = group_commits(entries)
        new_count = sum(len(v) for v in grouped.values())

        if output_format == "json":
            payload = {
                "generated_at": datetime.now().astimezone().isoformat(),
                "since": since_date.isoformat() if since_date else None,
                "until": until_date.isoformat(),
                "commit_count": len(raw_lines),
                "new_entries_count": new_count,
                "skipped_duplicates": 0,
                "grouped": {
                    cat: [{"hash": e.hash, "message": f"{e.commit_type}: {e.description}" if e.commit_type else e.description}
                          for e in entries_list]
                    for cat, entries_list in grouped.items()
                },
                "markdown_block": build_markdown_block(grouped),
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            return build_markdown_block(grouped)

    def update_changelog(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        last_n: Optional[int] = None,
        changelog_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> dict:
        """Parse git log, deduplicate, and insert new entries into CHANGELOG.md."""
        if changelog_path is None:
            changelog_path = self.project_root / "CHANGELOG.md"

        existing_hashes = load_existing_hashes(changelog_path)
        raw_lines = self._run_git_log(since=since, until=until, last_n=last_n)

        all_entries = [e for line in raw_lines if (e := parse_commit_line(line)) is not None]
        new_entries = [e for e in all_entries if e.hash not in existing_hashes]
        skipped = len(all_entries) - len(new_entries)

        since_date = self._resolve_since(since) if since else None
        until_date = self._resolve_until(until) if until else date.today()
        grouped = group_commits(new_entries)
        markdown_block = build_markdown_block(grouped)

        if not dry_run and markdown_block.strip():
            self._insert_into_changelog(changelog_path, markdown_block)

        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "since": since_date.isoformat() if since_date else None,
            "until": until_date.isoformat(),
            "commit_count": len(raw_lines),
            "new_entries_count": len(new_entries),
            "skipped_duplicates": skipped,
            "grouped": {
                cat: [{"hash": e.hash, "message": e.description} for e in el]
                for cat, el in grouped.items()
            },
            "markdown_block": markdown_block,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_git_log(
        self,
        since: Optional[str],
        until: Optional[str],
        last_n: Optional[int],
    ) -> list[str]:
        """Run git log and return list of raw lines."""
        cmd = ["git", "log", "--format=%h %s"]
        if last_n is not None:
            cmd += [f"-n{last_n}"]
        else:
            if since:
                since_date = self._resolve_since(since)
                cmd += [f"--since={since_date.isoformat()}"]
            if until:
                until_date = self._resolve_until(until)
                cmd += [f"--until={until_date.isoformat()}"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=self.project_root,
        )
        if result.returncode != 0:
            return []
        return [l for l in result.stdout.splitlines() if l.strip()]

    def _resolve_since(self, since: str) -> date:
        """Parse '--since' value: '7d' → date, 'YYYY-MM-DD' → date."""
        if re.match(r"^\d+d$", since):
            days = int(since[:-1])
            return date.today() - timedelta(days=days)
        return date.fromisoformat(since)

    def _resolve_until(self, until: str) -> date:
        return date.fromisoformat(until)

    def _insert_into_changelog(self, changelog_path: Path, markdown_block: str) -> None:
        """Insert markdown_block into CHANGELOG.md after '### Added' under '[Unreleased]'."""
        if not changelog_path.exists():
            changelog_path.write_text(
                f"# Changelog\n\n## [Unreleased]\n\n{markdown_block}\n",
                encoding="utf-8",
            )
            return

        content = changelog_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)

        # Find [Unreleased] section
        unreleased_idx = None
        for i, line in enumerate(lines):
            if "[Unreleased]" in line:
                unreleased_idx = i
                break

        if unreleased_idx is None:
            # Prepend [Unreleased] section
            new_content = f"## [Unreleased]\n\n{markdown_block}\n" + content
            changelog_path.write_text(new_content, encoding="utf-8")
            return

        # Find ### Added within [Unreleased] section
        added_idx = None
        for i in range(unreleased_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("## ") and "[Unreleased]" not in stripped:
                break  # Hit next version section
            if stripped == "### Added":
                added_idx = i
                break

        new_lines = markdown_block.splitlines(keepends=True)
        if not new_lines[-1].endswith("\n"):
            new_lines.append("\n")

        if added_idx is not None:
            # Insert right after ### Added line
            insert_at = added_idx + 1
            lines = lines[:insert_at] + new_lines + lines[insert_at:]
        else:
            # Create ### Added section after [Unreleased]
            insert_at = unreleased_idx + 1
            # Skip blank lines
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            header_lines = ["### Added\n"] + new_lines + ["\n"]
            lines = lines[:insert_at] + header_lines + lines[insert_at:]

        changelog_path.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate CHANGELOG entries from git log (Conventional Commits)."
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--since", default="7d", help="Since date: '7d' or 'YYYY-MM-DD'")
    group.add_argument("--last-n", type=int, metavar="N", help="Last N commits")
    p.add_argument("--until", help="Until date: 'YYYY-MM-DD' (default: today)")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown", dest="fmt")
    p.add_argument("--dry-run", action="store_true", help="Print only, do not write files")
    p.add_argument("--update-changelog", action="store_true", help="Insert into CHANGELOG.md")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    gen = ChangelogGenerator()

    if args.update_changelog:
        result = gen.update_changelog(
            since=args.since if not args.last_n else None,
            until=args.until,
            last_n=args.last_n,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        output = gen.generate(
            since=args.since if not args.last_n else None,
            until=args.until,
            last_n=args.last_n,
            output_format=args.fmt,
        )
        print(output)


if __name__ == "__main__":
    main()
