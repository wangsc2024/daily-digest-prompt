#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理 podcast-history.json 并提取 active note IDs 和 topics"""
import json
from datetime import datetime, timedelta

# 读取 podcast-history.json
with open('context/podcast-history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

today = datetime.strptime('2026-03-18', '%Y-%m-%d').date()
cooldown_days = data['summary'].get('cooldown_days', 30)

# 清理 recent_note_ids
active_note_ids = []
for item in data['summary']['recent_note_ids']:
    if isinstance(item, str):
        # 旧格式：直接字符串，跳过（无法判断过期）
        continue
    elif isinstance(item, dict):
        # 新格式：对象
        expires_at = datetime.strptime(item['expires_at'], '%Y-%m-%d').date()
        if expires_at >= today:
            active_note_ids.append(item['note_id'])

# 清理 recent_topics
active_topics = []
for item in data['summary']['recent_topics']:
    if isinstance(item, str):
        # 旧格式：直接字符串，跳过
        continue
    elif isinstance(item, dict):
        # 新格式：对象
        expires_at = datetime.strptime(item['expires_at'], '%Y-%m-%d').date()
        if expires_at >= today:
            active_topics.append(item['topic'])

# 输出结果
result = {
    "today": today.isoformat(),
    "cooldown_days": cooldown_days,
    "active_note_ids": active_note_ids,
    "active_topics": active_topics,
    "active_note_count": len(active_note_ids),
    "active_topic_count": len(active_topics)
}

print(json.dumps(result, ensure_ascii=False, indent=2))
