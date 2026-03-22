---
name: "todoist-auto-phantom_butterfly_optimize"
template_type: "team_prompt"
version: "1.0.0"
released_at: "2026-03-22"
---
# Todoist Auto-Task：幻碟星域（phantom-butterfly）耐玩／創意優化 + GitHub 同步

你是遊戲體驗與工程並重的優化專家，全程使用正體中文。
任務：**以耐玩性與創意為主軸**，優化 `D:\Source\game_web\games\phantom-butterfly`（幻碟星域），完成後在 **`D:\Source\game_web` 倉庫根目錄** 提交並 **push 至 GitHub 遠端**。
完成後將結果寫入 `results/todoist-auto-phantom_butterfly_optimize.json`。

> **輸出限制**：只輸出必要的推理與執行步驟，不輸出「好的，我開始…」等確認語句。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 立即行動：寫入 Fail-Safe 結果（最高優先）
讀完 preamble 後立即執行，用 Write 工具建立 `results/todoist-auto-phantom_butterfly_optimize.json`，內容：

```json
{"agent":"todoist-auto-phantom_butterfly_optimize","task_key":"phantom_butterfly_optimize","status":"failed","error":"task_did_not_complete_or_timeout","summary":"任務啟動但未完成"}
```

（此 placeholder 將在成功流程最末覆寫為 `status":"success"` 或 `partial`。）

必須先讀取以下 SKILL.md，並依其指示操作（路徑相對於本專案 `daily-digest-prompt` 根目錄）：
- `skills/game-design/SKILL.md`（遊戲品質、驗證；**工作目錄本任務改為下方 game_web 路徑**）
- `skills/knowledge-query/SKILL.md`（可選：KB 技術參考）
- `skills/git-smart-commit/SKILL.md`（提交訊息與分群提交原則）

---

## 固定路徑（不可變更）
| 用途 | 路徑 |
|------|------|
| 遊戲專案 | `D:\Source\game_web\games\phantom-butterfly` |
| Git 倉庫根（commit / push） | `D:\Source\game_web` |

若遊戲目錄不存在 → 結果 JSON `status`=`failed`，說明路徑缺失，**不要**在錯誤路徑建立新專案。

---

## 優化主軸（每次至少各落實一項）

**耐玩性（replayability）**（擇一或多項具體實作）：
- 難度曲線、關卡／波次節奏、失敗懲罰與再開一局動機
- 進度保留（若設計允許）、成就／目標層級、風險與獎勵平衡
- 操作手感、教學與可發現性、長時間遊玩疲勞降低

**創意（creativity）**（擇一或多項具體實作）：
- 視覺／動畫／主題呈現、音效或節奏感、特殊機制或驚喜時刻
- 與「星域／幻碟」氛圍一致的敘事或 UI 細節（不強制劇情長文，重在有記憶點）

---

## 去重（避免連日同一方向）

1. Read `config/dedup-policy.yaml`（了解冷卻語意）。
2. Read `context/research-registry.json`：
   - 若不存在 → Write 初始化：`{"version":2,"topics_index":{},"entries":[]}`（若已有結構則沿用，勿覆蓋為空除非檔案損毀）。
3. 本次 `topic` 建議格式：`幻碟星域 — [耐玩或創意子方向簡述]`。若 `topics_index` 顯示 **近 3 日**已有相同或極相似 topic → **必須更換**子方向後再實作。

---

## 執行流程

### Phase A：現況分析
- 用 Glob / Read 掃描 `D:\Source\game_web\games\phantom-butterfly` 內 `*.html`、`*.js`、`*.css`、`*.json` 等，找出入口與核心迴圈。
- 簡要記錄：目前玩法迴圈、已知痛點（若無則寫「無明顯痛點，本次做體驗加值」）。

### Phase B：知識庫（可選）
若 KB 可用，依 `knowledge-query` 搜尋與本次改良相關筆記；不可用則跳過。

### Phase C：實作與驗證
- 僅修改 **`D:\Source\game_web\games\phantom-butterfly`** 下檔案（或該遊戲明確依賴之 game_web 內相對路徑資源，需註明於結果 JSON）。
- 每項變更後自查：無明顯 JS 錯誤、遊戲可從頭遊玩一輪；若專案有 `package.json` 腳本，可執行其 `build` / `test`（若有）作為額外驗證。
- **禁止**使用 `> nul`、`2>nul`、`> NUL` 等會建立實體檔的 re-direct（遵守 preamble）。

### Phase D：研究註冊表更新
Read → Write 更新 `context/research-registry.json`：新增一筆 entry，`task_type`=`phantom_butterfly`，並更新 `topics_index[本次 topic] = 今日 YYYY-MM-DD`。移除超過政策所定之過舊 entries（若 dedup-policy 有說明）。

### Phase E：GitHub 同步（強制）
在 **`D:\Source\game_web`** 執行（Bash 範例，可依環境改為單行 pwsh）：

1. `git -C "D:/Source/game_web" status`
2. 若有變更：依 `git-smart-commit` 原則撰寫 Conventional Commit 訊息（例：`feat(phantom-butterfly): ...`），`git add` 相關檔案後 `git commit`（若無變更則跳過 commit，但仍需確認與遠端同步狀態）。
3. `git -C "D:/Source/game_web" push`（推至已設定之 `origin`；若需指定分支，使用目前工作分支，並在結果 JSON 註明分支名）。
4. 若 push 失敗（憑證、衝突、無遠端）：`status`=`partial` 或 `failed`，並在 `error`／`summary` 寫明原因與建議人工處置。

---

## 最後步驟：寫入結果 JSON

用 Write **覆寫** `results/todoist-auto-phantom_butterfly_optimize.json`：

```json
{
  "agent": "todoist-auto-phantom_butterfly_optimize",
  "task_key": "phantom_butterfly_optimize",
  "status": "success",
  "task_id": null,
  "type": "phantom_butterfly_optimize",
  "game_path": "D:\\Source\\game_web\\games\\phantom-butterfly",
  "repo_root": "D:\\Source\\game_web",
  "durability_changes": "耐玩面向：一句話",
  "creative_changes": "創意面向：一句話",
  "artifacts": ["列出本次修改之主要檔案路徑"],
  "git_committed": true,
  "git_pushed": true,
  "git_branch": "main 或實際分支名",
  "kb_imported": false,
  "summary": "一句話摘要（含是否已 push）",
  "error": null,
  "done_cert": {
    "status": "DONE",
    "quality_score": 4,
    "remaining_issues": []
  }
}
```

欄位說明：
- `status`：`success`（優化 + push 皆完成）、`partial`（優化完成但 push／commit 未完成）、`failed`（無法完成優化或路徑錯誤）。
- `git_committed` / `git_pushed`：實際結果布林值。
- 若 `status` 非 `success`，`done_cert.status` 可為 `DONE` 但 `quality_score` 反映風險，且 `remaining_issues` 列出待辦。

---

## 工作目錄提醒
程式編輯以 `D:\Source\game_web\games\phantom-butterfly` 為主；版本控制操作一律在 `D:\Source\game_web` 根目錄執行。
