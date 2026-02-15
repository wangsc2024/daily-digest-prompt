# 自動任務模板 — 程式開發類擴充

> 本模板與 `_base.md` 組合使用，為程式碼開發/優化類自動任務提供額外段落。
> 以下段落應插入在 `_base.md` 的 `{{TASK_STEPS}}` 位置。

## 必備額外 Skill 讀取
```
- skills/knowledge-query/SKILL.md
```

## 執行策略：Plan-Then-Execute

### 分析階段（必做）
1. 讀取目標專案結構（Glob 掃描關鍵目錄）
2. 讀取前次優化日誌（若存在）
3. 確認前次待辦事項 → 本次優先處理
4. 決定本次優化方向，輸出：「本次優化方向：[方向] — [依據]」

### 掃描階段（必做）
1. 安全掃描：Grep 搜尋硬編碼密鑰、SQL 注入、XSS 等模式
2. 品質掃描：函式過長、重複程式碼、裸 except、型別標注缺失
3. 測試覆蓋：比對測試檔案與原始碼模組

### 實施階段（嚴格限制）
- **每次只修復 1-3 個具體問題**，不做全面重構
- **安全問題優先**，品質問題其次
- 修改前備份：`cp 檔案 檔案.bak`
- 修改後驗證：
  - Python: `python -m py_compile 修改的檔案`
  - 若有測試: `python -m pytest tests/ -x --tb=short`
  - `git diff` 確認修改範圍

### 驗證失敗處理
- 還原備份
- 記錄為 remaining_issue
- 不強行修改

### 清理備份
驗證通過後移除所有 `.bak` 檔案。

## 結束步驟：寫入優化日誌

### 寫入專案日誌
用 Write 追加到 `{{PROJECT_DIR}}/logs/optimization-history.jsonl`（一行 JSON）：
```json
{"ts":"ISO-8601","direction":"優化方向","security_findings":[],"quality_findings":[],"files_modified":[],"tests_passed":true,"remaining_issues":[],"quality_score":3}
```

### 寫入知識庫
依 knowledge-query SKILL.md 匯入優化報告。

## 額外品質自評項
- 是否回顧了前次優化記錄？
- 安全掃描是否完整執行？
- 修改是否通過驗證？
- 優化日誌是否已寫入？
