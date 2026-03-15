# Cursor CLI 任務：唯識八識深度報告 + 知識庫 + Podcast 上傳 R2

你正在專案 D:\Source\daily-digest-prompt 中執行。請遵守專案根目錄 CLAUDE.md 的 Skill-First 與所有規則。

## 任務目標

1. **深入研究**唯識學派核心理論「八識」（眼、耳、鼻、舌、身、意、末那識、阿賴耶識），產出一份**深度洞察報告**（Markdown，建議 3000–6000 字）。
2. **將報告寫入知識庫**（依 skills/knowledge-query/SKILL.md 匯入流程，POST /api/import）。
3. **製作 podcast 並上傳 R2**（依 tools/article-to-podcast.ps1：從知識庫筆記生成雙主持人腳本 → TTS → 合併 MP3 → 上傳 Cloudflare R2）。

## 步驟 1：研究與撰寫報告

- 使用 WebSearch 或既有知識，深入研究唯識「八識」的核心理論、經典依據（如《成唯識論》）、與現代詮釋。
- 產出結構完整的 Markdown 報告，存檔於專案內，例如：`docs/research/唯識八識深度洞察報告_20260314.md`。
- 報告需含：八識各識功能、轉依與種子、與修行/現觀的關聯等。

## 步驟 2：寫入知識庫

- **執行原則**：若確認本機知識庫服務（localhost:3000）可連線，**必須在 CLI 內執行**本步驟（建立 import_note.json 並 POST 匯入），不得略過或改為手動說明。僅當實際執行 curl 後發生連線錯誤時，才在輸出中註明「知識庫服務未啟動，請手動匯入報告」並跳過步驟 3、改為說明手動做法。
- 先讀取 `skills/knowledge-query/SKILL.md` 的「匯入筆記」一節。
- 以 Write 工具建立 `import_note.json`：`title`、`contentText`（報告全文 Markdown）、`tags`（含 唯識、八識、佛教 等），`content` 不填。
- 執行：`curl -s -X POST "http://localhost:3000/api/import" -H "Content-Type: application/json; charset=utf-8" -d @import_note.json`（Windows 下若需避免引號問題，可改用 `Invoke-RestMethod` 或先以 Write 寫入 JSON 檔後 `-d @import_note.json`）。
- 若 curl 回傳連線錯誤（例如 connection refused、timeout），才在輸出中註明「知識庫服務未啟動，請手動匯入報告」，並跳過步驟 3，改為說明手動匯入與後續 podcast 做法。

## 步驟 3：製作 Podcast 並上傳 R2

- **執行原則**：若步驟 2 已成功取得筆記 id，**必須在 CLI 內執行**本步驟（呼叫 `tools/article-to-podcast.ps1`），不得略過或改為手動說明。僅當實際執行腳本後發生錯誤（例如 TTS 失敗、R2 上傳失敗、或 pwsh/腳本路徑不可用）時，才在輸出中註明「Podcast 製作未完成，請在本機手動執行 tools/article-to-podcast.ps1」並說明手動做法。
- 若步驟 2 成功：從 API 回傳取得新筆記 id，或呼叫 `GET http://localhost:3000/api/notes?limit=5` 取得剛匯入筆記的 id。
- 執行：`pwsh -ExecutionPolicy Bypass -File tools/article-to-podcast.ps1 -NoteId <筆記id> -Slug weishi-bashi-20260314`。
- 此腳本會：生成雙主持人對話腳本 → TTS 語音合成 → 合併 MP3 → 上傳至 Cloudflare R2（依 config/podcast.yaml）。
- 若腳本回傳錯誤或逾時，才在輸出中註明「Podcast 製作未完成，請在本機手動執行…」並說明手動做法；否則完成後依 `skills/ntfy-notify/SKILL.md` 發送通知至 topic **wangsc2025**（標題：唯識八識報告與 Podcast 已完成）。

## 最後回報

請在執行結束時簡要回報：
- 報告檔案路徑
- 是否已成功匯入知識庫（及筆記 id 若有的話）
- Podcast 是否已上傳 R2（及可播放連結若有的話）
- 任何錯誤或需手動處理的項目
