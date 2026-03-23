#!/usr/bin/env python3
"""cleanup_state.py - State 檔案膨脹清理工具（ADR-045）

功能：
  1. kb-note-scores.json：移除 scored_at > 30 天的舊評分（保留最新）
  2. research-quality.json：歸檔 timestamp > N 天的舊記錄至 backups/state-archive/

用法：
  uv run python tools/cleanup_state.py            # 預設（乾跑，只顯示計畫）
  uv run python tools/cleanup_state.py --apply    # 實際執行清理
  uv run python tools/cleanup_state.py --days 30  # 自訂保留天數
"""
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = Path(__file__).parent.parent
STATE_DIR = PROJECT_ROOT / "state"
ARCHIVE_DIR = PROJECT_ROOT / "backups" / "state-archive"


def parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def cleanup_kb_note_scores(retention_days: int, apply: bool) -> dict:
    """清理 kb-note-scores.json：移除超過 retention_days 的評分記錄"""
    path = STATE_DIR / "kb-note-scores.json"
    if not path.exists():
        return {"skipped": True, "reason": "檔案不存在"}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    notes = data.get("notes", [])
    if not isinstance(notes, list):
        return {"skipped": True, "reason": "notes 格式不符（非 list）"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    before_count = len(notes)
    kept = [n for n in notes if (parse_dt(n.get("scored_at", "")) or cutoff) >= cutoff]
    removed = before_count - len(kept)

    original_size = path.stat().st_size
    result = {
        "file": str(path.name),
        "before": before_count,
        "after": len(kept),
        "removed": removed,
        "original_size_kb": round(original_size / 1024, 1),
    }

    if apply and removed > 0:
        data["notes"] = kept
        data["cleaned_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        new_size = path.stat().st_size
        result["new_size_kb"] = round(new_size / 1024, 1)
        result["saved_kb"] = round((original_size - new_size) / 1024, 1)

    return result


def archive_research_quality(retention_days: int, apply: bool) -> dict:
    """歸檔 research-quality.json：將舊記錄移至 backups/state-archive/"""
    path = STATE_DIR / "research-quality.json"
    if not path.exists():
        return {"skipped": True, "reason": "檔案不存在"}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        return {"skipped": True, "reason": "entries 格式不符（非 list）"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    before_count = len(entries)
    kept = [e for e in entries if (parse_dt(e.get("timestamp", "")) or cutoff) >= cutoff]
    archived = [e for e in entries if (parse_dt(e.get("timestamp", "")) or cutoff) < cutoff]

    original_size = path.stat().st_size
    result = {
        "file": str(path.name),
        "before": before_count,
        "after": len(kept),
        "archived": len(archived),
        "original_size_kb": round(original_size / 1024, 1),
    }

    if apply and archived:
        # 確保歸檔目錄存在
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        # 寫入歸檔檔案
        archive_name = f"research-quality-{datetime.now().strftime('%Y%m%d')}.json"
        archive_path = ARCHIVE_DIR / archive_name
        archive_data = {
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "source": str(path),
            "retention_days": retention_days,
            "entries": archived,
        }
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)

        # 更新原檔（只保留新記錄）
        data["entries"] = kept
        data["cleaned_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        new_size = path.stat().st_size
        result["new_size_kb"] = round(new_size / 1024, 1)
        result["saved_kb"] = round((original_size - new_size) / 1024, 1)
        result["archive_path"] = str(archive_path)

    return result


def main():
    parser = argparse.ArgumentParser(description="State 檔案膨脹清理工具（ADR-045）")
    parser.add_argument("--apply", action="store_true", help="實際執行清理（預設乾跑）")
    parser.add_argument("--days", type=int, default=30, help="保留天數（預設 30）")
    args = parser.parse_args()

    mode = "實際清理" if args.apply else "乾跑（加 --apply 才執行）"
    print(f"\n=== State 檔案清理（{mode}，保留 {args.days} 天）===\n")

    # 清理 kb-note-scores.json
    r1 = cleanup_kb_note_scores(retention_days=args.days, apply=args.apply)
    if r1.get("skipped"):
        print(f"kb-note-scores.json：跳過（{r1['reason']}）")
    else:
        if r1["removed"] == 0:
            print(f"kb-note-scores.json：{r1['before']} 筆，無需清理（全部在 {args.days} 天內）")
        else:
            saved = r1.get("saved_kb", "N/A")
            print(f"kb-note-scores.json：{r1['before']} → {r1['after']} 筆，移除 {r1['removed']} 筆（節省 {saved}KB）")

    # 歸檔 research-quality.json
    r2 = archive_research_quality(retention_days=args.days, apply=args.apply)
    if r2.get("skipped"):
        print(f"research-quality.json：跳過（{r2['reason']}）")
    else:
        if r2["archived"] == 0:
            print(f"research-quality.json：{r2['before']} 筆，無需歸檔（全部在 {args.days} 天內）")
        else:
            saved = r2.get("saved_kb", "N/A")
            archive = r2.get("archive_path", "（乾跑）")
            print(f"research-quality.json：{r2['before']} → {r2['after']} 筆，歸檔 {r2['archived']} 筆（節省 {saved}KB）")
            print(f"  歸檔至：{archive}")

    print()


if __name__ == "__main__":
    main()
