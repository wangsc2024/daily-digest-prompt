# Cursor CLI 任務：Podcast 生成（podcast_create）

## 任務目標

從知識庫評分非佛學類別的筆記，選出最佳 3 篇，生成 AI 雙主持人對話腳本，TTS 合成後上傳 R2 並發送 ntfy 通知。

## 執行步驟

1. **評分 KB 筆記**：執行知識庫評分，排除佛學/佛教類標籤的筆記，選出評分最高的 3 篇：
   - POST http://localhost:3000/api/search/hybrid，query: "技術 AI 研究 學習 工具"，排除 tags 含「佛學」「佛教」「淨土」的筆記
   - 依相關性+新鮮度評分，取前 3 篇，記錄 note_id 與標題

2. **去重確認**：Read `context/podcast-history.json`，確認選出的 note_id 均未在近 30 天內使用過。若有重複，改選下一篇。

3. **生成對話腳本**：依據選出的 3 篇筆記，撰寫雙主持人（Host-A/Host-B）對話腳本（30-50 輪），寫入 `podcasts/<YYYYMMDD>/script_<YYYYMMDD_HHmmss>.jsonl`，格式：
   ```jsonl
   {"speaker": "Host-A", "text": "..."}
   {"speaker": "Host-B", "text": "..."}
   ```

4. **TTS 合成**：執行 `pwsh tools/article-to-podcast.ps1` 或呼叫腳本產生 MP3（如 TTS 服務不可用，跳至步驟 7 並在摘要中標注）。

5. **音訊合併**：若 TTS 成功，執行 `uv run python tools/concat_audio.py` 合併片段。

6. **R2 上傳**：上傳最終 MP3 至 Cloudflare R2（若憑證不可用，跳至步驟 7）。

7. **寫入結果檔**：用 Write 工具將以下 JSON 寫入 `results/todoist-auto-podcast_create.json`：
   ```json
   {
     "agent": "todoist-auto-podcast_create",
     "backend": "cursor_cli",
     "status": "completed",
     "summary": "<執行摘要（100字以內）>",
     "note_ids_used": ["<id1>", "<id2>", "<id3>"],
     "script_file": "<腳本路徑>",
     "tts_status": "success|skipped",
     "r2_status": "uploaded|skipped",
     "generated_at": "<ISO8601時間戳>"
   }
   ```

8. **更新 podcast-history.json**：在 `context/podcast-history.json` 追加本次使用的 note_id。

9. **發送 ntfy 通知**：
   - 用 Write 工具建立 `temp/podcast-create-notify.json`（UTF-8）
   - 執行 `curl -s -X POST https://ntfy.sh -H "Content-Type: application/json; charset=utf-8" -d @temp/podcast-create-notify.json`
   - 刪除暫存 JSON 檔

## 注意事項
- 全程使用正體中文輸出
- podcast_create 和 podcast_jiaoguangzong 共享 `context/podcast-history.json` 去重機制
- 禁止使用 `> nul`，輸出抑制用 `> /dev/null` 或 `| Out-Null`
- 結果檔必須在執行完畢後存在，TTS/R2 失敗不影響結果檔寫入

## 結構化摘要格式
執行完畢後必須提供：執行摘要、選用的 3 篇筆記標題、腳本檔路徑、TTS 狀態、R2 上傳狀態、通知發送狀態。
