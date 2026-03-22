#!/usr/bin/env python3
"""
Phase 結束預算查核工具（ADR-035）

每個 Phase 完成後由 PS1 腳本呼叫，查核 per-phase 和 per-trace token
是否超過 budget.yaml 設定的警戒與暫停閾值。

使用方式：
  uv run python tools/phase_budget_reporter.py --phase phase1 --trace-id abc123 --format json
  uv run python tools/phase_budget_reporter.py --phase phase2 --trace-id abc --summary
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TOKEN_USAGE_PATH = REPO_ROOT / "state" / "token-usage.json"
BUDGET_YAML_PATH = REPO_ROOT / "config" / "budget.yaml"


def _load_budget_config() -> dict:
    """載入 budget.yaml，失敗時回傳預設值。"""
    try:
        import yaml
        with open(BUDGET_YAML_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {
            "phase_budget": {
                "phase1": 500_000,
                "phase2": 2_000_000,
                "phase3": 200_000,
                "phase2_auto": 800_000,
            },
            "trace_budget": {
                "warn_threshold": 3_000_000,
                "suspend_threshold": 8_000_000,
            },
        }


def _load_token_usage() -> dict:
    """讀取 state/token-usage.json，不存在時回傳空結構。"""
    try:
        with open(TOKEN_USAGE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"daily": {}}


def _get_today_data(usage: dict) -> dict:
    """取得今日的 token 使用資料。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return usage.get("daily", {}).get(today, {})


def check_phase_budget(phase: str, trace_id: str) -> dict:
    """
    查核 per-phase 和 per-trace token 是否超過閾值。

    Args:
        phase: Phase 名稱（如 "phase1", "phase2", "phase2_auto"）
        trace_id: Trace ID（取前 12 字）

    Returns:
        {
            "phase": str,
            "trace_id": str,
            "phase_tokens": float,
            "phase_limit": int,
            "phase_utilization": float,
            "trace_tokens": float,
            "trace_warn_limit": int,
            "trace_suspend_limit": int,
            "trace_utilization": float,
            "warn_phase": bool,
            "warn_trace": bool,
            "suspend_trace": bool,
            "checked_at": str,
        }
    """
    config = _load_budget_config()
    phase_budgets = config.get("phase_budget", {})
    trace_budget = config.get("trace_budget", {})

    phase_limit = phase_budgets.get(phase, phase_budgets.get("default", 1_000_000))
    trace_warn = trace_budget.get("warn_threshold", 3_000_000)
    trace_suspend = trace_budget.get("suspend_threshold", 8_000_000)

    usage = _load_token_usage()
    today_data = _get_today_data(usage)

    # per-phase tokens（ADR-035 schema v3 新增的 phases 欄位）
    phases_data = today_data.get("phases", {})
    phase_entry = phases_data.get(phase, {})
    phase_tokens = phase_entry.get("estimated_tokens", 0.0)

    # per-trace tokens（ADR-035 schema v3 新增的 traces 欄位）
    trace_key = (trace_id or "")[:12]
    traces_data = today_data.get("traces", {})
    trace_entry = traces_data.get(trace_key, {})
    trace_tokens = trace_entry.get("total_tokens", 0.0)

    phase_utilization = phase_tokens / phase_limit if phase_limit > 0 else 0.0
    trace_utilization = trace_tokens / trace_suspend if trace_suspend > 0 else 0.0

    warn_phase = phase_tokens >= phase_limit * 0.80
    warn_trace = trace_tokens >= trace_warn
    suspend_trace = trace_tokens >= trace_suspend

    return {
        "phase": phase,
        "trace_id": trace_key,
        "phase_tokens": round(phase_tokens, 2),
        "phase_limit": phase_limit,
        "phase_utilization": round(phase_utilization, 4),
        "trace_tokens": round(trace_tokens, 2),
        "trace_warn_limit": trace_warn,
        "trace_suspend_limit": trace_suspend,
        "trace_utilization": round(trace_utilization, 4),
        "warn_phase": warn_phase,
        "warn_trace": warn_trace,
        "suspend_trace": suspend_trace,
        "checked_at": datetime.now().astimezone().isoformat(),
    }


def _send_budget_warning(phase: str, result: dict) -> None:
    """超限時發送 ntfy 告警（複用 budget_guard 模式：tempfile + curl）。"""
    try:
        import os
        import tempfile

        if result["warn_phase"]:
            title = f"[ADR-035] {phase} token 警告"
            pct = result["phase_utilization"] * 100
            msg = (
                f"Phase: {phase}\n"
                f"使用量: {result['phase_tokens']:,.0f} / {result['phase_limit']:,} tokens ({pct:.0f}%)\n"
                f"Trace: {result['trace_id']}\n"
                f"時間: {result['checked_at']}"
            )
        elif result["suspend_trace"]:
            title = f"[ADR-035] Trace token 暫停閾值"
            msg = (
                f"Trace {result['trace_id']} 已使用 {result['trace_tokens']:,.0f} tokens\n"
                f"超過暫停閾值 {result['trace_suspend_limit']:,}，後續任務暫停"
            )
        else:
            return  # 無需告警

        payload = {
            "topic": "wangsc2025",
            "title": title,
            "message": msg,
            "priority": 3,
            "tags": ["money_with_wings"],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(payload, f, ensure_ascii=False)
            tmp_path = f.name

        try:
            import subprocess
            subprocess.run(
                [
                    "curl", "-s", "-X", "POST",
                    "-H", "Content-Type: application/json; charset=utf-8",
                    "-d", f"@{tmp_path}",
                    "https://ntfy.sh",
                ],
                capture_output=True,
                timeout=10,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        pass  # 告警失敗不影響主流程


def format_phase_summary(trace_id: str) -> str:
    """
    格式化整個 trace 的 token 消耗摘要（供 Phase 3 組裝通知使用）。
    """
    usage = _load_token_usage()
    today_data = _get_today_data(usage)
    trace_key = (trace_id or "")[:12]

    traces_data = today_data.get("traces", {})
    trace_entry = traces_data.get(trace_key, {})

    if not trace_entry:
        return f"Trace {trace_key}: 無 token 使用記錄（schema v3 啟用前執行）"

    total_tokens = trace_entry.get("total_tokens", 0)
    phase_breakdown = trace_entry.get("phase_breakdown", {})

    lines = [f"Trace {trace_key} Token 消耗摘要："]
    lines.append(f"  總計：{total_tokens:,.0f} tokens")
    if phase_breakdown:
        lines.append("  Phase 分解：")
        for p, tokens in sorted(phase_breakdown.items()):
            lines.append(f"    {p}: {tokens:,.0f}")

    config = _load_budget_config()
    trace_budget = config.get("trace_budget", {})
    warn_limit = trace_budget.get("warn_threshold", 3_000_000)
    if total_tokens >= warn_limit:
        pct = total_tokens / warn_limit * 100
        lines.append(f"  ⚠ 已達警告閾值的 {pct:.0f}%")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADR-035 Phase 結束預算查核工具")
    parser.add_argument("--phase", required=True, help="Phase 名稱（phase1/phase2/phase3/phase2_auto）")
    parser.add_argument("--trace-id", default="", help="Trace ID")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--summary", action="store_true", help="輸出 Trace 消耗摘要")
    parser.add_argument("--no-alert", action="store_true", help="不發送 ntfy 告警")
    args = parser.parse_args()

    if args.summary:
        print(format_phase_summary(args.trace_id))
        return

    result = check_phase_budget(args.phase, args.trace_id)

    if not args.no_alert and (result["warn_phase"] or result["suspend_trace"]):
        _send_budget_warning(args.phase, result)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "⚠ WARN" if result["warn_phase"] else "✓ OK"
        print(f"[ADR-035] {args.phase} budget: {status}")
        print(f"  Phase tokens: {result['phase_tokens']:,.0f} / {result['phase_limit']:,}"
              f" ({result['phase_utilization']:.1%})")
        print(f"  Trace tokens: {result['trace_tokens']:,.0f}"
              f" (warn@{result['trace_warn_limit']:,}, suspend@{result['trace_suspend_limit']:,})")
        if result["warn_phase"]:
            print("  → Phase token 使用達到警戒線（80%+）")
        if result["warn_trace"]:
            print(f"  → Trace token 超過警告閾值 {result['trace_warn_limit']:,}")
        if result["suspend_trace"]:
            print(f"  → Trace token 超過暫停閾值 {result['trace_suspend_limit']:,}，建議停止後續任務")

    sys.exit(1 if result["suspend_trace"] else 0)


if __name__ == "__main__":
    main()
