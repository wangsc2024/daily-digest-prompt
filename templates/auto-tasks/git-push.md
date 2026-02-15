# 專案推送 GitHub 流程

> 觸發條件：Todoist 無可處理項目且 git_push_count < 2
> 由主 Agent 直接執行，不需子 Agent

## 步驟

### 1. 檢查是否有變更
```bash
cd D:\Source\daily-digest-prompt && git status --porcelain
```
- 輸出為空（無變更）→ 跳過推送，直接結束
- 有變更 → 繼續

### 2. Stage 與 Commit
```bash
cd D:\Source\daily-digest-prompt && git add -A && git commit -m "chore: auto-sync $(date +%Y-%m-%d_%H%M)"
```
- commit 訊息格式：`chore: auto-sync YYYY-MM-DD_HHMM`
- 敏感檔案已由 .gitignore 排除

### 3. Push 至 GitHub
```bash
cd D:\Source\daily-digest-prompt && git push origin main
```
- push 失敗 → 記錄錯誤，不重試

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`git_push_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入記錄
   ```json
   {
     "date": "今天日期",
     "timestamp": "ISO 8601",
     "type": "git_push",
     "commit_hash": "commit hash 或 null",
     "status": "success 或 failed 或 no_changes"
   }
   ```
3. 記錄結果供通知步驟使用
