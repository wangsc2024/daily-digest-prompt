#!/usr/bin/env python3
"""
tools/score-research-quality.py
研究品質評分工具 — Todoist 多後端分派優化 v3

輸入：results/todoist-auto-{task_key}.json（每個研究任務完成後呼叫）
輸出：追加至 state/research-quality.json（30 日滾動窗口）

使用方式：
    uv run python tools/score-research-quality.py results/todoist-auto-shurangama.json

低分處置（score < 60）：記錄 [QualityAlert]，供下次執行升級 fallback
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# ─── 設定 ────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
PROJECT_DIR  = SCRIPT_DIR.parent
REGISTRY_PATH = PROJECT_DIR / "context" / "research-registry.json"
QUALITY_PATH  = PROJECT_DIR / "state" / "research-quality.json"
LOW_SCORE_THRESHOLD = 60
ROLLING_DAYS = 30

# ─── 評分維度 ─────────────────────────────────────────────

def score_source_count(text: str) -> int:
    """source_count（0-25）：引用來源數量（5 個以上得滿分）"""
    urls = re.findall(r'https?://[^\s\)\]\"\']+', text)
    unique_urls = set(urls)
    count = len(unique_urls)
    if count >= 5:  return 25
    if count >= 3:  return 15
    if count >= 1:  return 8
    return 0

def score_source_diversity(text: str) -> int:
    """source_diversity（0-20）：來源域名多樣性（3 個不同域得滿分）"""
    urls = re.findall(r'https?://([^\s/\)\]\"\']+)', text)
    domains = set()
    for u in urls:
        parts = u.split('.')
        if len(parts) >= 2:
            domains.add('.'.join(parts[-2:]))
    count = len(domains)
    if count >= 3:  return 20
    if count >= 2:  return 12
    if count >= 1:  return 5
    return 0

def score_kb_novelty(text: str, task_key: str) -> int:
    """kb_novelty（0-25）：與 research-registry.json 比對，新主題/新角度"""
    if not REGISTRY_PATH.exists():
        return 15  # 無 registry 時給予部分分數

    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        entries  = registry.get('entries', [])
        # 取最近 7 天同 task_key 的 topics
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_topics = set()
        for e in entries:
            if e.get('task_type') != task_key:
                continue
            try:
                ts = datetime.fromisoformat(e.get('timestamp', '2000-01-01'))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    recent_topics.add(e.get('topic', '').lower())
            except Exception:
                pass

        # 從當前輸出提取關鍵詞
        words = set(re.findall(r'[\w\u4e00-\u9fff]{2,}', text.lower()))
        overlap = sum(1 for t in recent_topics if any(w in words for w in t.split()))

        if overlap == 0:    return 25   # 完全新主題
        if overlap <= 1:    return 15   # 有一些重疊
        if overlap <= 3:    return 8    # 中等重疊
        return 3                        # 高度重疊
    except Exception:
        return 10

def score_output_depth(text: str) -> int:
    """output_depth（0-20）：結果字元長度（500 字以上得滿分）"""
    length = len(text)
    if length >= 1500: return 20
    if length >= 800:  return 15
    if length >= 500:  return 10
    if length >= 200:  return 5
    return 0

def score_tool_utilization(data: dict) -> int:
    """tool_utilization（0-10）：是否有效使用 WebSearch / WebFetch / tool_calls"""
    # 從結果 JSON 的 metadata 或 tool_calls 判斷
    tool_calls = data.get('tool_calls', []) or []
    web_tools  = [t for t in tool_calls
                  if isinstance(t, dict) and t.get('name') in ('WebSearch', 'WebFetch', 'web_fetch', 'web_search')]

    output_text = data.get('output', '') or data.get('result', '') or ''
    has_url_in_output = bool(re.search(r'https?://', output_text))

    if web_tools or has_url_in_output:
        return 10
    return 0

# ─── 主評分函式 ──────────────────────────────────────────

def score_result(result_path: Path) -> dict:
    try:
        data = json.loads(result_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[QualityScore] ERROR reading {result_path}: {e}", file=sys.stderr)
        return {}

    # 提取任務 key
    stem = result_path.stem  # e.g. todoist-auto-shurangama
    task_key = stem.replace('todoist-auto-', '')

    # 提取輸出文字
    output_text = (
        data.get('output') or
        data.get('result') or
        data.get('content') or
        json.dumps(data, ensure_ascii=False)
    )
    if isinstance(output_text, list):
        output_text = ' '.join(str(x) for x in output_text)
    output_text = str(output_text)

    # 計算各維度分數
    s_source_count     = score_source_count(output_text)
    s_source_diversity = score_source_diversity(output_text)
    s_kb_novelty       = score_kb_novelty(output_text, task_key)
    s_output_depth     = score_output_depth(output_text)
    s_tool_utilization = score_tool_utilization(data)
    total_score        = s_source_count + s_source_diversity + s_kb_novelty + s_output_depth + s_tool_utilization

    record = {
        "task_key":         task_key,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "score":            total_score,
        "dimensions": {
            "source_count":     s_source_count,
            "source_diversity": s_source_diversity,
            "kb_novelty":       s_kb_novelty,
            "output_depth":     s_output_depth,
            "tool_utilization": s_tool_utilization,
        },
        "output_length":    len(output_text),
        "result_file":      str(result_path),
        "backend":          data.get('backend', 'unknown'),
        "alert":            total_score < LOW_SCORE_THRESHOLD,
    }

    # 低分告警
    if record['alert']:
        print(f"[QualityAlert] {task_key} score={total_score} < {LOW_SCORE_THRESHOLD} -> consider upgrading fallback to claude_sonnet")

    return record

# ─── 更新 state/research-quality.json ─────────────────────

def update_quality_file(record: dict):
    QUALITY_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 讀取現有資料
    if QUALITY_PATH.exists():
        try:
            existing = json.loads(QUALITY_PATH.read_text(encoding='utf-8'))
        except Exception:
            existing = {}
    else:
        existing = {}

    entries = existing.get('entries', [])

    # 移除 30 天外的舊記錄
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ROLLING_DAYS)).isoformat()
    entries = [e for e in entries if e.get('timestamp', '') >= cutoff]

    entries.append(record)

    # 更新 summary
    recent_by_key: dict = {}
    for e in entries[-200:]:
        k = e.get('task_key', 'unknown')
        recent_by_key.setdefault(k, []).append(e.get('score', 0))

    summary = {k: {
        'avg': round(sum(v) / len(v), 1),
        'count': len(v),
        'last': v[-1],
        'alert': v[-1] < LOW_SCORE_THRESHOLD,
    } for k, v in recent_by_key.items()}

    quality_data = {
        'updated':  datetime.now(timezone.utc).isoformat(),
        'summary':  summary,
        'entries':  entries,
    }

    QUALITY_PATH.write_text(
        json.dumps(quality_data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return quality_data

# ─── 入口 ────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: uv run python tools/score-research-quality.py <result_json_path>")
        sys.exit(1)

    result_path = Path(sys.argv[1])
    if not result_path.exists():
        print(f"[QualityScore] ERROR: File not found: {result_path}", file=sys.stderr)
        sys.exit(1)

    record = score_result(result_path)
    if not record:
        sys.exit(1)

    quality_data = update_quality_file(record)

    # 輸出評分摘要
    score = record['score']
    dims  = record['dimensions']
    alert_mark = ' [ALERT]' if record['alert'] else ''
    print(f"[QualityScore] {record['task_key']} score={score}/100{alert_mark}")
    print(f"  source_count={dims['source_count']} source_diversity={dims['source_diversity']} "
          f"kb_novelty={dims['kb_novelty']} output_depth={dims['output_depth']} "
          f"tool_utilization={dims['tool_utilization']}")
    print(f"  output_length={record['output_length']} backend={record['backend']}")
    print(f"  state/research-quality.json updated")

    # 輸出 JSON 方便管道使用
    json.dump(record, sys.stdout, ensure_ascii=False)
    print()
