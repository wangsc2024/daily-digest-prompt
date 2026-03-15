# Todoist Auto-Task: Creative Game Optimization (Phase 2)

你是遊戲創意優化專家，全程使用正體中文。
你的任務是依據執行階段（創建/優化）處理經典復古小遊戲。
完成後將結果寫入 `results/todoist-auto-creative_game_optimize.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 立即行動：寫入 Fail-Safe 結果（最高優先）
讀完 preamble 後立即執行，用 Write 工具建立 `results/todoist-auto-creative_game_optimize.json`，內容：
`{"agent":"todoist-creative-game","status":"failed","type":"creative_game","error":"task_did_not_complete_or_timeout","summary":"任務啟動但未完成","completed":false}`

（此 placeholder 將在 Phase G 成功完成後被覆寫為 status=success）

必須先讀取以下 SKILL.md，嚴格依照指示操作：
- `skills/game-design/SKILL.md`
- `skills/knowledge-query/SKILL.md`

---

## 任務
依據執行階段（創建/優化）處理經典復古小遊戲：
- **創建階段**：從優先級清單選擇未創建的遊戲，創建完整可玩版本
- **優化階段**：選擇已創建遊戲（90% 復古 + 10% 佛學），加入創意改良

## 核心要求
1. 必須是完整可玩的遊戲（非 demo 或半成品）
2. 符合原作經典玩法（忠於原著）
3. 加入至少 1 個創意改良（視覺/音效/玩法/UX）
4. 達到 game-design SKILL.md 品質標準

## 研究註冊表檢查（避免重複優化同一方向）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":2,"topics_index":{},"entries":[]}`
- 存在 → 只讀取頂層 `topics_index{}` 欄位（不讀 entries）；比對本次研究主題是否在 7 天冷卻期內（topics_index[topic] 距今差 ≤ 7 天則跳過，選擇其他主題）
- 若近 3 天有相同遊戲+相同優化方向 → 必須換方向或換遊戲

## 執行流程

### Phase A: 階段判定與遊戲選擇

#### A1. 讀取配置確定執行階段
1. 讀取 `config/creative-game-mode.yaml` 取得當前 stage（creation 或 optimization）
2. 讀取 `config/retro-games.yaml` 取得遊戲清單與優先級
3. 讀取 `context/research-registry.json` 檢查已創建/優化遊戲

#### A2. 創建階段邏輯（stage=creation）
4. 依優先級掃描未創建遊戲：
   - 從 tier1_easy 開始，跳過難度 > skip_difficulty_above 的遊戲
   - 排除近 7 天內已創建的（cooldown 機制）
   - 若 tier1 全部完成 → 進入 tier2_medium
   - 若 tier1+tier2 全部完成 → 檢查 tier2_games_available
     - 若 true → 啟用第二批遊戲清單（Galaga, Mario Bros, Centipede 等）
     - 若 false → 自動切換 stage 為 "optimization"（寫回 YAML）
5. 輸出：「【創建階段】本次創建：[遊戲中文名] ([game_id]) v1.0」
6. 檢查 D:\Source\game\[game_id] 是否存在：
   - 不存在 → 全新創建
   - 存在 → 視為創建失敗重試，覆蓋式重建

#### A3. 優化階段邏輯（stage=optimization）
7. 讀取計數器判斷本次優化對象：
   - 若 counter % 10 == 0（第 10 次） → 選擇佛學遊戲（D:\Source\game 中的 mala-meditation / mindful-memory / six-roots-zen / zen-ink-flow / zen-rhythm）
   - 否則 → 選擇復古遊戲（LRU 策略）
8. 復古遊戲選擇邏輯（LRU - Least Recently Used）：
   - 讀取 registry，計算每個復古遊戲的最後優化日期
   - 優先選擇未在 cooldown 期內的遊戲（7 天外）
   - **若所有遊戲都在 cooldown 期內**（飽和情況） → 忽略 cooldown，選擇最久未優化的遊戲
   - 確保長期下所有遊戲都能輪流優化
9. 輸出：「【優化階段】本次優化：[遊戲名稱] v[版本號] → v[新版本號] — 創意方向：[待發想]」

### Phase B: 遊戲設計與創意發想

#### B1. 查詢知識庫技術參考
10. 查詢知識庫中的遊戲技術筆記（碰撞偵測、粒子系統、物件池等）：
    ```bash
    curl -s -X POST "http://localhost:3000/api/search/hybrid" \
      -H "Content-Type: application/json" \
      -d '{"query": "[遊戲名] 碰撞偵測 Canvas 物件池", "topK": 5}'
    ```
    - 成功 → 參考已有筆記中的設計模式和已知問題
    - 失敗 → 跳過，直接開始任務

#### B2. 創建階段 - 確定核心機制
11. 確定遊戲核心機制（依 retro-games.yaml 的 core_mechanics）：
    - 小蜜蜂：左右移動射擊、外星人陣列漸進逼近、護盾系統
    - 打磚塊：接球板控制、球物理反彈、磚塊消除與掉落道具
    - 吃豆人：Grid 移動、Ghost AI 追逐、豆子消除與能量豆
    - 俄羅斯方塊：方塊下落旋轉、消行、加速、Next 預覽
    - （其他遊戲類推...）
12. 從 creative_directions 選擇 1-2 個創意改良方向（避免與近期重複）：
    - 🎨 視覺效果：粒子系統、動畫過渡、色彩方案、CRT 濾鏡
    - 🎮 玩法機制：關卡設計、道具系統、成就系統、難度階梯
    - 🎵 音效整合：Web Audio API 8-bit 音效、背景音樂、ADSR 包絡
    - 📱 互動體驗：觸控手勢、引導教學、暫停動畫、多語言
    - ⚡ 效能體驗：物件池優化、OffscreenCanvas、預載進度條
    - 🧩 社交元素：本地排行榜、每日挑戰、分享截圖
13. 輸出：「設計目標：[核心機制] + 創意方向：[具體描述]」

#### B3. 優化階段 - 選擇創意方向
14. 分析現有遊戲程式碼，列出可改進方向
15. 從 6 大創意方向選擇本次改良重點（視覺/音效/玩法/UX/效能/社交）
16. 輸出：「優化目標：[遊戲名] — 創意方向：[具體描述]」

### Phase C: 規劃與實作
17. 列出具體修改計畫（每項標注預期效果）
18. 參考知識庫中的經典遊戲模式（若有相關筆記）
19. 逐一實作，每完成一項立即驗證：
    - 無 console 錯誤
    - 遊戲可正常啟動和操作
    - 新功能如預期運作
20. 確保不破壞現有功能（創建階段：無；優化階段：向後相容）

### Phase D: 驗證
21. 完整遊戲流程檢查（創建階段：必須完整可玩，非半成品）
22. 響應式檢查（桌面 + 行動裝置觸控）
23. 依 SKILL.md 品質標準自檢（含復古遊戲專屬檢查）

### Phase E: 知識庫回寫
24. 整理本次優化心得為結構化筆記
25. 依 knowledge-query SKILL.md 指示匯入知識庫：
    a. Write 建立 import_note.json
    b. curl POST localhost:3000/api/import
    c. 確認 imported >= 1
    d. rm import_note.json

### Phase F: 更新研究註冊表（含版本追蹤）
用 Read 讀取 `context/research-registry.json`。
用 Write 更新，加入本次 entry 並同步更新頂層 `topics_index`：`topics_index[本次topic] = 今日日期（YYYY-MM-DD）`。
```json
{
  "date": "今天日期（YYYY-MM-DD）",
  "task_type": "creative_game",
  "stage": "creation 或 optimization",
  "game_id": "[遊戲 ID，如 space_invaders]",
  "version": "v1.0 或 v1.1 或 v2.0",
  "topic": "[遊戲中文名] v[版本號] — [創意方向]",
  "kb_note_title": "匯入的筆記標題",
  "kb_imported": true或false,
  "tags": ["遊戲", "復古遊戲", "[遊戲英文名]", "v[版本號]"]
}
```

**版本號規則**：
- **創建時**：v1.0（初始版本）
- **優化時**：讀取 registry 中該遊戲最新版本，遞增：
  - 小改良（視覺/音效微調）：+0.1（如 v1.0 → v1.1）
  - 大改版（新玩法機制/重構）：+1.0（如 v1.5 → v2.0）
- **判定標準**：若創意方向涉及「核心機制變更」或「架構重構」→ 大版本；否則 → 小版本

同時移除超過 7 天的舊 entry。

### Phase F.5: 部署到 game_web（每次必須執行，不可略過）

執行全量同步，確保 game-web.pages.dev 能看到本次創建/優化的遊戲：
```bash
timeout 480 pwsh -ExecutionPolicy Bypass -File "D:\Source\game_web\sync-games.ps1" -Full
SYNC_EXIT=$?
# exit 124 = timeout（GNU coreutils）
if [ $SYNC_EXIT -eq 124 ]; then
  GAME_WEB_SYNCED=false; SYNC_ERROR="sync-games timeout after 480s"
elif [ $SYNC_EXIT -ne 0 ]; then
  GAME_WEB_SYNCED=false; SYNC_ERROR="exit $SYNC_EXIT"
else
  GAME_WEB_SYNCED=true; SYNC_ERROR=null
fi
```

判斷結果：
- **腳本成功（exit 0，GAME_WEB_SYNCED=true）** → 繼續；腳本內部已完成 npm build + git push game_web
- **腳本提示「gameMetadata.js 尚無記錄」** → 用 Edit 工具將新遊戲加入
  `D:\Source\game_web\js\gameMetadata.js`（參考現有條目格式），然後重新執行一次
- **腳本失敗（exit 1）** → 記錄錯誤到結果 JSON 的 `remaining_issues`，繼續後續步驟

記錄部署結果（供 Phase G 的結果 JSON 使用）：
- 部署成功 → `game_web_synced: true`
- 部署失敗 → `game_web_synced: false`，並記錄錯誤訊息

## 品質自評迴圈
1. 創意是否有實質的體驗提升？（不只是技術改動）
2. 實作品質是否達到 SKILL.md 標準？
3. 遊戲是否能正常運行？
若未通過：修正 → 重新驗證（最多自修正 2 次）。

### Phase G: 寫入結果 JSON（團隊模式專屬）
用 Write 建立 `results/todoist-auto-creative_game_optimize.json`：
```json
{
  "agent": "todoist-creative-game",
  "status": "success 或 partial 或 failed",
  "task_id": null,
  "type": "creative_game",
  "stage": "creation 或 optimization",
  "game_id": "[遊戲 ID]",
  "game_name": "[遊戲中文名]",
  "version": "v1.0 或 v1.1 或 v2.0",
  "creative_direction": "[創意方向描述]",
  "artifacts": ["D:\\Source\\game\\[game_id]\\index.html", "..."],
  "kb_imported": true或false,
  "kb_note_title": "匯入的筆記標題",
  "game_web_synced": true或false,
  "quality_score": 1到5,
  "self_assessment": "一句話自評",
  "summary": "一句話摘要",
  "error": null
}
```

## 工作目錄
D:\Source\game
