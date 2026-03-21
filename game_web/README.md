# game_web（猜數字規則＋Vite 靜態站）

## 任務指定路徑

請將本目錄**完整複製**到 **`D:\source\game_web`**（若上層目錄不存在請先建立），以符合任務要求的產出路徑。

## 指令

```powershell
cd D:\source\game_web
npm install
npm run build
npm run preview
```

`npm run build` 產出 `dist/`，可直接上傳至 **Cloudflare Pages**（build output directory = `dist`）。

## 檔案

- `guess-number-rules.txt`：交付用**純規則文字**（與 `public/guess-number-rules.txt` 內容一致）。
- `docs/workflow-draft.md`：設計遊戲 workflow 概念／機制草稿。
- `docs/delivery-notes.md`：字數驗證與路徑說明。

## Git / 部署

於 `D:\source\game_web` 內初始化 repo、`git push` 至 GitHub 並連結 Cloudflare Pages 即可觸發部署。本機自動化若無遠端權限，請在本機手動完成 `git remote` 與推送。
