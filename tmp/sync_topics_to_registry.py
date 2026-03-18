#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 Podcast topics 到 research-registry.json"""
import json

# 读取 research-registry.json
with open('context/research-registry.json', 'r', encoding='utf-8') as f:
    registry = json.load(f)

# 确保 topics_index 存在
if 'topics_index' not in registry:
    registry['topics_index'] = {}

# 添加本集的 note_title 和 podcast_title
today = "2026-03-18"
note_title = "教觀綱宗研究：四教觀法與四種四諦的相攝關係 — 由教相到觀行的內在對應"
podcast_title = "四諦觀法：天台修證地圖"

registry['topics_index'][note_title] = today
registry['topics_index'][podcast_title] = today

# 写回文件
with open('context/research-registry.json', 'w', encoding='utf-8') as f:
    json.dump(registry, f, ensure_ascii=False, indent=2)

print("✅ research-registry.json topics_index 已更新")
print(f"- 新增: {note_title}")
print(f"- 新增: {podcast_title}")
