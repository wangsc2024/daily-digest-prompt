---
name: scheduler-state
description: |
  排程狀態管理。追蹤執行記錄，提供健康度報告。Agent 唯讀，PowerShell 腳本負責寫入。
  Use when: 狀態、健康度、執行記錄、排程狀態。
allowed-tools: Read
---

# Scheduler State Skill - 排程狀態管理

## 用途
追蹤每次排程執行的狀態，提供健康度報告。由 PowerShell 腳本（run-agent.ps1 / run-agent-team.ps1）負責寫入，Agent 僅讀取。

## 狀態檔案位置
- `state/scheduler-state.json` — 所有 Agent 的執行記錄
- `state/todoist-history.json` — Todoist 自動任務歷史（楞嚴經/Log審查/Git push）

## 狀態檔案格式

### scheduler-state.json

```json
{
  "runs": [
    {
      "timestamp": "2026-02-11T08:00:00",
      "agent": "daily-digest",
      "status": "success",
      "duration_seconds": 45,
      "sections": {
        "todoist": "success",
        "pingtung_news": "success",
        "hackernews": "cached",
        "habits": "success",
        "learning": "success",
        "knowledge": "skipped",
        "zen": "success",
        "ntfy": "success"
      },
      "error": null,
      "log_file": "20260211_080000.log"
    }
  ]
}
```

### agent 欄位值
- `daily-digest`：每日摘要（單一模式）
- `daily-digest-team`：每日摘要（團隊並行模式）
- `todoist`：Todoist 任務規劃

### 狀態值說明
- `success`：該區塊正常完成
- `cached`：使用快取資料完成
- `skipped`：主動跳過（如知識庫未啟動）
- `failed`：該區塊失敗
- `partial`：部分完成

## Agent 寫入狀態（ntfy 通知之後、最後一步）

**寫入由 PowerShell 腳本負責**（run-agent.ps1 / run-agent-team.ps1 / run-todoist-agent.ps1），Agent 不需操作此檔案。

PowerShell 腳本的寫入邏輯：
1. 讀取 `state/scheduler-state.json`（不存在則初始化 `{"runs":[]}`）
2. 將本次執行記錄加入 `runs` 陣列末尾
3. 若 `runs` 超過 200 筆，移除最舊的記錄
4. 寫回檔案

> **注意**：Agent 對此檔案為**唯讀**。若需要健康度資訊，用 Read 讀取後分析即可。

## Todoist 歷史追蹤（todoist-history.json）

Todoist Agent 在執行自動任務（楞嚴經研究、Log 審查、Git push）時，需額外寫入 `state/todoist-history.json`：

### 寫入時機
- 步驟 2.6（楞嚴經研究完成後）
- 步驟 2.7（Log 審查完成後）
- 步驟 2.8（Git push 完成後）
- 步驟 4.9（更新 daily_summary）

### 格式
```json
{
  "auto_tasks": [
    { "date": "2026-02-13", "timestamp": "ISO 8601", "type": "shurangama", "topic": "主題名稱", "status": "success" },
    { "date": "2026-02-13", "timestamp": "ISO 8601", "type": "log_audit", "findings": 1, "fixes": 1, "status": "success" },
    { "date": "2026-02-13", "timestamp": "ISO 8601", "type": "git_push", "commit_hash": "abc1234", "status": "success" }
  ],
  "daily_summary": [
    { "date": "2026-02-13", "shurangama_count": 2, "log_audit_count": 1, "git_push_count": 0, "todoist_completed": 6, "total_executions": 14 }
  ]
}
```

- `auto_tasks` 最多保留 200 條
- `daily_summary` 最多保留 30 天

## 健康度摘要（Agent 可選加入摘要開頭）

若狀態檔案存在且有記錄，計算近 7 天統計：

```
📊 系統健康度（近 7 天）
- 執行次數：N 次
- 成功率：XX%
- 平均耗時：XX 秒
- 最近失敗：[日期] [原因]（若無則顯示「無」）
```

## 查詢工具

使用 `query-logs.ps1` 進行靈活查詢（summary/detail/errors/todoist/trend 五種模式）。

## 注意事項
- 用 Write 工具建立 JSON 檔案，確保 UTF-8 編碼
- runs 陣列最多保留 200 筆
- 每次執行都要寫入，包括失敗的執行
- `log_file` 欄位記錄對應的日誌檔名，便於關聯查詢
