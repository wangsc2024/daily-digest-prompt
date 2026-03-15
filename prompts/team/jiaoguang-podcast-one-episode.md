# 淨土教觀學苑 Podcast 依序製作 1 集（cursor-cli skill 模式）

依 **docs/plans/淨土教觀學苑podcast專輯.md** 與 **context/jiaoguang-podcast-next.json** 依序製作 1 集，並更新下一集編號。

## 步驟

1. **讀取狀態**：Read `context/jiaoguang-podcast-next.json`，取得 `next_episode`（若無檔案或無效則視為 1）。
2. **讀取專輯列**：Read `docs/plans/淨土教觀學苑podcast專輯.md`，表格資料從第 29 行起，第 N 集為第 28+N 行（0-based 為 index 27+N）。從該列解析出「題目名稱」（第 2 欄）與「所屬課程」（第 3 欄，若有）。
3. **課程快取（Token 節省）**：
   - 取 `課程名` 作為快取 key（若無第 3 欄，用「未分類」）
   - 嘗試 Read `temp/jiaoguang-course-cache-<課程名>.json`
   - 若檔案存在且 `created_at` 距今 ≤ 7 天 → 直接使用快取中的 `description` 作為課程背景說明
   - 若不存在或已過期 → 從本集題目生成 1-2 句課程簡介，用 Write 工具寫入 `temp/jiaoguang-course-cache-<課程名>.json`：
     ```json
     { "course_name": "<課程名>", "description": "<課程簡介>", "created_at": "<ISO8601>", "ttl_days": 7 }
     ```
3.5. **跨系統去重檢查（統一入口）**：Read `context/podcast-history.json`，計算 today（YYYY-MM-DD）。
   - 從 `summary.recent_topics` 比對本集題目名稱是否已有 `expires_at >= today` 的項目：
     - 若**命中**：在執行紀錄中注記「⚠️ 本集主題『{題目名稱}』近期（{last_used}）已由其他系統製作，仍依計劃順序執行」（不跳過，維持計劃連貫性）
     - 若未命中：繼續正常執行
   - 從 `summary.recent_note_ids` 建立 `active_note_ids` 清單（expires_at >= today 者），供步驟 4 的 `article-to-podcast.ps1` 參考（若結果筆記全在清單中，仍照常執行但記錄警告）
4. **製作 1 集**：執行 `pwsh -ExecutionPolicy Bypass -File tools/article-to-podcast.ps1 -Query "<題目名稱>" -Slug "jiaoguang-ep<N>-yyyyMMdd"`（N 為本集編號，yyyyMMdd 為今日）。
5. **更新狀態**：將 `context/jiaoguang-podcast-next.json` 寫回：`next_episode` 為 N+1（若 N=750 則為 1）、`last_produced` 為 N、`last_topic` 為題目名稱、`updated_at` 為當前時間。
5.5. **寫入播客歷史（跨系統去重）**：Read `context/podcast-history.json`，在 `summary` 段落執行以下更新後寫回：
   - 計算 today = 今日日期（YYYY-MM-DD），expires_at = today + `cooldown_days`（預設 30）天
   - 若步驟 4 產出的 note_id 已存在於 `recent_note_ids`（比對 `.note_id`），則更新其 `last_used` 與 `expires_at`；否則在陣列末尾新增 `{"note_id": "<note_id>", "last_used": "<today>", "expires_at": "<expires_at>"}`
   - 將本集題目名稱加入 `recent_topics`：若已存在（比對 `.topic`）則更新 `last_used/expires_at`；否則新增 `{"topic": "<題目名稱>", "last_used": "<today>", "expires_at": "<expires_at>"}`
   - 同步移除 `recent_note_ids` 與 `recent_topics` 中 `expires_at < today` 的過期項目
   - 在 `episodes` 陣列開頭插入本集記錄：`{"episode_title": "<題目名稱>", "notes_used": ["<note_id>"], "note_titles": ["<note_title>"], "topics": ["<題目名稱>"], "source": "jiaoguang-plan", "created_at": "<ISO8601 now>"}`
   - **跨任務去重**：Read `context/research-registry.json`，在 `topics_index{}` 中以「課程名稱 + 題目」為 key、today 為 value 新增或更新，寫回 research-registry.json（保留 entries[] 原樣）

僅執行上述步驟，勿擴充其他任務。
