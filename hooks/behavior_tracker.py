#!/usr/bin/env python3
"""
Behavior Pattern Tracker — Instinct Lite 行為模式採集器。

靈感來源：everything-claude-code 的 Instinct Learning Engine。
將工具呼叫模式自動累積到 context/behavior-patterns.json，
為未來 Skill 自動演化提供數據基礎。

設計原則：
  - 輕量級：每次呼叫 < 5ms
  - 靜默失敗：任何錯誤不影響 Agent 流程
  - 原子級模式：tool + 簽名摘要作為模式 key
  - 信心分數：重複觀察 → 信心遞增（0.1 ~ 1.0）
  - 滾動視窗：30 天未觀察的模式自動衰減

使用方式：
  由 post_tool_logger.py 在寫入 JSONL 後呼叫 track()。
  也可獨立執行 `python behavior_tracker.py report` 查看統計。
"""
import json
import os
import hashlib
from datetime import datetime, timedelta


PATTERNS_FILE = os.path.join("context", "behavior-patterns.json")
MAX_PATTERNS = 500  # 避免無限增長
DECAY_DAYS = 30     # 超過 30 天未觀察的模式信心歸零
CONFIDENCE_INCREMENT = 0.05
CONFIDENCE_MAX = 1.0
CONFIDENCE_INITIAL = 0.1


def _compute_signature(tool: str, summary: str) -> str:
    """從工具名稱和摘要計算穩定簽名。

    正規化策略：移除動態部分（時間戳、UUID、數字後綴）保留結構。
    """
    import re
    # 移除常見動態部分
    normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}', '<uuid>', summary)
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}', '<date>', normalized)
    normalized = re.sub(r'\d{10,}', '<ts>', normalized)
    # 截斷到合理長度
    normalized = normalized[:120]
    sig = f"{tool}:{normalized}"
    return hashlib.md5(sig.encode()).hexdigest()[:12]


def _load_patterns() -> dict:
    """載入行為模式檔案。"""
    if not os.path.exists(PATTERNS_FILE):
        return {"version": 1, "patterns": {}, "last_cleanup": None}
    try:
        with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "patterns": {}, "last_cleanup": None}


def _save_patterns(data: dict):
    """寫入行為模式檔案。"""
    os.makedirs(os.path.dirname(PATTERNS_FILE), exist_ok=True)
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _cleanup_stale(data: dict) -> dict:
    """移除超過衰減期的模式。"""
    now = datetime.now().astimezone()
    cutoff = (now - timedelta(days=DECAY_DAYS)).isoformat()
    patterns = data.get("patterns", {})
    to_remove = [k for k, v in patterns.items() if v.get("last_seen", "") < cutoff]
    for k in to_remove:
        del patterns[k]
    data["last_cleanup"] = now.isoformat()
    return data


def track(tool: str, summary: str, tags: list, has_error: bool = False,
          input_len: int = 0, output_len: int = 0):
    """追蹤一次工具呼叫模式。

    Args:
        tool: 工具名稱（Bash/Read/Write/Edit 等）
        summary: 工具呼叫摘要
        tags: 自動標籤列表
        has_error: 是否出錯
        input_len: 輸入大小（chars）
        output_len: 輸出大小（chars）
    """
    try:
        sig = _compute_signature(tool, summary)
        data = _load_patterns()
        patterns = data.setdefault("patterns", {})
        now = datetime.now().astimezone().isoformat()

        if sig in patterns:
            p = patterns[sig]
            p["count"] += 1
            p["confidence"] = min(p["confidence"] + CONFIDENCE_INCREMENT, CONFIDENCE_MAX)
            p["last_seen"] = now
            if not has_error:
                p["success_count"] = p.get("success_count", 0) + 1
            # 更新 Token 經濟統計
            p["total_input"] = p.get("total_input", 0) + input_len
            p["total_output"] = p.get("total_output", 0) + output_len
        else:
            # 新模式
            if len(patterns) >= MAX_PATTERNS:
                # 移除信心最低的模式
                lowest = min(patterns, key=lambda k: patterns[k].get("confidence", 0))
                del patterns[lowest]

            patterns[sig] = {
                "tool": tool,
                "summary_sample": summary[:150],
                "tags": list(set(tags))[:5],
                "count": 1,
                "confidence": CONFIDENCE_INITIAL,
                "success_count": 1 if not has_error else 0,
                "first_seen": now,
                "last_seen": now,
                "total_input": input_len,
                "total_output": output_len,
            }

        # 每 100 次呼叫清理一次過期模式
        total_calls = sum(p.get("count", 0) for p in patterns.values())
        if total_calls % 100 == 0:
            data = _cleanup_stale(data)

        _save_patterns(data)
    except Exception:
        pass  # 靜默失敗，不中斷 Agent 流程


def report():
    """產出行為模式統計報告。"""
    data = _load_patterns()
    patterns = data.get("patterns", {})

    if not patterns:
        print("尚無行為模式記錄。")
        return

    # 按信心分數排序
    sorted_patterns = sorted(patterns.values(), key=lambda p: p.get("confidence", 0), reverse=True)

    print(f"=== 行為模式報告（共 {len(patterns)} 個模式） ===\n")

    # 高信心模式（>= 0.5）
    high_conf = [p for p in sorted_patterns if p.get("confidence", 0) >= 0.5]
    if high_conf:
        print(f"高信心模式（{len(high_conf)} 個，可考慮演化為 Skill）：")
        for p in high_conf[:10]:
            avg_io = (p.get("total_input", 0) + p.get("total_output", 0)) / max(p["count"], 1)
            print(f"  [{p['confidence']:.2f}] {p['tool']}: {p['summary_sample'][:60]}")
            print(f"         呼叫 {p['count']} 次 | 成功率 {p.get('success_count', 0)/max(p['count'],1)*100:.0f}% | 平均 I/O {avg_io:.0f} chars")
        print()

    # Token 經濟概要
    total_input = sum(p.get("total_input", 0) for p in sorted_patterns)
    total_output = sum(p.get("total_output", 0) for p in sorted_patterns)
    total_calls = sum(p.get("count", 0) for p in sorted_patterns)
    print(f"Token 經濟概要：")
    print(f"  總呼叫次數: {total_calls}")
    print(f"  總輸入量: {total_input:,} chars (~{total_input//4:,} tokens)")
    print(f"  總輸出量: {total_output:,} chars (~{total_output//4:,} tokens)")
    if total_calls > 0:
        print(f"  平均每次 I/O: {(total_input+total_output)//total_calls:,} chars")

    # 工具使用分布
    tool_counts = {}
    for p in sorted_patterns:
        t = p.get("tool", "unknown")
        tool_counts[t] = tool_counts.get(t, 0) + p.get("count", 0)
    print(f"\n工具使用分布：")
    for t, c in sorted(tool_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c} 次")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        print("用法: python behavior_tracker.py report")
