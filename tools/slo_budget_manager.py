#!/usr/bin/env python3
"""
SLO/Error Budget 治理工具（ADR-032）
計算 failure mode taxonomy、error budget 狀態，觸發 postmortem 提案。
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

BASE = Path(__file__).parent.parent


def load_json(path: Path) -> dict:
    """讀取 JSON 檔案，支援 UTF-8 BOM（Windows PowerShell 常見格式）。"""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except json.JSONDecodeError:
            return {}
        except Exception:
            continue
    return {}


def load_yaml_simple(path: Path) -> dict:
    """簡易 YAML 讀取（避免 yaml 依賴），只用於讀取 slo.yaml SLO 列表。"""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        # fallback: 無 yaml 時回傳空
        return {}
    except Exception:
        return {}


def classify_failure(error_text: str) -> str:
    """依關鍵字分類 failure mode。"""
    t = error_text.lower()
    if any(k in t for k in ["timeout", "timed out", "exceeded", "超時", "sigterm"]):
        return "timeout"
    if any(k in t for k in ["connection refused", "econnrefused", "503", "502", "curl: (7)", "服務未啟動"]):
        return "api_error"
    if any(k in t for k in ["json", "parse", "schema", "decode", "syntaxerror", "keyerror"]):
        return "parse_error"
    if any(k in t for k in ["quota", "rate limit", "429", "budget", "token limit"]):
        return "quota_exceeded"
    if any(k in t for k in ["template", "prompt not found", "模板不存在", "filenotfounderror"]):
        return "template_missing"
    if any(k in t for k in ["phase 1 failed", "phase1", "phase_failure"]):
        return "phase_failure"
    if any(k in t for k in ["config", "yaml", "configuration"]):
        return "config_error"
    return "unknown"


BLAST_RADIUS = {
    "timeout": "single_task",
    "api_error": "dependent_tasks",
    "parse_error": "single_task",
    "quota_exceeded": "all_tasks",
    "template_missing": "single_task",
    "phase_failure": "phase",
    "config_error": "all_tasks",
    "unknown": "unknown",
}


def calc_error_budget(slos: list, actual_rate: float, window_total: int) -> dict:
    """計算每個 SLO 的 error budget（支援 higher_is_better 和 lower_is_better）。"""
    budgets = {}
    for slo in slos:
        slo_id = slo.get("id", "")
        target = slo.get("target", 0.9)
        direction = slo.get("metric_direction", "higher_is_better")
        if actual_rate is None:
            continue

        if direction == "higher_is_better":
            # 越高越好：actual < target 時消耗預算
            budget_total = 1.0 - target
            consumed = max(0.0, target - actual_rate)
            consumed_pct = (consumed / budget_total * 100) if budget_total > 0 else 0.0
        else:
            # lower_is_better：actual > target 時消耗預算
            # budget_total = target（允許的最大值即為預算空間）
            budget_total = target
            consumed = max(0.0, actual_rate - target)
            consumed_pct = (consumed / budget_total * 100) if budget_total > 0 else 0.0

        remaining_pct = max(0.0, 100.0 - consumed_pct)
        budgets[slo_id] = {
            "name": slo.get("name", slo_id),
            "target": target,
            "actual": round(actual_rate, 4),
            "budget_total_pct": round(budget_total * 100, 1),
            "budget_consumed_pct": round(consumed_pct, 1),
            "budget_remaining_pct": round(remaining_pct, 1),
            "status": "green" if remaining_pct > 50 else ("yellow" if remaining_pct > 25 else "red"),
        }
    return budgets


def main() -> int:
    now_str = datetime.now().isoformat()

    # 1. 讀取 scheduler-state.json
    scheduler = load_json(BASE / "state" / "scheduler-state.json")
    runs = scheduler.get("runs", [])

    # 近 28 天 runs
    cutoff = (datetime.now() - timedelta(days=28)).isoformat()
    recent_runs = [
        r for r in runs
        if (r.get("timestamp") or r.get("start_time") or "") >= cutoff
    ]
    total = len(recent_runs)
    success = sum(1 for r in recent_runs if r.get("status") == "success")
    actual_rate = success / total if total > 0 else None

    # 2. 讀取 failure-stats.json
    failure_stats = load_json(BASE / "state" / "failure-stats.json")
    taxonomy_raw = failure_stats.get("failure_taxonomy", {})

    # 3. 分類近 28 天 failures from scheduler runs
    mode_counter: Counter = Counter()
    mode_last: dict[str, str] = {}
    for r in recent_runs:
        if r.get("status") != "success":
            err = str(r.get("error", "")) + str(r.get("sections", ""))
            mode = classify_failure(err)
            mode_counter[mode] += 1
            ts = r.get("timestamp", r.get("start_time", ""))
            if mode not in mode_last or ts > mode_last[mode]:
                mode_last[mode] = ts

    # 4. 載入 SLO 配置
    slo_cfg = load_yaml_simple(BASE / "config" / "slo.yaml")
    slos = slo_cfg.get("slos", [])
    budget_policy = slo_cfg.get("budget_policy", {})
    postmortem_trigger_pct = budget_policy.get("postmortem_trigger_pct", 20)

    # 5. 計算 error budget（僅對成功率類型）
    budgets = {}
    if actual_rate is not None:
        budgets = calc_error_budget(slos, actual_rate, total)

    # 6. Failure taxonomy（結合 failure-stats.json + 近期 runs 分類）
    taxonomy = {}
    all_modes = ["timeout", "api_error", "phase_failure", "parse_error",
                 "quota_exceeded", "template_missing", "config_error", "unknown"]
    total_stats = failure_stats.get("total", {})
    for mode in all_modes:
        count = mode_counter.get(mode, 0) or total_stats.get(mode, 0)
        taxonomy[mode] = {
            "count": count,
            "blast_radius": BLAST_RADIUS[mode],
            "last_occurrence": mode_last.get(mode),
        }

    # 7. Postmortem 觸發檢查
    postmortem_triggered = False
    postmortem_reasons = []
    for slo_id, b in budgets.items():
        consumed = b["budget_consumed_pct"]
        if consumed >= postmortem_trigger_pct:
            postmortem_triggered = True
            postmortem_reasons.append(
                f"{slo_id} budget consumed {consumed}% >= trigger {postmortem_trigger_pct}%"
            )

    # 8. 若觸發 postmortem → 寫入 context/postmortem/
    if postmortem_triggered:
        postmortem_dir = BASE / "context" / "postmortem"
        postmortem_dir.mkdir(parents=True, exist_ok=True)
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        pm_path = postmortem_dir / f"postmortem_{ts_tag}.md"
        top_mode = mode_counter.most_common(1)[0] if mode_counter else ("unknown", 0)
        pm_content = f"""# Postmortem：{top_mode[0]} 觸發 SLO 違規
生成時間：{now_str}

## 摘要
- SLO 違規原因：{'; '.join(postmortem_reasons)}
- 主要失敗模式：{top_mode[0]}（{top_mode[1]} 次）
- 28 天窗口：{total} runs，成功率 {actual_rate:.1%} （目標 ≥ 90%）

## 近期失敗分類
{chr(10).join(f'- {m}: {c} 次（blast_radius={BLAST_RADIUS.get(m,"?")}）' for m, c in mode_counter.most_common())}

## 行動項目（P0/P1）
1. [ ] 根因分析：找出 {top_mode[0]} 的觸發條件
2. [ ] 修復方案：針對最高頻 failure mode 提出修復
3. [ ] 驗證：修復後觀察 7 天，確認 success rate ≥ 90%
4. [ ] 回顧：更新 failure_taxonomy 並在 improvement-backlog.json 標記 resolved

## Error Budget 狀態
{chr(10).join(f'- {sid}: remaining={b["budget_remaining_pct"]}% ({b["status"]})' for sid, b in budgets.items())}
"""
        pm_path.write_text(pm_content, encoding="utf-8")
        print(f"[postmortem] 已寫入 {pm_path}")

    # 9. 計算 top_recurring_causes
    top_causes = [
        {"mode": m, "count": c, "blast_radius": BLAST_RADIUS.get(m, "unknown")}
        for m, c in mode_counter.most_common(3)
        if c > 0
    ]

    # 10. 輸出 state/slo-budget-report.json
    report = {
        "generated_at": now_str,
        "window_days": 28,
        "total_runs": total,
        "success_rate": round(actual_rate, 4) if actual_rate is not None else None,
        "slo_status": budgets,
        "failure_taxonomy": taxonomy,
        "unknown_rate_pct": round(
            mode_counter.get("unknown", 0) / max(sum(mode_counter.values()), 1) * 100, 1
        ),
        "postmortem_triggered": postmortem_triggered,
        "postmortem_reasons": postmortem_reasons,
        "top_recurring_causes": top_causes,
        "action_level": (
            "normal" if not budgets else (
                "full_freeze" if any(b["budget_remaining_pct"] <= 0 for b in budgets.values()) else
                "freeze_non_critical" if any(b["budget_remaining_pct"] < 25 for b in budgets.values()) else
                "slow_down" if any(b["budget_remaining_pct"] < 50 for b in budgets.values()) else
                "normal"
            )
        ),
        "_adr": "ADR-20260320-032",
    }

    report_path = BASE / "state" / "slo-budget-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[slo_budget_manager] 報告已寫入 {report_path}")
    print(f"  action_level: {report['action_level']}")
    print(f"  success_rate: {report['success_rate']}")
    print(f"  top_causes: {top_causes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
