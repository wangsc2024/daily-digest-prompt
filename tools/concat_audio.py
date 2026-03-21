"""
tools/concat_audio.py
Podcast 音訊後製：
  1. FFmpeg 生成 intro/outro 音調（sine wave）
  2. 將所有音訊統一轉換為相同格式 (pcm_s16le, 24000Hz, mono)
  3. 依 turn 順序串接所有段落音訊（段落間插入靜音）
  4. loudnorm 正規化（-14 LUFS）
  5. 輸出 MP3 128kbps

注意：concat demuxer 需要所有輸入格式完全一致，
      因此先把 intro/outro/silence/turn 都轉成相同 WAV 格式再串接。
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# 統一音訊格式（與 edge-tts 輸出一致，避免重採樣）
SAMPLE_RATE = 24000
CHANNELS = 1
CODEC = "pcm_s16le"


def load_config(config_path: str) -> dict:
    """載入 media-pipeline.yaml 的 podcast 區塊。"""
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("podcast", {})
    except Exception as e:
        print(f"[WARN] 無法載入配置 {config_path}: {e}", file=sys.stderr)
        return {}


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    """執行 ffmpeg 指令，失敗時拋出例外。"""
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 失敗: {result.stderr[-800:]}")
    return result


def normalize_to_wav(input_path: Path, output_path: Path):
    """將任意音訊格式轉換為統一 WAV（24000Hz mono pcm_s16le）。"""
    ffmpeg(
        "-i", str(input_path),
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-acodec", CODEC,
        str(output_path),
    )


def generate_chord(
    freqs: list[float],
    weights: list[float],
    duration_s: float,
    fade_in_s: float,
    fade_out_s: float,
    output: Path,
):
    """生成和弦 WAV（aevalsrc 多頻率合成，比單音更悅耳）。

    freqs   : 頻率列表（Hz），例如 [264, 330, 396]
    weights : 對應權重（建議總和 ≤ 1 以防削波）
    """
    if len(freqs) != len(weights):
        raise ValueError("freqs 與 weights 長度必須相同")

    # 建立 aevalsrc 運算式：Σ(weight * sin(2π * t * freq))
    terms = [f"{w:.3f}*sin(2*PI*t*{f})" for f, w in zip(freqs, weights)]
    expr = "+".join(terms)

    fade_out_start = max(0.0, duration_s - fade_out_s)
    ffmpeg(
        "-f", "lavfi",
        "-i", f"aevalsrc={expr}:s={SAMPLE_RATE}:d={duration_s}",
        "-af", f"afade=t=in:d={fade_in_s},afade=t=out:st={fade_out_start}:d={fade_out_s}",
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-acodec", CODEC,
        str(output),
    )


def generate_silence(duration_ms: int, output: Path):
    """生成靜音 WAV（統一格式：24000Hz mono pcm_s16le）。"""
    duration_s = duration_ms / 1000.0
    ffmpeg(
        "-f", "lavfi",
        "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
        "-t", str(duration_s),
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-acodec", CODEC,
        str(output),
    )


def read_turn_order(script_path: Path) -> list[dict]:
    """讀取 podcast-script.jsonl，回傳按 turn 排序的段落列表。"""
    turns = []
    with open(script_path, encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
                if "turn" not in t:
                    t["turn"] = idx
                turns.append(t)
            except json.JSONDecodeError:
                pass
    return sorted(turns, key=lambda t: t.get("turn", 0))


def resolve_host_key(turn: dict) -> str:
    h = turn.get("host")
    if h in ("host_a", "host_b"):
        return h
    sp = str(turn.get("speaker", "")).strip()
    if sp in ("Host-B", "host-b") or "Host-B" in sp:
        return "host_b"
    return "host_a"


def concat_and_export(
    audio_dir: Path,
    turns: list[dict],
    intro_wav: Path,
    outro_wav: Path,
    silence_wav: Path,
    output_mp3: Path,
    bitrate_kbps: int,
    target_lufs: float,
    norm_dir: Path,
):
    """串接音訊、正規化、輸出 MP3。"""

    # Step 1：將所有 turn MP3 轉換為統一 WAV 格式
    print("[INFO] 將 TTS 段落轉換為統一 WAV 格式...")
    turn_wavs: list[Path] = []
    for turn in turns:
        turn_num = turn.get("turn", 0)
        host = resolve_host_key(turn)
        mp3_file = audio_dir / f"turn_{turn_num:03d}_{host}.mp3"
        if not mp3_file.exists():
            print(f"[WARN] 音訊段落不存在，跳過: {mp3_file}", file=sys.stderr)
            continue
        wav_file = norm_dir / f"turn_{turn_num:03d}_{host}.wav"
        normalize_to_wav(mp3_file, wav_file)
        turn_wavs.append((turn, wav_file))

    # Step 2：組合 intro + turns + silences + outro（全部為相同格式 WAV）
    segments: list[Path] = [intro_wav]
    for turn, wav_file in turn_wavs:
        segments.append(wav_file)
        segments.append(silence_wav)
    # 移除最後多餘的靜音，加上 outro
    if segments and segments[-1] == silence_wav:
        segments.pop()
    segments.append(outro_wav)

    print(f"[INFO] 共 {len(segments)} 個音訊片段（含 intro/outro/silence）")

    # Step 3：建立 concat 清單（全部為相同格式 WAV，可安全使用 -c copy）
    concat_list = norm_dir / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for seg in segments:
            safe_path = str(seg.resolve()).replace("\\", "/").replace("'", "\\'")
            f.write(f"file '{safe_path}'\n")

    # Step 4：concat（全部同格式，使用 -c copy 零失真）
    concat_wav = norm_dir / "concat_raw.wav"
    print("[INFO] 串接所有音訊片段...")
    ffmpeg(
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(concat_wav),
    )

    # Step 5：loudnorm 正規化
    normalized_wav = norm_dir / "concat_norm.wav"
    print(f"[INFO] 正規化音量 ({target_lufs} LUFS)...")
    ffmpeg(
        "-i", str(concat_wav),
        "-filter:a", f"loudnorm=I={target_lufs}:TP=-1:LRA=11",
        str(normalized_wav),
    )

    # Step 6：匯出 MP3
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 匯出 MP3 ({bitrate_kbps}kbps)...")
    ffmpeg(
        "-i", str(normalized_wav),
        "-codec:a", "libmp3lame",
        "-b:a", f"{bitrate_kbps}k",
        str(output_mp3),
    )


def main():
    parser = argparse.ArgumentParser(description="Podcast 音訊後製：串接 + 正規化 + MP3 輸出")
    parser.add_argument("--audio-dir", required=True, help="podcast-audio/ 目錄路徑")
    parser.add_argument("--script", required=True, help="podcast-script.jsonl 路徑")
    parser.add_argument("--output", required=True, help="輸出 MP3 路徑")
    parser.add_argument("--config", default="config/media-pipeline.yaml")
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    script_path = Path(args.script)
    output_mp3 = Path(args.output)

    if not audio_dir.exists():
        print(f"[ERROR] 音訊目錄不存在: {audio_dir}", file=sys.stderr)
        sys.exit(1)
    if not script_path.exists():
        print(f"[ERROR] 腳本檔案不存在: {script_path}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(args.config)
    target_lufs = cfg.get("target_lufs", -14)
    bitrate_kbps = cfg.get("output_bitrate_kbps", 128)
    silence_ms = cfg.get("silence_between_turns_ms", 100)
    tone_duration = cfg.get("tone_duration_s", 2.5)
    fade_in_s = cfg.get("fade_in_s", 0.3)
    fade_out_s = cfg.get("fade_out_s", 1.2)

    # 和弦設定（支援新格式；回退舊格式 intro_freq_hz / outro_freq_hz）
    intro_freqs = cfg.get("intro_freqs_hz", [cfg.get("intro_freq_hz", 440)])
    intro_weights = cfg.get("intro_weights", [0.35] * len(intro_freqs))
    outro_freqs = cfg.get("outro_freqs_hz", [cfg.get("outro_freq_hz", 330)])
    outro_weights = cfg.get("outro_weights", [0.35] * len(outro_freqs))

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        intro_wav = tmp / "intro.wav"
        outro_wav = tmp / "outro.wav"
        silence_wav = tmp / "silence.wav"
        norm_dir = tmp / "normalized"
        norm_dir.mkdir()

        print(f"[INFO] 生成 Intro 和弦（{intro_freqs} Hz）...")
        generate_chord(intro_freqs, intro_weights, tone_duration, fade_in_s, fade_out_s, intro_wav)

        print(f"[INFO] 生成 Outro 和弦（{outro_freqs} Hz）...")
        generate_chord(outro_freqs, outro_weights, tone_duration, fade_in_s, fade_out_s, outro_wav)

        print(f"[INFO] 生成 {silence_ms}ms 靜音段落...")
        generate_silence(silence_ms, silence_wav)

        turns = read_turn_order(script_path)
        print(f"[INFO] 共 {len(turns)} 段對話，開始處理...")

        concat_and_export(
            audio_dir=audio_dir,
            turns=turns,
            intro_wav=intro_wav,
            outro_wav=outro_wav,
            silence_wav=silence_wav,
            output_mp3=output_mp3,
            bitrate_kbps=bitrate_kbps,
            target_lufs=target_lufs,
            norm_dir=norm_dir,
        )

    print(f"[DONE] Podcast 已輸出至: {output_mp3}")


if __name__ == "__main__":
    main()
