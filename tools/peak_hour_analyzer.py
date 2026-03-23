#!/usr/bin/env python3
"""peak_hour_analyzer.py - 高失敗時段根因分析工具（ADR-047）
分析 JSONL 日誌，識別 7:00 和 13:00 等高失敗時段的根因。
三層監控：alerts（即時告警）+ logging（結構化日誌）+ metrics（趨勢指標）
"""
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import argparse

PROJECT_ROOT = Path(__file__).parent.parent
TZ_OFFSET = 8  # UTC+8

def load_alert_config() -> dict:
    """載入高峰時段告警設定"""
    config_path = PROJECT_ROOT / "config" / "peak-hour-alerts.yaml"
    if not config_path.exists():
        return {"peak_hours": [7, 13], "failure_threshold": 0.15}
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {"peak_hours": [7, 13], "failure_threshold": 0.15}

def parse_logs(days: int = 14) -> list[dict]:
    """從 JSONL 日誌和 FSM state 解析執行記錄"""
    log_dir = PROJECT_ROOT / "logs" / "structured"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = []

    # 從 JSONL 結構化日誌讀取
    if log_dir.exists():
        for log_file in sorted(log_dir.glob("*.jsonl")):
            try:
                with open(log_file, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts_str = entry.get("timestamp", "")
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < cutoff:
                                continue
                        except Exception:
                            continue
                        records.append(entry)
            except Exception:
                continue

    # 從 run-fsm.json 補充執行記錄
    fsm_path = PROJECT_ROOT / "state" / "run-fsm.json"
    if fsm_path.exists():
        try:
            with open(fsm_path, encoding="utf-8") as f:
                fsm = json.load(f)
            runs = fsm.get("runs", fsm.get("history", []))
            if isinstance(runs, list):
                for run in runs:
                    ts_str = run.get("started_at", run.get("timestamp", ""))
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                    except Exception:
                        continue
                    records.append({
                        "timestamp": ts_str,
                        "type": "fsm_run",
                        "success": run.get("overall_success", run.get("success", True)),
                        "phase_results": run.get("phase_results", {}),
                        "error": run.get("error", ""),
                    })
        except Exception:
            pass

    return records

def classify_failure_cause(entry: dict) -> str:
    """分類失敗根因"""
    text = json.dumps(entry, ensure_ascii=False).lower()
    if any(kw in text for kw in ["timeout", "timed out", "time out", "逾時"]):
        return "timeout"
    if any(kw in text for kw in ["api", "curl", "http", "connection", "network"]):
        return "external_api"
    if any(kw in text for kw in ["memory", "oom", "resource", "cpu"]):
        return "resource"
    if any(kw in text for kw in ["parse", "json", "format", "schema"]):
        return "data_format"
    if any(kw in text for kw in ["phase", "phase2", "phase3"]):
        return "pipeline_phase"
    return "unknown"

def analyze_by_hour(records: list[dict]) -> dict:
    """按小時統計成功/失敗"""
    hourly = defaultdict(lambda: {"success": 0, "failure": 0, "causes": defaultdict(int)})

    for entry in records:
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            local_hour = (ts.hour + TZ_OFFSET) % 24
        except Exception:
            continue

        # 判斷是否失敗
        is_failure = False
        if entry.get("type") == "fsm_run":
            is_failure = not entry.get("success", True)
        elif "error" in entry.get("tags", []) or entry.get("blocked"):
            is_failure = True

        if is_failure:
            hourly[local_hour]["failure"] += 1
            cause = classify_failure_cause(entry)
            hourly[local_hour]["causes"][cause] += 1
        else:
            hourly[local_hour]["success"] += 1

    return {h: dict(v) for h, v in hourly.items()}

def compute_failure_rates(hourly: dict) -> dict:
    """計算各小時失敗率"""
    rates = {}
    for hour, counts in hourly.items():
        total = counts["success"] + counts["failure"]
        if total == 0:
            continue
        failure_rate = counts["failure"] / total
        causes = dict(counts.get("causes", {}))
        top_cause = max(causes, key=causes.get) if causes else "unknown"
        rates[hour] = {
            "failure_rate": round(failure_rate, 3),
            "total": total,
            "failures": counts["failure"],
            "top_cause": top_cause,
            "causes": causes,
        }
    return rates

def generate_alerts(failure_rates: dict, config: dict) -> list[dict]:
    """生成三層告警"""
    alerts = []
    threshold = config.get("failure_threshold", 0.15)
    peak_hours = config.get("peak_hours", [7, 13])

    for hour, data in sorted(failure_rates.items()):
        rate = data["failure_rate"]
        is_peak = hour in peak_hours

        # Layer 1: Alerts（即時告警）
        if rate > threshold:
            severity = "critical" if (rate > 0.30 or is_peak) else "warning"
            alerts.append({
                "layer": "alert",
                "severity": severity,
                "hour": hour,
                "message": f"{'[峰值時段] ' if is_peak else ''}時段 {hour:02d}:00 失敗率 {rate:.1%}（閾值 {threshold:.0%}）",
                "top_cause": data["top_cause"],
                "recommendation": _get_recommendation(data["top_cause"]),
            })

        # Layer 2: Logging（結構化紀錄）
        if is_peak:
            alerts.append({
                "layer": "logging",
                "hour": hour,
                "failure_rate": rate,
                "total_runs": data["total"],
                "cause_breakdown": data["causes"],
            })

    # Layer 3: Metrics（趨勢）
    if failure_rates:
        avg_rate = sum(d["failure_rate"] for d in failure_rates.values()) / len(failure_rates)
        alerts.append({
            "layer": "metrics",
            "avg_failure_rate": round(avg_rate, 3),
            "peak_hour_rates": {h: failure_rates[h]["failure_rate"] for h in peak_hours if h in failure_rates},
            "worst_hour": min(failure_rates, key=lambda h: failure_rates[h]["failure_rate"], default=None),
        })

    return alerts

def _get_recommendation(cause: str) -> str:
    recommendations = {
        "timeout": "增加 timeout 設定（config/timeouts.yaml）或改用背景執行模式",
        "external_api": "檢查 API 服務健康度；考慮增加重試次數或快取 TTL",
        "resource": "檢查系統資源使用率；避免高峰時段執行重型任務",
        "data_format": "檢查 API 回應 schema；更新解析邏輯",
        "pipeline_phase": "檢查 Phase 2/3 結果檔案；確認 todoist-auto-*.json 命名一致",
        "unknown": "查看 logs/structured/ 取得詳細錯誤訊息",
    }
    return recommendations.get(cause, "查看詳細日誌")

def main():
    parser = argparse.ArgumentParser(description="高失敗時段根因分析")
    parser.add_argument("--days", type=int, default=14, help="分析天數（預設 14）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--alerts-only", action="store_true", help="只顯示告警")
    args = parser.parse_args()

    config = load_alert_config()
    records = parse_logs(days=args.days)
    hourly = analyze_by_hour(records)
    failure_rates = compute_failure_rates(hourly)
    alerts = generate_alerts(failure_rates, config)

    if args.json:
        print(json.dumps({
            "failure_rates": failure_rates,
            "alerts": alerts,
            "analyzed_records": len(records),
        }, ensure_ascii=False, indent=2))
        return

    print(f"\n=== 高失敗時段根因分析（近 {args.days} 天，{len(records)} 筆記錄）===")

    if not failure_rates:
        print("（無足夠日誌數據，請確認 logs/structured/ 目錄有 JSONL 日誌）")
        print("\n基於設定的監控峰值時段：", config.get("peak_hours", [7, 13]))
        print("失敗率閾值：", f"{config.get('failure_threshold', 0.15):.0%}")
        return

    peak_hours = config.get("peak_hours", [7, 13])
    print(f"\n峰值時段設定：{peak_hours}")
    print(f"失敗率閾值：{config.get('failure_threshold', 0.15):.0%}")

    print("\n── 各小時失敗率 ──")
    for hour in sorted(failure_rates.keys()):
        data = failure_rates[hour]
        rate = data["failure_rate"]
        mark = "[XX]" if rate > 0.20 else "[!!]" if rate > 0.10 else "[OK]"
        peak_mark = " *峰值*" if hour in peak_hours else ""
        print(f"  {hour:02d}:00 {mark} {rate:.1%} ({data['failures']}/{data['total']}){peak_mark} [{data['top_cause']}]")

    alert_items = [a for a in alerts if a["layer"] == "alert"]
    if alert_items:
        print("\n── 告警（Layer 1）──")
        for a in alert_items:
            print(f"  [{a['severity'].upper()}] {a['message']}")
            print(f"    建議：{a['recommendation']}")

    metrics = next((a for a in alerts if a["layer"] == "metrics"), None)
    if metrics:
        print(f"\n── 指標摘要（Layer 3）──")
        print(f"  平均失敗率：{metrics['avg_failure_rate']:.1%}")
        for h, r in metrics.get("peak_hour_rates", {}).items():
            print(f"  峰值時段 {h:02d}:00：{r:.1%}")

    print()

if __name__ == "__main__":
    main()
