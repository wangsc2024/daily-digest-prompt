# 結構化驗證閘門（Iterative Quality Gate）

支援最多 **3 次迭代**（初始執行 + 2 次精練）。

## 1. 解析 DONE 認證

1. 用 Read 工具讀取 `task_result.txt`
2. 尋找 `===DONE_CERT_BEGIN===` 和 `===DONE_CERT_END===` 之間的 JSON
3. 若找不到 → `cert_status = "NO_CERT"`, `quality_score = 0`
4. 若找到 → 解析 JSON，提取 status、checklist、remaining_issues

## 2. 外部驗證

同時執行外部驗證（不完全依賴子 Agent 自評）：

### @code 任務（標籤 @code 或 allowedTools 含 Edit）
1. `git status` 檢查是否有新增/修改的檔案
2. 若有 Python 檔案 → `python -m py_compile <file>` 語法檢查
3. 若有測試檔案 → 執行測試套件
4. 記錄：ext_changes_exist、ext_syntax_ok、ext_tests_ok

### @research 任務（標籤 @research 或 allowedTools 含 WebSearch）
1. 檢查 artifacts_produced 中的產物是否存在
2. 輸出內容非空且超過 100 字
3. 記錄：ext_artifacts_ok

### 一般任務
1. exit code = 0 → ext_exit_ok = true
2. exit code ≠ 0 → ext_exit_ok = false

## 3. 綜合判定

```
通過 = (cert_status == "DONE")
     AND (quality_score >= 3)
     AND (remaining_issues 為空)
     AND (外部驗證全部通過)
```

- **通過** → 關閉任務
- **未通過** → 進入精練決策

## 4. 精練決策

1. `iteration_number >= 3` → 放棄精練，進入失敗處理
2. `cert_status == "FAILED"` 且 `remaining_issues` 為空 → 不可精練（子 Agent 認為徹底無法完成）
3. 外部驗證發現環境問題（Token 缺失、服務不可用）→ 不可精練
4. 其他情況 → 可精練，讀取 `templates/sub-agent/refinement.md` 建立精練 prompt

## 5. 失敗處理（Back-Pressure）

1. 任務保持 open 狀態
2. 若 priority > 1，降低 1 級
3. 設 due_string = "tomorrow"
4. 添加失敗評論（含迭代次數、最終狀態、殘留問題、下次處理建議）
