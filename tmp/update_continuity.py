#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新自动任务连续记忆"""
import json

# 读取现有连续记忆
with open('context/continuity/auto-task-podcast_jiaoguangzong.json', 'r', encoding='utf-8') as f:
    continuity = json.load(f)

# 新记录
new_run = {
    "executed_at": "2026-03-18T11:40:08+08:00",
    "topic": "四諦觀法：天台修證地圖（教觀綱宗研究：四教觀法與四種四諦的相攝關係）",
    "status": "completed",
    "key_findings": "四教四諦四觀是教觀一體的完整修證系統：藏教生滅四諦配析空觀、通教無生四諦配體空觀、別教無量四諦配次第三觀、圓教無作四諦配一心三觀，層層深入從分析到圓融",
    "kb_note_ids": ["c4c5f326-f98a-4593-b9fb-993200a425b0"],
    "next_suggested_angle": "可繼續深化天台宗其他觀法實踐（如二十五方便、四種三昧）或圓教一心三觀的具體修行步驟"
}

# 在 runs 开头插入
continuity['runs'].insert(0, new_run)

# 保留最新 5 笔
continuity['runs'] = continuity['runs'][:5]

# 写回文件
with open('context/continuity/auto-task-podcast_jiaoguangzong.json', 'w', encoding='utf-8') as f:
    json.dump(continuity, f, ensure_ascii=False, indent=2)

print("✅ 自動任務連續記憶已更新")
print(f"- 記錄數: {len(continuity['runs'])}")
