---
name: "podcast-create"
template_type: "auto_task_template"
version: "1.0.0"
released_at: "2026-03-20"
---
# 自動任務：Podcast 生成（AI 雙主持人知識電台）

> 觸發條件：round-robin 自動輪轉
> 後端：claude-sonnet-4-5（需完整工具鏈：Bash + Write + Read + KB API）
> 產出：podcasts/YYYYMMDD/podcast_{date}_{time}.mp3 → 上傳至 R2

```
你是 Podcast 製作人，負責將知識庫筆記轉化為 AI 雙主持人對話節目。
全程使用正體中文。遵守 `templates/shared/preamble.md` 所有規則。

## ⚡ Skill-First 規則
先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md
- skills/ntfy-notify/SKILL.md

---

## 步驟 0：讀取 Podcast 長久記憶

讀取過去的播客歷史，避免重複製作相同內容：

```bash
cat context/podcast-history.json
```

從回應中取得：
- **`summary.recent_note_ids`**：最近 `cooldown_days` 天內已用的筆記 ID 清單（本集必須排除）
- **`summary.recent_topics`**：最近覆蓋過的主題標籤（本集需優先選擇「不在此清單」的主題）

記錄這兩個清單，供步驟 1 選材時使用。

---

## 步驟 1：評分知識庫筆記，選出播客素材

執行評分工具，取得高品質筆記排行：

```bash
uv run --project . python tools/score-kb-notes.py --top 10
```

讀取評分結果：
```bash
cat state/kb-note-scores.json
```

從 `top_10` 中選出 **3 筆** 最高分的筆記作為本集素材，條件（依序套用）：
- `total >= 50`（低於 50 分的筆記內容不夠豐富）
- `podcast_suit >= 10`（需有敘述性，純程式碼筆記跳過）
- **排除** ID 在步驟 0 的 `recent_note_ids` 清單中的筆記
- 3 筆筆記的主題需具多樣性，且**優先選擇主題不在 `recent_topics` 清單**中的筆記

若高分筆記不足 3 筆，補充查詢知識庫：
```bash
curl -s "http://localhost:3000/api/notes?limit=20&sort=createdAt&order=desc"
```
手動選出補充筆記。

---

## 步驟 2：查詢每筆選中筆記的完整內容

對每個選中的 note_id，查詢完整內容：
```bash
curl -s "http://localhost:3000/api/notes/{note_id}"
```

記錄每筆筆記的：
- 標題（title）
- 正文（contentText）
- 標籤（tags）
- 建立日期

---

## 步驟 3：生成雙主持人對話腳本（JSONL 格式）

根據 3 筆筆記內容，撰寫 AI 雙主持人對話：

**主持人設定：**
- **host_a（曉晨，女聲解說者）**：條理清晰、善用比喻、深入淺出解說核心概念
- **host_b（云哲，男聲提問者）**：好奇心強、提問精準、引導聽眾理解深層問題

**腳本結構（每集約 20-30 輪對話，目標字數 1500-2500 字）：**

1. **開場白**（2 輪）：host_a 問候 + 本集主題預告
2. **主題一**（6-8 輪）：第一筆筆記核心概念深度討論
3. **主題二**（6-8 輪）：第二筆筆記，與主題一的連結/對比
4. **主題三**（4-6 輪）：第三筆筆記，融入實際應用視角
5. **總結與展望**（2 輪）：本集重點回顧 + 下集預告

**對話寫作原則：**
- 對話自然流暢，避免說教感
- 每段對話 50-150 字，TTS 友善（無特殊符號、數學符號展開說明）
- 適時加入「對！」「有意思」「好問題」等接話詞增加對話感
- 技術術語首次出現時需解釋（TTS 需展開縮寫：AI→人工智慧，ML→機器學習）

**JSONL 格式（每行一個 JSON 物件）：**
```json
{"turn": 1, "host": "host_a", "text": "大家好，我是曉晨。", "tts_text": "大家好，我是曉晨。"}
{"turn": 2, "host": "host_b", "text": "嗨！我是云哲。", "tts_text": "嗨！我是云哲。"}
```

`tts_text` 欄位：與 `text` 相同，但展開所有縮寫（AI→人工智慧、API→應用程式介面）。

---

## 步驟 4：儲存腳本到本地

取得今日日期與時間：
```bash
pwsh -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"
```

建立目錄並寫入腳本（使用 Write 工具）：
- 目錄：`podcasts/{YYYYMMDD}/`
- 腳本路徑：`podcasts/{YYYYMMDD}/script_{timestamp}.jsonl`

---

## 步驟 5：TTS 語音合成

> ⚡ **必須用 Bash tool 實際執行，不得只輸出命令文字**

從 config/media-pipeline.yaml 讀取聲音設定，然後執行：

```bash
uv run --project . python tools/generate_podcast_audio.py \
  --input "podcasts/{YYYYMMDD}/script_{timestamp}.jsonl" \
  --output "podcasts/{YYYYMMDD}/audio_{timestamp}/" \
  --voice-a "zh-TW-HsiaoChenNeural" \
  --voice-b "zh-TW-YunJheNeural" \
  --abbrev-rules "config/tts-abbreviation-rules.yaml"
```

**✅ Checkpoint（必須執行）**：
```bash
ls podcasts/{YYYYMMDD}/audio_{timestamp}/*.mp3 | wc -l
```
- 輸出 > 0：繼續步驟 6
- 輸出為 0：記錄錯誤，跳至步驟 9 寫入 `status: "error"`，停止流程

---

## 步驟 6：音訊後製（串接 + 正規化 + MP3 輸出）

> ⚡ **必須用 Bash tool 實際執行，不得只輸出命令文字**

```bash
uv run --project . python tools/concat_audio.py \
  --audio-dir "podcasts/{YYYYMMDD}/audio_{timestamp}/" \
  --script "podcasts/{YYYYMMDD}/script_{timestamp}.jsonl" \
  --output "podcasts/{YYYYMMDD}/podcast_{timestamp}.mp3" \
  --config "config/media-pipeline.yaml"
```

**✅ Checkpoint（必須執行）**：
```bash
ls -la "podcasts/{YYYYMMDD}/podcast_{timestamp}.mp3"
```
- 檔案存在：記錄 MP3 路徑，繼續步驟 7
- 不存在：記錄錯誤，跳至步驟 9 寫入 `status: "error"`，停止流程

---

## 步驟 7：上傳至 Cloudflare R2

使用現有的 `tools/upload-podcast.ps1`（已正確處理 URL 編碼、manifest 更新、環境變數讀取）：

```bash
pwsh -ExecutionPolicy Bypass -File tools/upload-podcast.ps1 \
  -LocalPath "podcasts/{YYYYMMDD}/podcast_{filename}.mp3" \
  -Title "{本集主題}" \
  -Topic "{主要主題}" \
  -Slug "{slug}-{YYYYMMDD}"
```

腳本回傳 JSON（stdout），解析取得 `cloud_url`：
```json
{"url": "https://podcasts.pdoont.us.kg/podcast_{filename}.mp3", "key": "...", "size_bytes": ..., "uploaded_at": "..."}
```

- 上傳成功：記錄 `cloud_url`，後續步驟使用此 URL
- 上傳失敗或 `skipped: true`：`cloud_url = "未上傳"`，繼續執行（非致命）

---

## 步驟 8：發送 ntfy 通知

依照 skills/ntfy-notify/SKILL.md 指示，使用 Write 工具建立通知 JSON 後發送。

通知內容（`cloud_url` 有值時加入播放連結）：
```
標題：🎙️ Podcast 已發佈：{本集主題}
內容：AI 雙主持人對話 | {主題1} × {主題2} × {主題3} | {對話輪數} 輪對話
Tags: headphones, white_check_mark
Click: https://podcast.pdoont.us.kg   ← 網站首頁（播放時自動觸發計數器）
```

若 `cloud_url = "未上傳"`：省略 Click 欄位，通知內容改為「本地檔案已就緒，尚未上傳至雲端」。

---

## 步驟 8.5：寫入 KB 筆記（Podcast 摘要）

依照 skills/knowledge-query/SKILL.md 的 POST /api/notes 說明，匯入本集 Podcast 摘要筆記：

```bash
curl -s -X POST "http://localhost:3000/api/notes" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @temp/podcast-kb-note.json
```

先用 Write 工具建立 `temp/podcast-kb-note.json`（UTF-8）：
```json
{
  "title": "【Podcast】{episode_title}",
  "contentText": "## 本集摘要\n\n**主題**：{主題1} × {主題2} × {主題3}\n**對話輪數**：{turns} 輪\n**雲端連結**：{cloud_url}\n\n## 使用的知識庫筆記\n\n1. {note_title_1}（{note_id_1}）\n2. {note_title_2}（{note_id_2}）\n3. {note_title_3}（{note_id_3}）\n\n## 重點摘錄\n\n從腳本中提取 3-5 個核心觀點（各 1-2 句話）：\n- [從對話腳本提取 host_a 的核心解說句]\n- [從對話腳本提取另一核心觀點]\n- ...",
  "tags": ["Podcast製作", "AI雙主持人", "{主題1}", "{主題2}", "{主題3}"],
  "source": "import"
}
```

解析回傳 JSON 取得 `kb_note_id`（即 `id` 欄位）：
- 成功（HTTP 201）：記錄 `kb_note_id`，後續寫入結果 JSON
- 失敗（網路/API 錯誤）：`kb_note_id = null`，繼續執行（非致命）

發送後刪除暫存檔：
```bash
rm -f temp/podcast-kb-note.json
```

---

## 步驟 9：寫入結果檔案

使用 Write 工具寫入 `results/todoist-auto-podcast_create.json`：
```json
{
  "type": "podcast_create",
  "task_key": "podcast_create",
  "episode_title": "（本集主題摘要）",
  "notes_used": ["（note_id 1）", "（note_id 2）", "（note_id 3）"],
  "note_titles": ["（標題1）", "（標題2）", "（標題3）"],
  "topics": ["（本集主題標籤1）", "（主題標籤2）"],
  "script_path": "podcasts/{YYYYMMDD}/script_{timestamp}.jsonl",
  "mp3_path": "podcasts/{YYYYMMDD}/podcast_{timestamp}.mp3",
  "cloud_url": "（R2 URL 或 '未上傳'）",
  "turns": （對話輪數）,
  "kb_imported": true,
  "kb_note_id": "（步驟 8.5 取得的 id，若失敗則 null）",
  "status": "success",
  "summary": "（episode_title）— （turns）輪對話",
  "completed_at": "（ISO 8601 時間）"
}
```

---

## 步驟 10：更新 Podcast 長久記憶

讀取現有 `context/podcast-history.json`，加入本集記錄後用 Write 工具**完整覆寫**。

**更新規則：**

1. 在 `episodes[]` 開頭插入新 episode（**最新集在最前**）：
```json
{
  "episode_title": "（本集主題）",
  "notes_used": ["（note_id 1）", "（note_id 2）", "（note_id 3）"],
  "note_titles": ["（標題1）", "（標題2）", "（標題3）"],
  "topics": ["（主題標籤1）", "（主題標籤2）", "（主題標籤3）"],
  "source": "auto-task",
  "created_at": "（ISO 8601）"
}
```

2. 更新 `summary`：
   - `total_episodes`：+1
   - `recent_note_ids`：在清單前方加入本集 3 筆 note_id，**保留最新 30 筆**（超過截斷舊的）
   - `recent_topics`：在清單前方加入本集 topics，**保留最新 50 個**（去重後截斷）
   - `updated_at`：更新為當前 ISO 8601 時間

3. 保留 `entries[]` 原樣（向後相容，不修改）

**topics 提取原則**：從筆記的 `tags` 陣列取前 2-3 個有意義的主題詞（排除 "Podcast製作"、"對話腳本" 等通用標籤），若 tags 為空則從 note_title 提取關鍵詞（2-4 個字的主題名詞）。

---

## 步驟 11：更新 KB 筆記評分（回饋迴圈）

將本次使用的 3 筆筆記標記為「已入播客」，避免近期重複：
```bash
uv run --project . python tools/score-kb-notes.py --limit 50
```

完成！在最終輸出中列出：
- 本集主題
- 使用的筆記標題（含主題標籤）
- MP3 路徑與雲端 URL
- 對話輪數與字數
- 更新後的 `recent_topics` 前 5 項
```
