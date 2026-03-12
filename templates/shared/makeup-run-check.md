# 補執行前置檢查（Makeup Run Check）

> 共用模板，供 Todoist Agent 在執行主要任務前引用。
> 引用方式：在 prompt 步驟 0 加入「用 Read 讀取 templates/shared/makeup-run-check.md，依指示執行」

---

## 補執行前置步驟

在執行本次任務之前，先讀取 `state/makeup-needed.json`：

**情況 A：檔案不存在或 `pending = false`**
→ 直接跳過此步驟，繼續執行主要任務。

**情況 B：`pending = true` 且 `schedule = "daily-digest-am"`**
→ 執行以下補執行流程：

1. **確認尚未補完**：用 Read 讀取 `context/auto-tasks-today.json`，確認今日無 daily-digest 執行記錄（若已有記錄，將 pending 設 false 後跳過）
2. **執行補摘要**：
   ```
   用 Bash 執行：pwsh -ExecutionPolicy Bypass -File run-agent-team.ps1
   ```
   （等待完成，預計 3-5 分鐘）
3. **清除標記**：用 Edit 更新 `state/makeup-needed.json`：
   - 設 `pending = false`
   - 加入 `resolved_at`（ISO 8601 當前時間）
   - 加入 `resolved_by`（本次 Agent task ID）
4. **記錄補執行**：在 plan.json 加入 `makeup_run: true`
5. **通知**（可選）：若補執行成功，用 ntfy-notify Skill 發送 priority=2 info 通知

**補執行完成後**：本次 Todoist Agent 執行結束（不繼續其他任務，避免 token 超額）。

---

## 注意事項

- 此模板僅補 `daily-digest-am`，其他排程類型不補
- 補執行使用 team 模式（`run-agent-team.ps1`），確保品質
- check-health.ps1 的 `[缺席偵測]` 區塊負責寫入 makeup-needed.json；本模板負責消費（補執行）
