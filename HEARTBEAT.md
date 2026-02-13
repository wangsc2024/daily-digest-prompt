---
schedules:
  daily-digest:
    cron: "0 8 * * *"
    script: run-agent-team.ps1
    timeout: 300
    retry: 1
    description: "每日摘要（團隊並行模式）"

  todoist-agent:
    cron: "0 9-22 * * *"
    interval: 60m
    script: run-todoist-agent.ps1
    timeout: 600
    retry: 0
    description: "Todoist 任務規劃（每小時）"

  gmail-digest:
    cron: "0 8 * * *"
    script: run-gmail-agent.ps1
    timeout: 180
    retry: 0
    description: "Gmail 郵件摘要"

---

# Heartbeat 排程定義

版本控制的排程元資料。所有排程定義集中在此檔案，供 `setup-scheduler.ps1 -FromHeartbeat` 讀取。

## 排程表

| 排程名稱 | 觸發時間 | 腳本 | 超時 | 說明 |
|---------|---------|------|------|------|
| daily-digest | 每日 08:00 | run-agent-team.ps1 | 300s | 每日摘要（團隊並行） |
| todoist-agent | 每小時 09:00-22:00 | run-todoist-agent.ps1 | 600s | Todoist 任務規劃 |
| gmail-digest | 每日 08:00 | run-gmail-agent.ps1 | 180s | Gmail 郵件摘要 |

## 使用方式

```powershell
# 從 HEARTBEAT.md 讀取設定並註冊排程
.\setup-scheduler.ps1 -FromHeartbeat

# 傳統方式（手動指定參數）
.\setup-scheduler.ps1 -Time "08:00" -Script "run-agent-team.ps1"
```
