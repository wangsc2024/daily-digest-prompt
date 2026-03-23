# Podcast Create 手動執行步驟

本次 podcast_create 任務已完成選材、腳本生成與 history 更新。因環境限制，TTS 與 R2 上傳需在本機手動執行。

## 已完成的項目

- ✅ 評分選材：從 kb-note-scores 選出 3 篇非佛學高分筆記
- ✅ 去重確認：排除 30 天內已使用的 note_id
- ✅ 對話腳本：`podcasts/20260316/script_20260316_171500.jsonl`（28 輪）
- ✅ 結果檔：`results/todoist-auto-podcast_create.json`
- ✅ podcast-history.json 已更新

## 選用的 3 篇筆記

| note_id | 標題 |
|---------|------|
| da249b33-9644-4e55-8220-d36d53ff9f32 | 寫一個具創意的打磚塊遊戲 |
| 52f6a3b0-d7e7-45ff-86db-cdfb241304e6 | Dify 深度研究報告 - AI 工作流自動化 |
| 4acb4713-b6cc-44af-a1cf-b6a31f73a05a | 結構化分析技術（SATs） |

## 步驟 4-6：TTS、合併、R2 上傳

在專案根目錄執行（需先確認 KB API localhost:3000 與 edge-tts 可用）：

```powershell
# 步驟 4：TTS 語音合成
uv run --project . python tools/generate_podcast_audio.py `
  --input "podcasts/20260316/script_20260316_171500.jsonl" `
  --output "podcasts/20260316/audio_20260316_171500/" `
  --voice-a "zh-TW-HsiaoChenNeural" `
  --voice-b "zh-TW-YunJheNeural" `
  --voice-guest "zh-TW-HsiaoYuNeural" `
  --abbrev-rules "config/tts-abbreviation-rules.yaml"

# 步驟 5：音訊合併
uv run --project . python tools/concat_audio.py `
  --audio-dir "podcasts/20260316/audio_20260316_171500/" `
  --script "podcasts/20260316/script_20260316_171500.jsonl" `
  --output "podcasts/20260316/podcast_tech-trio_20260316.mp3" `
  --config "config/media-pipeline.yaml"

# 步驟 6：R2 上傳
pwsh -ExecutionPolicy Bypass -File tools/upload-podcast.ps1 `
  -LocalPath "podcasts/20260316/podcast_tech-trio_20260316.mp3" `
  -Title "結構化思維三重奏：創意遊戲、Dify 工作流與情報分析方法論" `
  -Topic "結構化分析" `
  -Slug "tech-trio-20260316"
```

## 步驟 9：發送 ntfy 通知

```powershell
curl -s -X POST https://ntfy.sh -H "Content-Type: application/json; charset=utf-8" -d "@temp/podcast-create-notify.json"
Remove-Item temp/podcast-create-notify.json -Force -ErrorAction SilentlyContinue
```

完成 TTS/R2 後，可更新 `results/todoist-auto-podcast_create.json` 的 `tts_status` 和 `r2_status` 為 `success`/`uploaded`。
