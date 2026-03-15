# -*- coding: utf-8 -*-
"""
依網站抓取的標題與課程簡介，更新專輯 md 的「核心議題」欄位。
僅使用網站內容，不自行編造；無網站資料時註明請依官網補充。
"""
import json
from pathlib import Path

MD_PATH = Path("d:/Source/daily-digest-prompt/docs/plans/淨土教觀學苑podcast專輯.md")
JSON_PATH = Path(__file__).resolve().parent / "jiaoguang_course_vol_titles.json"


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(MD_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        line_stripped = line.rstrip("\n")
        if not line_stripped.strip().startswith("|") or not line_stripped.strip().endswith("|"):
            new_lines.append(line)
            continue
        parts = [p.strip() for p in line_stripped.split("|") if p.strip() != ""]
        if len(parts) == 6 and parts[0].isdigit():
            ep_num, title, course, vol, cat, _old_topic = parts
            vols = data.get(course, {}).get("vols", {})
            site_title = vols.get(vol) if vol not in ("簡體", "繁體") else None
            intro = (data.get(course) or {}).get("intro", "").strip()

            if site_title:
                topic = f"本講：{site_title}。"
            elif intro:
                topic = intro[:80] + "…（課程簡介）" if len(intro) > 80 else intro + "（課程簡介）"
            else:
                topic = "（請依官網該課程講義／講記補充）"

            new_lines.append(f"| {ep_num} | {title} | {course} | {vol} | {cat} | {topic} |\n")
            continue
        new_lines.append(line)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print("已依網站內容更新核心議題欄位。")


if __name__ == "__main__":
    main()
