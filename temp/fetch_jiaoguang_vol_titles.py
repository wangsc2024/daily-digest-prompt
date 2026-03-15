# -*- coding: utf-8 -*-
"""
從淨土教觀學苑課程 detail 頁抓取各講的網站標題，寫入 JSON。
核心議題僅使用網站上的內容（表格內標題或課程簡介），不自行編造。
"""
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://www.masterchingche.org/course/detail"

# 與 build_jiaoguangzong_300.py 對應：課程名稱 -> detail 頁 id（從專輯 md 連結取得）
COURSE_IDS = {
    "聞法儀軌": 1210,
    "皈依的意義與方法": 1213,
    "懺悔法門": 1216,
    "受戒須知": 1219,
    "五戒修學述要": 1222,
    "佛法修學概要": 1227,
    "菩提心修學述要": 1276,
    "唯識與淨土(義德寺)": 1283,
    "唯識學概要": 1288,
    "佛說阿彌陀經導讀(義德寺)": 1324,
    "阿彌陀佛四十八願導讀": 1338,
    "大勢至菩薩念佛圓通章導讀": 1350,
    "淨土十疑論導讀(義德寺)": 1355,
    "佛說觀無量壽佛經": 1362,
    "印光大師文鈔選讀": 1384,
    "淨心與淨土": 1409,
    "靈峰宗論導讀": 1419,
    "大乘百法明門論直解": 1446,
    "八識規矩頌直解": 1469,
    "唯識三十頌直解(淨律學佛院)": 1488,
    "菩薩戒修學法要": 1517,
    "瑜伽菩薩戒本講表": 1525,
    "修習止觀坐禪法要": 1555,
    "天台教觀綱宗": 1584,
    "楞嚴經修學法要": 1625,
    "禪觀與淨土 一、基礎篇(台北)": 1656,
    "禪觀與淨土 二、觀照篇(台北)": 1663,
    "禪觀與淨土 三、念佛篇(台北)": 1670,
    "禪觀與淨土 四、往生篇(台北)": 1677,
    "攝大乘論講表": 1685,
    "大乘起信論講表": 1754,
    "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經": 1797,
    "佛說阿彌陀經要解(淨律學佛院)": 1932,
    "佛遺教經": 1971,
    "佛說四十二章經": 1984,
}


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").strip()


def extract_table_vol_titles(html: str) -> dict[str, str]:
    """從課程 detail 頁 HTML 擷取表格：卷次 -> 該列第一個有意義的標題文字。"""
    vols = {}
    # 找 <table> 內所有 <tr>，跳過表頭（卷次 | 線上聽經...）
    table = re.search(r"<table[^>]*>.*?</table>", html, re.DOTALL | re.IGNORECASE)
    if not table:
        return vols
    table_html = table.group(0)
    # 每個 <tr>...</tr>
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr.group(1), re.DOTALL | re.IGNORECASE)
        if not cells:
            continue
        vol = strip_tags(cells[0]).strip()
        if not vol or vol == "卷次" or vol in ("簡體", "繁體"):
            continue
        # 取第一個非空、且看起來像標題的儲存格（非純數字、非純連結）
        title = ""
        for c in cells[1:]:
            t = strip_tags(c).strip()
            if not t:
                continue
            # 略過純數字、純「第N集」若已有更好標題則仍可採用
            if len(t) < 2:
                continue
            # 略過看起來是連結文字的
            if t.startswith("http") or "下載" in t or "YouTube" in t:
                continue
            title = t
            break
        if title:
            vols[vol] = title
    return vols


def extract_intro(html: str) -> str:
    """擷取課程簡介：<h1> 之後、<table> 之前的正文。"""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    before_table = re.split(r"<table", html, maxsplit=1, flags=re.IGNORECASE)[0]
    paras = re.findall(r"<p[^>]*>(.*?)</p>", before_table, re.DOTALL | re.IGNORECASE)
    for p in paras:
        t = strip_tags(p).strip()
        if len(t) > 30:
            return t[:500]
    # 若無 <p>：取 </h1> 與 <table> 之間所有文字
    between = re.search(r"</h1>\s*(.*?)<table", before_table, re.DOTALL | re.IGNORECASE)
    if between:
        t = strip_tags(between.group(1)).strip()
        if len(t) > 30:
            return t[:500]
    return ""


def main():
    out_path = Path(__file__).resolve().parent / "jiaoguang_course_vol_titles.json"
    result = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; podcast-plan)"})

    for course_name, cid in COURSE_IDS.items():
        url = f"{BASE}/{cid}"
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            html = r.text
        except Exception as e:
            print(f"[WARN] {course_name} ({cid}): {e}")
            result[course_name] = {"intro": "", "vols": {}}
            time.sleep(0.5)
            continue

        intro = extract_intro(html)
        vols = extract_table_vol_titles(html)
        result[course_name] = {"intro": intro, "vols": vols}
        n = len(vols)
        print(f"{course_name}: intro={len(intro)}字, {n} 講有網站標題")
        time.sleep(0.3)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {out_path}")


if __name__ == "__main__":
    main()
