# 自動任務模板 — 系統維護類擴充

> 本模板與 `_base.md` 組合使用，為系統維護類自動任務提供額外段落。
> 以下段落應插入在 `_base.md` 的 `{{TASK_STEPS}}` 位置。

## 必備額外 Skill 讀取
```
- skills/scheduler-state/SKILL.md
```

## 執行策略：日誌導向

### 日誌分析階段
1. 讀取 `state/scheduler-state.json` 確認近期執行狀態
2. 讀取 `logs/structured/` 下最新的 JSONL 日誌
3. 分析：
   - 失敗/錯誤事件數量
   - 被攔截的操作
   - 異常模式（如同一工具重複失敗）

### 維護執行階段
依分析結果執行維護動作，常見項目：
- **Log 審查**：識別錯誤模式、清理過期日誌（保留 7 天）
- **Git 推送**：`git add → commit → push`（遵循 commit 規範）
- **快取清理**：移除過期的 `cache/*.json`
- **狀態驗證**：確認 JSON 檔案格式正確

### 安全邊界
以下操作**禁止自動執行**，僅記錄到 remaining_issues：
- 修改 `scheduler-state.json`（PowerShell 獨佔寫入）
- 修改 SKILL.md 檔案
- 修改 config/*.yaml 配置
- 刪除非日誌類檔案

## 結束步驟：狀態更新

### 寫入知識庫（可選，僅重大發現時）
若發現重大問題（如系統持續失敗），依 knowledge-query SKILL.md 匯入分析報告。

## 額外品質自評項
- 日誌分析是否完整？
- 維護動作是否在安全邊界內？
- 是否有需要人工介入的問題？
