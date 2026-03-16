#!/usr/bin/env python3
"""
LLM-as-Router 元分類器（P3-A）— 用 Groq Llama 8B 自動分類任務類型

輸入：自由格式文字（如 Todoist 任務描述）
輸出：task_type（對應 llm-router.yaml 的 routing_rules 之一）

流程：
  1. 動態讀取 llm-router.yaml 取得所有 task_type 列表（確保與路由器一致）
  2. 建構分類 prompt（ClassifierStrategy 模式）
  3. 呼叫 Groq Relay（mode=classify）→ JSON{"task_type":"...", "confidence":0.0-1.0}
  4. 驗證輸出 schema，失敗時最多重試 2 次（Instructor retry 模式）
  5. 回傳分類結果，可直接傳給 llm_router.py 的 route()

使用方式：
  uv run python tools/llm_classifier.py --input "幫我把這篇英文文章翻譯成中文"
  # 期望：{"task_type":"en_to_zh","confidence":0.95}

  uv run python tools/llm_classifier.py --input "研究 AI 蒸餾最新論文" --dry-run
  # 期望：{"task_type":"research_synthesis","confidence":0.0,"dry_run":true}
"""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "llm-router.yaml"

# Classifier 輸出 schema（Instructor retry 模式參考）
CLASSIFIER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["task_type", "confidence"],
    "properties": {
        "task_type": {"type": "string"},
        "confidence": {"type": "number"},
    },
}


def _load_routing_rules() -> dict[str, dict]:
    """動態讀取 llm-router.yaml 的 routing_rules（確保與路由器一致）。"""
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("routing_rules", {})
    except ImportError:
        raise ImportError("需要 pyyaml：uv add pyyaml")
    except FileNotFoundError:
        return {}


def build_classifier_prompt(user_input: str, valid_task_types: list[str], retry_count: int = 0) -> str:
    """
    ClassifierStrategy 模式：動態從 routing_rules 建構分類 prompt。
    retry_count > 0 時加強 JSON 格式要求（Instructor retry 模式）。
    """
    type_list = "\n".join(f"  - {t}" for t in valid_task_types)
    retry_prefix = ""
    if retry_count > 0:
        retry_prefix = (
            f"[重試 {retry_count}] 上次輸出格式不符。"
            "必須只回傳純 JSON，不得有任何其他文字或 markdown。\n\n"
        )

    return (
        f"{retry_prefix}"
        "你是任務路由分類器。給定以下任務描述，從候選列表選擇最合適的 task_type。\n"
        "只回傳純 JSON（不含 markdown）：{\"task_type\": \"...\", \"confidence\": 0.0-1.0}\n\n"
        f"候選 task_type：\n{type_list}\n\n"
        f"任務描述：{user_input}"
    )


def validate_classifier_output(raw: str, valid_task_types: list[str]) -> dict:
    """
    驗證分類器回傳格式（參考 Instructor schema 驗證）。
    回傳驗證後的 dict，或拋出 ValueError。
    """
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        raise ValueError(f"非法 JSON：{e}")

    if not isinstance(result, dict):
        raise ValueError(f"回傳非 dict：{type(result)}")

    if "task_type" not in result:
        raise ValueError("缺少 task_type 欄位")

    if "confidence" not in result:
        raise ValueError("缺少 confidence 欄位")

    task_type = result["task_type"]
    if task_type not in valid_task_types:
        raise ValueError(f"task_type '{task_type}' 不在合法列表中")

    confidence = result["confidence"]
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence 值域錯誤：{confidence}")

    return {"task_type": task_type, "confidence": float(confidence)}


def _call_groq_classify(endpoint: str, prompt: str, max_tokens: int = 100) -> str:
    """呼叫 Groq Relay classify 端點，回傳原始字串。"""
    url = endpoint if "/groq/chat" in endpoint else endpoint.rstrip("/") + "/groq/chat"
    payload = json.dumps({
        "mode": "classify",
        "content": prompt,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("result", "")


def classify_with_retry(
    user_input: str,
    valid_task_types: list[str],
    endpoint: str = "",
    max_retries: int = 2,
    fallback_task_type: str = "research_synthesis",
) -> dict:
    """
    呼叫 Groq classify mode，確保輸出符合 classifier schema。
    若輸出不合規，最多重試 max_retries 次（每次加強 prompt）。

    Returns:
        {"task_type": str, "confidence": float}
        或降級：{"task_type": fallback_task_type, "confidence": 0.0, "fallback": True, "error": str}
    """
    if not endpoint:
        from tools.config_loader import get_groq_endpoint
        endpoint = get_groq_endpoint()

    last_error = ""
    for attempt in range(max_retries + 1):
        prompt = build_classifier_prompt(user_input, valid_task_types, retry_count=attempt)
        try:
            raw = _call_groq_classify(endpoint, prompt)
            return validate_classifier_output(raw, valid_task_types)
        except (urllib.error.URLError, OSError) as e:
            # Relay 不可用，直接降級（不重試網路錯誤）
            return {
                "task_type": fallback_task_type,
                "confidence": 0.0,
                "fallback": True,
                "error": f"Groq Relay 不可用：{e}",
            }
        except ValueError as e:
            last_error = str(e)
            # 格式錯誤才重試

    return {
        "task_type": fallback_task_type,
        "confidence": 0.0,
        "fallback": True,
        "error": f"達到重試上限（{max_retries}）：{last_error}",
    }


def classify(
    user_input: str,
    dry_run: bool = False,
) -> dict:
    """
    主分類函數：讀取 llm-router.yaml → 建構 prompt → 呼叫 Groq → 驗證。

    Args:
        user_input: 自由格式文字（Todoist 任務描述、用戶輸入）
        dry_run:    只回傳分類計畫，不實際呼叫 Groq

    Returns:
        {"task_type": str, "confidence": float}
    """
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except (ImportError, FileNotFoundError):
        config = {}

    rules = config.get("routing_rules", {})
    valid_task_types = list(rules.keys())
    from tools.config_loader import get_groq_endpoint
    endpoint = (
        config.get("providers", {}).get("groq", {}).get("endpoint")
        or get_groq_endpoint()
    )

    if dry_run:
        return {
            "task_type": valid_task_types[0] if valid_task_types else "research_synthesis",
            "confidence": 0.0,
            "dry_run": True,
            "valid_task_types": valid_task_types,
        }

    if not valid_task_types:
        return {"task_type": "research_synthesis", "confidence": 0.0, "fallback": True,
                "error": "routing_rules 為空"}

    return classify_with_retry(user_input, valid_task_types, endpoint=endpoint)


def main():
    parser = argparse.ArgumentParser(description="LLM 元分類器 — 自動判斷任務 task_type")
    parser.add_argument("--input", required=True, help="要分類的自由格式文字")
    parser.add_argument("--dry-run", action="store_true", help="不實際呼叫 Groq")
    args = parser.parse_args()

    result = classify(args.input, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
