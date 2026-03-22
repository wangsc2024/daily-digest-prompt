#!/usr/bin/env python3
"""
時段風險評分器（ADR-037）

分析 logs/structured/*.jsonl 中各小時的失敗率，結合外部 SLA 盤點，
計算當前時段的風險評分，供 run-todoist-agent-team.ps1 Phase 0e 閘門使用。

使用方式：
  uv run python tools/time_slot_risk_scorer.py
  uv run python tools/time_slot_risk_scorer.py --hour 5
  uv run python tools/time_slot_risk_scorer.py --days 14 --format json
  uv run python tools/time_slot_risk_scorer.py --write-report
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).parent.parent
LOG_DIR = REPO_ROOT / "logs" / "structured"
EXTERNAL_SLA_PATH = REPO_ROOT / "config" / "external-sla.yaml"
STATE_DIR = REPO_ROOT / "state"


# ── 資料結構 ────────────────────────────────────────────────────────────────

@dataclass
class HourStats:
    hour: int
    total_runs: int
    failed_runs: int
    failure_rate: float
    failure_modes: dict = field(default_factory=dict)  # {"timeout": 3, "api_error": 2}


@dataclass
class RiskScore:
    hour: int
    risk_score: float                  # 0.0 - 1.0
    risk_level: str                    # "low" | "medium" | "high" | "critical"
    recommended_action: str            # "normal" | "extend_timeout" | "skip_non_critical" | "skip_phase2"
    skip_task_types: list = field(default_factory=list)
    contributing_factors: dict = field(default_factory=dict)


# ── 配置載入 ─────────────────────────────────────────────────────────────────

def _load_sla_config() -> dict:
    """載入 external-sla.yaml，失敗時回傳預設值。"""
    try:
        import yaml
        with open(EXTERNAL_SLA_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {
            "risk_model": {
                "weights": {
                    "historical_failure_rate": 0.40,
                    "external_sla_risk": 0.25,
                    "resource_contention": 0.20,
                    "task_complexity": 0.15,
                },
                "thresholds": {"low": 0.30, "medium": 0.55, "high": 0.75},
            },
            "known_high_risk_hours": [5, 7, 13],
            "degradation": {
                "medium": {"action": "extend_timeout", "timeout_multiplier": 1.30},
                "high": {"action": "skip_non_critical", "skip_task_types": ["research", "creative"]},
                "critical": {"action": "skip_phase2", "notify": True},
            },
        }


# ── 日誌讀取 ─────────────────────────────────────────────────────────────────

def _iter_jsonl(path: Path) -> Iterator[dict]:
    """逐行解析 JSONL，跳過無效行。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass
    except OSError:
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


# ── 核心分析 ─────────────────────────────────────────────────────────────────

def compute_hour_stats(days: int = 14) -> dict[int, HourStats]:
    """
    掃描最近 N 天的日誌，依 hour_of_day 統計各小時失敗率。

    Returns:
        dict mapping hour (0-23) → HourStats
    """
    entries = _load_recent_entries(days)

    hour_data: dict[int, dict] = defaultdict(lambda: {
        "total": 0, "errors": 0, "modes": Counter()
    })

    for entry in entries:
        ts = entry.get("ts", "")
        if not ts:
            continue
        try:
            hour = datetime.fromisoformat(ts).hour
        except (ValueError, TypeError):
            continue

        hour_data[hour]["total"] += 1
        if entry.get("has_error"):
            hour_data[hour]["errors"] += 1
            mode = entry.get("error_category", "unknown")
            hour_data[hour]["modes"][mode] += 1
        # loop-suspected 也計為失敗信號
        if "loop-suspected" in entry.get("tags", []):
            hour_data[hour]["errors"] += 1
            hour_data[hour]["modes"]["loop_suspected"] += 1

    result: dict[int, HourStats] = {}
    for h, data in hour_data.items():
        total = data["total"]
        errors = data["errors"]
        result[h] = HourStats(
            hour=h,
            total_runs=total,
            failed_runs=errors,
            failure_rate=errors / total if total > 0 else 0.0,
            failure_modes=dict(data["modes"].most_common(5)),
        )

    return result


def score_time_slot(hour: int, hour_stats: dict[int, HourStats]) -> RiskScore:
    """
    套用多因子加權風險評分模型，計算指定小時的風險評分。

    四個因子：
    1. historical_failure_rate — 歷史失敗率
    2. external_sla_risk — 外部服務 SLA 風險（known_high_risk_hours）
    3. resource_contention — 資源競爭（尖峰時段特徵）
    4. task_complexity — 任務複雜度（靜態基準）
    """
    config = _load_sla_config()
    weights = config.get("risk_model", {}).get("weights", {})
    thresholds = config.get("risk_model", {}).get("thresholds", {})
    known_high_risk = set(config.get("known_high_risk_hours", [5, 7, 13]))

    # Factor 1: 歷史失敗率（0.0 - 1.0）
    stats = hour_stats.get(hour)
    if stats and stats.total_runs >= 3:  # 至少 3 筆才有統計意義
        f_historical = min(stats.failure_rate * 2, 1.0)  # 放大係數
    elif hour in known_high_risk:
        f_historical = 0.6  # known 高風險時段，無足夠資料時給予警戒值
    else:
        f_historical = 0.1  # 資料不足，給予低風險預設

    # Factor 2: 外部 SLA 風險（基於 known_high_risk_hours）
    f_external_sla = 0.6 if hour in known_high_risk else 0.1

    # Factor 3: 資源競爭（商業尖峰時段：09-12, 14-17）
    if 9 <= hour <= 12 or 14 <= hour <= 17:
        f_resource = 0.4
    elif 0 <= hour <= 6:
        f_resource = 0.1  # 深夜/清晨競爭低
    else:
        f_resource = 0.2

    # Factor 4: 任務複雜度（靜態基準 0.2，未來可動態化）
    f_complexity = 0.2

    # 加權總分
    w_hist = weights.get("historical_failure_rate", 0.40)
    w_ext = weights.get("external_sla_risk", 0.25)
    w_res = weights.get("resource_contention", 0.20)
    w_cmp = weights.get("task_complexity", 0.15)

    risk_score = (
        f_historical * w_hist +
        f_external_sla * w_ext +
        f_resource * w_res +
        f_complexity * w_cmp
    )
    risk_score = round(min(risk_score, 1.0), 4)

    contributing_factors = {
        "historical_failure_rate": round(f_historical * w_hist, 4),
        "external_sla_risk": round(f_external_sla * w_ext, 4),
        "resource_contention": round(f_resource * w_res, 4),
        "task_complexity": round(f_complexity * w_cmp, 4),
    }

    # 風險等級判斷
    thr_low = thresholds.get("low", 0.30)
    thr_med = thresholds.get("medium", 0.55)
    thr_high = thresholds.get("high", 0.75)

    if risk_score < thr_low:
        risk_level = "low"
    elif risk_score < thr_med:
        risk_level = "medium"
    elif risk_score < thr_high:
        risk_level = "high"
    else:
        risk_level = "critical"

    # 降級策略
    degradation = config.get("degradation", {})
    deg_conf = degradation.get(risk_level, {})
    action = deg_conf.get("action", "normal")
    skip_task_types = deg_conf.get("skip_task_types", [])

    # "low" 無降級策略，設為 normal
    if risk_level == "low":
        action = "normal"
        skip_task_types = []

    return RiskScore(
        hour=hour,
        risk_score=risk_score,
        risk_level=risk_level,
        recommended_action=action,
        skip_task_types=skip_task_types,
        contributing_factors=contributing_factors,
    )


def get_current_risk(days: int = 14) -> RiskScore:
    """
    一站式函式：計算當前小時的風險評分。
    供 PS1 腳本直接呼叫。
    """
    current_hour = datetime.now().hour
    hour_stats = compute_hour_stats(days=days)
    return score_time_slot(current_hour, hour_stats)


def write_risk_report(output_path: str | None = None) -> dict:
    """
    計算當前時段風險並寫入 state/time-slot-risk.json。

    Returns:
        報告 dict（含 generated_at, current_hour, risk, hour_stats）
    """
    current_hour = datetime.now().hour
    hour_stats = compute_hour_stats()
    risk = score_time_slot(current_hour, hour_stats)

    # 序列化 hour_stats
    stats_dict = {}
    for h, s in sorted(hour_stats.items()):
        stats_dict[str(h)] = {
            "hour": s.hour,
            "total_runs": s.total_runs,
            "failed_runs": s.failed_runs,
            "failure_rate": round(s.failure_rate, 4),
            "failure_modes": s.failure_modes,
        }

    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "current_hour": current_hour,
        "risk": asdict(risk),
        "hour_stats": stats_dict,
    }

    target_path = output_path or str(STATE_DIR / "time-slot-risk.json")
    try:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[time_slot_risk_scorer] 寫入報告失敗: {e}", file=sys.stderr)

    return report


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ADR-037 時段風險評分器")
    parser.add_argument("--hour", type=int, default=None, help="指定小時（0-23，預設當前小時）")
    parser.add_argument("--days", type=int, default=14, help="分析最近 N 天日誌（預設 14）")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--write-report", action="store_true", help="寫入 state/time-slot-risk.json")
    args = parser.parse_args()

    hour = args.hour if args.hour is not None else datetime.now().hour
    hour_stats = compute_hour_stats(days=args.days)
    risk = score_time_slot(hour, hour_stats)

    if args.write_report:
        report = write_risk_report()
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"[時段風險評估] hour={hour} level={risk.risk_level} score={risk.risk_score}")
            print(f"  建議動作: {risk.recommended_action}")
            if risk.skip_task_types:
                print(f"  跳過類型: {', '.join(risk.skip_task_types)}")
        return

    if args.format == "json":
        output = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "current_hour": hour,
            "risk": asdict(risk),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"[時段風險評估] hour={hour} level={risk.risk_level} score={risk.risk_score}")
        print(f"  建議動作: {risk.recommended_action}")
        if risk.skip_task_types:
            print(f"  跳過類型: {', '.join(risk.skip_task_types)}")
        print("  貢獻因子:")
        for factor, value in risk.contributing_factors.items():
            print(f"    {factor}: {value:.4f}")


if __name__ == "__main__":
    main()
