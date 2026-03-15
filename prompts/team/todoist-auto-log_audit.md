你是系統維護助手，全程使用正體中文。
你的任務是對 daily-digest-prompt 系統進行 Log 深度審查，找出問題並執行修正。
完成後將結果寫入 `results/todoist-auto-log_audit.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 立即行動：寫入 Fail-Safe 結果（最高優先）
讀完 preamble 後立即執行，用 Write 工具建立 `results/todoist-auto-log_audit.json`，內容：
`{"agent":"todoist-logaudit","status":"failed","type":"log_audit","error":"task_did_not_complete_or_timeout","summary":"任務啟動但未完成","completed":false}`

（此 placeholder 將在步驟 8 成功完成後被覆寫為 status=success）

必須先讀取以下 SKILL.md：
- `skills/scheduler-state/SKILL.md`
- `skills/knowledge-query/SKILL.md`

---

## 前處理（Groq 加速）

在執行正式步驟前，嘗試用 Groq Relay 預分類日誌模式：

```bash
GROQ_OK=$(curl -s --max-time 3 http://localhost:3002/groq/health 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
```

若 `GROQ_OK` 為 `ok`：
1. 讀取 `state/scheduler-state.json`，取最近 10 筆 runs 的 status 欄位
2. 用 Write 工具建立 `temp/groq-req-log_audit.json`（UTF-8）：
   ```json
   {"mode": "classify", "content": "<最近10筆runs的status清單>"}
   ```
3. 執行：
   ```bash
   curl -s --max-time 20 -X POST http://localhost:3002/groq/chat -H "Content-Type: application/json; charset=utf-8" -d @temp/groq-req-log_audit.json > temp/groq-result-log_audit.json
   ```
4. Read `temp/groq-result-log_audit.json`，取得分類結果供步驟 1 直接使用

若 `GROQ_OK` 不為 `ok`：略過此步驟，由 Claude 自行完成（無降級邏輯改變）。

## 步驟 1：讀取系統狀態
1. 讀取 `state/scheduler-state.json` — 分析最近 30 筆執行記錄
2. 讀取 `context/digest-memory.json` — 分析記憶中的異常模式

## 步驟 2：委派 Explore 子 Agent 掃描 Log 檔案

**禁止主 Agent 逐一 Read 每個 log 檔案**（10+ 個大型 .log 檔案會耗盡 context）。
使用 Agent 工具（`subagent_type=Explore`）委派掃描，主 Agent 只接收摘要：

向子 Agent 提問（prompt 內容）：
> 請用 Bash 掃描 `logs/` 目錄下最近 7 天的 .log 檔案（`ls -t logs/*.log | head -10`）。
> 對每個 log 檔案用 `grep -c` 統計關鍵字出現次數：`ERROR`、`WARN`、`RETRY`、`TIMEOUT`、`failed`、`cache_degraded`、`nul`。
> 同時擷取每種關鍵字的最新一行（`grep -m1 "PATTERN" 檔案`）作為代表樣本。
> 回傳 JSON 格式：`{"file": "filename", "counts": {"ERROR": N, ...}, "samples": {"ERROR": "最新一行"}}`。
> 限制回傳 ≤ 50 行 JSON。

從子 Agent 回傳的摘要識別高頻問題（counts 大於 0 的類型）。

## 步驟 3：分析問題並分類
```
🔍 Log 審查發現
━━━━━━━━━━━━━━━━━━━━━
🔴 嚴重問題（必須修復）：
🟡 改善建議（建議優化）：
🟢 正常狀態
```

若全部 🟢 → 跳至步驟 7（僅記錄，不修正）。

## 步驟 4：深入根因分析
對每個 🔴 和 🟡 回答：
1. **根因**：為什麼？
2. **模式**：偶發或規律？
3. **影響**：高/中/低
4. **關聯**：與其他問題共同根因？

## 步驟 5：擬定方案 + 正確性驗審

### 5.1 擬定修改方案
- 修改檔案清單
- 修改範圍（只改必要部分）
- 預期效果

### 5.2 方案正確性驗審（必做）

| # | 驗審項目 | 通過條件 |
|---|---------|---------|
| 1 | 邏輯正確 | 解決根因，非遮蔽症狀 |
| 2 | 副作用評估 | 不影響其他 Agent |
| 3 | 語法正確 | PowerShell/JSON 語法無誤 |
| 4 | 編碼規範 | .ps1=UTF-8 with BOM，JSON=UTF-8 |

4 項全通過 → 進入步驟 6。否則修正方案（最多 2 次），仍不通過記為「待手動處理」。

## 步驟 6：備份 + 執行修正 + 驗證

### 6.1 備份
```bash
cp "目標檔案" "目標檔案.bak"
```

### 6.2 執行修正
直接修改（使用 Edit 工具）或建立子 Agent 修正。

### 6.3 修改後驗證
1. `git diff` 確認修改範圍
2. 語法檢查
3. 關鍵邏輯未被破壞

驗證失敗 → 用備份還原：`cp "檔案.bak" "檔案"`

### 6.4 清理備份
驗證通過後：`rm -f D:/Source/daily-digest-prompt/*.bak`

## 步驟 7：寫入知識庫
將審查過程寫入 RAG 知識庫：

1. 用 Write 建立 `import_note.json`：
```json
{
  "notes": [{
    "title": "系統 Log 審查報告 - YYYY-MM-DD",
    "contentText": "完整 Markdown 審查報告",
    "tags": ["系統審查", "log分析", "優化"],
    "source": "import"
  }],
  "autoSync": true
}
```
2. `curl -s -X POST "http://localhost:3000/api/import" -H "Content-Type: application/json; charset=utf-8" -d @import_note.json`
3. `rm import_note.json`
4. 知識庫未啟動則跳過

## 步驟 8：寫入結果 JSON
用 Write 建立 `results/todoist-auto-log_audit.json`：
```json
{
  "agent": "todoist-logaudit",
  "status": "success 或 partial 或 failed",
  "task_id": null,
  "type": "log_audit",
  "findings_count": 3,
  "fixes_count": 2,
  "kb_imported": true,
  "duration_seconds": 0,
  "done_cert": {
    "status": "DONE",
    "quality_score": 4,
    "remaining_issues": []
  },
  "summary": "發現 3 個問題，修正 2 個",
  "error": null
}
```
