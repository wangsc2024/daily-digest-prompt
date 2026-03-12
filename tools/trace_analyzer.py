#!/usr/bin/env python3
"""
可觀測性成熟度 Level 4 — 根因分析（P3-B）

掃描 logs/structured/*.jsonl，找出同一 trace_id 下的錯誤鏈，
輸出根因分析報告。

使用方式：
  uv run python tools/trace_analyzer.py
  uv run python tools/trace_analyzer.py --days 7
  uv run python tools/trace_analyzer.py --trace-id abc123
  uv run python tools/trace_analyzer.py --format json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).parent.parent
LOG_DIR = REPO_ROOT / "logs" / "structured"

# ── 根因規則（pattern → suggested_fix）──────────────────────────────────────
ROOT_CAUSE_RULES: list[dict] = [
    {
        "pattern": {"tags_contains": "api-call", "has_error": True},
        "root_cause": "外部 API 呼叫失敗",
        "category": "api_failure",
        "suggested_fix": "確認 API 端點可用性（check-health.ps1）；檢查 circuit-breaker-utils.ps1 斷路狀態",
    },
    {
        "pattern": {"tool": "Bash", "has_error": True, "tags_contains": "python"},
        "root_cause": "Python 腳本執行失敗",
        "category": "script_error",
        "suggested_fix": "查看 error_category 欄位；確認 uv run python 指令格式正確",
    },
    {
        "pattern": {"has_error": True, "phase": "phase2"},
        "root_cause": "Phase 2 子 Agent 失敗",
        "category": "phase2_failure",
        "suggested_fix": "確認對應 prompt 檔存在（prompts/team/todoist-auto-*.md）；查看任務 timeout 設定（config/timeouts.yaml）",
    },
    {
        "pattern": {"tags_contains": "loop-suspected"},
        "root_cause": "偵測到迴圈行為（LoopDetector）",
        "category": "loop_detected",
        "suggested_fix": "查看 state/loop-state-*.json；檢查是否重複讀取相同檔案",
    },
    {
        "pattern": {"tags_contains": "blocked"},
        "root_cause": "Hook 攔截事件",
        "category": "hook_blocked",
        "suggested_fix": "查看 hooks/query_logs.py --blocked 取得詳細攔截記錄",
    },
    {
        "pattern": {"has_error": True, "tool": "Write"},
        "root_cause": "檔案寫入失敗",
        "category": "write_error",
        "suggested_fix": "確認目標路徑存在且有寫入權限；排除 pre_write_guard.py 攔截",
    },
]


def _iter_jsonl(path: Path) -> Iterator[dict]:
    """逐行解析 JSONL，跳過無效行。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass


def _load_recent_entries(days: int) -> list[dict]:
    """讀取最近 N 天的日誌記錄。"""
    entries = []
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=i)
        log_file = LOG_DIR / f"{d.isoformat()}.jsonl"
        if log_file.exists():
            entries.extend(_iter_jsonl(log_file))
    return entries


def _match_rule(entry: dict, pattern: dict) -> bool:
    """判斷記錄是否符合規則模式。"""
    for key, value in pattern.items():
        if key == "tags_contains":
            tags = entry.get("tags", [])
            if value not in tags:
                return False
        elif entry.get(key) != value:
            return False
    return True


def _classify_entry(entry: dict) -> dict | None:
    """對記錄套用根因規則，回傳第一個命中的規則。"""
    for rule in ROOT_CAUSE_RULES:
        if _match_rule(entry, rule["pattern"]):
            return rule
    return None


def _infer_phase(trace_entries: list[dict]) -> list[str]:
    """從 trace 記錄中提取受影響的 phase 列表。"""
    phases = sorted({e.get("phase", "") for e in trace_entries if e.get("phase")})
    return phases


def analyze_trace(trace_id: str, entries: list[dict]) -> dict:
    """
    分析單一 trace_id 的錯誤鏈。

    Returns:
        {
            "trace_id": str,
            "total_entries": int,
            "error_count": int,
            "affected_phases": list[str],
            "root_cause": str,
            "category": str,
            "suggested_fix": str,
            "error_entries": list[dict],
        }
    """
    error_entries = [e for e in entries if e.get("has_error") or "loop-suspected" in e.get("tags", []) or "blocked" in e.get("tags", [])]
    affected_phases = _infer_phase(entries)

    if not error_entries:
        return {
            "trace_id": trace_id,
            "total_entries": len(entries),
            "error_count": 0,
            "affected_phases": affected_phases,
            "root_cause": "無錯誤",
            "category": "healthy",
            "suggested_fix": "",
            "error_entries": [],
        }

    # 找第一個命中的規則（按時間序，取最早的錯誤）
    root_cause = "未知錯誤"
    category = "unknown"
    suggested_fix = "查看完整日誌取得更多資訊"
    matched_rule = None

    for entry in sorted(error_entries, key=lambda e: e.get("ts", "")):
        rule = _classify_entry(entry)
        if rule:
            matched_rule = rule
            break

    if matched_rule:
        root_cause = matched_rule["root_cause"]
        category = matched_rule["category"]
        suggested_fix = matched_rule["suggested_fix"]

    # 壓縮 error_entries（只保留關鍵欄位，避免輸出過長）
    compact_errors = [
        {
            "ts": e.get("ts", ""),
            "phase": e.get("phase", ""),
            "agent": e.get("agent", ""),
            "tool": e.get("tool", ""),
            "tags": e.get("tags", []),
            "error_category": e.get("error_category", ""),
        }
        for e in error_entries[:5]  # 最多顯示 5 筆
    ]

    return {
        "trace_id": trace_id,
        "total_entries": len(entries),
        "error_count": len(error_entries),
        "affected_phases": affected_phases,
        "root_cause": root_cause,
        "category": category,
        "suggested_fix": suggested_fix,
        "error_entries": compact_errors,
    }


def run_analysis(days: int = 3, trace_id_filter: str | None = None) -> dict:
    """
    執行根因分析，回傳摘要報告。

    Returns:
        {
            "analyzed_days": int,
            "total_traces": int,
            "error_traces": int,
            "healthy_traces": int,
            "top_issues": list[dict],
            "traces": list[dict],
        }
    """
    entries = _load_recent_entries(days)

    # 依 trace_id 分組（空 trace_id 的記錄跳過）
    trace_groups: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        tid = entry.get("trace_id", "")
        if not tid:
            continue
        trace_groups[tid].append(entry)

    if trace_id_filter:
        trace_groups = {k: v for k, v in trace_groups.items() if k == trace_id_filter}

    results = []
    for tid, trace_entries in trace_groups.items():
        analysis = analyze_trace(tid, trace_entries)
        results.append(analysis)

    error_traces = [r for r in results if r["category"] != "healthy"]
    healthy_traces = [r for r in results if r["category"] == "healthy"]

    # Top issues：依 category 聚合
    category_counts: dict[str, int] = defaultdict(int)
    category_fixes: dict[str, str] = {}
    for r in error_traces:
        cat = r["category"]
        category_counts[cat] += 1
        category_fixes[cat] = r["suggested_fix"]

    top_issues = [
        {
            "category": cat,
            "count": count,
            "root_cause": next(
                r["root_cause"] for r in error_traces if r["category"] == cat
            ),
            "suggested_fix": category_fixes[cat],
        }
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1])
    ]

    return {
        "analyzed_days": days,
        "total_traces": len(results),
        "error_traces": len(error_traces),
        "healthy_traces": len(healthy_traces),
        "top_issues": top_issues,
        "traces": sorted(results, key=lambda r: r["error_count"], reverse=True),
    }


def format_text_report(report: dict) -> str:
    """格式化純文字輸出（供 check-health.ps1 嵌入）。"""
    lines = []
    lines.append(f"  分析範圍：近 {report['analyzed_days']} 天")
    lines.append(f"  Trace 總數：{report['total_traces']}（異常：{report['error_traces']}，健康：{report['healthy_traces']}）")

    if report["top_issues"]:
        lines.append("\n  ── 前三大問題類別 ──")
        for issue in report["top_issues"][:3]:
            lines.append(f"  [{issue['count']}次] {issue['root_cause']} ({issue['category']})")
            lines.append(f"       建議：{issue['suggested_fix']}")
    else:
        lines.append("  ✓ 無異常 trace")

    if report["traces"]:
        error_only = [t for t in report["traces"] if t["category"] != "healthy"]
        if error_only:
            lines.append("\n  ── 異常 Trace 列表 ──")
            for t in error_only[:5]:
                phases = "/".join(t["affected_phases"]) or "—"
                lines.append(f"  {t['trace_id'][:12]} | {phases} | {t['root_cause']} ({t['error_count']} 錯誤)")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="可觀測性 Level 4 根因分析（P3-B）")
    parser.add_argument("--days", type=int, default=3, help="分析最近 N 天（預設 3）")
    parser.add_argument("--trace-id", help="只分析特定 trace_id")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    report = run_analysis(days=args.days, trace_id_filter=args.trace_id)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("\n[根因分析]")
        print(format_text_report(report))

    # 退出碼：有異常 trace 則 1，否則 0
    sys.exit(1 if report["error_traces"] > 0 else 0)


if __name__ == "__main__":
    main()
