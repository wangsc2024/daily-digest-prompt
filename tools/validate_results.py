#!/usr/bin/env python3
"""
ADR-026/041: results/todoist-auto-*.json 格式驗證 + Agent Middleware 驗證層

使用方式：
  uv run python tools/validate_results.py               # 驗證全部 results/todoist-auto-*.json
  uv run python tools/validate_results.py results/foo.json   # 驗證單一檔案
  uv run python tools/validate_results.py --dir results/ # 驗證指定目錄

回傳碼：0=全部通過，1=有驗證錯誤
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "config/schemas/results-auto-task-schema.json"
RESULTS_DIR = PROJECT_ROOT / "results"

# 一次性路徑設定並快取 hook_utils 驗證函數（避免每次 validate_file 重複 insert）
_hooks_dir = str(PROJECT_ROOT / "hooks")
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)
try:
    from hook_utils import validate_json_schema as _validate_json_schema
except ImportError:
    _validate_json_schema = None


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        print(f"[WARN] Schema 不存在：{SCHEMA_PATH}，跳過驗證", file=sys.stderr)
        return {}
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate_file(path: Path, schema: dict) -> list[str]:
    """驗證單一 JSON 檔，回傳錯誤訊息清單（空 = 通過）。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON 解析失敗: {e}"]
    if not schema:
        return []
    if _validate_json_schema is not None:
        _, errors = _validate_json_schema(data, schema)
        return errors
    return _fallback_validate(data, schema)


def _fallback_validate(data: dict, schema: dict) -> list[str]:
    """hook_utils 不可用時的基本必填欄位檢查。"""
    return [
        f"缺少必填欄位: {field}"
        for field in schema.get("required", [])
        if field not in data
    ]


def middleware_validate(result_dict: dict) -> tuple[bool, list[str]]:
    """Agent Middleware 驗證層：驗證結果 JSON 必填欄位。"""
    errors = []
    if "task_type" not in result_dict and "agent" not in result_dict:
        errors.append("缺少必填欄位: task_type 或 agent")
    for field in ("task_key", "status", "summary"):
        if field not in result_dict:
            errors.append(f"缺少必填欄位: {field}")
    valid_statuses = {"success", "partial", "failed", "format_failed", "partial_success"}
    if "status" in result_dict and result_dict["status"] not in valid_statuses:
        errors.append(f"status 值不合法: {result_dict['status']}")
    return (not errors, errors)


def auto_fix_tier1(result_dict: dict, filename: str = "") -> dict:
    """自動補上可推斷的缺失欄位（Tier 1 修復）。"""
    fixed = dict(result_dict)
    stem = filename.replace("todoist-auto-", "").replace(".json", "") if filename else ""
    if stem:
        if "task_type" not in fixed and "agent" not in fixed:
            fixed["task_type"] = "auto"
            fixed["agent"] = f"todoist-auto-{stem}"
        if "task_key" not in fixed:
            fixed["task_key"] = stem
    if "summary" not in fixed:
        fixed["summary"] = "(auto-fixed: no summary provided)"
    return fixed


def find_result_files(target: str | None) -> list[Path]:
    """解析目標路徑，回傳待驗證檔案清單（包含 todoist-auto-* 和 todoist-result-*）。"""
    if target is None:
        return sorted(
            list(RESULTS_DIR.glob("todoist-auto-*.json"))
            + list(RESULTS_DIR.glob("todoist-result-*.json"))
        )
    p = Path(target)
    if p.is_dir():
        return sorted(
            list(p.glob("todoist-auto-*.json")) + list(p.glob("todoist-result-*.json"))
        )
    return [p] if p.exists() else []


def _print_validation_results(files: list[Path], schema: dict) -> tuple[int, int]:
    """驗證並印出結果，回傳 (passed, failed)。"""
    passed = failed = 0
    for path in files:
        errors = validate_file(path, schema)
        rel = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        if errors:
            failed += 1
            print(f"[FAIL] {rel}")
            for e in errors:
                print(f"       - {e}")
        else:
            passed += 1
            print(f"[ OK ] {rel}")
    return passed, failed


def _run_middleware_mode(args: list[str]) -> int:
    """--middleware 模式：驗證單一 result dict。"""
    if "--test" in args:
        test_data = {"task_key": "test", "status": "success", "summary": "test"}
        ok, errors = middleware_validate(test_data)
        print(f"middleware_validate test: ok={ok}, errors={errors}")
        fixed = auto_fix_tier1({}, "todoist-auto-test.json")
        print(f"auto_fix_tier1 test: {json.dumps(fixed, ensure_ascii=False)}")
        return 0
    print("[INFO] --middleware 模式需搭配 --test 或由其他工具呼叫")
    return 0


def _run_phase3_mode(soft_fail: bool) -> int:
    """--phase3 模式：驗證所有 todoist-auto/result JSON。"""
    schema = load_schema()
    files = sorted(
        list(RESULTS_DIR.glob("todoist-auto-*.json"))
        + list(RESULTS_DIR.glob("todoist-result-*.json"))
    )
    if not files:
        print("[INFO] results/ 無 JSON 檔案")
        return 0
    passed, failed = _print_validation_results(files, schema)
    print(f"\nPhase 3 驗證：{passed} 通過，{failed} 失敗（共 {len(files)} 個檔案）")
    return 0 if (soft_fail or failed == 0) else 1


def main() -> int:
    args = sys.argv[1:]
    if "--middleware" in args:
        return _run_middleware_mode(args)
    if "--phase3" in args:
        return _run_phase3_mode("--soft-fail" in args)
    target = None
    if args and args[0] == "--dir" and len(args) > 1:
        target = args[1]
    elif args and not args[0].startswith("--"):
        target = args[0]

    schema = load_schema()
    files = find_result_files(target)
    if not files:
        print("[INFO] 找不到符合條件的 results JSON 檔案，跳過驗證")
        return 0
    passed, failed = _print_validation_results(files, schema)
    print(f"\n總計：{passed} 通過，{failed} 失敗（共 {len(files)} 個檔案）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
