#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新 podcast-history.json（TTL 感知）"""
import json
from datetime import datetime, timedelta

# 读取当前 podcast-history.json
with open('context/podcast-history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 新集信息
new_episode = {
    "episode_title": "四諦觀法：天台修證地圖",
    "notes_used": ["c4c5f326-f98a-4593-b9fb-993200a425b0"],
    "note_titles": ["教觀綱宗研究：四教觀法與四種四諦的相攝關係 — 由教相到觀行的內在對應"],
    "topics": ["四教觀法", "四種四諦", "教觀雙運"],
    "source": "auto-task",
    "created_at": "2026-03-18T11:40:08+08:00",
    "mp3_url": "https://podcasts.pdoont.us.kg/教觀綱宗-20260318-1133.mp3",
    "slug": "教觀綱宗-20260318-1133"
}

# 在 episodes 开头插入
data['episodes'].insert(0, new_episode)

# 更新 summary
today = datetime.strptime('2026-03-18', '%Y-%m-%d').date()
cooldown_days = data['summary']['cooldown_days']
expires_at = (today + timedelta(days=cooldown_days)).isoformat()

# 处理 recent_note_ids（清理旧格式 + 添加新项）
note_ids_cleaned = []
for item in data['summary']['recent_note_ids']:
    if isinstance(item, dict):
        # 只保留未过期的
        exp = datetime.strptime(item['expires_at'], '%Y-%m-%d').date()
        if exp >= today:
            note_ids_cleaned.append(item)

# 添加新 note_id
note_ids_cleaned.append({
    "note_id": "c4c5f326-f98a-4593-b9fb-993200a425b0",
    "last_used": today.isoformat(),
    "expires_at": expires_at
})

# 保留最新 30 筆
data['summary']['recent_note_ids'] = sorted(
    note_ids_cleaned,
    key=lambda x: x['last_used'],
    reverse=True
)[:30]

# 处理 recent_topics（清理旧格式 + 添加新项）
topics_cleaned = []
for item in data['summary']['recent_topics']:
    if isinstance(item, dict):
        exp = datetime.strptime(item['expires_at'], '%Y-%m-%d').date()
        if exp >= today:
            topics_cleaned.append(item)

# 添加新 topics（去重）
new_topics = ["四教觀法", "四種四諦", "教觀雙運"]
existing_topic_names = {t['topic'] for t in topics_cleaned}
for topic in new_topics:
    if topic not in existing_topic_names:
        topics_cleaned.append({
            "topic": topic,
            "last_used": today.isoformat(),
            "expires_at": expires_at
        })

# 保留最新 50 個
data['summary']['recent_topics'] = sorted(
    topics_cleaned,
    key=lambda x: x['last_used'],
    reverse=True
)[:50]

# 更新统计
data['summary']['total_episodes'] += 1
data['updated_at'] = "2026-03-18T11:40:08"

# 写回文件
with open('context/podcast-history.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ podcast-history.json 已更新")
print(f"- total_episodes: {data['summary']['total_episodes']}")
print(f"- recent_note_ids: {len(data['summary']['recent_note_ids'])} 筆")
print(f"- recent_topics: {len(data['summary']['recent_topics'])} 個")
