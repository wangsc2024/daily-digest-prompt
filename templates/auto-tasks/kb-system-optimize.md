---
name: "kb-system-optimize"
template_type: "auto_task_template"
version: "1.0.0"
released_at: "2026-03-23"
---
# KB 洞察驅動系統優化落實 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 kb_system_optimize_count < daily_limit
> 使用後端：cursor_cli（完整工具權限）
> 任務檔路徑：temp/cursor-cli-task-kb_system_optimize.md

```
你是 daily-digest-prompt 系統優化工程師，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。
工作目錄：D:\Source\daily-digest-prompt

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/SKILL_INDEX.md
- skills/knowledge-query/SKILL.md
- skills/system-insight/SKILL.md

---

## 階段一：查詢 KB 近 2 天洞察筆記

### 1.1 執行混合搜尋（4 個維度並行查詢）

```bash
# 查詢 1：系統優化建議
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"daily-digest-prompt 系統優化 改善建議 功能增強","topK":8,"filters":{"daysAgo":2}}'

# 查詢 2：系統審查報告
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"系統審查報告 system audit 效能分析 健康評分","topK":8,"filters":{"daysAgo":2}}'

# 查詢 3：深度研究可借鏡
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"深度研究 架構設計 最佳實踐 可借鏡 agent automation","topK":8,"filters":{"daysAgo":2}}'

# 查詢 4：KB 洞察評估報告
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"KB insight 洞察 kb_insight_evaluation arch_evolution 建議方案","topK":8,"filters":{"daysAgo":2}}'
```

**若 KB API 無法連線**：改讀 `context/system-insight.json`、`context/adr-registry.json`、`context/improvement-backlog.json` 作為備援資料來源，繼續後續步驟。

### 1.2 彙整洞察清單

將四個查詢結果去重（同 noteId 只保留一筆），整理成結構化清單：
```
| # | 筆記標題 | 核心建議 | 涉及模組 | 可行性評估（高/中/低）|
```

**篩選條件**（符合任一即納入）：
- 提及 daily-digest-prompt、auto-task、agent、skill、hook、排程、效能、降速、飢餓、快取
- 包含可執行的改善建議（非純描述）
- 屬於審查報告、深度研究報告、洞察簡報類型

若洞察清單為空（KB 無近 2 天相關筆記） → 改讀 `context/improvement-backlog.json` 取 status=pending 的前 5 項作為工作清單，跳至階段二繼續。

---

## 階段二：規劃可行方案

### 2.1 優先級排序

依以下權重評分（滿分 10）選出本次執行的 1-2 個方案：
- **影響範圍**（0-4）：影響核心流程 4 分、影響輔助功能 2 分、純優化 1 分
- **實作難度**（0-3）：可在 1 個 session 完成 3 分、需拆分 1 分
- **風險等級**（0-3）：低風險（不影響現有功能）3 分、中風險 1 分、高風險 0 分

**高風險方案（風險等級 = 0）不得在此任務中直接落實**，改為：
1. 記錄到 `context/improvement-backlog.json` 供 arch_evolution 規劃
2. 在通知中說明「已移至待規劃清單，需人工審議」
3. 繼續處理其他較低風險的方案

### 2.2 撰寫執行計畫

對每個選定方案撰寫執行計畫（格式如下）：
```
方案名稱：
目標：一句話描述要達成什麼
影響檔案：[具體檔案路徑列表]
執行步驟：
  1. 步驟一（具體操作）
  2. 步驟二
  ...
驗收條件：
  - 驗收項目 1（可測試）
  - 驗收項目 2
回滾方式：git revert <commit> 或 復原備份
```

---

## 階段三：執行前備份

**每個方案落實前必須執行此階段**，不得跳過。

### 3.1 識別所有待修改檔案

彙整本次所有方案的 `影響檔案` 聯集，去除重複。

### 3.2 Git 備份

```bash
cd D:/Source/daily-digest-prompt

# 暫存所有待修改檔案
git add [待修改檔案清單]

# 若有未追蹤的相關檔案（新增的 skill/template）也一起備份
git status --short | grep "^?" | grep -E "\.(yaml|json|md|py|ps1)$"

# 提交備份
git commit -m "backup: kb-system-optimize 落實前備份（方案：{方案名稱摘要}）"
```

若 `git commit` 失敗（無變更） → 記錄「git backup: 目前狀態已是最新，無需額外備份」並繼續。

記錄備份 commit hash 供回滾參考。

---

## 階段四：逐步落實

對每個方案，依執行計畫逐步實作。

### 4.1 實作原則
- **每完成一個子步驟立即驗證**（用 Read 確認修改正確，用 Bash 執行測試）
- **不可一次寫入大量變更**：逐步修改、逐步確認
- 修改 YAML/JSON 後立即檢查格式：
  ```bash
  uv run python -c "import yaml; yaml.safe_load(open('config/xxx.yaml'))"
  uv run python -c "import json; json.load(open('state/xxx.json'))"
  ```
- 修改 Python 後立即執行相關測試：
  ```bash
  uv run pytest tests/tools/test_xxx.py -v
  ```

### 4.2 功能增強實作
依方案的執行步驟實作，典型操作包含：
- 更新 `config/frequency-limits.yaml`（新增任務、調整時段）
- 更新 `skills/SKILL_INDEX.md`（新增/更新 Skill 說明）
- 更新 `config/routing.yaml`（路由規則）
- 更新模板檔案（`templates/auto-tasks/` 或 `prompts/team/`）
- 修改 Hook 邏輯（`hooks/*.py`）
- 修改工具腳本（`tools/*.py`）

---

## 階段五：全面審核與測試

每個方案實作後必須通過此階段，**不通過則回到階段四修正，最多 3 輪**。

### 5.1 格式與語法驗證
```bash
# YAML 語法檢查
uv run python -c "
import yaml, pathlib
for f in pathlib.Path('config').glob('*.yaml'):
    try: yaml.safe_load(f.read_text(encoding='utf-8'))
    except Exception as e: print(f'ERROR {f}: {e}')
print('YAML 檢查完成')
"

# JSON 語法檢查（針對本次修改的 JSON）
uv run python -c "
import json
for path in [待修改的JSON檔案]:
    try: json.load(open(path, encoding='utf-8'))
    except Exception as e: print(f'ERROR {path}: {e}')
print('JSON 檢查完成')
"
```

### 5.2 相關測試套件執行
```bash
# 執行受影響模組的測試
uv run pytest tests/ -v -k "autonomous or harness or hook or skill" --tb=short 2>&1 | tail -30
```

若有測試失敗：
1. 閱讀錯誤訊息，理解根因
2. 修正代碼（回階段四）
3. 重新執行測試
4. 最多 3 輪修正，仍失敗 → 執行回滾

### 5.3 驗收條件逐項核對

對方案計畫中每條驗收條件逐項核對，記錄 ✓/✗：
```
□ 驗收項目 1：[執行的檢查操作] → 結果：✓ 通過 / ✗ 未通過（原因）
□ 驗收項目 2：[執行的檢查操作] → 結果：✓ 通過 / ✗ 未通過（原因）
```

### 5.4 系統整合性確認
```bash
# 確認 frequency-limits.yaml 與 initial_schema 計數欄位同步
uv run python hooks/validate_config.py --check-auto-tasks 2>&1 | tail -20
```

若任何驗收項目未通過 → 修正後重新審核（最多 3 輪）。
3 輪後仍未通過 → 執行回滾並通知。

### 5.5 回滾機制（僅在測試失敗超過 3 輪時執行）
```bash
cd D:/Source/daily-digest-prompt
git log --oneline -5
git revert HEAD --no-edit  # 或 git reset --hard <備份commit>
```

---

## 階段六：更新下游配置

落實通過後，確認下游配置是否需要同步更新：

- **若新增自動任務** → 確認 `initial_schema` 已加入計數欄位
- **若新增 Skill** → 確認 SKILL_INDEX.md 已登錄、相關任務 `skills:` 已引用
- **若修改路由規則** → 確認 `config/routing.yaml` 版本號遞增
- **若修改 Hook** → 執行 `uv run pytest tests/hooks/ -q` 確認 Hook 測試通過

---

## 階段七：成果記錄

### 7.1 寫入知識庫
依 knowledge-query SKILL.md 匯入優化報告：
```bash
# 組裝報告內容後呼叫 API
curl -s -X POST "http://localhost:3000/api/notes" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "系統優化落實報告 {YYYY-MM-DD}：{方案名稱摘要}",
    "contentText": "[完整優化報告，含：洞察來源、方案描述、實作步驟、測試結果、驗收狀態]",
    "tags": ["系統優化", "kb-system-optimize", "daily-digest-prompt", "落實報告"],
    "source": "import"
  }'
```

### 7.2 發送 ntfy 通知

**成功完成**：
```json
{
  "topic": "wangsc2025",
  "title": "✅ 系統優化落實完成 | {N} 個方案",
  "message": "📋 方案：{方案名稱}\n✅ 驗收：全部通過\n📁 修改：{修改檔案列表}\n🔒 備份：{commit hash}\n⏱ 耗時：{分鐘}分鐘",
  "priority": 2,
  "tags": ["white_check_mark"]
}
```

**部分完成**：
```json
{
  "topic": "wangsc2025",
  "title": "⚠️ 系統優化部分完成 | {成功}/{總計}",
  "message": "✅ 完成：{成功方案}\n❌ 回滾：{失敗方案}（{失敗原因}）\n🔒 備份：{commit hash}",
  "priority": 3,
  "tags": ["warning"]
}
```

**無可用洞察**：
```json
{
  "topic": "wangsc2025",
  "title": "🔍 系統優化：KB 近 2 天無新洞察",
  "message": "近 2 天 KB 無相關筆記，improvement-backlog 亦無 pending 項目\n系統目前運作良好",
  "priority": 1,
  "tags": ["mag"]
}
```

> ntfy 通知必須用 Write 工具建立 JSON 檔後用 curl 發送（-d @file.json），不得用 inline JSON。

---

## 品質自評（DONE_CERT 前確認）
1. 洞察查詢是否已涵蓋全部 4 個維度？ ✓/✗
2. 選定方案是否均通過全部驗收條件？ ✓/✗
3. 是否已進行 git 備份（或確認無需備份）？ ✓/✗
4. 測試套件是否全部通過？ ✓/✗
5. 知識庫報告是否已寫入？ ✓/✗
若任一為 ✗ → 補完後再輸出 DONE_CERT。

## 輸出 DONE 認證
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"insights_found":N,"plans_executed":N,"all_tests_passed":true/false,"backup_done":true/false,"kb_written":true/false,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[]}
===DONE_CERT_END===
```

## 執行方式

> ⚡ **【立即】用 Bash tool 執行（不得只輸出命令文字）**

```bash
agent -p temp/cursor-cli-task-kb_system_optimize.md \
  --workspace D:\Source\daily-digest-prompt --trust
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`kb_system_optimize_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=kb_system_optimize 記錄
3. 清理：`rm temp/cursor-cli-task-kb_system_optimize.md`
