---
name: git-smart-commit
version: "1.0.0"
description: |
  將雜亂的 git 變更依功能邏輯自動拆分為多個語義化的 Conventional Commit。
  Use when: 自動推送前需要將多個變更分群提交，或手動整理 git 歷史時使用。
allowed-tools: Bash, Read, Write
cache-ttl: N/A
triggers:
  - "git commit"
  - "smart commit"
  - "智慧提交"
  - "conventional commit"
  - "分群提交"
  - "git push"
---

# Git Smart Commit — 智慧分群提交

將 git 暫存區的變更依功能邏輯分群，產生多個有意義的 Conventional Commit。
專為 daily-digest-prompt 專案的自動推送場景設計。

## 適用場景

- `templates/auto-tasks/git-push.md` 自動推送時取代 `git add -A && git commit -m "chore: auto-sync"`
- 手動整理 git 變更時（例如開發完多個功能後一次提交）

## 流程

### 步驟 1：取得變更清單

```bash
git status --porcelain
```

若無變更，結束流程。

### 步驟 2：分群

依檔案路徑的**頂層目錄**分群，對應 scope 與 type：

| 目錄 / 檔案模式 | scope | 預設 type | 說明 |
|-----------------|-------|-----------|------|
| `config/` | config | chore | 配置檔調整 |
| `hooks/` | hooks | fix 或 refactor | Hooks 修改 |
| `skills/` | skills | docs | Skill 文件更新 |
| `templates/` | templates | refactor | 模板結構調整 |
| `prompts/team/` | todoist | feat | 團隊模式 prompt |
| `tests/` | tests | test | 測試檔案 |
| `docs/` | docs | docs | 文件 |
| `*.ps1`（根目錄） | scripts | chore | PowerShell 腳本 |
| `*.md`（根目錄） | project | docs | 專案文件 |
| `state/` + `context/` + `cache/` + `results/` | — | — | **不獨立 commit**（見下方規則） |

### 步驟 3：特殊規則

1. **資料檔案合併**：`state/`、`context/`、`cache/`、`results/` 的變更不獨立 commit。
   - 若有程式碼變更 → 併入最後一個 commit
   - 若僅有資料檔案變更 → 用 `chore: auto-sync {timestamp}` 單一 commit

2. **少量變更簡化**：若總變更 ≤ 5 個檔案且全在同一 scope → 用單一 commit

3. **上限控制**：每次最多 5 個 commit。超過時合併相近 scope：
   - `skills/` + `docs/` → `docs(skills)`
   - `config/` + `templates/` → `chore(config)`
   - 其餘併入最後一組

4. **type 判斷**：
   - 新增檔案（`A` 或 `??`）→ `feat`
   - 刪除檔案（`D`）→ `chore`
   - 修改檔案（`M`）→ 依 scope 預設，或：
     - 修改含 `fix` / `bug` 關鍵字 → `fix`
     - 純格式 / 命名調整 → `style`

### 步驟 4：產生 Commit 訊息

格式：`<type>(<scope>): <簡短描述>`

規則：
- 使用正體中文描述
- 不超過 50 字
- 動詞開頭：新增、調整、修正、移除、重構、更新
- 不以句號結尾

範例：
```
feat(todoist): 新增 AI 深度研究自動任務
chore(config): 調整快取 TTL 為 30 分鐘
fix(hooks): 修正 pre_bash_guard 正則匹配
docs(skills): 更新 system-audit 評分指南
test(hooks): 新增 cjk_guard 邊界測試
chore: auto-sync 2026-02-25_2130
```

### 步驟 5：逐批執行

```bash
# 對每個分群依序執行
git add <group_files...>
git commit -m "<type>(<scope>): <description>"
```

若某次 commit 失敗（例如 pre-commit hook 攔截）：
- 記錄錯誤
- `git reset HEAD` 取消 staging
- 降級為原始 `git add -A && git commit -m "chore: auto-sync {timestamp}"`

### 步驟 6：確認結果

```bash
git log --oneline -10
```

回報 commit 數量與各 commit 摘要。

## 容錯設計

- **Skill 讀取失敗** → fallback 為 `chore: auto-sync {timestamp}`
- **分群邏輯出錯** → fallback 為 `chore: auto-sync {timestamp}`
- **單次 commit 失敗** → reset + fallback
- **pre-commit hook 攔截** → 修正後重試一次，仍失敗則 fallback

## 不適用場景

- `shurangama-web` 倉庫（保持原有 `sync: KB 同步` 格式）
- `game_web` 倉庫（由 `sync-games.ps1` 管理）
- 僅 state/context/cache 變更且無程式碼修改（直接用 auto-sync）
