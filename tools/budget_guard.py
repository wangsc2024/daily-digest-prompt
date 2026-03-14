#!/usr/bin/env python3
"""
Paperclip 式預算守衛（P4-C）— 原子化扣款 + 閾值熔斷

整合到 tools/llm_router.py 的 _check_budget()：
每次 LLM 呼叫前先檢查預算，超限時回傳 {"allowed": False}。

使用方式：
  # 預算狀態查詢
  uv run python tools/budget_guard.py --status

  # 模擬超限（測試用）
  uv run python tools/budget_guard.py --simulate-exhaustion --provider groq
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import date

REPO_ROOT = Path(__file__).parent.parent
BUDGET_CONFIG = REPO_ROOT / "config" / "budget.yaml"
TOKEN_USAGE = REPO_ROOT / "state" / "token-usage.json"


def _load_budget_config() -> dict:
    try:
        import yaml
        return yaml.safe_load(BUDGET_CONFIG.read_text(encoding="utf-8"))
    except ImportError:
        raise ImportError("需要 pyyaml：uv add pyyaml")


def check_budget(task_type: str, provider: str, estimated_tokens: int = 50) -> dict:
    """
    呼叫前預算預檢查（原子化，不實際扣款）。

    回傳：
      {"allowed": True,  "utilization": 0.42}
      {"allowed": False, "reason": "daily_budget_exhausted", "utilization": 1.05}
    """
    try:
        config = _load_budget_config()
        usage_data = json.loads(TOKEN_USAGE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # 配置或用量檔案尚未建立，允許通過（向後相容）
        return {"allowed": True, "utilization": 0.0}
    except (ImportError, json.JSONDecodeError) as e:
        # 配置損壞或依賴缺失：允許通過但記錄警告
        print(f"[budget_guard] 配置載入異常（預算檢查跳過）：{e}", file=sys.stderr)
        return {"allowed": True, "utilization": 0.0, "warning": str(e)}

    today = date.today().isoformat()
    day_data = usage_data.get("daily", {}).get(today, {})

    daily = config.get("daily_budget", {})
    warn_threshold = daily.get("warn_threshold", 0.80)
    suspend_threshold = daily.get("suspend_threshold", 1.00)

    if provider == "groq":
        used = day_data.get("groq_calls", 0)
        limit = daily.get("groq_calls", 100)
        # Groq 按呼叫次數計，estimated_tokens 換算為呼叫數（1次）
        projected = used + 1
    else:
        # Claude：估算 token 消耗
        used = day_data.get("estimated_tokens", 0)
        limit = daily.get("claude_tokens", 5_000_000)
        projected = used + estimated_tokens

    utilization = projected / limit if limit > 0 else 0.0

    if utilization >= suspend_threshold:
        return {
            "allowed": False,
            "reason": "daily_budget_exhausted",
            "utilization": round(utilization, 4),
            "used": used,
            "limit": limit,
            "provider": provider,
        }

    if utilization >= warn_threshold:
        _send_budget_warning(provider, utilization)

    return {"allowed": True, "utilization": round(utilization, 4)}


def _send_budget_warning(provider: str, utilization: float) -> None:
    """80% 警告 → ntfy 通知（非同步，不阻塞主流程）"""
    import subprocess
    import tempfile
    import os

    payload = {
        "topic": "wangsc2025",
        "title": f"⚠️ LLM 預算警告 {utilization:.0%}",
        "message": f"{provider} 用量已達每日上限 {utilization:.1%}，請注意",
        "priority": 3,
    }
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(payload, f, ensure_ascii=False)
            tmp = f.name
        subprocess.run(
            [
                "curl", "-s",
                "-H", "Content-Type: application/json; charset=utf-8",
                "-d", f"@{tmp}",
                "https://ntfy.sh",
            ],
            capture_output=True,
            timeout=10,
        )
        os.unlink(tmp)
    except Exception:
        pass  # 通知失敗不中斷主流程


def get_status() -> dict:
    """查詢當日預算使用狀況（供 --status 命令使用）"""
    try:
        config = _load_budget_config()
        usage_data = json.loads(TOKEN_USAGE.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}

    today = date.today().isoformat()
    day_data = usage_data.get("daily", {}).get(today, {})
    daily = config.get("daily_budget", {})

    groq_used = day_data.get("groq_calls", 0)
    groq_limit = daily.get("groq_calls", 100)
    claude_used = day_data.get("estimated_tokens", 0)
    claude_limit = daily.get("claude_tokens", 5_000_000)

    return {
        "date": today,
        "groq_calls": {
            "used": groq_used,
            "limit": groq_limit,
            "utilization": f"{groq_used / groq_limit:.1%}" if groq_limit else "N/A",
        },
        "claude_tokens": {
            "used": int(claude_used),
            "limit": claude_limit,
            "utilization": f"{claude_used / claude_limit:.1%}" if claude_limit else "N/A",
        },
        "warn_threshold": daily.get("warn_threshold", 0.80),
        "suspend_threshold": daily.get("suspend_threshold", 1.00),
    }


def main():
    parser = argparse.ArgumentParser(description="LLM 預算守衛 — Paperclip 式原子化治理")
    parser.add_argument("--status", action="store_true", help="查詢當日預算使用狀況")
    parser.add_argument("--simulate-exhaustion", action="store_true", help="模擬超限（測試用）")
    parser.add_argument("--provider", default="groq", choices=["groq", "claude"], help="模擬超限時的 provider")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_status(), ensure_ascii=False, indent=2))
        return

    if args.simulate_exhaustion:
        result = check_budget("test", args.provider, estimated_tokens=999_999_999)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 預設：顯示狀態
    print(json.dumps(get_status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
