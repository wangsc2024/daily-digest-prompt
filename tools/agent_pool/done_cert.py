#!/usr/bin/env python3
"""
done_cert（完成憑證）生成與驗證（P5-A）

設計：只有通過 JSON schema 驗證的 Worker 結果，才能被 Coordinator 消費。
Phase 3 組裝前先呼叫 verify_done_cert()，確保結果完整後才組裝。

解決「Phase 2 結果缺失」架構級預防：
  - 舊模式：Phase 3 直接讀結果檔，若缺失才報錯（為時已晚）
  - 新模式：Worker 完成後即簽發 done_cert；Phase 3 只讀有憑證的結果

使用方式：
  # 簽發憑證（Worker 完成後）
  uv run python tools/agent_pool/done_cert.py --issue \\
      --task-id "test-task-001" --worker-type web_search \\
      --result-file results/todoist-auto-ai-research.json

  # 驗證憑證（Phase 3 組裝前）
  uv run python tools/agent_pool/done_cert.py --verify --task-id "test-task-001"

  # 批次驗證（Phase 3 組裝前全量確認）
  uv run python tools/agent_pool/done_cert.py --verify-all

  # 清理過期憑證（>24h，由 self-heal 呼叫）
  uv run python tools/agent_pool/done_cert.py --cleanup --max-age-hours 24
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
CERT_DIR = REPO_ROOT / "state" / "done-certs"


def _file_hash(path: Path) -> str | None:
    """串流讀取計算 SHA256（64KB 塊，防 OOM）。檔案不存在時回傳 None。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except FileNotFoundError:
        return None


def issue_cert(
    task_id: str,
    phase: int,
    worker_type: str,
    result_file: Path,
    schema_valid: bool = True,
) -> dict:
    """
    Worker 完成後簽發完成憑證。

    Args:
        task_id:      任務唯一識別碼
        phase:        階段（通常為 2）
        worker_type:  "web_search" | "kb_import" | "file_sync" | "notification"
        result_file:  結果 JSON 檔路徑
        schema_valid: 結果是否通過 schema 驗證

    Returns:
        已簽發的憑證 dict（同時寫入 state/done-certs/{task_id}.json）
    """
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    result_path = Path(result_file)

    cert = {
        "task_id": task_id,
        "phase": phase,
        "worker_type": worker_type,
        "result_file": str(result_path),
        "schema_valid": schema_valid,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "result_hash": _file_hash(result_path) if result_path.exists() else None,
    }
    cert_path = CERT_DIR / f"{task_id}.json"
    cert_path.write_text(
        json.dumps(cert, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cert


def verify_done_cert(task_id: str) -> tuple[bool, str]:
    """
    Phase 3 組裝前驗證：done_cert 存在且 result_file 未被篡改。

    Returns:
        (ok: bool, reason: str)
    """
    cert_path = CERT_DIR / f"{task_id}.json"
    if not cert_path.exists():
        return False, f"done_cert 不存在：{task_id}"

    try:
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"done_cert JSON 解析失敗：{e}"

    if not cert.get("schema_valid"):
        return False, f"schema 驗證未通過：{task_id}"

    result_file = Path(cert["result_file"])
    if not result_file.exists():
        return False, f"結果檔案已消失：{result_file}"

    stored_hash = cert.get("result_hash")
    if stored_hash and _file_hash(result_file) != stored_hash:
        return False, f"結果檔案 hash 不符（可能被篡改）：{task_id}"

    return True, "ok"


def verify_all_certs() -> dict:
    """
    批次驗證所有 done-certs。

    Returns:
        {
            "total": int, "passed": int, "failed": int,
            "results": [{"task_id": str, "ok": bool, "reason": str}, ...]
        }
    """
    if not CERT_DIR.exists():
        return {"total": 0, "passed": 0, "failed": 0, "results": []}

    results = []
    for cert_path in sorted(CERT_DIR.glob("*.json")):
        task_id = cert_path.stem
        ok, reason = verify_done_cert(task_id)
        results.append({"task_id": task_id, "ok": ok, "reason": reason})

    passed = sum(1 for r in results if r["ok"])
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }


def cleanup_stale_certs(max_age_hours: int = 24) -> dict:
    """
    清理超過 max_age_hours 的過期憑證（由 self-heal 定期呼叫）。

    Returns:
        {"removed": [str], "errors": [str]}
    """
    import time

    result = {"removed": [], "errors": []}
    if not CERT_DIR.exists():
        return result

    cutoff = time.time() - max_age_hours * 3600
    for cert_path in CERT_DIR.glob("*.json"):
        try:
            if cert_path.stat().st_mtime < cutoff:
                cert_path.unlink()
                result["removed"].append(cert_path.name)
        except OSError as e:
            result["errors"].append(f"{cert_path.name}: {e}")

    return result


def main():
    parser = argparse.ArgumentParser(description="done_cert — Phase 2 完成憑證系統")
    parser.add_argument("--issue", action="store_true", help="簽發憑證")
    parser.add_argument("--verify", action="store_true", help="驗證單一憑證")
    parser.add_argument("--verify-all", action="store_true", help="批次驗證所有憑證")
    parser.add_argument("--cleanup", action="store_true", help="清理過期憑證")
    parser.add_argument("--task-id", help="任務 ID（--issue / --verify 用）")
    parser.add_argument("--worker-type", default="web_search", help="Worker 類型（--issue 用）")
    parser.add_argument("--result-file", help="結果檔案路徑（--issue 用）")
    parser.add_argument("--phase", type=int, default=2, help="階段編號（預設 2）")
    parser.add_argument("--max-age-hours", type=int, default=24, help="清理閾值（小時）")
    args = parser.parse_args()

    if args.issue:
        if not args.task_id or not args.result_file:
            print("--issue 需要 --task-id 和 --result-file", file=sys.stderr)
            sys.exit(1)
        cert = issue_cert(args.task_id, args.phase, args.worker_type, Path(args.result_file))
        print(json.dumps(cert, ensure_ascii=False, indent=2))

    elif args.verify:
        if not args.task_id:
            print("--verify 需要 --task-id", file=sys.stderr)
            sys.exit(1)
        ok, reason = verify_done_cert(args.task_id)
        print(json.dumps({"ok": ok, "reason": reason}, ensure_ascii=False))
        sys.exit(0 if ok else 1)

    elif args.verify_all:
        summary = verify_all_certs()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        sys.exit(0 if summary["failed"] == 0 else 1)

    elif args.cleanup:
        result = cleanup_stale_certs(args.max_age_hours)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
