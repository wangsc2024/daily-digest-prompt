# Cursor CLI 任務：唯識「第八識」深度報告 + 知識庫 + Podcast 上傳 R2

你正在專案 D:\Source\daily-digest-prompt 中執行。請遵守專案根目錄 CLAUDE.md 的 Skill-First 與所有規則。

## 任務目標

1. **深入研究**唯識學派核心理論中的**第八識**（阿賴耶識）：功能、種子與現行、異熟、與前七識的關係、轉依、經典依據與現代詮釋。產出一份**深度洞察報告**（Markdown，建議 3000–5000 字）。
2. **將報告寫入知識庫**（依 skills/knowledge-query/SKILL.md 匯入流程，POST /api/import）。
3. **製作 podcast 並上傳 R2**（依 tools/article-to-podcast.ps1：從知識庫筆記生成雙主持人腳本 → TTS → 合併 MP3 → 上傳 Cloudflare R2）。

## 步驟 1：研究與撰寫報告

- 使用 WebSearch 或既有知識，聚焦**第八識（阿賴耶識）**：藏識、種子識、異熟識、與七識的關係、轉依、經典（如《成唯識論》《解深密經》）。
- 產出結構完整的 Markdown 報告，存檔於：`docs/research/唯識第八識深度洞察報告_20260314.md`。
- 報告需含：第八識定義與異名、種子與現行、能藏所藏執藏、與修行/轉依的關聯、現代詮釋。

## 步驟 2：寫入知識庫

- 先讀取 `skills/knowledge-query/SKILL.md` 的「匯入筆記」一節。
- 以 Write 工具建立 `import_note.json`：`title`、`contentText`（報告全文 Markdown）、`tags`（含 唯識、第八識、阿賴耶識、佛教 等），`content` 不填。
- 執行：`curl -s -X POST "http://localhost:3000/api/import" -H "Content-Type: application/json; charset=utf-8" -d @import_note.json`。
- 若 localhost:3000 無法連線，在輸出中註明「知識庫服務未啟動，請手動匯入報告」，並跳過步驟 3。

## 步驟 3：製作 Podcast 並上傳 R2

- 若步驟 2 成功：從 API 回傳或 `GET http://localhost:3000/api/notes?limit=5` 取得新筆記 id。
- 執行：`pwsh -ExecutionPolicy Bypass -File tools/article-to-podcast.ps1 -NoteId <筆記id> -Slug weishi-dibashi-20260314`。
- 完成後可依 `skills/ntfy-notify/SKILL.md` 發送通知至 topic **wangsc2025**。

## 最後回報

- 報告檔案路徑
- 是否已匯入知識庫（及筆記 id）
- Podcast 是否已上傳 R2（及可播放連結）
- 任何錯誤或需手動處理的項目
