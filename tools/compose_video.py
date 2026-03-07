"""
tools/compose_video.py
影片合成準備：讀取 storyboard.json + 音訊目錄，
計算每個場景的幀數（ffprobe 讀音訊時長 × fps），
下載 AI 場景背景圖（Pollinations.ai，無需 API Key），
輸出 remotion-data.json 供 Remotion 渲染使用。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote as url_quote

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def get_audio_duration(audio_path: Path) -> float:
    """用 ffprobe 取得音訊時長（秒）。找不到檔案回傳 0.0。"""
    if not audio_path.exists():
        return 0.0
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            duration = float(stream.get("duration", 0))
            if duration > 0:
                return duration
    except Exception as e:
        print(f"[WARN] ffprobe 失敗 {audio_path.name}: {e}", file=sys.stderr)
    return 0.0


def duration_to_frames(duration_s: float, fps: int, min_frames: int = 30) -> int:
    """將秒數換算為幀數，至少保留 min_frames 幀。"""
    frames = int(duration_s * fps)
    return max(frames, min_frames)


# 專有名詞／抽象詞 → 圖庫可搜到的具體英文關鍵字（依內容選圖用）
CONTENT_TO_KEYWORDS = {
    "avalokitesvara": "statue,buddha,temple",
    "guanyin": "statue,buddha,temple",
    "lotus sutra": "lotus,flower,pond",
    "sutra": "book,ancient,scroll",
    "meditation": "meditation,person,sitting",
    "zen": "zen,garden,stones",
    "fire water wind": "fire,water,nature",
    "elements": "fire,water,nature",
    "seven elements": "fire,water,nature",
    "golden light": "sunlight,golden,morning",
    "radiating": "light,sun,glow",
    "prayer beads": "beads,wood,hands",
    "mountain temple": "mountain,temple,clouds",
    "misty mountain": "mountain,mist,forest",
    "thousand-armed": "statue,buddha,temple",
    "buddhist": "temple,buddha,lotus",
    "buddha": "buddha,statue,temple",
    "dharma": "book,temple,lotus",
    "wisdom": "book,light,candle",
}

# 場景類型專用 fallback 關鍵字（當主關鍵字導致重複圖時使用）
SCENE_TYPE_FALLBACK_KEYWORDS = {
    "title_card": "landscape,sunset,horizon",
    "content_slide": "nature,forest,path",
    "code_highlight": "computer,code,keyboard",
    "quote": "book,candle,wood",
    "split_view": "balance,minimal,two",
    "outro": "sunrise,mountain,light",
}


def _extract_loremflickr_keywords(image_prompt: str) -> str:
    """從 imagePrompt 提取圖庫可搜到的關鍵字（最多 5 個）。
    先做內容映射（專有名詞→具體詞），再取前段主題詞，過濾 stop words。
    """
    if not image_prompt or not image_prompt.strip():
        return "nature,landscape"

    STOP_WORDS = {
        "a", "an", "the", "at", "in", "on", "of", "to", "and", "or", "with",
        "cinematic", "dark", "16:9", "no", "text", "light", "glowing",
        "abstract", "soft", "view", "aerial", "closeup", "close",
        "radiating", "merging", "streams", "nodes", "flow",
    }
    subject = image_prompt.split(",")[0].strip().lower()
    max_keywords = 5

    # 先做整句內容映射（最長匹配優先）
    mapped = subject
    for phrase, replacement in sorted(CONTENT_TO_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if phrase in mapped:
            mapped = mapped.replace(phrase, replacement.replace(",", " "))

    words = mapped.split()
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2][:max_keywords]
    return ",".join(keywords) if keywords else "nature,landscape"


def fetch_scene_image(
    image_prompt: str,
    dest_path: Path,
    scene_index: int = 0,
    width: int = 1280,
    height: int = 720,
    keywords_override: str | None = None,
    lock_offset: int = 0,
) -> bool:
    """從 LoremFlickr 下載場景圖（依關鍵字搜尋）。keywords_override 用於重試時改用 fallback 關鍵字。"""
    if not HAS_REQUESTS:
        print("[WARN] requests 未安裝，跳過圖片下載。執行 uv add requests 後重試。", file=sys.stderr)
        return False

    keywords = keywords_override if keywords_override else _extract_loremflickr_keywords(image_prompt)
    lock = 1000 + scene_index + lock_offset
    url = f"https://loremflickr.com/{width}/{height}/{url_quote(keywords)}"
    params = {"lock": lock}

    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "image" not in content_type:
                print(f"[WARN] 非圖片回應 ({content_type})，跳過", file=sys.stderr)
                return False
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(resp.content)
            return True
        except Exception as e:
            print(f"[WARN] 圖片下載失敗（第 {attempt}/3 次）: {e}", file=sys.stderr)
            if attempt < 3:
                time.sleep(2 * attempt)

    return False


def _file_md5(path: Path) -> str:
    """檔案的 MD5 前 8 字元，用於偵測重複圖。"""
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


def fetch_images_for_scenes(scenes: list, public_dir: Path, slug: str) -> dict[str, str]:
    """為所有場景下載背景圖（依內容關鍵字）。若與前一張重複則用場景類型 fallback 重試。"""
    if not HAS_REQUESTS:
        return {}

    image_dir = public_dir / "images" / slug
    if image_dir.exists():
        shutil.rmtree(image_dir)
    image_dir.mkdir(parents=True)

    image_map: dict[str, str] = {}
    seen_md5: set[str] = set()

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("id", "")
        scene_type = scene.get("type", "content_slide")
        image_prompt = scene.get("imagePrompt", "")
        if not image_prompt:
            continue

        dest_path = image_dir / f"{scene_id}.jpg"
        print(f"  [IMG] {scene_id}: 下載圖片... prompt={image_prompt[:50]}")
        success = fetch_scene_image(image_prompt, dest_path, scene_index=idx)

        if success and dest_path.exists():
            current_md5 = _file_md5(dest_path)
            if current_md5 in seen_md5:
                fallback_kw = SCENE_TYPE_FALLBACK_KEYWORDS.get(
                    scene_type, "nature,landscape"
                )
                print(f"  [IMG] {scene_id}: 與前面某張重複，改用 fallback 關鍵字 [{fallback_kw}] 重試")
                retry_ok = fetch_scene_image(
                    image_prompt,
                    dest_path,
                    scene_index=idx,
                    keywords_override=fallback_kw,
                    lock_offset=2000 + idx,
                )
                if retry_ok and dest_path.exists():
                    current_md5 = _file_md5(dest_path)
            seen_md5.add(current_md5)
            image_map[scene_id] = f"images/{slug}/{scene_id}.jpg"
            print(f"  [IMG] {scene_id}: ✓ 儲存完成")
        else:
            print(f"  [IMG] {scene_id}: ✗ 失敗，使用 fallback 背景")

    return image_map


def copy_audio_to_public(audio_dir: Path, public_dir: Path, slug: str) -> Path:
    """複製音訊檔案到 video-studio/public/audio/<slug>/ 供 Remotion staticFile() 使用。"""
    dest_dir = public_dir / "audio" / slug
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    copied = 0
    for mp3 in audio_dir.glob("*.mp3"):
        shutil.copy2(mp3, dest_dir / mp3.name)
        copied += 1

    print(f"[INFO] 已複製 {copied} 個音訊檔案到 {dest_dir}")
    return dest_dir


def compose(storyboard_path: Path, audio_dir: Path, fps: int, output_path: Path):
    """讀取 storyboard.json，計算幀數，輸出 remotion-data.json。"""
    with open(storyboard_path, encoding="utf-8") as f:
        storyboard = json.load(f)

    meta = storyboard.get("meta", {})
    slug = meta.get("slug", "default")
    scenes_in = storyboard.get("scenes", [])
    scenes_out = []
    total_frames = 0

    # output_path 例如 tools/video-studio/src/data/remotion-data.json
    # public_dir = tools/video-studio/public/
    video_studio_dir = output_path.parent.parent.parent
    public_dir = video_studio_dir / "public"

    # 複製音訊到 public/audio/<slug>/
    copy_audio_to_public(audio_dir, public_dir, slug)

    # 下載 AI 場景背景圖到 public/images/<slug>/
    print(f"[INFO] 開始下載 AI 場景背景圖...")
    image_map = fetch_images_for_scenes(scenes_in, public_dir, slug)
    if image_map:
        print(f"[INFO] 成功下載 {len(image_map)} / {len(scenes_in)} 張場景圖")
    else:
        print("[INFO] 未下載任何場景圖（無 imagePrompt 或 requests 未安裝），使用 fallback 背景")

    for scene in scenes_in:
        scene_id = scene.get("id", "")
        script_file = scene.get("script_file", "")

        # 推斷對應音訊檔名（同名，副檔名改 .mp3）
        if script_file:
            stem = Path(script_file).stem
            audio_path = audio_dir / f"{stem}.mp3"
        else:
            audio_path = audio_dir / f"{scene_id}.mp3"

        duration_s = get_audio_duration(audio_path)
        frames = duration_to_frames(duration_s, fps)

        # 使用相對於 public/ 的路徑，讓 Remotion staticFile() 可以正確解析
        audio_relative = f"audio/{slug}/{audio_path.name}" if audio_path.exists() else None

        scene_out = {
            "id": scene_id,
            "type": scene.get("type", "content_slide"),
            "durationFrames": frames,
            "audioFile": audio_relative,
            "imageFile": image_map.get(scene_id),
            "props": scene.get("props", {}),
        }
        scenes_out.append(scene_out)
        total_frames += frames

        status = f"{duration_s:.2f}s → {frames}f"
        missing = "" if audio_path.exists() else " [音訊不存在，使用最小幀數]"
        print(f"  {scene_id} ({scene.get('type', '?')}): {status}{missing}")

    remotion_data = {
        "meta": {
            "title": meta.get("title", ""),
            "slug": meta.get("slug", ""),
            "fps": fps,
            "width": meta.get("width", 1280),
            "height": meta.get("height", 720),
            "totalFrames": total_frames,
            "durationSeconds": round(total_frames / fps, 2),
        },
        "scenes": scenes_out,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(remotion_data, f, ensure_ascii=False, indent=2)

    return total_frames, len(scenes_out)


def main():
    parser = argparse.ArgumentParser(description="Storyboard → Remotion 資料 JSON")
    parser.add_argument("--storyboard", required=True, help="storyboard.json 路徑")
    parser.add_argument("--audio-dir", required=True, help="audio/ 目錄路徑")
    parser.add_argument("--fps", type=int, default=30, help="影格率")
    parser.add_argument("--output", required=True, help="remotion-data.json 輸出路徑")
    args = parser.parse_args()

    storyboard_path = Path(args.storyboard)
    audio_dir = Path(args.audio_dir)
    output_path = Path(args.output)

    if not storyboard_path.exists():
        print(f"[ERROR] Storyboard 不存在: {storyboard_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 讀取分鏡稿: {storyboard_path}")
    total_frames, scene_count = compose(storyboard_path, audio_dir, args.fps, output_path)

    duration_s = total_frames / args.fps
    print(f"[DONE] remotion-data.json 已寫入: {output_path}")
    print(f"       共 {scene_count} 個場景，總長 {duration_s:.1f}s（{total_frames} 幀 @ {args.fps}fps）")


if __name__ == "__main__":
    main()
