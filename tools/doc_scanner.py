#!/usr/bin/env python3
"""
掃描 Python 源碼，量化 docstring 覆蓋率，識別文件債務。

使用 ast 模組解析，只計算「公開項目」：
- 非 `_` 開頭的函式、方法、類別
- dunder 方法（__init__ 等）不計入

CLI 用法：
    uv run python tools/doc_scanner.py                    # JSON 輸出（預設）
    uv run python tools/doc_scanner.py --format text      # 人類可讀報告
    uv run python tools/doc_scanner.py --min-coverage 70  # 只顯示低於門檻的檔案
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "doc-generation.yaml"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    """Per-file scan result."""
    file: str
    module_doc: bool
    public_functions: dict  # {total, documented, missing: [str]}
    public_classes: dict    # {total, documented, missing: [str]}
    coverage_pct: float


# ---------------------------------------------------------------------------
# Core scanning
# ---------------------------------------------------------------------------

def _has_docstring(node: ast.AST) -> bool:
    """Return True if the node has a docstring as its first statement."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
        return False
    body = getattr(node, "body", [])
    if not body:
        return False
    first = body[0]
    return isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)


def _is_public(name: str) -> bool:
    """Return True if name is public (not _-prefixed, not dunder)."""
    return not name.startswith("_")


def scan_file(path: Path) -> ScanResult:
    """Parse a Python file and return its ScanResult."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return ScanResult(
            file=str(path),
            module_doc=False,
            public_functions={"total": 0, "documented": 0, "missing": []},
            public_classes={"total": 0, "documented": 0, "missing": []},
            coverage_pct=0.0,
        )

    module_doc = _has_docstring(tree)

    func_total = func_doc = 0
    func_missing: list[str] = []
    cls_total = cls_doc = 0
    cls_missing: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_public(node.name):
                continue
            func_total += 1
            if _has_docstring(node):
                func_doc += 1
            else:
                func_missing.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if not _is_public(node.name):
                continue
            cls_total += 1
            if _has_docstring(node):
                cls_doc += 1
            else:
                cls_missing.append(node.name)

    total_items = (1 if True else 0) + func_total + cls_total  # module_doc always counts
    documented_items = (1 if module_doc else 0) + func_doc + cls_doc
    coverage_pct = (documented_items / total_items * 100.0) if total_items > 0 else 100.0

    return ScanResult(
        file=str(path),
        module_doc=module_doc,
        public_functions={"total": func_total, "documented": func_doc, "missing": func_missing},
        public_classes={"total": cls_total, "documented": cls_doc, "missing": cls_missing},
        coverage_pct=round(coverage_pct, 1),
    )


# ---------------------------------------------------------------------------
# DocScanner
# ---------------------------------------------------------------------------

class DocScanner:
    def __init__(
        self,
        scan_dirs: list[Path] | None = None,
        exclude_patterns: list[str] | None = None,
        config_path: Path = _CONFIG_PATH,
    ) -> None:
        if scan_dirs is not None:
            self.scan_dirs = scan_dirs
            self.exclude_patterns = exclude_patterns or []
        else:
            cfg = self._load_config(config_path)
            self.scan_dirs = [_PROJECT_ROOT / d for d in cfg.get("scan_dirs", ["hooks", "tools"])]
            self.exclude_patterns = cfg.get("exclude_patterns", [])
        self.config_path = config_path

    def scan(self) -> dict[str, Any]:
        """Scan all configured directories and return the report dict."""
        results: list[ScanResult] = []

        for scan_dir in self.scan_dirs:
            if not scan_dir.exists():
                continue
            for py_file in sorted(scan_dir.glob("*.py")):
                if self._is_excluded(py_file):
                    continue
                results.append(scan_file(py_file))

        return self._build_report(results)

    def format_text(self, report: dict[str, Any], min_coverage: float = 0.0) -> str:
        """Format report as human-readable text."""
        s = report["summary"]
        lines = [
            f"=== Doc Scanner ({datetime.now().strftime('%Y-%m-%d')}) ===",
            f"Coverage: {s['documented_items']}/{s['total_items']} ({s['coverage_pct']}%)  "
            f"Debt: {s['debt_items']} items",
            "",
        ]

        below = {k: v for k, v in report["by_file"].items() if v["coverage_pct"] < min_coverage or min_coverage == 0}
        if any(v["coverage_pct"] < 100 for v in below.values()):
            lines.append(f"BELOW {min_coverage:.0f}%:" if min_coverage > 0 else "ALL FILES:")
            for fname, info in sorted(below.items(), key=lambda x: x[1]["coverage_pct"]):
                missing = info["public_functions"]["missing"] + info["public_classes"]["missing"]
                miss_str = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
                lines.append(f"  {fname:<50} {info['coverage_pct']:5.1f}%  missing: {miss_str}")
            lines.append("")

        # Top debt files
        debt_by_file: dict[str, int] = {}
        for d in report["debt_report"]:
            debt_by_file[d["file"]] = debt_by_file.get(d["file"], 0) + 1
        if debt_by_file:
            lines.append("TOP DEBT FILES:")
            for fname, count in sorted(debt_by_file.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  {fname} — {count} missing")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_excluded(self, path: Path) -> bool:
        name = path.name
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    @staticmethod
    def _load_config(config_path: Path) -> dict:
        if not config_path.exists():
            return {}
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("doc_scanner", {}) if data else {}

    @staticmethod
    def _build_report(results: list[ScanResult]) -> dict[str, Any]:
        total_files = len(results)
        total_items = 0
        documented_items = 0
        debt_report: list[dict] = []
        by_file: dict[str, Any] = {}

        for r in results:
            # Relative path key for display
            try:
                rel = str(Path(r.file).relative_to(_PROJECT_ROOT))
            except ValueError:
                rel = r.file

            t = 1 + r.public_functions["total"] + r.public_classes["total"]
            d = (1 if r.module_doc else 0) + r.public_functions["documented"] + r.public_classes["documented"]
            total_items += t
            documented_items += d

            by_file[rel] = {
                "module_doc": r.module_doc,
                "public_functions": r.public_functions,
                "public_classes": r.public_classes,
                "coverage_pct": r.coverage_pct,
            }

            for fname in r.public_functions["missing"]:
                debt_report.append({"file": rel, "item": fname, "type": "function"})
            for cname in r.public_classes["missing"]:
                debt_report.append({"file": rel, "item": cname, "type": "class"})
            if not r.module_doc:
                debt_report.append({"file": rel, "item": "<module>", "type": "module"})

        coverage_pct = round(documented_items / total_items * 100.0, 1) if total_items > 0 else 100.0

        return {
            "scanned_at": datetime.now().astimezone().isoformat(),
            "config_used": str(_CONFIG_PATH),
            "summary": {
                "total_files": total_files,
                "total_items": total_items,
                "documented_items": documented_items,
                "coverage_pct": coverage_pct,
                "debt_items": len(debt_report),
            },
            "by_file": by_file,
            "debt_report": debt_report,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scan Python docstring coverage.")
    p.add_argument("--format", choices=["json", "text"], default="json", dest="fmt")
    p.add_argument("--min-coverage", type=float, default=0.0, metavar="PCT")
    p.add_argument("--dirs", nargs="+", metavar="DIR", help="Override scan directories")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if args.dirs:
        scanner = DocScanner(scan_dirs=[Path(d) for d in args.dirs], exclude_patterns=[])
    else:
        scanner = DocScanner()

    report = scanner.scan()

    if args.fmt == "json":
        if args.min_coverage > 0:
            report["by_file"] = {
                k: v for k, v in report["by_file"].items()
                if v["coverage_pct"] < args.min_coverage
            }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(scanner.format_text(report, min_coverage=args.min_coverage))


if __name__ == "__main__":
    main()
