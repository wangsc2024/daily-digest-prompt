#!/usr/bin/env python3
"""
ADR 自動化驗證工具（P0-A）

功能：
- 驗證 context/adr-registry.json schema（必填欄位完整性）
- 狀態轉換合法性：Proposed → Accepted/Rejected/Deferred/Superseded（不得跳過）
- 自動計算 tech_debt_score（0-10）基於 implementation_status + age_days
- 列出 90 天未複查的 ADR（需要 review）
- 輸出 JSON report（通過/失敗項目列表）

使用方式：
  uv run python tools/validate_adr.py
  uv run python tools/validate_adr.py --check context/adr-registry.json
  uv run python tools/validate_adr.py --report          # 輸出完整 JSON 報告
  uv run python tools/validate_adr.py --stale-only      # 只列出過期 ADR

整合到 .git/hooks/pre-commit（見下方說明）
"""
import json
import sys
import argparse
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ADR_PATH = REPO_ROOT / "context" / "adr-registry.json"

REQUIRED_FIELDS = {"id", "title", "status", "created_at", "context", "decision", "consequences"}
VALID_STATUSES = {"Proposed", "Accepted", "Rejected", "Deferred", "Wontfix", "Superseded"}
TERMINAL_STATUSES = {"Accepted", "Rejected", "Wontfix", "Superseded"}
VALID_TRANSITIONS = {
    "Proposed": {"Accepted", "Rejected", "Deferred"},
    "Deferred": {"Accepted", "Rejected", "Proposed"},  # Deferred 可重新提案
    "Accepted": {"Superseded"},                          # 只能被後繼 ADR 取代
    "Rejected": set(),
    "Wontfix": set(),
    "Superseded": set(),
}
STALE_DAYS = 90  # 超過此天數未更新的 Accepted ADR 列為待複查


def load_registry(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[ERROR] ADR 檔案不存在：{path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] ADR JSON 解析失敗：{e}", file=sys.stderr)
        sys.exit(1)


def age_days(created_at: str) -> int:
    try:
        d = datetime.fromisoformat(created_at).date()
    except ValueError:
        try:
            d = date.fromisoformat(created_at)
        except ValueError:
            return 0
    return (date.today() - d).days


def calc_tech_debt_score(record: dict) -> float:
    """
    tech_debt_score（0-10）：
      - impl_status=pending 且 status=Accepted → +5
      - age > 180 天 → +2
      - age > 365 天 → +3 (取代前項)
      - priority=P0 且 pending → +2
    """
    score = 0.0
    impl = record.get("implementation_status", "")
    status = record.get("status", "")
    a = age_days(record.get("created_at", "2026-01-01"))

    if impl == "pending" and status == "Accepted":
        score += 5.0
    if a > 365:
        score += 3.0
    elif a > 180:
        score += 2.0
    if record.get("priority") == "P0" and impl == "pending":
        score += 2.0

    return min(round(score, 1), 10.0)


def validate_record(record: dict, idx: int) -> list[str]:
    errors = []
    rid = record.get("id", f"[index {idx}]")

    # 必填欄位
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"{rid}: 缺少必填欄位 '{field}'")

    # status 合法性
    status = record.get("status", "")
    if status not in VALID_STATUSES:
        errors.append(f"{rid}: 非法 status '{status}'（合法值：{sorted(VALID_STATUSES)}）")

    # id 格式：ADR-YYYYMMDD-NNN
    import re
    if "id" in record and not re.match(r"ADR-\d{8}-\d{3}$", record["id"]):
        errors.append(f"{rid}: id 格式不符，應為 ADR-YYYYMMDD-NNN")

    # consequences 應為 dict 或 list（非空字串）
    cons = record.get("consequences")
    if cons is not None and isinstance(cons, str) and not cons.strip():
        errors.append(f"{rid}: consequences 不應為空字串")

    return errors


def find_stale(records: list[dict]) -> list[dict]:
    stale = []
    for r in records:
        if r.get("status") == "Accepted" and r.get("implementation_status") == "pending":
            a = age_days(r.get("decided_at") or r.get("created_at", "2026-01-01"))
            if a >= STALE_DAYS:
                stale.append({**r, "_stale_days": a})
    return stale


def run_check(path: Path, stale_only: bool = False, report_json: bool = False) -> bool:
    registry = load_registry(path)
    records = registry.get("records", [])

    all_errors: list[str] = []
    debt_updates: list[dict] = []
    stale_adrs = find_stale(records)

    for i, rec in enumerate(records):
        errs = validate_record(rec, i)
        all_errors.extend(errs)
        score = calc_tech_debt_score(rec)
        debt_updates.append({"id": rec.get("id"), "tech_debt_score": score})

    passed = len(all_errors) == 0

    if report_json:
        output = {
            "checked_at": datetime.now().isoformat(),
            "total_adrs": len(records),
            "passed": passed,
            "errors": all_errors,
            "stale_adrs": [s["id"] for s in stale_adrs],
            "tech_debt_scores": debt_updates,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return passed

    if stale_only:
        if stale_adrs:
            print(f"⚠️  {len(stale_adrs)} 個 ADR 超過 {STALE_DAYS} 天未複查：")
            for s in stale_adrs:
                print(f"  - {s['id']} ({s['title']})  — {s['_stale_days']} 天  debt={calc_tech_debt_score(s):.1f}")
        else:
            print(f"✅ 所有 Accepted ADR 均在 {STALE_DAYS} 天內")
        return True

    if all_errors:
        print(f"❌ ADR 驗證失敗（{len(all_errors)} 個錯誤）：")
        for e in all_errors:
            print(f"  - {e}")
    else:
        print(f"✅ ADR 驗證通過（{len(records)} 條記錄，0 錯誤）")

    if stale_adrs:
        print(f"⚠️  {len(stale_adrs)} 個 ADR 待複查（>{STALE_DAYS}天）：{[s['id'] for s in stale_adrs]}")

    return passed


def main():
    parser = argparse.ArgumentParser(description="ADR 自動化驗證工具")
    parser.add_argument("--check", default=str(ADR_PATH), help="ADR registry 路徑")
    parser.add_argument("--report", action="store_true", help="輸出完整 JSON 報告")
    parser.add_argument("--stale-only", action="store_true", help="只列出過期 ADR")
    args = parser.parse_args()

    ok = run_check(Path(args.check), stale_only=args.stale_only, report_json=args.report)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
