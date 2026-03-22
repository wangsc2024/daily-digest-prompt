"""
groq_direct.py — 直接呼叫 Groq API（無需 relay）

金鑰來源：優先 GROQ_API_KEY 環境變數，fallback 讀取 bot/.env

Usage:
    uv run python tools/groq_direct.py <mode> "<content>"

Modes:
    translate  英文 → 正體中文（保留技術術語括弧附原文）
    summarize  30 字以內正體中文摘要
    classify   主題分類，回傳 JSON {"tags": [...]}
    extract    結構化萃取，回傳 JSON {"key_points":[],"summary":"","confidence":0.9}

Exit codes:
    0  成功，譯文/結果輸出至 stdout
    1  一般錯誤（連線逾時、API 錯誤等）
    2  Quota 超限（HTTP 429），呼叫端改用 fallback
"""

import json
import os
import sys
from pathlib import Path

import requests

SYSTEM_PROMPTS = {
    "translate": "技術翻譯助手。英文→正體中文，保留技術術語並括弧附上原文，只回覆譯文本身",
    "summarize": "精簡摘要助手。30字以內正體中文摘要，只回覆摘要本身",
    "classify": '分類助手。只回覆 JSON {"tags": [...]}（最多5標籤）',
    "extract": '結構化萃取助手。只回覆 JSON {"key_points": [], "summary": "", "confidence": 0.9}',
}

MAX_TOKENS = {
    "translate": 500,
    "summarize": 200,
    "classify": 100,
    "extract": 300,
}


def load_dotenv(env_path: Path) -> dict:
    """從 .env 檔案解析 key=value，不依賴 python-dotenv。"""
    result = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                result[key.strip()] = value
    except FileNotFoundError:
        pass
    return result


def get_api_key() -> str:
    # 1. 系統環境變數（最優先）
    key = os.environ.get("GROQ_API_KEY", "")
    if key and key != "your_groq_api_key_here":
        return key
    # 2. bot/.env（相對於此腳本的上層目錄）
    env_file = Path(__file__).parent.parent / "bot" / ".env"
    env = load_dotenv(env_file)
    key = env.get("GROQ_API_KEY", "")
    if key and key != "your_groq_api_key_here":
        return key
    return ""


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <mode> <content>", file=sys.stderr)
        print(f"Modes: {', '.join(SYSTEM_PROMPTS)}", file=sys.stderr)
        sys.exit(1)

    mode, content = sys.argv[1], sys.argv[2]
    if mode not in SYSTEM_PROMPTS:
        print(f"Unknown mode: {mode}. Valid: {', '.join(SYSTEM_PROMPTS)}", file=sys.stderr)
        sys.exit(1)

    api_key = get_api_key()
    if not api_key:
        print("GROQ_API_KEY not found in env or bot/.env", file=sys.stderr)
        sys.exit(1)

    model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPTS[mode]},
                    {"role": "user", "content": content},
                ],
                "max_tokens": MAX_TOKENS[mode],
                "temperature": 0.1,
            },
            timeout=20,
        )
    except requests.exceptions.Timeout:
        print("Groq API timeout", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"Groq API connection error: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 429:
        print("QUOTA_EXCEEDED", file=sys.stderr)
        sys.exit(2)

    if not resp.ok:
        print(f"Groq API error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)

    try:
        result = resp.json()["choices"][0]["message"]["content"].strip()
        print(result)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Unexpected response format: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
