---
name: "qa-system-optimize"
template_type: "auto_task_template"
version: "1.0.0"
released_at: "2026-03-20"
---
# QA System 品質與安全優化 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 qa_optimize_count < 2

```
你是資訊安全與軟體品質工程師，全程使用正體中文。
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令 + Shell 執行強制規則）。

## 工作目錄
D:\Source\qa_system

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/SKILL_INDEX.md
- skills/knowledge-query/SKILL.md

## 任務
以最嚴格的資訊安全標準，漸進式優化 QA System 的品質與安全性。
每次執行前必須回顧前次優化記錄，確認待辦事項，以之前成果為基礎持續改進。

## 第零步：回顧前次優化記錄（必做）

### 0.1 查詢知識庫
```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "QA System 優化 安全 品質", "topK": 5}'
```

### 0.2 讀取專案優化日誌
讀取 `D:\Source\qa_system\logs\optimization-history.jsonl`（若存在）。
取最近 2 筆記錄，確認：
- 前次優化了什麼？ → 本次不重複
- 有無 remaining_issues？ → 本次優先處理
- quality_score 趨勢？ → 確認持續改善
- 前次新增的待辦？ → 本次接續

### 0.3 決定本次優化方向
根據前次記錄選擇本次重點（依優先級排序）：
1. **前次待辦事項**（最高優先）
2. **資訊安全漏洞**（OWASP Top 10）
3. **程式碼品質**（lint、type-check、code smell）
4. **測試覆蓋率**（補全缺失的測試）
5. **架構改善**（效能、可維護性）

輸出：「本次優化方向：[方向] — [依據：前次待辦/新發現/計畫排程]」

## 第一步：安全掃描（每次必做）

### 1.1 靜態安全分析
在 D:\Source\qa_system 目錄下執行：

1. 搜尋硬編碼密鑰：
   Grep 搜尋 SECRET_KEY, PASSWORD, TOKEN, API_KEY 等（排除 .gitignore 列出的檔案）

2. 搜尋 SQL 注入風險：
   Grep 搜尋 text(), execute(), raw SQL 等模式

3. 搜尋 XSS 風險：
   Grep 搜尋 |safe, innerHTML, document.write 等模式

4. 搜尋不安全的 CORS：
   Grep 搜尋 allow_origins, CORSMiddleware, "*"

5. 搜尋不安全的 Cookie：
   Grep 搜尋 httponly, secure, samesite 設定

6. 搜尋不安全的 JWT：
   Grep 搜尋 JWT 配置、token 過期時間

### 1.2 依賴安全
讀取 requirements.txt，用 WebSearch 查詢已知 CVE。

### 1.3 安全評估
輸出安全評估報告：
| 風險等級 | 項目 | 狀態 | 說明 |
|---------|------|------|------|
| 🔴 嚴重 | ... | 待修/已修 | ... |
| 🟡 中等 | ... | 待修/已修 | ... |
| 🟢 低風險 | ... | 正常 | ... |

## 第二步：品質掃描

### 2.1 程式碼品質
1. 讀取關鍵模組（routers/, models/, schemas/, dependencies.py）
2. 檢查：
   - 函式過長（>50 行）
   - 重複程式碼
   - 未使用的 import
   - 異常處理不完整（裸 except）
   - 型別標注缺失

### 2.2 測試覆蓋
1. 讀取 tests/ 下所有測試檔案
2. 比對 routers/ 中的端點，列出未覆蓋的 API
3. 檢查 conftest.py 的 fixture 是否完整

## 第三步：實施修復（嚴格限制範圍）

### 修復原則
- **每次只修復 1-3 個具體問題**，不做全面重構
- **安全問題優先**，品質問題其次
- **修改前備份**：`cp 檔案 檔案.bak`
- **修改後驗證**：語法檢查 + 功能驗證

### 修復前驗審（必做）
| # | 驗審項目 | 通過條件 |
|---|---------|---------|
| 1 | 邏輯正確 | 修改解決根因，非遮蔽症狀 |
| 2 | 副作用評估 | 不影響現有功能 |
| 3 | 安全合規 | 不引入新的安全風險 |
| 4 | 向後相容 | 資料庫 schema 相容、API 契約不變 |

### 修復後驗證（必做）
1. Python 語法檢查：`python -m py_compile 修改的檔案`
2. 若修改了測試相關：`cd D:\Source\qa_system && python -m pytest tests/ -x --tb=short`
3. 若修改了路由/模型：確認 import 無誤
4. `git diff` 確認修改範圍正確

若驗證失敗 → 還原備份 → 記錄為 remaining_issue

## 第四步：清理備份
驗證通過後：`rm -f D:/Source/qa_system/*.bak D:/Source/qa_system/app/*.bak D:/Source/qa_system/app/routers/*.bak`

## 第五步：寫入優化日誌（必做）

### 5.1 寫入專案日誌
確保目錄存在：`mkdir -p D:/Source/qa_system/logs`

用 Write 工具將本次優化記錄追加到 `D:\Source\qa_system\logs\optimization-history.jsonl`：
格式（一行 JSON）：
```json
{"ts":"ISO-8601","direction":"本次優化方向","based_on_previous":"前次記錄ts或null","security_findings":[{"level":"🔴/🟡/🟢","item":"描述","status":"fixed/pending/noted"}],"quality_findings":[{"item":"描述","status":"fixed/pending"}],"files_modified":["修改的檔案清單"],"tests_run":true,"tests_passed":true,"remaining_issues":["下次需處理的項目"],"quality_score":3,"self_assessment":"一句話自評"}
```

### 5.2 寫入知識庫
依 knowledge-query SKILL.md 匯入優化報告：
- tags: ["QA System", "安全優化", "品質改善", "本次具體方向"]
- contentText: 完整優化報告 Markdown
- source: "import"

## 品質自評迴圈
1. 是否回顧了前次優化記錄？
2. 安全掃描是否完整執行？
3. 修改是否通過驗證？
4. 優化日誌是否已寫入？
5. 知識庫是否已匯入？
若任何項目未通過：分析原因 → 修正 → 再檢查（最多 2 次）。

## 輸出 DONE 認證
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["修改的檔案列表"],"tests_passed":true/false,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":["下次待處理"],"iteration_count":1}
===DONE_CERT_END===
```

## 執行方式
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`qa_optimize_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 加入 type=qa_optimize 記錄
3. 清理：`rm task_prompt.md`
