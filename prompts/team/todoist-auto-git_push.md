你是 Git 推送助手，全程使用正體中文。
你的任務是：(1) 同步知識庫 Vite 網站並推送 GitHub (2) 將 daily-digest-prompt 專案的變更 commit 並 push 至 GitHub。
完成後將結果寫入 `results/todoist-auto-git_push.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

- 禁止 `git push --force`

---

## 步驟 0：同步知識庫 Vite 網站（wangsc2024/knowledge）

### 0.1 執行知識庫同步腳本
```bash
cd D:/Source/knowledge && python sync_knowledge.py
```
- 腳本查詢 KB API（localhost:3000），增量更新 `public/data/` 下的 JSON
- KB API 不可用 → 腳本印出「同步跳過」，繼續後續步驟
- 記錄輸出中的新增/更新/跳過數量

### 0.2 建置 Vite 網站
```bash
cd D:/Source/knowledge && npm run build
```
- 產生 `dist/` 目錄
- 建置失敗 → 記錄錯誤，`knowledge_sync.status = "build_failed"`，跳到步驟 1

### 0.3 敏感資訊與個資審查
```bash
cd D:/Source/knowledge && python scripts/privacy_check.py
```
- exit 0（通過）→ 繼續推送
- exit 1（BLOCK）→ **禁止推送**，記錄 `knowledge_sync.status = "blocked_by_privacy"`，跳到步驟 1
- exit 2（WARN）→ 允許推送，記錄 `knowledge_sync.privacy_warnings` 數量

### 0.4 推送 knowledge 至 GitHub
```bash
cd D:/Source/knowledge && git status --porcelain
```
- 輸出為空（無變更）→ 記錄 `knowledge_sync.pushed = false`，跳到步驟 1
- 有變更 → 繼續：
```bash
cd D:/Source/knowledge && git add -A && git commit -m "sync: KB 同步 $(date +%Y-%m-%d_%H%M)" && git push origin main
```
- push 成功 → 記錄 `knowledge_sync.pushed = true`
- push 失敗 → 記錄錯誤，不重試，繼續步驟 1

---

## 步驟 1：檢查 daily-digest-prompt 是否有變更
```bash
cd D:/Source/daily-digest-prompt && git status --porcelain
```
- 輸出為空（無變更）→ 跳到步驟 4，status="no_changes"
- 有變更 → 繼續

## 步驟 2：智慧分群提交（Smart Commit）

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

## 步驟 3：Push 至 GitHub
```bash
cd D:/Source/daily-digest-prompt && git push origin main
```
- push 失敗 → 記錄錯誤，不重試

## 步驟 4：寫入結果 JSON
用 Write 建立 `results/todoist-auto-git_push.json`：

有變更且推送成功時：
```json
{
  "agent": "todoist-gitpush",
  "status": "success",
  "task_id": null,
  "type": "git_push",
  "knowledge_sync": {
    "status": "success",
    "new_articles": 3,
    "updated_articles": 1,
    "pushed": true
  },
  "commit_hash": "abc1234",
  "files_changed": 3,
  "duration_seconds": 0,
  "summary": "知識庫同步 +3 篇，已推送兩個 repo",
  "error": null
}
```

無變更時：
```json
{
  "agent": "todoist-gitpush",
  "status": "success",
  "task_id": null,
  "type": "git_push",
  "knowledge_sync": {
    "status": "skipped",
    "new_articles": 0,
    "updated_articles": 0,
    "pushed": false
  },
  "commit_hash": null,
  "files_changed": 0,
  "duration_seconds": 0,
  "summary": "無變更，跳過推送",
  "error": null
}
```

推送失敗時：
```json
{
  "agent": "todoist-gitpush",
  "status": "failed",
  "task_id": null,
  "type": "git_push",
  "knowledge_sync": {
    "status": "failed",
    "new_articles": 0,
    "updated_articles": 0,
    "pushed": false
  },
  "commit_hash": null,
  "files_changed": 0,
  "duration_seconds": 0,
  "summary": "推送失敗",
  "error": "錯誤訊息"
}
```
