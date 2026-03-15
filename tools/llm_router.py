#!/usr/bin/env python3
"""
LLM Router（P1-B）— 動態讀取 llm-router.yaml，決定呼叫 Groq Relay 或回傳 Claude 指示。

routing_rules 為 mapping 格式（key=task_type），O(1) dict lookup。

使用方式：
  uv run python tools/llm_router.py --task-type news_summary --input "AI news..."
  uv run python tools/llm_router.py --task-type research_synthesis --dry-run

回傳 JSON（stdout）：
  Groq 成功：{"provider":"groq","result":"...","model":"llama-3.1-8b-instant","cached":false}
  Claude 路徑：{"provider":"claude","use_claude":true,"rationale":"...","task_type":"..."}
  Groq 離線：{"provider":"fallback_skipped","error":"...","action":"skip_and_log"}
  預算超限：{"provider":"budget_suspended","reason":"daily_budget_exhausted","utilization":1.05}
"""
import json
import sys
import argparse
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "llm-router.yaml"
TOKEN_USAGE_PATH = REPO_ROOT / "state" / "token-usage.json"

# P4-B：classify/extract 回傳 schema（Structured Generation）
class SchemaViolationError(ValueError):
    """Groq Relay 回傳格式不符合預期 schema。"""
    def __init__(self, mode: str, raw_result, detail: str = ""):
        self.mode = mode
        self.raw_result = raw_result
        self.detail = detail
        super().__init__(f"Schema violation for mode={mode}: {detail}")


_RELAY_SCHEMAS: dict[str, dict] = {
    "classify": {
        "type": "object",
        "required": ["labels"],
        "properties": {
            "labels": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
        },
    },
    "extract": {
        "type": "object",
        "required": ["extracted"],
        "properties": {
            "extracted": {"type": "object"},
        },
    },
}


def validate_relay_response(mode: str, raw_result) -> dict:
    """
    P4-B：驗證 Groq Relay 回傳格式（Structured Generation）。

    - summarize / translate：純字串，直接包裝回傳
    - classify / extract：期望 JSON，驗證 schema；失敗時回傳降級結構

    Args:
        mode:       "summarize" | "translate" | "classify" | "extract"
        raw_result: relay 回傳的 result 欄位（字串或 dict）

    Returns:
        驗證後的 dict，或 {"result": raw_result, "schema_violation": True}
    """
    schema = _RELAY_SCHEMAS.get(mode)
    if schema is None:
        # summarize / translate：純字串，直接包裝
        return {"result": raw_result}

    try:
        parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        _validate_schema(parsed, schema)
        return parsed
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise SchemaViolationError(mode, raw_result, str(e))


def _validate_schema(data: dict, schema: dict) -> None:
    """簡易 JSON schema 驗證（不引入 jsonschema 依賴）。"""
    if not isinstance(data, dict):
        raise TypeError(f"期望 dict，得到 {type(data)}")
    for field in schema.get("required", []):
        if field not in data:
            raise ValueError(f"缺少必填欄位：{field}")


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        raise ImportError("需要 pyyaml：uv add pyyaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML 檔案格式錯誤（期望 dict）：{path}")
    return data


def load_config() -> dict:
    return _load_yaml(CONFIG_PATH)


def match_rule(config: dict, task_type: str) -> dict | None:
    """
    routing_rules 是 mapping 格式（key=task_type）O(1) lookup。
    回傳規則 dict 或 None（未命中）。
    """
    rules = config.get("routing_rules", {})
    return rules.get(task_type)


def call_groq_relay(endpoint: str, mode: str, content: str, max_tokens: int) -> dict:
    """
    POST 到 groq-relay。
    Relay 接口：{"mode": "summarize|translate|classify|extract", "content": "..."}
    成功回傳：{"result": "...", "cached": bool, "model": "..."}
    """
    # endpoint 可能包含 /groq/chat，也可能只有 host
    url = endpoint if "/groq/chat" in endpoint else endpoint.rstrip("/") + "/groq/chat"
    payload = json.dumps({
        "mode": mode,
        "content": content,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def update_token_usage(provider: str) -> None:
    """更新 state/token-usage.json 的 groq_calls / claude_calls 計數（schema v2）。"""
    try:
        import datetime
        usage = json.loads(TOKEN_USAGE_PATH.read_text(encoding="utf-8"))
        today = datetime.date.today().isoformat()
        day_record = usage.setdefault("daily", {}).setdefault(today, {})
        key = "groq_calls" if provider == "groq" else ("groq_skipped" if provider == "groq_skipped" else "claude_calls")
        day_record[key] = day_record.get(key, 0) + 1
        TOKEN_USAGE_PATH.write_text(
            json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass  # token usage 追蹤失敗不中斷主流程


def _check_budget(task_type: str, provider: str) -> dict | None:
    """
    呼叫 budget_guard.check_budget()（P4-C）。
    若 budget_guard 未安裝則跳過（向後相容）。
    回傳 None 表示允許；回傳 dict 表示被阻擋。
    """
    try:
        # C1 修正：命令列執行時 sys.path 不含 REPO_ROOT，需手動注入
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from tools.budget_guard import check_budget
        result = check_budget(task_type, provider, estimated_tokens=50)
        if not result.get("allowed", True):
            return {
                "provider": "budget_suspended",
                "reason": result.get("reason", "budget_limit_reached"),
                "utilization": result.get("utilization", 0),
            }
    except (ImportError, FileNotFoundError):
        pass  # budget_guard 未建立時跳過
    return None


def route(task_type: str, content: str, dry_run: bool = False) -> dict:
    config = load_config()
    rule = match_rule(config, task_type)

    if rule is None:
        return {
            "provider": "claude",
            "use_claude": True,
            "rationale": f"task_type '{task_type}' 未在 routing_rules 中定義，預設 Claude",
            "task_type": task_type,
        }

    provider = rule.get("provider", "claude")

    if dry_run:
        return {
            "provider": provider,
            "rule": {"task_type": task_type, **rule},
            "dry_run": True,
            "endpoint": config.get("providers", {}).get("groq", {}).get("endpoint"),
        }

    # 預算預檢查（P4-C）
    budget_block = _check_budget(task_type, provider)
    if budget_block:
        return budget_block

    if provider == "groq":
        provider_cfg = config.get("providers", {}).get("groq", {})
        endpoint = provider_cfg.get("endpoint", "http://localhost:3002/groq/chat")
        # 優先讀 groq_mode，回退到 mode，再回退到 summarize
        mode = rule.get("groq_mode") or rule.get("mode", "summarize")
        max_tokens = rule.get("max_tokens", 300)

        try:
            relay_resp = call_groq_relay(endpoint, mode, content, max_tokens)
            update_token_usage("groq")
            # P4-B：驗證 classify/extract 回傳 schema
            raw_result = relay_resp.get("result", "")
            try:
                validated = validate_relay_response(mode, raw_result)
            except SchemaViolationError as sve:
                validated = {"result": raw_result, "schema_warning": str(sve)}
            return {
                "provider": "groq",
                "result": validated.get("result", raw_result),
                "validated": validated,
                "model": provider_cfg.get("model", "llama-3.1-8b-instant"),
                "cached": relay_resp.get("cached", False),
                "task_type": task_type,
            }
        except urllib.error.URLError as e:
            update_token_usage("groq_skipped")  # 記錄 Groq 降級次數（relay 離線）
            fallback_action = (
                config.get("fallback", {})
                .get("groq_unavailable", {})
                .get("action", "skip_and_log")
            )
            return {
                "provider": "fallback_skipped",
                "error": str(e),
                "action": fallback_action,
                "task_type": task_type,
            }
        except Exception as e:
            update_token_usage("groq_skipped")  # 記錄 Groq 降級次數（其他錯誤）
            return {
                "provider": "fallback_skipped",
                "error": str(e),
                "action": "skip_and_log",
                "task_type": task_type,
            }

    # Claude 路徑
    update_token_usage("claude")
    return {
        "provider": "claude",
        "use_claude": True,
        "rationale": rule.get("rationale") or rule.get("reason", ""),
        "task_type": task_type,
    }


def main():
    parser = argparse.ArgumentParser(description="LLM Router — 動態路由到 Groq 或 Claude")
    parser.add_argument("--task-type", required=True, help="對應 llm-router.yaml routing_rules 的 key")
    parser.add_argument("--input", default="", help="要處理的文字內容")
    parser.add_argument("--input-file", help="從檔案讀取輸入（優先於 --input）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示路由決策，不實際呼叫")
    args = parser.parse_args()

    content = args.input
    if args.input_file:
        content = Path(args.input_file).read_text(encoding="utf-8")

    result = route(args.task_type, content, args.dry_run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
