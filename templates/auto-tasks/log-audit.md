# 系統 Log 深度審查 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 log_audit_count < 1
> 主 Agent 用此模板建立 task_prompt.md，透過 `claude -p` 執行

## 審查流程

### 1. 讀取系統狀態
1. 讀取 `skills/scheduler-state/SKILL.md`
2. 讀取 `state/scheduler-state.json` — 分析最近 30 筆執行記錄
3. 讀取 `context/digest-memory.json` — 分析記憶中的異常模式

### 2. 掃描 Log 檔案
用 Bash 讀取最近 7 天的日誌：
```bash
ls -t logs/*.log | head -10
```

逐一讀取每個 log 檔案（用 Read 工具），重點搜尋：

| 搜尋模式 | 問題類型 | 嚴重度 |
|---------|---------|--------|
| `[ERROR]` | 執行錯誤 | 高 |
| `[WARN]` | 警告訊息 | 中 |
| `RETRY` | 重試觸發 | 中 |
| `TIMEOUT` | 超時 | 高 |
| `failed` | 區塊失敗 | 高 |
| `cache_degraded` | 快取降級 | 低 |
| `duration_seconds.*([3-9][0-9][0-9]\|[0-9]{4,})` | 耗時超過 300 秒 | 中 |
| `nul` | 可能的 nul 檔案問題 | 高 |

### 3. 分析問題並分類
```
🔍 Log 審查發現
━━━━━━━━━━━━━━━━━━━━━
🔴 嚴重問題（必須修復）：
1. [問題描述] — 出現次數 N 次 — 影響範圍

🟡 改善建議（建議優化）：
1. [問題描述] — 出現次數 N 次 — 可能的改善方向

🟢 正常狀態：
- 成功率 XX% | 平均耗時 XX 秒
```

若全部 🟢 正常 → 跳至寫入知識庫（僅記錄分析結果）。

### 4. 深入根因分析（每個 🔴/🟡 項目必做）
對每個問題回答：
1. **根因**：程式碼 bug、設定錯誤、外部依賴還是設計缺陷？
2. **模式**：偶發還是規律性？與特定時段/任務類型有關嗎？
3. **影響**：對系統穩定性、執行效率、用戶體驗的實際影響？
4. **關聯**：是否與其他問題有共同根因？

### 5. 擬定方案 + 正確性驗審

#### 5.1 搜尋參考案例
- 用 WebSearch 搜尋相關解決方案
- 用知識庫 hybrid search 查詢歷史審查筆記

#### 5.2 擬定修改方案
- **修改檔案清單**：每個檔案的具體變更
- **修改範圍**：只改必要的部分，不做額外重構
- **預期效果**：修改後應觀察到什麼改變

#### 5.3 方案正確性驗審（必做）

| # | 驗審項目 | 通過條件 |
|---|---------|---------|
| 1 | 邏輯正確 | 修改真正解決根因，而非遮蔽症狀 |
| 2 | 副作用評估 | 不影響其他 Agent，不改變下游解析格式 |
| 3 | 語法正確 | PowerShell / Markdown / JSON 語法無誤 |
| 4 | 編碼規範 | .ps1 維持 UTF-8 with BOM，JSON 維持 UTF-8 |

> 4 項全部通過 → 進入備份與執行。任一項不通過 → 修正方案（最多 2 次），仍不通過則記錄為「待手動處理」。

### 6. 備份目標檔案（修改前必做）
```bash
cp "目標檔案路徑" "目標檔案路徑.bak"
```

### 7. 建立子 Agent 執行修正
用 Write 工具建立 `task_prompt.md`（UTF-8），含：
- 問題描述 + 根因分析
- 修改方案（已通過驗審）
- 驗證清單
- DONE_CERT 要求

執行：
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,Edit,Glob,Grep"
```

### 7.1 修改後驗證（子 Agent 完成後）
1. `git diff` 確認修改範圍與方案一致
2. 功能驗證（.ps1 可讀性檢查）
3. 回歸確認（關鍵邏輯未被破壞）

若驗證失敗 → 用備份還原：`cp "檔案.bak" "檔案"`

### 7.2 清理備份
驗證通過後：`rm -f D:/Source/daily-digest-prompt/*.bak`

### 8. 將分析結果寫入知識庫
用 Write 建立 `import_note.json`，匯入 localhost:3000/api/import。

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`log_audit_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=log_audit 記錄（含 findings 和 fixes 數量）
3. 清理：`rm task_prompt.md`
