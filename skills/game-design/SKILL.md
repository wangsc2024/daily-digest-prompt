---
name: game-design
version: "1.0.0"
description: |
  遊戲設計與優化 — HTML5/JS 遊戲品質提升、復古遊戲創建、UX 最佳化、Cloudflare Pages 部署。
  支援兩大方向：1) 經典復古遊戲現代化（Space Invaders/Pac-Man/Tetris 等）
              2) 創意主題遊戲優化（佛學/正念等主題遊戲）
  Use when: 遊戲、game、遊戲優化、遊戲設計、HTML5、復古遊戲、經典遊戲、Cloudflare Pages。
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
cache-ttl: 0min
triggers:
  - "遊戲"
  - "game"
  - "遊戲優化"
  - "遊戲設計"
  - "HTML5 遊戲"
  - "遊戲品質"
  - "Cloudflare Pages"
  - "Canvas 遊戲"
  - "JavaScript 遊戲"
  - "遊戲部署"
  - "遊戲效能"
  - "HTML5"
---

# 遊戲設計與優化

HTML5/JavaScript 遊戲品質提升、UX 最佳化與 Cloudflare Pages 部署指引。

## 適用場景

- HTML5 Canvas / JavaScript 遊戲開發與優化
- 遊戲 UX 設計改善（操控性、視覺回饋、難度曲線）
- Cloudflare Pages 靜態網站部署
- 遊戲效能分析（FPS、記憶體、載入時間）
- 程式碼品質審查（針對遊戲邏輯特性）

## 經典復古遊戲技術實作要點

| 遊戲 | 核心技術 | 碰撞類型 | 難點 |
|------|---------|---------|------|
| Space Invaders | 陣列移動、子彈池 | AABB | 護盾像素級碰撞 |
| Breakout | 球物理、反彈角度 | 圓形+AABB | 角度計算精度 |
| Pac-Man | Grid 移動、Ghost AI | Grid-based | Pathfinding 演算法 |
| Tetris | 矩陣運算、旋轉 | Grid-based | SRS 旋轉系統 |
| Pong | 簡單物理、AI 預測 | AABB | AI 難度調整 |
| Frogger | 碰撞偵測、車流 | AABB | 時間壓力設計 |
| Dig Dug | 地形破壞、敵人 AI | Grid-based | 地形動態更新 |

## 創意現代化方向
- 視覺：粒子效果、螢幕震動、色彩主題切換、CRT 濾鏡
- 音效：Web Audio API 8-bit 音效合成、動態背景音樂
- 玩法：關卡編輯器、道具系統、成就解鎖、Boss 關卡
- UX：觸控優化、手勢操控、引導動畫、多語言
- 效能：物件池優化、OffscreenCanvas、預載進度條
- 社交：本地排行榜、每日挑戰、分享截圖

## 品質標準（強制 — 過去品質不佳，以下為必達標準）

### 1. 程式碼品質
- 遊戲循環（game loop）必須使用 `requestAnimationFrame`，禁止 `setInterval`/`setTimeout`
- 碰撞偵測精確度：最低 AABB，建議 SAT 或圓形碰撞
- 資源管理：所有圖片/音效必須預載，顯示載入進度條
- 記憶體管理：離開畫面的物件必須及時回收，避免記憶體洩漏
- 事件處理：必須同時支援鍵盤、滑鼠、觸控三種輸入
- 狀態管理：遊戲必須有明確的狀態機（載入→選單→遊戲中→暫停→結束）

### 2. UX 品質
- 操控回饋：每個玩家動作需有視覺或音效回饋（延遲 < 100ms）
- 難度曲線：漸進式設計，第一關必須讓新手能輕鬆通過
- UI 清晰度：分數、生命值、關卡等資訊必須一眼可見
- 響應式設計：手機（觸控）與桌面（鍵盤+滑鼠）皆可玩
- 無障礙：色彩對比度 >= 4.5:1（WCAG AA），重要資訊不僅依賴顏色
- 暫停功能：遊戲中必須可暫停，按 Esc 或觸控暫停按鈕

### 3. 效能標準
- 目標 60 FPS（最低可接受 30 FPS）
- 首次載入 < 3 秒（透過 Cloudflare Pages CDN）
- 單幀繪製時間 < 16ms（用 `performance.now()` 測量）
- Canvas 繪製：批次繪製同類物件，減少 context 切換

### 4. 部署流程（Cloudflare Pages）
1. 確認專案結構：`index.html` + `js/` + `assets/`
2. 確認無 Node.js 依賴（純靜態）或有正確的 build 設定
3. 用 git push 到 GitHub（Pages 自動部署）或 `npx wrangler pages deploy ./`
4. 驗證部署 URL 可存取且遊戲可正常運行

## 知識庫整合

執行遊戲任務前，建議先查詢知識庫已有的遊戲設計筆記：
```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "遊戲設計 HTML5 最佳實踐", "topK": 5}'
```
- 成功 → 參考已有筆記中的設計模式和已知問題
- 失敗 → 跳過，直接開始任務

## 完成後回寫知識庫

遊戲優化完成後，將本次修改的心得寫入知識庫：
1. 用 Write 建立 `import_note.json`
2. `curl -s -X POST "http://localhost:3000/api/import" -H "Content-Type: application/json; charset=utf-8" -d @import_note.json`
3. 確認 `imported >= 1`
4. `rm import_note.json`

## 程式碼審查清單（完成後必須逐項自檢）

- [ ] 遊戲可啟動且無 console 錯誤
- [ ] 主要遊戲機制運作正常（移動、碰撞、得分）
- [ ] 觸控與鍵盤操控皆可用
- [ ] 無明顯效能問題（肉眼可見卡頓）
- [ ] 遊戲有完整狀態流程（載入→遊戲→結束）
- [ ] 部署 URL 可存取（若有部署步驟）

## 復古遊戲品質檢查（額外項目）
- [ ] 遊戲機制忠於原作經典玩法
- [ ] 有明確的遊戲結束條件（勝利/失敗）
- [ ] 分數系統正確計算與顯示
- [ ] 至少有 1 個創意改良（非單純複製）
- [ ] 首次遊玩 30 秒內能理解玩法（無需說明書）
