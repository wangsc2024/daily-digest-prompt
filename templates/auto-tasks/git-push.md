# 專案推送 GitHub + 知識庫同步流程

> 觸發條件：Todoist 無可處理項目且 git_push_count < 4
> 由主 Agent 直接執行，不需子 Agent

## 步驟

### 0. 同步遊戲到 game_web（確保 game-web.pages.dev 最新）

執行增量同步（僅同步今日新增/修改的遊戲，由腳本自動判斷）：
```bash
pwsh -ExecutionPolicy Bypass -File "D:\Source\game_web\sync-games.ps1"
```

判斷結果：
- **腳本輸出「今日無新增/修改的遊戲」** → 今日無新遊戲，跳過，繼續下一步
- **腳本成功同步（exit 0）** → 腳本內部已完成 npm build + git push game_web，繼續下一步
- **腳本失敗（exit 1）** → 記錄錯誤，繼續後續步驟（不阻斷 daily-digest-prompt 推送）

> 注意：若腳本提示「gameMetadata.js 尚無記錄」，用 Edit 工具將新遊戲加入
> `D:\Source\game_web\js\gameMetadata.js` 後，重新執行一次（不帶 -Full）。

### 1. 同步知識庫網站
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

### 2. 檢查 daily-digest-prompt 是否有變更
```bash
cd D:/Source/daily-digest-prompt && git status --porcelain
```
- 輸出為空（無變更）→ 跳過推送，直接結束
- 有變更 → 繼續

### 3. 智慧分群提交（Smart Commit）

先讀取 `skills/git-smart-commit/SKILL.md`，依其流程執行：

1. `git status --porcelain` 取得變更清單
2. 依 Skill 定義的分群規則，將檔案按目錄/模組分組
3. 每組產生一個 Conventional Commit（`<type>(<scope>): <描述>`）
4. 逐批 `git add <files> && git commit -m "<message>"`

若 Skill 讀取失敗或分群出錯，降級為：
```bash
cd D:/Source/daily-digest-prompt && git add -A && git commit -m "chore: auto-sync $(date +%Y-%m-%d_%H%M)"
```

- 敏感檔案已由 .gitignore 排除

### 4. Push 至 GitHub
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
