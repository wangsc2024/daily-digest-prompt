# 唯識第八識任務執行回報

**執行時間**：2026-03-14  
**任務檔**：temp/cursor-cli-task-weishi-dibashi.md

---

## 一、報告檔案

| 項目 | 說明 |
|------|------|
| **路徑** | `docs/research/唯識第八識深度洞察報告_20260314.md` |
| **字數** | 約 4,200 字 |
| **結構** | 七章 + 結語：定義與異名、種子與現行、能藏所藏執藏、與前七識關係、轉依、經典依據、現代詮釋 |

報告已依任務要求完成，涵蓋：第八識定義與異名、種子與現行、能藏所藏執藏、與修行/轉依的關聯、現代詮釋。

---

## 二、知識庫匯入（需手動執行）

由於本環境無法執行終端指令，請在專案目錄下手動執行下列步驟：

### 步驟 2.1：產生 import_note.json

```powershell
cd D:\Source\daily-digest-prompt
uv run python tools/create_import_dibashi.py
```

此腳本會讀取報告並產生 `import_note.json`（符合 knowledge-query SKILL 的 notes 陣列格式）。

### 步驟 2.2：確認知識庫服務

```powershell
curl -s "http://localhost:3000/api/health"
```

若服務未啟動，請先啟動知識庫（localhost:3000），再繼續。

### 步驟 2.3：匯入至知識庫

```powershell
curl -s -X POST "http://localhost:3000/api/import" -H "Content-Type: application/json; charset=utf-8" -d @import_note.json
```

成功時會回傳 `noteIds`，記錄該 id 供步驟 3 使用。

### 步驟 2.4：刪除暫存檔

```powershell
Remove-Item import_note.json -ErrorAction SilentlyContinue
```

---

## 三、Podcast 製作與上傳 R2（需手動執行）

### 步驟 3.1：取得筆記 ID

若步驟 2 成功，從 API 回傳的 `result.noteIds[0]` 取得 id。或執行：

```powershell
curl -s "http://localhost:3000/api/notes?limit=5"
```

從最近筆記列表取得「唯識第八識（阿賴耶識）深度洞察報告」的 id。

### 步驟 3.2：執行 article-to-podcast

```powershell
pwsh -ExecutionPolicy Bypass -File tools/article-to-podcast.ps1 -NoteId <筆記id> -Slug weishi-dibashi-20260314
```

將 `<筆記id>` 替換為實際的 UUID（可為短 ID 前綴，腳本會自動解析）。

### 步驟 3.3：輸出與通知

- MP3 輸出：`output/podcasts/<標題>_<時間戳>.mp3`
- 若 config/podcast.yaml 的 `cloud_upload.enabled: true`，會自動上傳 R2 並回傳公開 URL
- 腳本會自動發送 ntfy 通知至 topic `wangsc2025`

---

## 四、已完成項目

- [x] 深入研究第八識並產出深度洞察報告
- [x] 報告存檔：docs/research/唯識第八識深度洞察報告_20260314.md
- [x] 建立 tools/create_import_dibashi.py（匯入腳本）

## 五、待手動完成項目

- [ ] 執行 create_import_dibashi.py 產生 import_note.json
- [ ] 執行 curl POST /api/import 匯入知識庫
- [ ] 執行 article-to-podcast.ps1 製作 Podcast
- [ ] 確認 R2 上傳與 ntfy 通知

---

## 六、錯誤與備註

- **知識庫服務未啟動**：若 localhost:3000 無法連線，請先啟動知識庫後再執行步驟 2、3
- **終端指令限制**：本環境無法執行終端指令，上述步驟需在本機 PowerShell 中手動執行
