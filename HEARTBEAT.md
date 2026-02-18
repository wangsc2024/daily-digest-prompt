---
schedules:
  daily-digest-0615:
    cron: "15 6 * * *"
    script: run-agent-team.ps1
    timeout: 900
    retry: 1
    description: "每日摘要 - 早（06:15）"

  daily-digest-1645:
    cron: "45 16 * * *"
    script: run-agent-team.ps1
    timeout: 900
    retry: 1
    description: "每日摘要 - 傍晚（16:45）"

  daily-digest-pm:
    cron: "15 21 * * *"
    script: run-agent-team.ps1
    timeout: 900
    retry: 1
    description: "每日摘要 - 晚（21:15）"

  system-audit:
    cron: "40 0 * * *"
    script: run-system-audit-team.ps1
    timeout: 1800
    retry: 1
    description: "每日系統審查 - 團隊模式（00:40）"

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
    timeout: 2700
    retry: 0
    description: "Todoist 團隊模式（每小時半點）"

---

# Heartbeat 排程定義

版本控制的排程元資料。所有排程定義集中在此檔案，供 `setup-scheduler.ps1 -FromHeartbeat` 讀取。

## 排程表

| 排程名稱 | 觸發時間 | 腳本 | 超時 | 說明 |
|---------|---------|------|------|------|
| daily-digest-0615 | 每日 06:15 | run-agent-team.ps1 | 900s (15min) | 每日摘要 - 早 |
| daily-digest-1645 | 每日 16:45 | run-agent-team.ps1 | 900s (15min) | 每日摘要 - 傍晚 |
| daily-digest-pm | 每日 21:15 | run-agent-team.ps1 | 900s (15min) | 每日摘要 - 晚 |
| system-audit | 每日 00:40 | run-system-audit-team.ps1 | 1800s (30min) | 每日系統審查 - 團隊模式 |
| todoist-single | 每小時整點 02:00-23:00 | run-todoist-agent.ps1 | 3600s (60min) | Todoist 單一模式 |
| todoist-team | 每小時半點 02:30-23:30 | run-todoist-agent-team.ps1 | 2700s (45min) | Todoist 團隊模式 |

## Todoist 驅動任務（由每小時排程撿起）

| 任務名稱 | Todoist 到期時間 | 實際執行排程 | 標籤 | 說明 |
|---------|----------------|------------|------|------|
| 遊戲同步：game → game_web → GitHub | 每日 11:20 | todoist-team 11:30 撿起 | 網站優化, 遊戲開發 | 同步今日新增遊戲並部署 |

> **說明：** Todoist 任務 11:20 到期 → 11:30 的 todoist-team 排程查詢後執行。
> Claude Agent 會讀取任務描述，按 MAINTENANCE.md 規範執行同步流程。
> 同步輔助腳本：`D:\Source\game_web\sync-games.ps1`（非 AI 步驟用）

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
