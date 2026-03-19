# Podcast Create（podcast_create）執行指南

## 一鍵執行（推薦）

專案已內建完整流程，在專案根目錄執行：

```powershell
pwsh -ExecutionPolicy Bypass -File run-podcast-create.ps1
```

或若僅需選材與腳本（跳過 TTS、R2 上傳）：

```powershell
pwsh -ExecutionPolicy Bypass -File run-podcast-create.ps1 -SkipTts
```

## 前置條件

1. **知識庫服務**：`http://localhost:3000` 已啟動（`run-podcast-create.ps1` 會先檢查 `/api/health`）
2. **Python 環境**：`uv run` 可用，依賴已安裝（`uv sync`）
3. **TTS（可選）**：`edge-tts` 可合成語音；若不可用，使用 `-SkipTts` 仍可完成選材、腳本、結果檔、history、ntfy
4. **R2 憑證（可選）**：`tools/upload-podcast.ps1` 需 Cloudflare R2 環境變數；若無則自動跳過

## 流程摘要

| 步驟 | 內容 | 執行者 |
|------|------|--------|
| 1 | POST `/api/search/hybrid`（query: 技術 AI 研究 學習 工具），排除 tags 含 佛學/佛教/淨土 等 | `run_podcast_create.py` |
| 2 | 讀取 `context/podcast-history.json`，過濾 30 天內已用 note_id | 同上 |
| 3 | 選出前 3 篇，取得完整筆記內容 | 同上 |
| 4 | 生成雙主持人對話腳本（30–50 輪）→ `podcasts/YYYYMMDD/script_*.jsonl` | 同上 |
| 5 | TTS 合成 → `generate_podcast_audio.py` | 同上 |
| 6 | 音訊合併 → `concat_audio.py` | 同上 |
| 7 | R2 上傳 → `upload-podcast.ps1` | 同上 |
| 8 | 寫入 `results/todoist-auto-podcast_create.json` | 同上 |
| 9 | 更新 `context/podcast-history.json` | 同上 |
| 10 | 發送 ntfy 通知（topic: wangsc2025） | 同上 |

## 結果檔格式

`results/todoist-auto-podcast_create.json` 內容範例：

```json
{
  "agent": "todoist-auto-podcast_create",
  "backend": "cursor_cli",
  "status": "completed",
  "summary": "選用 xxx… 等 3 篇筆記，35 輪對話，TTS=success，R2=uploaded",
  "note_ids_used": ["id1", "id2", "id3"],
  "script_file": "podcasts/20260319/script_20260319_123456.jsonl",
  "tts_status": "success|skipped",
  "r2_status": "uploaded|skipped",
  "generated_at": "2026-03-19T12:34:56+08:00"
}
```

## 腳本格式說明

對話腳本每行一筆 JSON，欄位為：

- `host`: `host_a`（女聲）或 `host_b`（男聲）
- `text`: 顯示用文字
- `tts_text`: TTS 用文字（縮寫已展開，如 AI→A I）

與任務說明中的 `speaker: Host-A/Host-B` 對應關係：Host-A = host_a，Host-B = host_b。

## 去重與排除

- `podcast_create` 與 `podcast_jiaoguangzong` 共用 `context/podcast-history.json`
- 排除 tags：佛學、佛教、淨土、天台宗、教觀綱宗、禪、法華、八識、唯識
- 冷卻期：同一 note_id 30 天內不重複使用

## 故障排除

| 狀況 | 建議 |
|------|------|
| `KB 服務未啟動` | 啟動 knowledge-base-search 或本機 KB 服務 |
| `僅取得 0–2 筆筆記` | 檢查 KB 是否有足夠非佛學筆記；可調整 `run_podcast_create.py` 的 `EXCLUDE_TAGS` 或 query |
| TTS 失敗 | 使用 `-SkipTts`，仍會寫入結果檔與腳本 |
| R2 上傳失敗 | 檢查環境變數（如 `R2_*`）；失敗不影響結果檔寫入 |
