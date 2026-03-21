# result_file_missing_or_invalid 說明與評估

## 一、什麼是 result_file_missing_or_invalid

`result_file_missing_or_invalid` 是 **Phase 2 補寫機制**（`Repair-CompletedAutoTaskResultFile`）在以下情況寫入結果檔的 `reason` 欄位：

1. **Job 已結束**（exit 0）
2. **結果檔不存在**，或
3. **結果檔存在但被判定為無效**（見下方「有效判定」）

腳本會寫入一個**結構化失敗／部分成功物件**，取代整段 stdout，讓 Phase 3 能正常解析並顯示失敗原因。

---

## 二、有效判定邏輯（run-todoist-agent-team.ps1 第 286 行）

```powershell
$existingValid = (($existing.type -or $existing.agent) -and $existing.status)
```

結果檔被視為**有效**的條件：

- 有 `type` **或** `agent` 欄位
- **且** 有 `status` 欄位

若不符合，即使內容正確，也會被視為無效並觸發補寫。

---

## 三、本次案例（2026/3/20 08:37）

| 項目 | 說明 |
|------|------|
| 任務 | 系統自癒迴圈（self_heal） |
| 現象 | 通知顯示「系統健康無需修復，ADR-032/033/034 為大型架構改動已記錄人工介入」但 **原因：result_file_missing_or_invalid** |
| 根因 | self_heal 依 prompt 產出 `task_key`、`task_type`、`status`，**未產出 `agent` 或 `type`**，導致 `$existingValid = false`，補寫覆蓋了原本有效結果 |

---

## 四、是否需要修復

**建議修復**，理由：

1. **誤判有效結果**：self_heal 已正確產出，卻被當成無效而覆蓋
2. **通知混淆**：使用者看到「系統健康無需修復」卻同時看到「result_file_missing_or_invalid」
3. **影響範圍**：所有使用 `task_key` / `task_type` 而非 `agent` / `type` 的自動任務都可能被誤判

---

## 五、修復方案

### 方案 A：放寬 Repair 有效判定（推薦）

在 `Repair-CompletedAutoTaskResultFile` 中，將有效判定改為也接受 `task_key`：

```powershell
$existingValid = (($existing.type -or $existing.agent -or $existing.task_key) -and $existing.status)
```

**優點**：一處修改，所有符合 `task_key` + `status` 的結果檔都不會被誤覆蓋。

### 方案 B：統一 self_heal 輸出格式

在 `prompts/team/todoist-auto-self_heal.md` 要求產出時加入 `agent` 與 `type`：

```json
{
  "agent": "todoist-auto-self_heal",
  "type": "self_heal",
  "task_key": "self_heal",
  "status": "success",
  ...
}
```

**優點**：與其他自動任務格式一致；**缺點**：需逐一檢查並更新其他可能只用 `task_key` 的任務。

---

## 六、已實施修復

已採用 **方案 A**：在 `run-todoist-agent-team.ps1` 的 `Repair-CompletedAutoTaskResultFile` 中，將有效判定改為：

```powershell
$existingValid = (($existing.type -or $existing.agent -or $existing.task_key) -and $existing.status)
```

產出含 `task_key` 與 `status` 的結果檔（如 self_heal）將不再被誤判為無效而覆蓋。
