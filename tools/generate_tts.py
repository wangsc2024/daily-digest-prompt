"""
tools/generate_tts.py
影片旁白 TTS 生成：讀取 script/ 目錄下各章節 MD 檔，
提取 tts_text 欄位，用 edge-tts 批次轉換為 WAV 檔案。

Script MD 格式：
  <!-- tts_text: 實際要 TTS 的文字（縮寫已展開）-->
  <!-- scene_type: content_slide -->
  正文內容...
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

import edge_tts
import yaml


def load_abbrev_rules(rules_path: str) -> dict:
    try:
        with open(rules_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[WARN] 無法載入縮寫規則: {e}", file=sys.stderr)
        return {}


def expand_abbreviations(text: str, rules: dict) -> str:
    """展開縮寫（與 generate_podcast_audio.py 共用邏輯）。"""
    exceptions = set(rules.get("exceptions", []))
    explicit = rules.get("explicit_rules", {})

    for abbr, expanded in explicit.items():
        text = re.sub(rf"\b{re.escape(abbr)}\b", expanded, text)

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


def extract_tts_text(md_content: str) -> str:
    """從 MD 檔案提取 tts_text HTML 注釋，若無則使用全文（去除 Markdown 語法）。"""
    match = re.search(r"<!--\s*tts_text:\s*(.*?)\s*-->", md_content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # fallback：移除 Markdown 標記，使用純文字
    text = re.sub(r"<!--.*?-->", "", md_content, flags=re.DOTALL)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)  # 標題
    text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)     # 粗/斜體
    text = re.sub(r"`[^`]+`", "", text)                      # 行內程式碼
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)   # 程式碼區塊
    text = re.sub(r"\n{3,}", "\n\n", text)                   # 多餘空行
    return text.strip()


async def synthesize(text: str, voice: str, output_path: Path) -> bool:
    """edge-tts 合成語音（MP3 格式）。"""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return True
    except Exception as e:
        print(f"[ERROR] TTS 失敗 {output_path.name}: {e}", file=sys.stderr)
        return False


async def generate_all(
    input_dir: Path,
    output_dir: Path,
    voice: str,
    abbrev_rules: dict,
) -> int:
    """批次處理 script/ 目錄下所有 MD 檔。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        print(f"[WARN] 未找到任何 MD 檔案: {input_dir}", file=sys.stderr)
        return 0

    total = len(md_files)
    failures = 0
    print(f"[INFO] 共 {total} 個章節，開始 TTS 生成...")

    for i, md_file in enumerate(md_files, 1):
        raw_text = md_file.read_text(encoding="utf-8")
        tts_text = extract_tts_text(raw_text)
        tts_text = expand_abbreviations(tts_text, abbrev_rules)

        if not tts_text.strip():
            print(f"[WARN] {md_file.name} 內容為空，跳過", file=sys.stderr)
            continue

        # 輸出與輸入同名，副檔名改為 .mp3
        out_path = output_dir / (md_file.stem + ".mp3")
        print(f"[{i}/{total}] {md_file.name} → {out_path.name} ({len(tts_text)} 字)")

        ok = await synthesize(tts_text, voice, out_path)
        if not ok:
            failures += 1

        if i < total:
            await asyncio.sleep(0.3)

    return failures


def main():
    parser = argparse.ArgumentParser(description="影片旁白 TTS 生成")
    parser.add_argument("--input", required=True, help="script/ 目錄路徑")
    parser.add_argument("--output", required=True, help="audio/ 輸出目錄")
    parser.add_argument("--voice", default="zh-TW-HsiaoChenNeural", help="edge-tts 聲音名稱")
    parser.add_argument("--abbrev-rules", default="config/tts-abbreviation-rules.yaml")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        print(f"[ERROR] Script 目錄不存在: {input_dir}", file=sys.stderr)
        sys.exit(1)

    rules = load_abbrev_rules(args.abbrev_rules)
    failures = asyncio.run(generate_all(input_dir, output_dir, args.voice, rules))

    if failures > 0:
        print(f"[WARN] {failures} 個章節 TTS 失敗", file=sys.stderr)
        sys.exit(1)

    print(f"[DONE] 音訊檔案已輸出至: {output_dir}")


if __name__ == "__main__":
    main()
