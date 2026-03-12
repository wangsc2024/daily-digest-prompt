#!/usr/bin/env python3
"""
不可變審計日誌驗證工具（P4-D）— 鏈式 hash 完整性驗證

設計：
  - post_tool_logger.py 的 append_with_checksum() 為每筆記錄計算
    SHA256（排除 _hash 欄位本身，避免循環依賴），存入 _hash 欄位
  - 每筆記錄的 _prev_hash 指向前一筆的 _hash（鏈式結構）
  - 本工具驗證：重算 hash 是否一致、鏈式連接是否未斷

遇到 rotation_marker（50MB 輪轉標記）時重置鏈起點，不視為斷鏈。

使用方式：
  uv run python tools/audit_verify.py --log logs/structured/hooks.jsonl
  uv run python tools/audit_verify.py --log-dir logs/structured/
  uv run python tools/audit_verify.py --mission-alignment
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).parent.parent
LOG_DIR = REPO_ROOT / "logs" / "structured"
BACKLOG_PATH = REPO_ROOT / "context" / "improvement-backlog.json"
MISSION_PATH = REPO_ROOT / "context" / "mission.yaml"


def _compute_entry_hash(entry: dict) -> str:
    """
    計算 entry 的 hash（排除 _hash 欄位本身）。
    與 post_tool_logger.py append_with_checksum() 使用相同方法。
    """
    payload = {k: v for k, v in entry.items() if k != "_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def _iter_jsonl(path: Path) -> Iterator[tuple[int, dict]]:
    """逐行解析 JSONL，回傳 (行號, dict) 的迭代器。"""
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield lineno, json.loads(line)
            except json.JSONDecodeError:
                yield lineno, {"_parse_error": True, "_raw": line[:100]}


def verify_log_file(path: Path) -> dict:
    """
    驗證單一 JSONL 日誌的鏈式完整性。

    Returns:
        {
            "file": str, "total": int, "valid": int, "errors": list[str],
            "rotations": int, "passed": bool
        }
    """
    errors = []
    valid_count = 0
    rotation_count = 0
    prev_hash = ""
    total = 0

    for lineno, entry in _iter_jsonl(path):
        total += 1

        if entry.get("_parse_error"):
            errors.append(f"L{lineno}: JSON 解析失敗")
            prev_hash = ""  # 斷鏈後重置
            continue

        # 輪轉標記：重置鏈起點（不視為錯誤）
        if entry.get("_type") == "rotation_marker":
            rotation_count += 1
            prev_hash = entry.get("_hash", "")
            valid_count += 1
            continue

        stored_hash = entry.get("_hash")

        # 若記錄不含 _hash（舊格式），跳過驗證
        if stored_hash is None:
            valid_count += 1
            continue

        # 驗證 _prev_hash 一致性
        entry_prev = entry.get("_prev_hash", "")
        if entry_prev != prev_hash:
            errors.append(
                f"L{lineno}: _prev_hash 不符（期望 '{prev_hash[:8]}...'，"
                f"實際 '{entry_prev[:8]}...'）"
            )

        # 驗證 hash 重算一致性
        computed = _compute_entry_hash(entry)
        if computed != stored_hash:
            errors.append(
                f"L{lineno}: hash 不符（期望 '{stored_hash}'，"
                f"重算 '{computed}'）— 可能被篡改"
            )
        else:
            valid_count += 1

        prev_hash = stored_hash

    passed = len(errors) == 0
    return {
        "file": str(path),
        "total": total,
        "valid": valid_count,
        "errors": errors[:20],  # 最多顯示 20 個錯誤
        "rotations": rotation_count,
        "passed": passed,
    }


def verify_log_dir(log_dir: Path) -> dict:
    """批次驗證目錄下所有 JSONL 日誌。"""
    if not log_dir.exists():
        return {"error": f"目錄不存在：{log_dir}", "files_checked": 0, "all_passed": True}

    results = []
    for jsonl_file in sorted(log_dir.glob("*.jsonl")):
        results.append(verify_log_file(jsonl_file))

    all_passed = all(r["passed"] for r in results)
    return {
        "log_dir": str(log_dir),
        "files_checked": len(results),
        "all_passed": all_passed,
        "results": results,
    }


def check_mission_alignment() -> dict:
    """
    P4-D：查詢 improvement-backlog.json 的目標對齊狀況。
    統計每個 goal_id 的任務數，確認任務都有對齊目標。
    """
    if not BACKLOG_PATH.exists():
        return {"error": "improvement-backlog.json 不存在"}
    if not MISSION_PATH.exists():
        return {"error": "context/mission.yaml 不存在"}

    try:
        backlog = json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))
        items = backlog if isinstance(backlog, list) else backlog.get("items", [])
    except (json.JSONDecodeError, Exception) as e:
        return {"error": f"解析失敗：{e}"}

    try:
        import yaml
        mission = yaml.safe_load(MISSION_PATH.read_text(encoding="utf-8"))
        goals = {g["id"]: g["title"] for g in mission.get("goals", [])}
    except ImportError:
        goals = {}

    goal_counts: dict[str, int] = {}
    no_goal = 0

    for item in items:
        goal_id = item.get("goal_id")
        if goal_id:
            goal_counts[goal_id] = goal_counts.get(goal_id, 0) + 1
        else:
            no_goal += 1

    alignment = []
    for gid, title in goals.items():
        count = goal_counts.get(gid, 0)
        alignment.append({
            "goal_id": gid,
            "title": title,
            "backlog_items": count,
        })

    return {
        "total_items": len(items),
        "items_with_goal": len(items) - no_goal,
        "items_without_goal": no_goal,
        "goal_alignment": alignment,
    }


def main():
    parser = argparse.ArgumentParser(description="審計日誌鏈式完整性驗證（P4-D）")
    parser.add_argument("--log", help="驗證單一 JSONL 日誌檔案")
    parser.add_argument("--log-dir", help="批次驗證目錄（預設 logs/structured/）")
    parser.add_argument("--mission-alignment", action="store_true", help="查詢目標對齊狀況")
    args = parser.parse_args()

    if args.mission_alignment:
        result = check_mission_alignment()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.log:
        result = verify_log_file(Path(args.log))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["passed"] else 1)

    # 預設：批次驗證 logs/structured/
    log_dir = Path(args.log_dir) if args.log_dir else LOG_DIR
    result = verify_log_dir(log_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["all_passed"] else 1)


if __name__ == "__main__":
    main()
