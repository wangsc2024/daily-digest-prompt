# 自動任務：教觀綱宗 Podcast 生成（每次 1 集，每日合計 3 集）

> 觸發條件：round-robin 自動輪轉（daily_limit: 3）
> 後端：claude-sonnet-4-5（需完整工具鏈：Bash + Write + Read + KB API）
> 產出：results/article-教觀綱宗-{slug}/podcast-final.mp3 → 上傳至 R2

```
你是 Podcast 製作人，負責將教觀綱宗相關知識庫筆記轉化為 AI 雙主持人對話節目。
全程使用正體中文。遵守 `templates/shared/preamble.md` 所有規則。

## ⚡ Skill-First 規則
先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md
- skills/ntfy-notify/SKILL.md

---

## 步驟 0：讀取 Podcast 長久記憶

讀取過去的播客歷史，取得已用筆記與主題：

```bash
cat context/podcast-history.json
```

記錄：
- **`summary.recent_note_ids`**：30 天內已用筆記 ID（本次必須排除）
- **`summary.recent_topics`**：近期主題標籤（本次選擇不在此清單的切入角度）

---

## 步驟 1：查詢教觀綱宗可用筆記

搜尋知識庫，取得教觀綱宗相關筆記：

```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"query": "教觀綱宗", "topK": 15}'
```

選取規則（依序）：
1. **排除** ID 在步驟 0 的 `recent_note_ids` 中的筆記
2. 優先選取主題**不在** `recent_topics` 中的筆記
3. 若所有筆記都已用過（冷卻中），選**分數最低**的（允許最舊的筆記循環重用）

記錄選定筆記的 `note_id`。

---

## 步驟 2：取得筆記完整內容

```bash
curl -s "http://localhost:3000/api/notes/{選定的 note_id}"
```

記錄：title、contentText、tags、id。

---

## 步驟 3：構思播客主題與 slug

根據筆記標題與內容：
- 構思一個 **4-12 字**的播客標題（`podcast_title`），需與歷史中所有 episode_title 不同
- 從 tags 提取 2-3 個主題詞（排除「Podcast製作」、「對話腳本」等通用標籤）作為 `topics`
- 建立 `slug`：`教觀綱宗-{YYYYMMDD}-{HHmm}`（用 `pwsh -Command "Get-Date -Format 'yyyyMMdd-HHmm'"` 取得）

---

## 步驟 4：生成雙主持人對話腳本（JSONL 格式）

根據筆記內容撰寫 **30-40 輪**對話（≥2000 字）：

**主持人設定：**
- **host_a（曉晨，女聲解說者）**：條理清晰、善用比喻、深入淺出解說核心概念
- **host_b（云哲，男聲提問者）**：好奇心強、提問精準、引導聽眾理解深層問題

**腳本結構：**
1. 開場白（2 輪）：主題預告
2. 主體（24-34 輪）：深入討論筆記核心概念，每段推進新資訊，禁止重複
3. 總結與展望（2 輪）：重點回顧

**對話寫作原則：**
- 對話自然流暢，避免說教感
- 每段 50-150 字，TTS 友善（無特殊符號）
- tts_text 中全大寫縮寫加字母間空格（API→A P I，但 URL/HTTP/JSON 不展開）

用 **Write 工具**建立 `results/article-{slug}/podcast-script.jsonl`（每行一個 JSON）：
```json
{"turn": 1, "host": "host_a", "text": "...", "tts_text": "..."}
```

用 **Write 工具**建立 `results/article-{slug}/podcast-meta.json`：
```json
{"note_id": "...", "note_title": "...", "query": "教觀綱宗", "podcast_title": "...", "topics": [...], "slug": "..."}
```

---

## 步驟 5：TTS 語音合成

```bash
uv run --project . python tools/generate_podcast_audio.py \
  --input "results/article-{slug}/podcast-script.jsonl" \
  --output "results/article-{slug}/podcast-audio/" \
  --voice-a "zh-TW-HsiaoChenNeural" \
  --voice-b "zh-TW-YunJheNeural"
```

等待完成。若失敗：記錄錯誤，跳至步驟 7 寫入失敗結果。

---

## 步驟 6：音訊串接（MP3 輸出）

```bash
uv run --project . python tools/concat_audio.py \
  --audio-dir "results/article-{slug}/podcast-audio/" \
  --script "results/article-{slug}/podcast-script.jsonl" \
  --output "results/article-{slug}/podcast-final.mp3"
```

---

## 步驟 7：上傳至 Cloudflare R2

```bash
pwsh -ExecutionPolicy Bypass -File tools/upload-podcast.ps1 \
  -LocalPath "results/article-{slug}/podcast-final.mp3" \
  -Title "{podcast_title}" \
  -Topic "教觀綱宗" \
  -Slug "{slug}"
```

解析回傳 JSON 取得 `cloud_url`。
- 上傳成功：記錄 `cloud_url`
- 失敗或 `skipped: true`：`cloud_url = "未上傳"`

---

## 步驟 8：發送 ntfy 通知

依照 skills/ntfy-notify/SKILL.md 指示，用 Write 工具建立通知 JSON 後發送：
```
標題：🎙️ 教觀綱宗 Podcast：{podcast_title}
內容：{對話輪數} 輪對話 | {topics 前 3 個主題}
Tags: headphones, white_check_mark
Click: https://podcast.pdoont.us.kg
```

---

## 步驟 9：寫入結果檔案

用 Write 工具寫入 `results/todoist-auto-podcast_jiaoguangzong.json`：
```json
{
  "task_key": "podcast_jiaoguangzong",
  "episode_title": "（播客標題）",
  "note_id": "（note_id）",
  "note_title": "（筆記標題）",
  "topics": ["（主題標籤）"],
  "slug": "（slug）",
  "mp3_path": "results/article-{slug}/podcast-final.mp3",
  "cloud_url": "（R2 URL 或 '未上傳'）",
  "turns": （對話輪數）,
  "status": "success",
  "completed_at": "（ISO 8601）"
}
```

---

## 步驟 10：更新 Podcast 長久記憶

**重新讀取**最新的 `context/podcast-history.json`：
```bash
cat context/podcast-history.json
```

在 `episodes[]` **開頭**插入新集：
```json
{
  "episode_title": "（podcast_title）",
  "notes_used": ["（note_id）"],
  "note_titles": ["（note_title）"],
  "topics": ["（topic1）", "（topic2）"],
  "source": "auto-task",
  "created_at": "（ISO 8601）",
  "mp3_url": "（cloud_url）",
  "slug": "（slug）"
}
```

更新 `summary`：
- `total_episodes`：+1
- `recent_note_ids`：前方加入本集 note_id，保留最新 30 筆
- `recent_topics`：前方加入本集 topics，去重後保留最新 50 個
- `updated_at`：更新為當前 ISO 8601

用 **Write 工具**完整覆寫 `context/podcast-history.json`（version:2 格式，保留 entries[] 原樣）。

完成！在最終輸出中列出：
- podcast_title 與 slug
- note_title
- 對話輪數與估算時長
- cloud_url
```
