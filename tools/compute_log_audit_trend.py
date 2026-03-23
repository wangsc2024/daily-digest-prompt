#!/usr/bin/env python3
"""
從 state/failure-stats.json 的 daily.phase_failure 依時間窗計算趨勢結論（決定性、可機讀）。

供 todoist-auto-log_audit 流程呼叫，避免 LLM 以「全窗最大→全窗最小」誤判為時間趨勢。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_iso_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@dataclass(frozen=True)
class DayPoint:
    date: str
    phase_failure: int


def _load_daily(stats_path: Path) -> dict[str, Any]:
    raw = stats_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    daily = data.get("daily")
    if not isinstance(daily, dict):
        return {}
    return daily


def build_series(daily: dict[str, Any], *, end: date, window_days: int) -> list[DayPoint]:
    if window_days < 1:
        return []
    start = end - timedelta(days=window_days - 1)
    out: list[DayPoint] = []
    for n in range(window_days):
        d = start + timedelta(days=n)
        key = d.isoformat()
        if key not in daily:
            continue
        row = daily[key]
        if not isinstance(row, dict):
            continue
        v = row.get("phase_failure")
        if v is None:
            continue
        try:
            pf = int(v)
        except (TypeError, ValueError):
            continue
        out.append(DayPoint(date=key, phase_failure=pf))
    out.sort(key=lambda p: p.date)
    return out


def _peak_point(series: list[DayPoint]) -> DayPoint | None:
    if not series:
        return None
    # 同值取「日期較晚」為高峰（較符合「最近尖峰」語意）
    return max(series, key=lambda p: (p.phase_failure, p.date))


def _median_int(values: list[int]) -> float | None:
    if not values:
        return None
    return float(median(values))


def compute_trend(series: list[DayPoint]) -> dict[str, Any]:
    guardrails = [
        "禁止以「全窗最大 phase_failure」直接銜接「全窗最小 phase_failure」描述成時間先後的下降趨勢（若最小值日期早於最大值日期，更屬誤判）。",
        "「整體趨勢」「改善中」僅在：最近一日嚴格低於前一日，且敘述已說明比較的是哪兩個日期時，才可使用；若最近一日高於前一日，不得宣稱短期改善。",
        "log 內 grep 的 ERROR 次數與 failure-stats 的 phase_failure 可能不同欄位；不可混用數字寫成單一句子趨勢。",
        "Markdown 報告中的趨勢表必須依日期由舊到新排序。",
    ]

    if len(series) == 0:
        return {
            "metric": "phase_failure",
            "source": "state/failure-stats.json",
            "series_chronological": [],
            "peak": None,
            "last": None,
            "prior": None,
            "short_term_vs_prior": "n/a",
            "median_window": None,
            "last_vs_median": "n/a",
            "summary_zh": "近窗內無 phase_failure 日資料（failure-stats daily 無對應日期鍵）。",
            "improvement_allowed_zh": None,
            "narrative_guardrails_zh": guardrails,
        }

    if len(series) == 1:
        only = series[0]
        pk = _peak_point(series)
        return {
            "metric": "phase_failure",
            "source": "state/failure-stats.json",
            "series_chronological": [{"date": only.date, "phase_failure": only.phase_failure}],
            "peak": {"date": pk.date, "value": pk.phase_failure} if pk else None,
            "last": {"date": only.date, "value": only.phase_failure},
            "prior": None,
            "short_term_vs_prior": "n/a",
            "median_window": float(only.phase_failure),
            "last_vs_median": "n/a",
            "summary_zh": f"近窗僅有單日資料 {only.date}（phase_failure={only.phase_failure}），不足以判斷時間趨勢。",
            "improvement_allowed_zh": None,
            "narrative_guardrails_zh": guardrails,
        }

    last = series[-1]
    prior = series[-2]
    peak = _peak_point(series)
    vals = [p.phase_failure for p in series]
    med = _median_int(vals)
    assert med is not None

    if last.phase_failure > prior.phase_failure:
        st = "worsening"
    elif last.phase_failure < prior.phase_failure:
        st = "improving"
    else:
        st = "stable"

    if last.phase_failure > med:
        lvm = "above_median"
    elif last.phase_failure < med:
        lvm = "below_median"
    else:
        lvm = "at_median"

    parts: list[str] = []
    if st == "worsening":
        parts.append(
            f"最近一日 {last.date} 的 phase_failure 為 {last.phase_failure}，"
            f"高於前一日 {prior.date}（{prior.phase_failure}），短期趨勢為惡化，不得描述為「改善中」。"
        )
    elif st == "improving":
        parts.append(
            f"最近一日 {last.date} 的 phase_failure 為 {last.phase_failure}，"
            f"低於前一日 {prior.date}（{prior.phase_failure}），短期趨勢為改善。"
        )
    else:
        parts.append(
            f"最近兩日 {prior.date} 與 {last.date} 的 phase_failure 皆為 {last.phase_failure}，短期持平。"
        )

    if peak:
        if peak.date != last.date or peak.phase_failure != last.phase_failure:
            if last.phase_failure < peak.phase_failure:
                parts.append(f"相較窗內高峰 {peak.date}（{peak.phase_failure} 次）已回落。")
            elif last.phase_failure == peak.phase_failure:
                parts.append(f"與窗內高峰同水準（{peak.date}，{peak.phase_failure} 次）。")

    if med is not None:
        parts.append(f"窗內 phase_failure 中位數為 {med:g}；最近一日相對中位數為「{'高於' if lvm == 'above_median' else '低於' if lvm == 'below_median' else '等於'}」中位數。")

    improvement_allowed: str | None
    if st == "worsening":
        improvement_allowed = (
            "禁止使用「改善中」「整體趨勢下降」等語描述 phase_failure，"
            "除非另指非 failure-stats 之指標並分開註明資料來源。"
        )
    elif st == "improving":
        improvement_allowed = (
            f"可描述短期改善：{last.date} 低於前一日 {prior.date}。"
            "若使用「整體改善」須同時寫出比較日期區間，且不得與 summary_zh 中「高於中位數」等事實矛盾。"
        )
    else:
        improvement_allowed = "短期持平；避免使用「改善中」除非另附其他日期區間之明確下降證據。"

    return {
        "metric": "phase_failure",
        "source": "state/failure-stats.json",
        "series_chronological": [{"date": p.date, "phase_failure": p.phase_failure} for p in series],
        "peak": {"date": peak.date, "value": peak.phase_failure} if peak else None,
        "last": {"date": last.date, "value": last.phase_failure},
        "prior": {"date": prior.date, "value": prior.phase_failure},
        "short_term_vs_prior": st,
        "median_window": med,
        "last_vs_median": lvm,
        "summary_zh": "".join(parts),
        "improvement_allowed_zh": improvement_allowed,
        "narrative_guardrails_zh": guardrails,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute deterministic phase_failure trend from failure-stats.json")
    parser.add_argument("--days", type=int, default=7, help="Rolling calendar window length (default: 7)")
    parser.add_argument(
        "--stats",
        type=Path,
        default=None,
        help="Path to failure-stats.json (default: <repo>/state/failure-stats.json)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Window end date YYYY-MM-DD (default: local today)",
    )
    args = parser.parse_args()

    root = _project_root()
    stats_path = args.stats or (root / "state" / "failure-stats.json")
    if not stats_path.is_file():
        print(json.dumps({"error": f"missing_file:{stats_path}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.end_date:
        end = _parse_iso_date(args.end_date)
    else:
        end = date.today()

    daily = _load_daily(stats_path)
    series = build_series(daily, end=end, window_days=args.days)
    payload = compute_trend(series)
    payload["window_days_requested"] = args.days
    payload["end_date"] = end.isoformat()
    if series and series[-1].date < end.isoformat():
        payload["data_lag_warning_zh"] = (
            f"failure-stats 最晚有資料日為 {series[-1].date}，早於視窗終點 {end.isoformat()}；"
            "趨勢僅反映統計檔現況，審查前請確認是否需先更新 state/failure-stats.json。"
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
