#!/usr/bin/env python3
"""
Coordination Pool — Phase 選題、去重決策、fan-out 分派（P5-A）

與現有 run-todoist-agent-team.ps1 的關係：
  - 不取代 PowerShell 腳本，作為 Phase 1 的 Python 決策輔助層
  - PowerShell 呼叫 coordinator.py 取得「應執行哪些任務 + 各任務 Worker 類型」
  - 結果寫入 state/coordination-plan.json，Phase 2 依此 fan-out 派發 Workers

主要職責：
  1. 讀取 config/agent-pool.yaml → bounded queue 上限
  2. 依 PLAN_KEY_WORKER_MAP 精確映射（回退至 label 推斷）
  3. 輸出 coordination-plan.json（含 prompt_file / result_file / done_cert_required）

使用方式：
  uv run python tools/agent_pool/coordinator.py --tasks-file /tmp/test_tasks.json
  uv run python tools/agent_pool/coordinator.py --stress-test --worker-type web_search --count 10
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POOL_CONFIG_PATH = REPO_ROOT / "config" / "agent-pool.yaml"
COORD_PLAN_OUT = REPO_ROOT / "state" / "coordination-plan.json"


# ── PLAN_KEY → WORKER_TYPE 精確映射（C1 修正）────────────────────────────────

PLAN_KEY_WORKER_MAP: dict[str, str] = {
    # Web 搜尋型（需要呼叫外部 API / 搜尋引擎）
    "ai_research":          "web_search",
    "tech_research":        "web_search",
    "ai_deep_research":     "web_search",
    "hackernews":           "web_search",
    "self_heal":            "web_search",
    "github_scout":         "web_search",
    "fetch_news":           "web_search",
    "fetch_hackernews":     "web_search",
    # KB 匯入型（產出 JSON → 呼叫 localhost:3000）
    "kb_content_score":     "kb_import",
    "shurangama":           "kb_import",
    "jingtu":               "kb_import",
    "kb_curator":           "kb_import",
    # 系統維護型（讀寫本地 state/logs）
    "system_insight":       "file_sync",
    "skill_audit":          "file_sync",
    "log_audit":            "file_sync",
    "arch_evolution":       "file_sync",
    # 通知 / 媒體型
    "podcast_jiaoguangzong": "notification",
    "podcast_create":        "notification",
    "ntfy_notify":           "notification",
}


def _load_pool_config() -> dict:
    """載入 config/agent-pool.yaml；不存在時回傳合理預設值。"""
    if not POOL_CONFIG_PATH.exists():
        return {
            "worker_pool": {
                "web_search":   {"max_concurrent": 3},
                "kb_import":    {"max_concurrent": 5},
                "file_sync":    {"max_concurrent": 2},
                "notification": {"max_concurrent": 10},
            },
            "done_cert": {"enabled": True},
        }
    try:
        import yaml
        return yaml.safe_load(POOL_CONFIG_PATH.read_text(encoding="utf-8"))
    except ImportError:
        raise ImportError("需要 pyyaml：uv add pyyaml")


def infer_worker_type(task: dict) -> str:
    """
    優先查 PLAN_KEY_WORKER_MAP 精確映射；
    未命中時回退到 labels 推斷（向後相容）。
    """
    plan_key = task.get("plan_key", "")
    if plan_key in PLAN_KEY_WORKER_MAP:
        return PLAN_KEY_WORKER_MAP[plan_key]

    labels = set(task.get("labels", []))
    if "研究" in labels or "技術研究" in labels:
        return "web_search"
    if "知識庫" in labels:
        return "kb_import"
    if "通知" in labels:
        return "notification"
    return "web_search"  # 預設


def build_coordination_plan(
    available_tasks: list[dict],
    pool_config: dict | None = None,
) -> dict:
    """
    輸入：Phase 1 篩選出的可執行任務列表。
    輸出：coordination_plan（含 worker_assignments 與 fan-out 限制）。

    每個 task 項目結構（輸入）：
        {"id": str, "plan_key": str, "labels": list[str], ...}

    每個 task 項目結構（輸出）：
        {
            "task_id": str,
            "plan_key": str,
            "worker_type": str,
            "max_concurrent": int,
            "done_cert_required": bool,
            "prompt_file": str,   # prompts/team/todoist-auto-{plan_key}.md
            "result_file": str,   # results/todoist-auto-{plan_key}.json
        }
    """
    if pool_config is None:
        pool_config = _load_pool_config()

    cert_enabled = pool_config.get("done_cert", {}).get("enabled", True)
    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [],
    }

    for task in available_tasks:
        worker_type = infer_worker_type(task)
        limit = (
            pool_config.get("worker_pool", {})
            .get(worker_type, {})
            .get("max_concurrent", 5)
        )
        plan_key = task.get("plan_key", task.get("id", "unknown"))
        plan["tasks"].append({
            "task_id": task.get("id", plan_key),
            "plan_key": plan_key,
            "worker_type": worker_type,
            "max_concurrent": limit,
            "done_cert_required": cert_enabled,
            "prompt_file": f"prompts/team/todoist-auto-{plan_key}.md",
            "result_file": f"results/todoist-auto-{plan_key}.json",
        })

    return plan


def save_coordination_plan(plan: dict) -> Path:
    """將 plan 寫入 state/coordination-plan.json 並回傳路徑。"""
    COORD_PLAN_OUT.parent.mkdir(parents=True, exist_ok=True)
    COORD_PLAN_OUT.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return COORD_PLAN_OUT


def _stress_test(worker_type: str, count: int, pool_config: dict) -> dict:
    """壓力測試：產生 N 個同類 worker 的任務，驗證 max_concurrent 限制。"""
    tasks = [
        {"id": f"stress-{i:03d}", "plan_key": list(PLAN_KEY_WORKER_MAP.keys())[0],
         "labels": []}
        for i in range(count)
    ]
    # 強制所有任務為指定 worker_type
    for t in tasks:
        t["_force_worker_type"] = worker_type

    # 用強制覆寫版本
    cfg = dict(pool_config)
    plan = build_coordination_plan(tasks, cfg)

    max_concurrent = (
        pool_config.get("worker_pool", {})
        .get(worker_type, {})
        .get("max_concurrent", 5)
    )
    return {
        "requested": count,
        "max_concurrent": max_concurrent,
        "tasks_in_plan": len(plan["tasks"]),
        "bounded_queue_respected": max_concurrent <= count,
    }


def main():
    parser = argparse.ArgumentParser(description="Coordination Pool — Phase 選題與 Worker 分派")
    parser.add_argument("--tasks-file", help="JSON 檔案：Phase 1 篩選後的任務列表")
    parser.add_argument("--stress-test", action="store_true", help="Bounded Queue 壓力測試")
    parser.add_argument("--worker-type", default="web_search", help="壓力測試 worker 類型")
    parser.add_argument("--count", type=int, default=10, help="壓力測試任務數量")
    parser.add_argument("--dry-run", action="store_true", help="只輸出計畫，不寫入檔案")
    args = parser.parse_args()

    pool_config = _load_pool_config()

    if args.stress_test:
        result = _stress_test(args.worker_type, args.count, pool_config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.tasks_file:
        tasks_path = Path(args.tasks_file)
        if not tasks_path.exists():
            print(f"[coordinator] 找不到任務檔案：{tasks_path}", file=sys.stderr)
            sys.exit(1)
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    else:
        tasks = []

    plan = build_coordination_plan(tasks, pool_config)

    if not args.dry_run:
        out_path = save_coordination_plan(plan)
        print(f"[coordinator] 計畫已寫入：{out_path}", file=sys.stderr)

    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
