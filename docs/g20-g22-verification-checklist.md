# G20-G22 P1 修復驗證清單

> 這三項修復已在 bot.js 和 index.html 實施完畢（2026-02-28 確認）。
> 本文件記錄手動驗證步驟，確認功能正常運作。

## 前置條件

1. bot.js 已啟動（`node D:\Source\wsc-bot01\bot.js`）
2. Gun Relay 已啟動（`node D:\Source\my-gun-relay\index.js`）
3. 開啟 `http://localhost:8765`（前端聊天室）
4. Chrome DevTools 開啟（Network + Console 面板）

---

## G20：Bot Epub 簽章驗證防 MITM

**驗證目標**：確認前端會驗證 bot epub 的 SEA 簽章，偽造 epub 時拒絕連線。

**測試步驟**：
1. 在 Gun Relay 的 `data/radata/` 目錄中找到 `wsc-bot/handshake` 節點
2. 手動修改 `epub` 值為偽造字串（保留 `sig` 不變）
3. 重新整理前端頁面，觀察 Console

**預期結果**：
- Console 顯示：`[Gun] Bot epub 驗證失敗，可能存在中間人攻擊，拒絕連線`
- 前端不建立 sharedSecret
- 聊天室無法發送訊息

**驗證程式碼位置**：
- bot.js L492-494：`SEA.sign(myPair.epub, myPair)` → 廣播 `epub + sig`
- index.html L966-980：`SEA.verify(hw.sig, hw.epub)` → 驗證失敗則 `resolve(null)`

---

## G21：API Key SessionStorage 防 XSS

**驗證目標**：確認 API Key 僅存於 sessionStorage（非 localStorage），頁籤關閉即清除。

**測試步驟**：
1. 開啟 `http://localhost:8765`，在 API Key 輸入框填入測試值（如 `test-key-123`）
2. 點擊「連線」或觸發保存動作
3. 開啟 DevTools → Application → Storage
4. 確認：
   - `sessionStorage` 有 `gun_bot_api_key = test-key-123` ✅
   - `localStorage` **沒有** `gun_bot_api_key` ✅
5. 關閉此頁籤，重新開啟 `http://localhost:8765`
6. 確認 API Key 輸入框為**空白**（sessionStorage 已清除）

**驗證程式碼位置**：
- index.html L817：`type="password"` 遮罩輸入
- index.html L928-933：初始化讀取 sessionStorage
- index.html L1016-1024：儲存到 sessionStorage（非 localStorage）

---

## G22：排程 API 指數退避重試

**驗證目標**：確認 bot.js 關閉時，前端重試間隔依序為指數退避（非固定 30 秒）。

**測試步驟**：
1. 開啟 `http://localhost:8765`，確認排程面板已載入
2. 關閉 bot.js（Ctrl+C 停止進程）
3. 開啟 DevTools → Network 面板，篩選 `scheduled-tasks` 請求
4. 觀察請求時間間隔：

| 失敗次數 | 預期等待時間 |
|---------|------------|
| 第 1 次 | ~2 秒 |
| 第 2 次 | ~4 秒 |
| 第 3 次 | ~8 秒 |
| 第 4 次 | ~16 秒 |
| 第 5 次+ | ~30 秒（上限） |

5. 重新啟動 bot.js，確認成功後計數歸零（下次失敗重從 2 秒開始）

**驗證程式碼位置**：
- index.html L1148-1149：`scheduleFailCount = 0` 失敗計數器
- index.html L1183-1190：`fetchWithTimeout()` 8 秒逾時封裝
- index.html L1210-1218：`Math.min(1000 * Math.pow(2, scheduleFailCount), 30000)`

---

## 驗證結果記錄

| 項目 | 測試日期 | 通過 | 備註 |
|------|---------|------|------|
| G20 MITM 防護 | | ⬜ 待測試 | |
| G21 sessionStorage | | ⬜ 待測試 | |
| G22 指數退避 | | ⬜ 待測試 | |
