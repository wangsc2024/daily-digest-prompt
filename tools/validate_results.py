#!/usr/bin/env python3
"""
ADR-026：results/todoist-auto-*.json 格式驗證工具

使用方式：
  uv run python tools/validate_results.py               # 驗證全部 results/todoist-auto-*.json
  uv run python tools/validate_results.py results/foo.json   # 驗證單一檔案
  uv run python tools/validate_results.py --dir results/ # 驗證指定目錄

回傳碼：0=全部通過，1=有驗證錯誤
"""
import json
import sys
from pathlib import Path

# 專案根目錄（tools/ 的上一層）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "config/schemas/results-auto-task-schema.json"
RESULTS_DIR = PROJECT_ROOT / "results"


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

    # 使用 hook_utils 的通用驗證函數（避免重複邏輯）
    sys.path.insert(0, str(PROJECT_ROOT / "hooks"))
    try:
        from hook_utils import validate_json_schema
        _, errors = validate_json_schema(data, schema)
        return errors
    except ImportError:
        return _fallback_validate(data, schema)


def _fallback_validate(data: dict, schema: dict) -> list[str]:
    """hook_utils 不可用時的基本必填欄位檢查。"""
    errors = []
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"缺少必填欄位: {field}")
    return errors


def find_result_files(target: str | None) -> list[Path]:
    """解析目標路徑，回傳待驗證檔案清單。"""
    if target is None:
        return sorted(RESULTS_DIR.glob("todoist-auto-*.json"))
    p = Path(target)
    if p.is_dir():
        return sorted(p.glob("todoist-auto-*.json"))
    return [p] if p.exists() else []


def main() -> int:
    # 解析簡單引數
    target = None
    args = sys.argv[1:]
    if args and args[0] == "--dir" and len(args) > 1:
        target = args[1]
    elif args and not args[0].startswith("--"):
        target = args[0]

    schema = load_schema()
    files = find_result_files(target)

    if not files:
        print("[INFO] 找不到符合條件的 results JSON 檔案，跳過驗證")
        return 0

    passed = 0
    failed = 0
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

    print(f"\n總計：{passed} 通過，{failed} 失敗（共 {len(files)} 個檔案）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
