# -*- coding: utf-8 -*-
"""Build full-episode list for 淨土教觀學苑 podcast from 聞法次第 course structure."""
# Data from https://www.masterchingche.org/course/3 and each course/detail page
# 全輯涵蓋五大類 35 門課，共 750 集

COURSES = [
    ("新學入門", "聞法儀軌", 2, ["001", "002"]),
    ("新學入門", "皈依的意義與方法", 2, ["001", "002"]),
    ("新學入門", "懺悔法門", 2, ["001", "002"]),
    ("新學入門", "受戒須知", 2, ["001", "002"]),
    ("新學入門", "五戒修學述要", 4, ["001", "002", "003", "004"]),
    ("新學入門", "佛法修學概要", 48, ["修學綱要"] + [f"{i:03d}" for i in range(1, 21)] + ["020_期中座談1", "020_期中座談2"] + [f"{i:03d}" for i in range(21, 29)] + ["028_期中座談3", "028_期中座談4"] + [f"{i:03d}" for i in range(29, 37)] + ["036_期中座談5"] + [f"{i:03d}" for i in range(37, 41)] + ["040_期中座談6", "040_期中座談7"]),
    ("新學入門", "菩提心修學述要", 6, [f"{i:03d}" for i in range(1, 7)]),
    ("新學入門", "唯識與淨土(義德寺)", 4, ["001", "002", "003", "004"]),
    ("新學入門", "唯識學概要", 34, ["講記全冊"] + [f"{i:03d}" for i in range(1, 13)] + ["013_期中研討_1", "014_期中研討_2"] + [f"{i:03d}" for i in range(15, 21)] + ["021_期中研討_3", "022_期中研討_4"] + [f"{i:03d}" for i in range(23, 27)] + ["027_期中研討_5", "028_期中研討_6"] + [f"{i:03d}" for i in range(29, 34)]),
    ("淨土必修", "佛說阿彌陀經導讀(義德寺)", 13, ["講記全冊"] + [f"{i:03d}" for i in range(1, 13)]),
    ("淨土必修", "阿彌陀佛四十八願導讀", 11, ["講記全冊"] + [f"{i:03d}" for i in range(1, 11)]),
    ("淨土必修", "大勢至菩薩念佛圓通章導讀", 4, ["001", "002", "003", "004"]),
    ("淨土必修", "淨土十疑論導讀(義德寺)", 6, [f"{i:03d}" for i in range(1, 7)]),
    ("淨土必修", "佛說觀無量壽佛經", 21, ["001", "001_1"] + [f"{i:03d}" for i in range(2, 21)]),
    ("淨土必修", "印光大師文鈔選讀", 24, [f"{i:03d}" for i in range(1, 25)]),
    ("淨土必修", "淨心與淨土", 8, [f"{i:03d}" for i in range(1, 9)]),
    ("深入廣學", "靈峰宗論導讀", 26, [f"{i:03d}" for i in range(1, 27)]),
    ("深入廣學", "大乘百法明門論直解", 22, [f"{i:03d}" for i in range(1, 23)]),
    ("深入廣學", "八識規矩頌直解", 18, [f"{i:03d}" for i in range(1, 19)]),
    ("深入廣學", "唯識三十頌直解(淨律學佛院)", 28, [f"{i:03d}" for i in range(1, 29)]),
    ("深入廣學", "菩薩戒修學法要", 7, ["講記(全)"] + [f"{i:03d}" for i in range(1, 7)]),
    ("深入廣學", "瑜伽菩薩戒本講表", 28, [f"{i:03d}" for i in range(1, 29)]),
    # 止觀精修
    ("止觀精修", "修習止觀坐禪法要", 28, [f"{i:03d}" for i in range(1, 29)]),
    ("止觀精修", "天台教觀綱宗", 40, [f"{i:03d}" for i in range(1, 41)]),
    ("止觀精修", "楞嚴經修學法要", 30, [f"{i:03d}" for i in range(1, 31)]),
    ("止觀精修", "禪觀與淨土 一、基礎篇(台北)", 6, [f"{i:03d}" for i in range(1, 7)]),
    ("止觀精修", "禪觀與淨土 二、觀照篇(台北)", 6, [f"{i:03d}" for i in range(1, 7)]),
    ("止觀精修", "禪觀與淨土 三、念佛篇(台北)", 6, [f"{i:03d}" for i in range(1, 7)]),
    ("止觀精修", "禪觀與淨土 四、往生篇(台北)", 6, [f"00{i}_第{i}集" for i in range(1, 7)]),
    # 經論導讀
    ("經論導讀", "攝大乘論講表", 68, [f"{i:03d}" for i in range(1, 69)]),
    ("經論導讀", "大乘起信論講表", 42, [f"{i:03d}" for i in range(1, 43)]),
    ("經論導讀", "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經", 134, [f"001_要義1", "002_要義2"] + [f"{i:03d}_第{i-2}集" for i in range(3, 89)] + [f"{i:03d}" for i in range(89, 135)]),
    ("經論導讀", "佛說阿彌陀經要解(淨律學佛院)", 38, [f"{i:03d}" for i in range(1, 39)]),
    ("經論導讀", "佛遺教經", 12, [f"{i:03d}" for i in range(1, 13)]),
    ("經論導讀", "佛說四十二章經", 14, [f"{i:03d}" for i in range(1, 15)]),
]

def main():
    episodes = []
    ep = 0
    for cat, title, n, vols in COURSES:
        for i in range(n):
            ep += 1
            vol_label = vols[i] if i < len(vols) else f"{i+1:03d}"
            if vol_label in ("講記全冊", "修學綱要", "講記(全)"):
                topic = f"{title} {vol_label}"
            else:
                topic = f"{title} 第{vol_label}講"
            episodes.append((ep, topic, title, vol_label, cat))

    # Markdown table
    lines = [
        "| 集數 | 題目名稱 | 對應課程 | 對應卷次 | 所屬類別 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for ep_num, topic, course, vol, cat in episodes:
        lines.append(f"| {ep_num} | {topic} | {course} | {vol} | {cat} |")
    return "\n".join(lines)

if __name__ == "__main__":
    print(main())
