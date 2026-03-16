你是 Podcast 製作人，負責將知識庫高品質筆記轉化為 AI 雙主持人知識電台節目。
全程使用正體中文。完成後將結果寫入 `results/todoist-auto-podcast_create.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

必須先讀取以下 SKILL.md：
- `skills/knowledge-query/SKILL.md`
- `skills/ntfy-notify/SKILL.md`

## ⚡ 強制執行規則（最高優先級）

> **任何 Shell 命令都必須用 Bash tool 實際執行，不得只輸出命令文字。**
> 每個關鍵步驟執行後，立即用 Bash tool 確認輸出檔案存在。
> `status: "success"` 只能在確認 MP3 檔案實際存在後才能設定。

## 主要任務

依照 `templates/auto-tasks/podcast-create.md` 的完整流程執行：

1. **評分選材**：【立即】用 Bash tool 執行：
   ```bash
   uv run --project . python tools/score-kb-notes.py --top 10
   ```
2. **選出 3 筆**高分筆記（total >= 50，podcast_suit >= 10，主題多樣）
   - **排除佛學分類**：tags 含 `佛學`、`天台宗`、`教觀綱宗`、`淨土`、`禪`、`法華`、`八識`、`唯識`、`佛教` 等佛教相關標籤的筆記，由 `podcast_jiaoguangzong` 專屬任務負責，此處跳過不選
   - 若排除後高分筆記不足 3 筆，可降低 total 門檻至 40，但仍須排除上述標籤
2.5. **先寫入進度檔**（在 TTS 之前執行，確保持久化）：
   ```json
   {
     "agent": "todoist-auto-podcast_create",
     "type": "podcast_create",
     "status": "in_progress",
     "summary": "正在生成 Podcast，腳本已完成，TTS 進行中..."
   }
   ```
   用 Write 工具寫入 `results/todoist-auto-podcast_create.json`
3. **撰寫雙主持人對話腳本**（JSONL 格式，20-30 輪，1500-2500 字）
   - host_a（曉晨）：解說者，深入淺出
   - host_b（云哲）：提問者，引導理解
   - 腳本完成後用 Write 工具寫入 `podcasts/{YYYYMMDD}/script_{timestamp}.jsonl`
4. **TTS 語音合成**：【立即】用 Bash tool 執行（填入實際路徑）：
   ```bash
   uv run --project . python tools/generate_podcast_audio.py \
     --input "podcasts/{YYYYMMDD}/script_{timestamp}.jsonl" \
     --output "podcasts/{YYYYMMDD}/audio_{timestamp}/" \
     --voice-a "zh-TW-HsiaoChenNeural" \
     --voice-b "zh-TW-YunJheNeural" \
     --abbrev-rules "config/tts-abbreviation-rules.yaml"
   ```
   **✅ Checkpoint**：執行後立即確認 MP3 存在：
   ```bash
   ls podcasts/{YYYYMMDD}/audio_{timestamp}/*.mp3 | wc -l
   ```
   若輸出為 0，停止流程，寫入 `status: "error"`。
5. **音訊後製**：【立即】用 Bash tool 執行：
   ```bash
   uv run --project . python tools/concat_audio.py \
     --audio-dir "podcasts/{YYYYMMDD}/audio_{timestamp}/" \
     --script "podcasts/{YYYYMMDD}/script_{timestamp}.jsonl" \
     --output "podcasts/{YYYYMMDD}/podcast_{timestamp}.mp3" \
     --config "config/media-pipeline.yaml"
   ```
   **✅ Checkpoint**：執行後確認最終 MP3 存在：
   ```bash
   ls -la "podcasts/{YYYYMMDD}/podcast_{timestamp}.mp3"
   ```
   若不存在，停止流程，寫入 `status: "error"`。
6. **上傳 R2**：【立即】用 Bash tool 執行：
   ```bash
   pwsh -ExecutionPolicy Bypass -File tools/upload-podcast.ps1 \
     -LocalPath "podcasts/{YYYYMMDD}/podcast_{timestamp}.mp3" \
     -Title "{本集主題}" -Topic "{主要主題}" -Slug "{slug}-{YYYYMMDD}"
   ```
7. **ntfy 通知** + 更新結果檔案（status 從 `in_progress` 改為 `success`，補寫完整欄位）

詳細流程（含欄位格式）請讀取 `templates/auto-tasks/podcast-create.md`。
