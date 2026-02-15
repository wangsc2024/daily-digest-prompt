# 專案推送 GitHub + 知識庫同步流程

> 觸發條件：Todoist 無可處理項目且 git_push_count < 4
> 由主 Agent 直接執行，不需子 Agent

## 步驟

### 0. 同步知識庫網站
```bash
python D:/Source/knowledge/shurangama-web/scripts/sync_knowledge.py
```
- 腳本自動查詢 KB API → 篩選 → 增量合併至 `data/articles.json`
- KB API 不可用 → 跳過同步，繼續後續步驟

```bash
cd D:/Source/knowledge/shurangama-web && npm run generate
```
- 重新生成網站 HTML

```bash
python D:/Source/knowledge/shurangama-web/scripts/privacy_check.py
```
- exit 0（通過）→ 繼續推送
- exit 1（BLOCK）→ **禁止推送**，記錄錯誤，跳到步驟 1
- exit 2（WARN）→ 允許推送，記錄警告

```bash
cd D:/Source/knowledge/shurangama-web && git status --porcelain
```
- 有變更且審查通過 → commit 並 push：
```bash
cd D:/Source/knowledge/shurangama-web && git add -A && git commit -m "sync: KB 同步 $(date +%Y-%m-%d_%H%M)" && git push origin master
```
- 無變更或審查攔截 → 跳過

### 1. 檢查 daily-digest-prompt 是否有變更
```bash
cd D:/Source/daily-digest-prompt && git status --porcelain
```
- 輸出為空（無變更）→ 跳過推送，直接結束
- 有變更 → 繼續

### 2. Stage 與 Commit
```bash
cd D:/Source/daily-digest-prompt && git add -A && git commit -m "chore: auto-sync $(date +%Y-%m-%d_%H%M)"
```
- commit 訊息格式：`chore: auto-sync YYYY-MM-DD_HHMM`
- 敏感檔案已由 .gitignore 排除

### 3. Push 至 GitHub
```bash
cd D:/Source/daily-digest-prompt && git push origin main
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
     "status": "success 或 failed 或 no_changes",
     "knowledge_sync": "success 或 skipped 或 failed"
   }
   ```
3. 記錄結果供通知步驟使用
