#!/usr/bin/env python3
"""系統洞察資料收集腳本"""
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# 資料路徑（以腳本位置動態計算，tools/ 的上一層即專案根目錄）
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs/structured"
STATE_DIR = BASE_DIR / "state"
CONTEXT_DIR = BASE_DIR / "context"
CONFIG_DIR = BASE_DIR / "config"


def _load_research_exclude_keys() -> set:
    """從 benchmark.yaml 讀取 avg_io_per_call.exclude_task_keys（研究類任務排除清單）"""
    benchmark_path = CONFIG_DIR / "benchmark.yaml"
    if not benchmark_path.exists():
        return set()
    try:
        if _YAML_AVAILABLE:
            with open(benchmark_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        else:
            # yaml 未安裝時：用簡單字串解析取得 exclude_task_keys 段落
            with open(benchmark_path, 'r', encoding='utf-8') as f:
                content = f.read()
            keys = set()
            in_exclude = False
            for line in content.splitlines():
                stripped = line.strip()
                if "exclude_task_keys:" in stripped:
                    in_exclude = True
                    continue
                if in_exclude:
                    if stripped.startswith("- "):
                        keys.add(stripped[2:].strip())
                    elif stripped and not stripped.startswith("#"):
                        in_exclude = False
            return keys

        for metric in data.get("metrics", []):
            if metric.get("name") == "avg_io_per_call":
                return set(metric.get("exclude_task_keys", []))
    except Exception:
        pass
    return set()


RESEARCH_EXCLUDE_KEYS = _load_research_exclude_keys()

# 時間範圍（近 7 天）
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=6)

def collect_jsonl_stats():
    """收集 JSONL 日誌統計（含 block_rate，供系統洞察使用，避免 LLM 誤用日誌內數字）"""
    stats = {
        "total_calls": 0,
        "blocked_count": 0,
        "block_rate": 0.0,
        "tool_distribution": Counter(),
        "tag_distribution": Counter(),
        "unique_skills": set(),
        "skill_count": 0,
        "avg_output_len": 0,
        "excluded_research_calls": 0,
        "data_available": False
    }

    total_output_len = 0
    call_count = 0

    try:
        # 遍歷近 7 天的 JSONL 檔案
        for i in range(7):
            date = START_DATE + timedelta(days=i)
            file_path = LOGS_DIR / f"{date.strftime('%Y-%m-%d')}.jsonl"

            if not file_path.exists():
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        stats["total_calls"] += 1

                        # 攔截事件：僅計 event==blocked 或 tags 含 "blocked"（與 query_logs 一致）
                        if entry.get("event") == "blocked" or "blocked" in entry.get("tags", []):
                            stats["blocked_count"] += 1

                        # 工具分佈
                        tool_name = entry.get("tool")
                        if tool_name:
                            stats["tool_distribution"][tool_name] += 1

                        # 標籤分佈
                        tags = entry.get("tags", [])
                        for tag in tags:
                            stats["tag_distribution"][tag] += 1

                            # skill-read 中的 Skill 名稱
                            if tag == "skill-read":
                                summary = entry.get("summary", "")
                                if "/skills/" in summary or "\\skills\\" in summary:
                                    # 支援 Unix 和 Windows 路徑分隔符
                                    path_parts = summary.replace("\\", "/").split("/skills/")
                                    if len(path_parts) > 1:
                                        skill_name = path_parts[1].split("/")[0]
                                        stats["unique_skills"].add(skill_name)

                        # 輸出長度（排除研究類任務，其報告完整性不受字元限制）
                        output_len = entry.get("output_len", 0)
                        if output_len:
                            task_key = entry.get("cause_chain", {}).get("task_key", "")
                            if task_key in RESEARCH_EXCLUDE_KEYS:
                                stats["excluded_research_calls"] += 1
                            else:
                                total_output_len += output_len
                                call_count += 1
                    except json.JSONDecodeError:
                        continue

        if stats["total_calls"] > 0:
            stats["data_available"] = True
            stats["block_rate"] = round(stats["blocked_count"] / stats["total_calls"], 4)
            stats["unique_skills"] = sorted(list(stats["unique_skills"]))
            stats["skill_count"] = len(stats["unique_skills"])
            stats["avg_output_len"] = int(total_output_len / call_count) if call_count > 0 else 0
            # 轉換 Counter 為 dict
            stats["tool_distribution"] = dict(stats["tool_distribution"])
            stats["tag_distribution"] = dict(stats["tag_distribution"])

    except Exception as e:
        print(f"JSONL 統計錯誤: {e}")
        stats["data_available"] = False

    return stats

def collect_scheduler_stats():
    """收集 scheduler-state.json 統計"""
    stats = {
        "total_runs": 0,
        "success_count": 0,
        "failed_count": 0,
        "success_rate": 0.0,
        "high_failure_hours": [],
        "data_available": False
    }

    try:
        file_path = STATE_DIR / "scheduler-state.json"
        if not file_path.exists():
            return stats

        with open(file_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        # 統計近 7 天
        hour_failures = defaultdict(int)
        runs = data.get("runs", [])

        for run in runs:
            if not isinstance(run, dict):
                continue

            timestamp = run.get("timestamp")
            if not timestamp:
                continue

            try:
                run_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if START_DATE <= run_date <= END_DATE:
                    stats["total_runs"] += 1

                    sections = run.get("sections", {})
                    # 檢查各 section 是否有失敗
                    has_failure = any(
                        status != "success"
                        for status in sections.values()
                    )

                    if not has_failure and sections:
                        stats["success_count"] += 1
                    else:
                        stats["failed_count"] += 1
                        hour_failures[run_date.hour] += 1
            except (ValueError, KeyError, TypeError):
                continue

        if stats["total_runs"] > 0:
            stats["data_available"] = True
            stats["success_rate"] = round(stats["success_count"] / stats["total_runs"], 3)

            # 找出失敗次數 >= 3 的小時
            stats["high_failure_hours"] = sorted([
                hour for hour, count in hour_failures.items() if count >= 3
            ])

    except Exception as e:
        print(f"Scheduler 統計錯誤: {e}")
        stats["data_available"] = False

    return stats

def collect_auto_task_stats():
    """收集自動任務統計"""
    stats = {
        "task_counts": {},
        "fairness_score": 0.0,
        "data_available": False
    }

    try:
        file_path = CONTEXT_DIR / "auto-tasks-today.json"
        if not file_path.exists():
            return stats

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 提取任務計數
        task_counts = {}
        for key, value in data.items():
            if key.endswith("_count") and not key.startswith("write_"):
                task_name = key.replace("_count", "")
                task_counts[task_name] = value

        if task_counts:
            stats["data_available"] = True
            stats["task_counts"] = task_counts

            # 計算公平性：stddev / mean
            counts = list(task_counts.values())
            if len(counts) > 1:
                mean_val = statistics.mean(counts)
                if mean_val > 0:
                    stddev_val = statistics.stdev(counts)
                    stats["fairness_score"] = round(stddev_val / mean_val, 3)

    except Exception as e:
        print(f"Auto-task 統計錯誤: {e}")
        stats["data_available"] = False

    return stats

def collect_research_stats():
    """收集研究註冊表統計"""
    stats = {
        "unique_topics": 0,
        "total_entries": 0,
        "diversity": 0.0,
        "recent_topics": 0,
        "data_available": False
    }

    try:
        file_path = CONTEXT_DIR / "research-registry.json"
        if not file_path.exists():
            return stats

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        entries = data.get("entries", [])
        unique_topics = set()
        recent_count = 0

        for entry in entries:
            topic = entry.get("topic")
            if topic:
                unique_topics.add(topic)

            # 近 7 天新增
            timestamp = entry.get("timestamp")
            if timestamp:
                try:
                    entry_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    if START_DATE <= entry_date <= END_DATE:
                        recent_count += 1
                except (ValueError, TypeError):
                    pass

        stats["data_available"] = True
        stats["unique_topics"] = len(unique_topics)
        stats["total_entries"] = len(entries)
        stats["recent_topics"] = recent_count

        if stats["total_entries"] > 0:
            stats["diversity"] = round(stats["unique_topics"] / stats["total_entries"], 3)

    except Exception as e:
        print(f"Research 統計錯誤: {e}")
        stats["data_available"] = False

    return stats

def collect_behavior_stats():
    """收集行為模式統計"""
    stats = {
        "pattern_count": None,
        "high_confidence_count": None,
        "data_available": False
    }

    try:
        file_path = CONTEXT_DIR / "behavior-patterns.json"
        if not file_path.exists():
            return stats

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        patterns = data.get("patterns", {})

        stats["data_available"] = True
        stats["pattern_count"] = len(patterns)
        stats["high_confidence_count"] = sum(
            1 for p in patterns.values() if p.get("confidence", 0) >= 0.5
        )

    except Exception as e:
        print(f"Behavior 統計錯誤: {e}")
        stats["data_available"] = False

    return stats

def main():
    """主函數"""
    print("開始收集系統資料...")

    # 收集各項統計
    jsonl_stats = collect_jsonl_stats()
    print(f"✓ JSONL 統計完成: {jsonl_stats['total_calls']} 次呼叫, blocked={jsonl_stats.get('blocked_count', 0)}, block_rate={jsonl_stats.get('block_rate', 0)}")

    scheduler_stats = collect_scheduler_stats()
    print(f"✓ Scheduler 統計完成: {scheduler_stats['total_runs']} 次執行")

    auto_task_stats = collect_auto_task_stats()
    print(f"✓ Auto-task 統計完成: {len(auto_task_stats['task_counts'])} 個任務")

    research_stats = collect_research_stats()
    print(f"✓ Research 統計完成: {research_stats['unique_topics']} 個主題")

    behavior_stats = collect_behavior_stats()
    print(f"✓ Behavior 統計完成: {behavior_stats.get('pattern_count', 'N/A')} 個模式")

    # 組裝最終結果
    result = {
        "collected_at": datetime.now().isoformat(),
        "period": {
            "start": START_DATE.strftime("%Y-%m-%d"),
            "end": END_DATE.strftime("%Y-%m-%d"),
            "days": 7
        },
        "jsonl_stats": jsonl_stats,
        "scheduler_stats": scheduler_stats,
        "auto_task_stats": auto_task_stats,
        "research_stats": research_stats,
        "behavior_stats": behavior_stats
    }

    # 寫入結果檔案
    output_path = BASE_DIR / "tmp/system-insight-data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✓ 資料收集完成，已寫入: {output_path}")
    print(f"  - JSONL: {jsonl_stats['data_available']}")
    print(f"  - Scheduler: {scheduler_stats['data_available']}")
    print(f"  - Auto-task: {auto_task_stats['data_available']}")
    print(f"  - Research: {research_stats['data_available']}")
    print(f"  - Behavior: {behavior_stats['data_available']}")

if __name__ == "__main__":
    main()
