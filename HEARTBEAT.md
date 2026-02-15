---
schedules:
  daily-digest-am:
    cron: "0 8 * * *"
    script: run-agent-team.ps1
    timeout: 900
    retry: 1
    description: "每日摘要 - 早（08:00）"

  daily-digest-mid:
    cron: "15 11 * * *"
    script: run-agent-team.ps1
    timeout: 900
    retry: 1
    description: "每日摘要 - 午（11:15）"

  daily-digest-pm:
    cron: "15 21 * * *"
    script: run-agent-team.ps1
    timeout: 900
    retry: 1
    description: "每日摘要 - 晚（21:15）"

  todoist-single:
    cron: "0 2-23 * * *"
    interval: 60m
    script: run-todoist-agent.ps1
    timeout: 3600
    retry: 0
    description: "Todoist 單一模式（每小時整點）"

  todoist-team:
    cron: "30 2-23 * * *"
    interval: 60m
    script: run-todoist-agent-team.ps1
    timeout: 2400
    retry: 0
    description: "Todoist 團隊模式（每小時半點）"

---

# Heartbeat 排程定義

版本控制的排程元資料。所有排程定義集中在此檔案，供 `setup-scheduler.ps1 -FromHeartbeat` 讀取。

## 排程表

| 排程名稱 | 觸發時間 | 腳本 | 超時 | 說明 |
|---------|---------|------|------|------|
| daily-digest-am | 每日 08:00 | run-agent-team.ps1 | 900s (15min) | 每日摘要 - 早 |
| daily-digest-mid | 每日 11:15 | run-agent-team.ps1 | 900s (15min) | 每日摘要 - 午 |
| daily-digest-pm | 每日 21:15 | run-agent-team.ps1 | 900s (15min) | 每日摘要 - 晚 |
| todoist-single | 每小時整點 02:00-23:00 | run-todoist-agent.ps1 | 3600s (60min) | Todoist 單一模式 |
| todoist-team | 每小時半點 02:30-23:30 | run-todoist-agent-team.ps1 | 2400s (40min) | Todoist 團隊模式 |

## 雙軌比較說明

兩種 Todoist 模式時間錯開 30 分鐘，比較效能與成功率：
- **single-mode**：一個 claude 完成查詢+執行+通知，CLI 啟動快（~20s）
- **team-mode**：Phase 1 查詢 → Phase 2 並行執行 → Phase 3 組裝，適合多任務

## 使用方式

```powershell
# 從 HEARTBEAT.md 讀取設定並註冊排程
.\setup-scheduler.ps1 -FromHeartbeat

# 傳統方式（手動指定參數）
.\setup-scheduler.ps1 -Time "08:00" -Script "run-agent-team.ps1"
```
