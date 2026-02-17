# 遊戲 7 維度審查任務

## 任務資訊
- 任務ID：{{task_id}}
- 任務名稱：{{task_name}}

## 操作步驟

### Step 1: 動態掃描遊戲目錄並更新追蹤檔案

```bash
# 掃描所有遊戲目錄
ls -d d:/Source/game/*/

# 讀取追蹤檔案（若不存在則建立空結構）
Read context/game-audit-tracker.json
```

**動態更新邏輯**：
1. 比對掃描結果與追蹤檔案中的 `games` 物件
2. 新發現的遊戲自動加入，初始值：
   ```json
   {
     "path": "d:/Source/game/new-game",
     "last_audit_date": null,
     "last_score": null,
     "audit_count": 0,
     "first_seen": "2026-02-17"
   }
   ```
3. 更新 `last_scan_date` 為當前日期
4. 用 Edit 工具更新追蹤檔案

### Step 2: 選出 2 個優先審查的遊戲

**選取邏輯**（依優先級排序）：
1. **優先級 1**：`last_audit_date` 為 null 的遊戲（從未審查）
2. **優先級 2**：`last_audit_date` 最舊的遊戲
3. **Tiebreaker 1**：若日期相同，比較 `last_score`（低分優先，null = 0）
4. **Tiebreaker 2**：若分數相同，比較 `audit_count`（少者優先）
5. **Tiebreaker 3**：字典序排序（遊戲名稱）
6. 記錄選中的 2 個遊戲路徑

### Step 3: 對選中的 2 個遊戲分別執行 7 維度審查

**目標遊戲 1**：`{game1_path}`

```bash
Read skills/system-audit/SKILL.md
Read config/audit-scoring.yaml
```

依照 SKILL.md 的 Phase 0-8 執行完整審查：
- Phase 0: 準備（目標系統 = game1_path，權重模型 = balanced）
- Phase 1: 資訊安全審查（6 子項）
- Phase 2: 系統架構審查（6 子項）
- Phase 3: 系統品質審查（6 子項）
- Phase 4: 系統工作流審查（5 子項）
- Phase 5: 技術棧審查（5 子項）
- Phase 6: 系統文件審查（5 子項）
- Phase 7: 系統完成度審查（5 子項）
- Phase 8: 彙總與報告

**產出**：
- 報告：`reports/audit-{game1_name}-{date}.md`
- 總分：XX/100
- 等級：X (S/A/B/C/D/F)
- TOP 5 改善建議

**目標遊戲 2**：`{game2_path}`（重複上述流程）

### Step 4: 自動修正（每個遊戲最多 5 項簡單問題）

優先修正：
- 缺失的 .gitignore
- 過時的 README.md
- 缺少的配置檔案注釋
- 簡單的程式碼品質問題（lint 錯誤）

### Step 5: 更新追蹤檔案

```bash
Edit context/game-audit-tracker.json
```

更新對應遊戲的欄位：
```json
{
  "name": "game1_name",
  "last_audit_date": "2026-02-17",
  "last_score": 72,
  "audit_count": 1
}
```

### Step 6: 匯入知識庫

將 2 個審查報告摘要寫入知識庫：
```bash
curl -s -X POST "http://localhost:3000/api/notes" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @note.json
```

### Step 7: DONE_CERT

完成認證：
```
✅ 遊戲審查完成
- 遊戲 1：{game1_name} | 分數：XX/100 | 等級：X | 報告：reports/...
- 遊戲 2：{game2_name} | 分數：YY/100 | 等級：Y | 報告：reports/...
- 追蹤檔案已更新：context/game-audit-tracker.json
- 知識庫已匯入 2 筆審查記錄
```
