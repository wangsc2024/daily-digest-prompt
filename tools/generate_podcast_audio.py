"""
tools/generate_podcast_audio.py
Podcast TTS 生成：讀取 podcast-script.jsonl，
依 host 使用不同 edge-tts 聲音，逐段輸出 MP3 檔案。
支援三聲道（host_a 曉晨、host_b 云哲、host_guest 特別來賓）。
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import edge_tts
import yaml


def resolve_host_key(turn: dict) -> str:
    """從 host 或 speaker 取得 TTS 與檔名用的 host 鍵。
    支援 host_a（曉晨）、host_b（云哲）、host_guest（特別來賓）。
    """
    h = turn.get("host")
    if h in ("host_a", "host_b", "host_guest"):
        return h
    sp = str(turn.get("speaker", "")).strip()
    if sp in ("Host-B", "host-b") or "Host-B" in sp:
        return "host_b"
    if sp in ("Host-Guest", "host-guest", "guest") or "Guest" in sp:
        return "host_guest"
    return "host_a"


def load_abbrev_rules(rules_path: str) -> dict:
    """載入縮寫展開規則 YAML。讀取失敗時回傳空規則（容錯）。"""
    try:
        with open(rules_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[WARN] 無法載入縮寫規則 {rules_path}: {e}", file=sys.stderr)
        return {}


def expand_abbreviations(text: str, rules: dict) -> str:
    """展開縮寫：explicit_rules 優先，auto_expand_caps 次之。"""
    exceptions = set(rules.get("exceptions", []))
    explicit = rules.get("explicit_rules", {})

    # 1. 手動規則（精確匹配整個單詞）
    for abbr, expanded in explicit.items():
        text = re.sub(rf"\b{re.escape(abbr)}\b", expanded, text)

    # 2. 自動展開全大寫縮寫（不在例外清單中）
    if rules.get("auto_expand_caps", False):
        min_len = rules.get("auto_expand_min_length", 2)

        def auto_expand(m):
            word = m.group(0)
            if word in exceptions or word in explicit:
                return word
            if len(word) >= min_len:
                return " ".join(list(word))
            return word

        text = re.sub(r"\b[A-Z]{2,}\b", auto_expand, text)

    return text


async def synthesize_segment(text: str, voice: str, output_path: Path) -> bool:
    """呼叫 edge-tts 合成單段語音，儲存為 MP3（edge-tts 7.x 預設 MP3）。"""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return True
    except Exception as e:
        print(f"[ERROR] TTS 失敗 {output_path.name}: {e}", file=sys.stderr)
        return False


async def generate_all(
    script_path: Path,
    output_dir: Path,
    voice_a: str,
    voice_b: str,
    abbrev_rules: dict,
    voice_guest: str | None = None,
) -> int:
    """批次生成所有對話段落音訊，回傳失敗數量。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    voice_map = {"host_a": voice_a, "host_b": voice_b}
    if voice_guest:
        voice_map["host_guest"] = voice_guest
    failures = 0

    with open(script_path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    total = len(lines)
    print(f"[INFO] 共 {total} 段對話，開始 TTS 生成...")

    for i, line in enumerate(lines, 1):
        try:
            turn = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"[WARN] 第 {i} 行 JSON 解析失敗: {e}", file=sys.stderr)
            failures += 1
            continue

        turn_num = turn.get("turn", i)
        host = resolve_host_key(turn)
        # 優先使用已展開的 tts_text，否則使用 text
        raw_text = turn.get("tts_text") or turn.get("text", "")
        tts_text = expand_abbreviations(raw_text, abbrev_rules)
        voice = voice_map.get(host, voice_a)

        # 輸出檔名：turn_001_host_a.mp3
        filename = f"turn_{turn_num:03d}_{host}.mp3"
        output_path = output_dir / filename

        print(f"[{i}/{total}] {filename} ({len(tts_text)} 字)")
        ok = await synthesize_segment(tts_text, voice, output_path)
        if not ok:
            failures += 1

        # edge-tts 免費 API，稍作間隔避免觸發速率限制
        if i < total:
            await asyncio.sleep(0.3)

    return failures


def main():
    parser = argparse.ArgumentParser(description="Podcast 雙聲道 TTS 生成")
    parser.add_argument("--input", required=True, help="podcast-script.jsonl 路徑")
    parser.add_argument("--output", required=True, help="音訊輸出目錄")
    parser.add_argument("--voice-a", default="zh-TW-HsiaoChenNeural", help="host_a 聲音（曉晨）")
    parser.add_argument("--voice-b", default="zh-TW-YunJheNeural", help="host_b 聲音（云哲）")
    parser.add_argument("--voice-guest", default=None, help="host_guest 聲音（特別來賓，可選）")
    parser.add_argument("--abbrev-rules", default="config/tts-abbreviation-rules.yaml")
    args = parser.parse_args()

    script_path = Path(args.input)
    output_dir = Path(args.output)

    if not script_path.exists():
        print(f"[ERROR] 腳本檔案不存在: {script_path}", file=sys.stderr)
        sys.exit(1)

    rules = load_abbrev_rules(args.abbrev_rules)
    failures = asyncio.run(
        generate_all(script_path, output_dir, args.voice_a, args.voice_b, rules, args.voice_guest)
    )

    if failures > 0:
        print(f"[WARN] {failures} 段 TTS 生成失敗", file=sys.stderr)
        sys.exit(1)

    print(f"[DONE] 音訊檔案已輸出至: {output_dir}")


if __name__ == "__main__":
    main()
