#!/usr/bin/env python3
"""
行程規劃大綱產出工具。

依使用者提供的開始日期、開始時間、限制條件，產出包含目標、必訪地點類型
（市場、文化、景點）、排除項目（溫泉、夜市、寺廟）的規劃大綱。

使用方式：
  uv run python tools/trip_plan_outline.py --date 2026-03-21 --time 09:00 --constraints "三天兩夜、台北、大眾運輸、預算中等"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 地區關鍵字 → 預設建議（市場、文化、景點，皆排除溫泉/夜市/寺廟）
REGION_SUGGESTIONS: dict[str, dict[str, list[str]]] = {
    "台北": {
        "market": ["南門市場（台北市中正區）– 傳統南北貨與熟食", "東門市場（大安區）– 在地食材與小吃"],
        "cultural": ["國立故宮博物院 – 中華文物典藏", "松山文創園區 – 藝文展覽與文創"],
        "attraction": ["陽明山國家公園 – 自然景觀與步道", "大稻埕碼頭 – 河岸休閒"],
    },
    "新北": {
        "market": ["三峽老街市場 – 傳統市集與藍染文化", "淡水老街市集 – 在地特產"],
        "cultural": ["十三行博物館 – 考古與史前文化", "鶯歌陶瓷博物館 – 陶藝文化"],
        "attraction": ["九份山城 – 山城景觀與懷舊", "十分瀑布 – 自然景觀"],
    },
    "屏東": {
        "market": ["屏東中央市場 – 傳統市集與在地食材", "東港華僑市場 – 海鮮與在地特產"],
        "cultural": ["屏東美術館 – 藝文展覽", "恆春古城 – 歷史古蹟"],
        "attraction": ["墾丁國家公園 – 海岸與自然景觀", "大鵬灣 – 潟湖生態"],
    },
    "高雄": {
        "market": ["哈瑪星代天宮市場 – 傳統市集", "三民市場 – 在地小吃與食材"],
        "cultural": ["高雄市立美術館 – 當代藝術", "駁二藝術特區 – 文創與展覽"],
        "attraction": ["西子灣 – 海岸景觀", "壽山 – 自然步道"],
    },
    "台中": {
        "market": ["第二市場 – 傳統市集與美食", "第五市場 – 在地食材"],
        "cultural": ["國立台灣美術館 – 當代藝術", "霧峰林家花園 – 歷史建築"],
        "attraction": ["高美濕地 – 生態景觀", "彩虹眷村 – 藝術彩繪"],
    },
    "台南": {
        "market": ["水仙宮市場 – 傳統市集", "東菜市 – 在地食材"],
        "cultural": ["奇美博物館 – 藝術與樂器典藏", "赤崁樓 – 歷史古蹟"],
        "attraction": ["安平古堡周邊 – 歷史與海岸", "四草綠色隧道 – 紅樹林生態"],
    },
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")

EXCLUSIONS = ["溫泉", "夜市", "寺廟"]


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


def validate_date(value: str) -> ValidationResult:
    if not DATE_RE.match(value):
        return ValidationResult(False, ["日期格式錯誤，請使用 YYYY-MM-DD（例：2026-03-21）"])
    try:
        parts = value.split("-")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        if m < 1 or m > 12 or d < 1 or d > 31:
            return ValidationResult(False, ["日期數值無效"])
    except (ValueError, IndexError):
        return ValidationResult(False, ["日期格式錯誤"])
    return ValidationResult(True, [])


def validate_time(value: str) -> ValidationResult:
    if not TIME_RE.match(value):
        return ValidationResult(False, ["時間格式錯誤，請使用 24 小時制 HH:MM（例：09:00）"])
    try:
        parts = value.split(":")
        h, m = int(parts[0]), int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            return ValidationResult(False, ["時間數值無效"])
    except (ValueError, IndexError):
        return ValidationResult(False, ["時間格式錯誤"])
    return ValidationResult(True, [])


def parse_constraints(text: str) -> dict[str, str | list[str]]:
    """從限制條件文字萃取出結構化資訊。"""
    parsed: dict[str, str | list[str]] = {}
    t = text.strip()
    # 天數
    for m in re.finditer(r"(\d+)\s*天", t):
        parsed["days"] = m.group(1)
        break
    for m in re.finditer(r"(\d+)\s*夜", t):
        parsed["nights"] = m.group(1)
        break
    # 預算
    if "預算" in t or "預算" in t:
        if "高" in t or "充裕" in t:
            parsed["budget"] = "高"
        elif "低" in t or "省" in t or "便宜" in t:
            parsed["budget"] = "低"
        else:
            parsed["budget"] = "中"
    # 交通
    if "大眾運輸" in t or "公車" in t or "捷運" in t or "火車" in t:
        parsed["transport"] = "大眾運輸"
    elif "開車" in t or "自駕" in t:
        parsed["transport"] = "自駕"
    # 地區
    for region in REGION_SUGGESTIONS:
        if region in t:
            parsed["region"] = region
            break
    return parsed


def infer_goal(constraints: dict[str, str | list[str]], constraints_text: str) -> str:
    """根據限制條件推斷行程目標。"""
    days = constraints.get("days", "")
    region = constraints.get("region", "")
    budget = constraints.get("budget", "")
    transport = constraints.get("transport", "")

    parts = []
    if days:
        parts.append(f"在 {days} 天內")
    if region:
        parts.append(f"深度體驗{region}在地文化與景觀")
    else:
        parts.append("深度體驗當地文化與景觀")
    if budget == "低":
        parts.append("，以經濟實惠方式")
    elif budget == "高":
        parts.append("，享受優質體驗")
    if transport == "大眾運輸":
        parts.append("，全程使用大眾運輸")

    if parts:
        return "".join(parts) + "。"
    return "依限制條件安排符合需求的行程，涵蓋傳統市場、文化場所與自然景點。"


def get_suggestions(
    constraints: dict[str, str | list[str]],
    suggestions_json: Path | None,
) -> dict[str, list[str]]:
    """取得必訪地點建議。"""
    if suggestions_json and suggestions_json.exists():
        try:
            data = json.loads(suggestions_json.read_text(encoding="utf-8"))
            return {
                "market": data.get("market", []),
                "cultural": data.get("cultural", []),
                "attraction": data.get("attraction", []),
            }
        except (json.JSONDecodeError, OSError):
            pass

    region = constraints.get("region")
    if region and region in REGION_SUGGESTIONS:
        return REGION_SUGGESTIONS[region].copy()

    return {
        "market": ["請依限制條件使用 WebSearch 查詢傳統市場建議（排除夜市）"],
        "cultural": ["請依限制條件使用 WebSearch 查詢博物館/古蹟/藝文展覽（排除寺廟）"],
        "attraction": ["請依限制條件使用 WebSearch 查詢自然景觀或著名景區（排除溫泉）"],
    }


def format_outline(
    goal: str,
    suggestions: dict[str, list[str]],
    exclusions: list[str],
) -> str:
    """產出規劃大綱文字。"""
    lines = [
        "# 行程規劃大綱",
        "",
        "## 1. 行程目標",
        "",
        f"- {goal}",
        "",
        "## 2. 必訪地點類型",
        "",
        "### a. 市場（傳統市集，不含夜市）",
    ]
    for s in suggestions.get("market", []):
        lines.append(f"   - {s}")
    lines.extend([
        "",
        "### b. 文化（博物館、古蹟、藝文展覽，不含寺廟）",
    ])
    for s in suggestions.get("cultural", []):
        lines.append(f"   - {s}")
    lines.extend([
        "",
        "### c. 景點（自然景觀、著名景區，不含溫泉）",
    ])
    for s in suggestions.get("attraction", []):
        lines.append(f"   - {s}")
    lines.extend([
        "",
        "## 3. 排除項目",
        "",
    ])
    for e in exclusions:
        lines.append(f"- {e}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="行程規劃大綱產出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--date", required=True, help="開始日期，格式 YYYY-MM-DD")
    parser.add_argument("--time", required=True, help="開始時間，24 小時制 HH:MM")
    parser.add_argument("--constraints", required=True, help="限制條件（文字敘述）")
    parser.add_argument(
        "--suggestions-json",
        type=Path,
        help="地點建議 JSON 檔，含 market/cultural/attraction 陣列",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="輸出檔案路徑，未指定則輸出至 stdout",
    )
    args = parser.parse_args()

    errors: list[str] = []

    dr = validate_date(args.date)
    if not dr.valid:
        errors.extend(dr.errors)

    tr = validate_time(args.time)
    if not tr.valid:
        errors.extend(tr.errors)

    if not args.constraints.strip():
        errors.append("限制條件不可為空")

    if errors:
        for e in errors:
            print(f"錯誤：{e}", file=sys.stderr)
        return 1

    constraints = parse_constraints(args.constraints)
    goal = infer_goal(constraints, args.constraints)
    suggestions = get_suggestions(constraints, args.suggestions_json)
    outline = format_outline(goal, suggestions, EXCLUSIONS)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(outline, encoding="utf-8")
        print(f"已寫入：{args.output}", file=sys.stderr)
    else:
        print(outline)

    return 0


if __name__ == "__main__":
    sys.exit(main())
