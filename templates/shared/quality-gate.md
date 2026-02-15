# 結構化驗證閘門（Iterative Quality Gate）

支援最多 **3 次迭代**（初始執行 + 2 次精練）。

## 1. 解析 DONE 認證

1. 用 Read 工具讀取 `task_result.txt`
2. 尋找 `===DONE_CERT_BEGIN===` 和 `===DONE_CERT_END===` 之間的 JSON
3. 若找不到 → `cert_status = "NO_CERT"`, `quality_score = 0`
4. 若找到 → 解析 JSON，提取 status、checklist、remaining_issues

## 2. 外部驗證

同時執行外部驗證（不完全依賴子 Agent 自評）：

### 程式碼任務（標籤 ^Claude Code / ^GitHub / ^專案優化 / ^網站優化 / ^UI/UX，或 allowedTools 含 Edit）
1. `git status` 檢查是否有新增/修改的檔案
2. 若有 Python 檔案 → `python -m py_compile <file>` 語法檢查
3. 若有測試檔案 → 執行測試套件
4. 記錄：ext_changes_exist、ext_syntax_ok、ext_tests_ok

### 研究任務（標籤 ^研究 / ^深度思維 / ^邏輯思維，或 allowedTools 含 WebSearch）
1. 檢查 artifacts_produced 中的產物是否存在
2. 輸出內容非空且超過 100 字
3. 記錄：ext_artifacts_ok

### 遊戲任務（標籤 ^遊戲優化 / ^遊戲開發）
1. 遊戲可啟動且無 console 錯誤（grep -r "console.error" 或語法檢查）
2. 主要遊戲機制運作正常（遊戲循環、碰撞偵測、狀態機完整）
3. 觸控與鍵盤操控皆已綁定事件
4. 記錄：ext_game_ok、ext_touch_ok、ext_no_errors

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
