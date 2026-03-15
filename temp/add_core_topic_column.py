# -*- coding: utf-8 -*-
"""Add 核心議題 column to 淨土教觀學苑podcast專輯.md table. One sentence per episode."""

# 每門課程一句核心主題，供該課程所有講次共用；錄製時可依講義再細修
COURSE_THEMES = {
    "聞法儀軌": "聞法前之恭敬、發心與如法儀軌",
    "皈依的意義與方法": "皈依三寶的意義與如法行持",
    "懺悔法門": "懺悔的理觀與事修",
    "受戒須知": "受戒前之認識與準備",
    "五戒修學述要": "五戒內容與持犯開遮",
    "佛法修學概要": "佛法修學次第與綱要",
    "菩提心修學述要": "發菩提心之次第與實踐",
    "唯識與淨土(義德寺)": "唯識與淨土法門之會通",
    "唯識學概要": "唯識名相與義理綱要",
    "佛說阿彌陀經導讀(義德寺)": "阿彌陀經要義導讀",
    "阿彌陀佛四十八願導讀": "四十八願內容與修行實踐",
    "大勢至菩薩念佛圓通章導讀": "念佛圓通法門要義",
    "淨土十疑論導讀(義德寺)": "淨土常見疑難之釋疑",
    "佛說觀無量壽佛經": "觀經十六觀與淨業三福",
    "印光大師文鈔選讀": "印祖開示之修行要點",
    "淨心與淨土": "心淨則國土淨之理觀與事修",
    "靈峰宗論導讀": "蕅益大師宗論要義",
    "大乘百法明門論直解": "百法名相與唯識入門",
    "八識規矩頌直解": "八識體用與轉識成智",
    "唯識三十頌直解(淨律學佛院)": "三十頌唯識綱要",
    "菩薩戒修學法要": "菩薩戒持犯與懺悔",
    "瑜伽菩薩戒本講表": "瑜伽菩薩戒條與開遮",
    "修習止觀坐禪法要": "止觀坐禪之次第與要領",
    "天台教觀綱宗": "天台教觀綱宗要義",
    "楞嚴經修學法要": "楞嚴經修學綱領",
    "禪觀與淨土 一、基礎篇(台北)": "禪觀與淨土之基礎",
    "禪觀與淨土 二、觀照篇(台北)": "觀照與念佛",
    "禪觀與淨土 三、念佛篇(台北)": "念佛與往生",
    "禪觀與淨土 四、往生篇(台北)": "往生資糧與正念",
    "攝大乘論講表": "攝大乘論要義",
    "大乘起信論講表": "大乘起信論一心二門",
    "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經": "楞嚴經修證了義",
    "佛說阿彌陀經要解(淨律學佛院)": "阿彌陀經要解精要",
    "佛遺教經": "佛遺教經要義",
    "佛說四十二章經": "四十二章經要義",
}

def core_topic(course: str, vol: str) -> str:
    theme = COURSE_THEMES.get(course, "本課程核心要義")
    if vol in ("講記全冊", "修學綱要", "講記(全)"):
        return f"本講闡述「{course}」{vol}：{theme}。"
    return f"本講闡述「{course}」第{vol}講：{theme}。"

def main():
    md_path = "d:/Source/daily-digest-prompt/docs/plans/淨土教觀學苑podcast專輯.md"
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Table: header has 5 columns, then data rows
    header1 = "| 集數 | 題目名稱 | 對應課程 | 對應卷次 | 所屬類別 |"
    header2 = "| --- | --- | --- | --- | --- |"
    new_header1 = "| 集數 | 題目名稱 | 對應課程 | 對應卷次 | 所屬類別 | 核心議題 |"
    new_header2 = "| --- | --- | --- | --- | --- | --- |"

    if new_header1 in content:
        print("Already has 核心議題 column.")
        return

    lines = content.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == header1.strip():
            new_lines.append(new_header1)
            i += 1
            if i < len(lines) and lines[i].strip() == header2.strip():
                new_lines.append(new_header2)
                i += 1
            continue
        # Data row: | N | title | course | vol | cat |
        if line.strip().startswith("|") and line.strip().endswith("|"):
            parts = [p.strip() for p in line.split("|") if p.strip() != ""]
            if len(parts) == 5 and parts[0].isdigit():
                ep_num, title, course, vol, cat = parts
                topic = core_topic(course, vol)
                new_lines.append(f"| {ep_num} | {title} | {course} | {vol} | {cat} | {topic} |")
                i += 1
                continue
        new_lines.append(line)
        i += 1

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))
    print("Added 核心議題 column to all rows.")

if __name__ == "__main__":
    main()
