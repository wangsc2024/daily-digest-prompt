"""
Groq Quota Guard - 監控 Groq API quota exhaustion

當 Groq API 回傳 "You've hit your usage limit" 時，
寫入 state/groq-quota.json 並阻擋後續依賴 Groq 的任務（TTL 6 小時）

Usage:
    uv run python tools/groq_quota_guard.py check              # 檢查是否在封鎖期
    uv run python tools/groq_quota_guard.py block <task_key>   # 標記任務因 quota 被封鎖
    uv run python tools/groq_quota_guard.py clear              # 手動清除封鎖
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_FILE = Path("state/groq-quota.json")
TTL_HOURS = 6

def load_state():
    if not STATE_FILE.exists():
        return {"quota_exceeded_at": None, "blocked_tasks": [], "ttl_hours": TTL_HOURS}
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def check():
    """檢查是否在封鎖期（exit code 0=正常，1=封鎖中）"""
    state = load_state()
    if not state["quota_exceeded_at"]:
        print("ok")
        sys.exit(0)

    exceeded_at = datetime.fromisoformat(state["quota_exceeded_at"])
    now = datetime.now(timezone.utc)
    elapsed = (now - exceeded_at).total_seconds() / 3600

    if elapsed < state["ttl_hours"]:
        print(f"blocked ({state['ttl_hours'] - elapsed:.1f}h remaining)")
        print(f"blocked_tasks: {','.join(state['blocked_tasks'])}")
        sys.exit(1)
    else:
        # TTL 過期，自動清除
        state["quota_exceeded_at"] = None
        state["blocked_tasks"] = []
        save_state(state)
        print("ok (TTL expired, auto-cleared)")
        sys.exit(0)

def block(task_key):
    """標記 quota exhaustion"""
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()

    if not state["quota_exceeded_at"]:
        state["quota_exceeded_at"] = now

    if task_key not in state["blocked_tasks"]:
        state["blocked_tasks"].append(task_key)

    save_state(state)
    print(f"✓ Blocked {task_key} due to Groq quota exhaustion (TTL {TTL_HOURS}h)")

def clear():
    """手動清除封鎖"""
    state = load_state()
    state["quota_exceeded_at"] = None
    state["blocked_tasks"] = []
    save_state(state)
    print("✓ Groq quota block cleared")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "check":
        check()
    elif cmd == "block" and len(sys.argv) == 3:
        block(sys.argv[2])
    elif cmd == "clear":
        clear()
    else:
        print(__doc__)
        sys.exit(1)
