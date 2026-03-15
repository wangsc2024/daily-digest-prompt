#!/usr/bin/env python3
"""資料收集與統計分析腳本"""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from statistics import mean, stdev

# 設定日期範圍
END_DATE = datetime(2026, 3, 14)
START_DATE = datetime(2026, 3, 8)

def collect_jsonl_stats():
    """統計 JSONL 日誌"""
    stats = {
        "tool_calls": Counter(),
        "tags": Counter(),
        "unique_skills": set(),
        "output_lens": [],
        "total_calls": 0,
        "session_ids": set()
    }

    logs_dir = Path("D:/Source/daily-digest-prompt/logs/structured")

    for day_offset in range(7):
        date = START_DATE + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")
        jsonl_file = logs_dir / f"{date_str}.jsonl"

        if not jsonl_file.exists():
            continue

        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    stats["total_calls"] += 1

                    # 工具呼叫
                    if "tool" in entry:
                        stats["tool_calls"][entry["tool"]] += 1

                    # 標籤
                    if "tags" in entry and isinstance(entry["tags"], list):
                        for tag in entry["tags"]:
                            stats["tags"][tag] += 1

                            # 提取 Skill 名稱（從檔案路徑）
                            if tag == "skill-read" and "summary" in entry:
                                path = entry["summary"]
                                # 例如：D:\Source\daily-digest-prompt\skills\kb-research-strategist\SKILL.md
                                if "\\skills\\" in path or "/skills/" in path:
                                    parts = path.replace("\\", "/").split("/skills/")
                                    if len(parts) > 1:
                                        skill_name = parts[1].split("/")[0]
                                        stats["unique_skills"].add(skill_name)

                    # I/O 大小
                    if "output_len" in entry:
                        stats["output_lens"].append(entry["output_len"])

                    # Session ID
                    if "sid" in entry:
                        stats["session_ids"].add(entry["sid"])

                except json.JSONDecodeError:
                    continue

    return {
        "tool_calls": dict(stats["tool_calls"]),
        "tags": dict(stats["tags"]),
        "unique_skills": sorted(list(stats["unique_skills"])),
        "avg_io_per_call": int(mean(stats["output_lens"])) if stats["output_lens"] else 0,
        "total_calls": stats["total_calls"],
        "session_count": len(stats["session_ids"])
    }

def collect_scheduler_stats():
    """統計排程器狀態"""
    state_file = Path("D:/Source/daily-digest-prompt/state/scheduler-state.json")

    if not state_file.exists():
        return {"error": "scheduler-state.json not found"}

    with open(state_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    success_count = 0
    failure_count = 0
    hour_failures = defaultdict(int)

    for run in data.get("runs", []):
        timestamp = run.get("timestamp", "")
        if not timestamp:
            continue

        try:
            # timestamp 格式：2026-03-06T06:47:41（無時區）
            exec_time = datetime.fromisoformat(timestamp)
            if START_DATE <= exec_time <= END_DATE:
                if run.get("status") == "success":
                    success_count += 1
                elif run.get("status") == "error":
                    failure_count += 1
                    hour_failures[exec_time.hour] += 1
        except:
            continue

    total = success_count + failure_count
    success_rate = success_count / total if total > 0 else 0

    # 找出失敗最多的小時
    high_failure_hours = sorted(hour_failures.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": round(success_rate, 3),
        "high_failure_hours": [h for h, _ in high_failure_hours]
    }

def collect_auto_tasks_stats():
    """統計自動任務"""
    tasks_file = Path("D:/Source/daily-digest-prompt/context/auto-tasks-today.json")

    if not tasks_file.exists():
        return {"error": "auto-tasks-today.json not found"}

    with open(tasks_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    # 提取任務計數（排除 metadata 欄位）
    task_counts = {}
    for key, value in data.items():
        if key.endswith('_count') and not key.startswith('write_'):
            task_counts[key.replace('_count', '')] = value

    total_tasks = len(task_counts)
    completed_tasks = sum(1 for count in task_counts.values() if count > 0)
    completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0

    # 計算公平性指標
    counts = list(task_counts.values())
    if len(counts) > 1:
        fairness_index = stdev(counts) / mean(counts) if mean(counts) > 0 else 0
    else:
        fairness_index = 0

    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "completion_rate": round(completion_rate, 3),
        "task_counts": task_counts,
        "fairness_index": round(fairness_index, 3)
    }

def collect_research_stats():
    """統計研究註冊表"""
    registry_file = Path("D:/Source/daily-digest-prompt/context/research-registry.json")

    if not registry_file.exists():
        return {"error": "research-registry.json not found"}

    with open(registry_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    all_entries = data.get("entries", [])
    total_entries = len(all_entries)

    # 提取唯一主題和近期主題
    topics = set()
    recent_topics = []

    for entry in all_entries:
        topic = entry.get("topic")
        if topic:
            topics.add(topic)

            # 檢查是否為近 7 天新增
            last_updated = entry.get("last_updated", "")
            try:
                update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                if START_DATE <= update_time <= END_DATE:
                    recent_topics.append(topic)
            except:
                continue

    unique_topics = len(topics)
    diversity_index = unique_topics / total_entries if total_entries > 0 else 0

    return {
        "total_entries": total_entries,
        "unique_topics": unique_topics,
        "diversity_index": round(diversity_index, 3),
        "recent_topics": list(set(recent_topics))[:10]  # 最多顯示 10 個
    }

def collect_behavior_stats():
    """統計行為模式（可選）"""
    behavior_file = Path("D:/Source/daily-digest-prompt/context/behavior-patterns.json")

    if not behavior_file.exists():
        return None

    try:
        with open(behavior_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        patterns = data.get("patterns", [])
        pattern_count = len(patterns)
        high_confidence = sum(1 for p in patterns if p.get("confidence", 0) >= 0.5)

        return {
            "pattern_count": pattern_count,
            "high_confidence_patterns": high_confidence
        }
    except:
        return None

def main():
    """主程序"""
    errors = []

    # 收集各項統計
    print("收集 JSONL 日誌統計...")
    jsonl_stats = collect_jsonl_stats()

    print("收集排程器統計...")
    scheduler_stats = collect_scheduler_stats()
    if "error" in scheduler_stats:
        errors.append(scheduler_stats["error"])
        scheduler_stats = None

    print("收集自動任務統計...")
    auto_tasks_stats = collect_auto_tasks_stats()
    if "error" in auto_tasks_stats:
        errors.append(auto_tasks_stats["error"])
        auto_tasks_stats = None

    print("收集研究註冊表統計...")
    research_stats = collect_research_stats()
    if "error" in research_stats:
        errors.append(research_stats["error"])
        research_stats = None

    print("收集行為模式統計...")
    behavior_stats = collect_behavior_stats()

    # 組裝結果
    result = {
        "jsonl_stats": jsonl_stats,
        "scheduler_stats": scheduler_stats,
        "auto_tasks_stats": auto_tasks_stats,
        "research_stats": research_stats,
        "behavior_stats": behavior_stats,
        "errors": errors
    }

    # 輸出 JSON
    output_file = Path("D:/Source/daily-digest-prompt/temp/stats_output.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n統計完成！結果已寫入：{output_file}")
    print(f"\n摘要：")
    print(f"- 總工具呼叫：{jsonl_stats['total_calls']}")
    print(f"- 唯一 Skills：{len(jsonl_stats['unique_skills'])}")
    print(f"- 自動任務完成率：{auto_tasks_stats['completion_rate'] if auto_tasks_stats else 'N/A'}")
    print(f"- 研究主題多樣性：{research_stats['diversity_index'] if research_stats else 'N/A'}")

if __name__ == "__main__":
    main()
