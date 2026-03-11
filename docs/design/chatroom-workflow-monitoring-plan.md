# Chatroom 工作流程與監控設計方案

> 版本：1.0 | 日期：2026-03-10 | 作者：系統設計

---

## 一、現狀分析與問題清單

### 1.1 目前系統架構（As-Is）

```
用戶 (Web/LINE)
    ↓ 傳訊
Gun.js Relay (port 8765)  ← D:\Source\my-gun-relay\index.js
    ↕ P2P 加密同步
bot.js (port 3001)         ← D:\Source\daily-digest-prompt\bot\bot.js
    ↓ HTTP API (/api/tasks)
chatroom-scheduler.py      ← 每 5 分鐘輪詢
    ↓ subprocess
process_messages.ps1       ← poll → claim → work → complete
    ↓ claude -p
Claude Code CLI            ← 實際執行任務
    ↓ 結果
bot.js → Gun.js → 用戶     ← 回報
```

### 1.2 已知問題

| 編號 | 問題 | 根因 | 嚴重度 |
|------|------|------|--------|
| P1 | chatroom-scheduler 重啟後未啟動 | restart-bot.ps1 健康檢查失敗 → exit 1 → Step 7 未執行 | 🔴 嚴重 |
| P2 | 重啟失敗無 ntfy 告警 | restart-bot.ps1 原版無告警邏輯（已修復） | 🔴 嚴重 |
| P3 | chatroom-scheduler 無 watchdog | 進程死掉後無人重啟 | 🔴 嚴重 |
| P4 | 任務執行無 SLA 追蹤 | 無逾時告警機制 | 🟡 中 |
| P5 | LINE 整合未實作 | 無 LINE Bot 串接 | 🟡 中 |
| P6 | 失敗任務無 Dead Letter Queue | failed 狀態任務積累後無處理 | 🟡 中 |
| P7 | 端對端可觀測性缺失 | 無統一日誌追蹤 trace_id | 🟡 中 |

---

## 二、目標架構（To-Be）

### 2.1 完整工作流程（含 LINE）

```
┌─────────────────────────────────────────────────────────────┐
│                      任務派送層                              │
├──────────────────┬──────────────────────────────────────────┤
│  Web UI          │  LINE Bot                                │
│  (index.html)    │  (待實作)                                │
│  port 8765       │  Webhook → bot.js /api/line-webhook      │
└────────┬─────────┴──────────┬──────────────────────────────┘
         │ Gun.js P2P          │ HTTP POST
         ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   bot.js (port 3001)                        │
│  接收訊息 → 建立 task (pending) → 寫入 records.json         │
│  每次任務產生 trace_id = uuid-v4                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP GET /api/tasks?status=pending
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              chatroom-scheduler.py（每 5 分鐘）              │
│  - 確認 bot.js 健康                                          │
│  - 觸發 process_messages.ps1                                │
│  - 自身存活寫入 state/scheduler-heartbeat.json              │
└──────────────────────────┬──────────────────────────────────┘
                           │ subprocess
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           process_messages.ps1（poll→claim→work→complete）  │
│  poll: GET /api/tasks?status=pending                        │
│  claim: POST /api/tasks/{id}/claim (含 worker_id)           │
│  work: claude -p 執行（含 trace_id 傳入）                    │
│  complete: POST /api/tasks/{id}/complete（result + elapsed） │
│  failed: POST /api/tasks/{id}/fail（error + retry_count）   │
└──────────────────────────┬──────────────────────────────────┘
                           │ 結果回傳
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              bot.js → Gun.js → Web/LINE 用戶                │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、監控方案詳細設計

### 3.1 Watchdog 機制（最高優先）

**方案：Windows Task Scheduler 定時監控**

建立新排程 `Claude_chatroom-watchdog`，每 10 分鐘執行：

```powershell
# bot/watchdog-chatroom.ps1
# 每 10 分鐘由 Windows Task Scheduler 觸發
# 職責：確保 chatroom-scheduler 持續運行

$ProjectDir = "D:\Source\daily-digest-prompt"
$HeartbeatFile = Join-Path $ProjectDir "state\scheduler-heartbeat.json"
$LogFile = Join-Path $ProjectDir "bot\logs\watchdog.log"

function Write-WLog([string]$msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [watchdog] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# 1. 進程存活檢查
$schedProcs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
    Where-Object { $_.CommandLine -match "chatroom-scheduler" }

if ($schedProcs) {
    Write-WLog "chatroom-scheduler 正常運行 (PID $($schedProcs[0].ProcessId))"
    exit 0
}

# 2. 進程已死：檢查 heartbeat 確認多久未活動
$staleMinutes = 999
if (Test-Path $HeartbeatFile) {
    try {
        $hb = Get-Content $HeartbeatFile -Raw | ConvertFrom-Json
        $lastTs = [datetime]$hb.timestamp
        $staleMinutes = [int]((Get-Date) - $lastTs).TotalMinutes
    } catch {}
}

Write-WLog "[WARN] chatroom-scheduler 未運行！最後心跳：${staleMinutes} 分鐘前"

# 3. 嘗試重啟
$schedulerScript = Join-Path $ProjectDir "chatroom-scheduler.py"
if (Test-Path $schedulerScript) {
    Start-Process -FilePath "pwsh.exe" `
        -ArgumentList "-NoProfile","-WindowStyle","Hidden","-Command",
            "uv run --project '$ProjectDir' python '$schedulerScript'" `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden
    Write-WLog "已重啟 chatroom-scheduler"

    # 4. 等待 5 秒確認
    Start-Sleep -Seconds 5
    $check = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
        Where-Object { $_.CommandLine -match "chatroom-scheduler" }
    if ($check) {
        Write-WLog "重啟成功 (PID $($check[0].ProcessId))"
    } else {
        Write-WLog "[ERROR] 重啟後仍未偵測到進程"
        # ntfy 告警
        $ntfyFile = Join-Path $ProjectDir "ntfy_watchdog_fail.json"
        @{
            topic    = "wangsc2025"
            title    = "⚠️ Chatroom-Scheduler Watchdog 重啟失敗"
            message  = "自動重啟嘗試失敗，請手動執行 restart-bot.ps1`n時間: $(Get-Date -Format 'MM-dd HH:mm')"
            priority = 4
            tags     = @("warning", "robot")
        } | ConvertTo-Json -Compress | Set-Content -Path $ntfyFile -Encoding UTF8
        curl -s -H "Content-Type: application/json; charset=utf-8" -d "@$ntfyFile" https://ntfy.sh 2>/dev/null
        Remove-Item $ntfyFile -Force -ErrorAction SilentlyContinue
    }
}
```

**HEARTBEAT.md 新增條目：**
```
Claude_chatroom-watchdog | 每 10 分鐘 (*/10 * * * *) | bot/watchdog-chatroom.ps1
```

---

### 3.2 Scheduler 心跳機制

在 `chatroom-scheduler.py` 每次觸發時寫入心跳：

```python
# 在 trigger_process_messages() 開頭加入
import json
from datetime import datetime

HEARTBEAT_FILE = os.path.join(PROJECT_DIR, "state", "scheduler-heartbeat.json")

def update_heartbeat(status: str = "running"):
    """更新 scheduler 心跳檔案，供 watchdog 讀取。"""
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
        data = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "pid": os.getpid(),
        }
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"無法更新心跳檔案: {e}")
```

---

### 3.3 任務 SLA 監控

**新增 SLA 配置** (`config/chatroom-sla.yaml`)：

```yaml
# 聊天室任務 SLA 設定
sla:
  # 任務從建立到開始執行的最大等待時間（分鐘）
  max_pending_minutes: 10

  # 任務從認領到完成的最大執行時間（分鐘）
  max_execution_minutes: 35

  # Dead Letter Queue：超過幾次重試後放棄
  max_retry_count: 3

  # SLA 違規通知
  alert:
    topic: wangsc2025
    priority: 4
```

**SLA 檢查腳本**（在 `process_messages.ps1` 結尾呼叫）：

```powershell
function Check-TaskSLA {
    param([string]$ApiBase)
    try {
        $tasks = Invoke-RestMethod -Uri "$ApiBase/api/tasks" -Method GET
        $now = Get-Date
        $violations = @()

        foreach ($t in $tasks.tasks) {
            if ($t.status -eq "pending") {
                $created = [datetime]$t.created_at
                $pendingMin = [int]($now - $created).TotalMinutes
                if ($pendingMin -gt 10) {
                    $violations += "pending 任務 [$($t.id.Substring(0,8))] 已等待 ${pendingMin} 分鐘"
                }
            }
            if ($t.status -eq "claimed") {
                $claimed = [datetime]$t.claimed_at
                $execMin = [int]($now - $claimed).TotalMinutes
                if ($execMin -gt 35) {
                    $violations += "執行中任務 [$($t.id.Substring(0,8))] 已超時 ${execMin} 分鐘"
                }
            }
        }

        if ($violations.Count -gt 0) {
            Write-Log "[SLA] 發現 $($violations.Count) 個違規："
            $violations | ForEach-Object { Write-Log "  - $_" }
            # 可在此觸發 ntfy 告警
        }
    } catch {
        Write-Log "[SLA] 無法取得任務列表：$_"
    }
}
```

---

### 3.4 Dead Letter Queue 設計

當任務 `retry_count >= max_retry_count` 時，移入 DLQ：

**bot.js 新增端點** (`POST /api/tasks/{id}/fail`)：
```javascript
// bot.js 中新增邏輯
app.post('/api/tasks/:id/fail', async (req, res) => {
    const { error, retry_count } = req.body;
    const task = findTask(req.params.id);
    if (!task) return res.status(404).json({ error: 'not found' });

    if (retry_count >= MAX_RETRY) {
        task.status = 'dead_letter';
        task.failed_at = new Date().toISOString();
        task.error = error;
        // 通知用戶任務失敗
        await notifyUser(task.user_id, `您的任務處理失敗：${error}`);
    } else {
        task.status = 'pending';  // 放回佇列重試
        task.retry_count = retry_count + 1;
        task.retry_after = new Date(Date.now() + 60000 * retry_count).toISOString();
    }
    saveRecords();
    res.json({ status: task.status });
});
```

---

## 四、LINE Bot 整合計畫

### 4.1 架構設計

```
LINE 用戶 → LINE Platform → Webhook → bot.js /api/line-webhook
                                            ↓
                                     建立 task（同 Web 流程）
                                            ↓ 完成後
                                     LINE API → 回覆用戶
```

### 4.2 實作步驟

1. **申請 LINE Developers 帳號**，建立 Messaging API channel
2. **安裝 SDK**：`npm install @line/bot-sdk`
3. **實作 Webhook** (`bot/routes/line-webhook.js`)：
   ```javascript
   const line = require('@line/bot-sdk');
   const config = { channelSecret: process.env.LINE_CHANNEL_SECRET };
   const client = new line.messagingApi.MessagingApiClient({
       channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN
   });

   router.post('/api/line-webhook',
       line.middleware(config),
       async (req, res) => {
           res.status(200).end();
           for (const event of req.body.events) {
               if (event.type === 'message' && event.message.type === 'text') {
                   await createTask({
                       source: 'line',
                       user_id: event.source.userId,
                       reply_token: event.replyToken,
                       content: event.message.text,
                   });
               }
           }
       }
   );
   ```
4. **設定環境變數**：`LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`
5. **Webhook URL 需公開 HTTPS**：使用 ngrok（測試）或 Cloudflare Tunnel（正式）

---

## 五、端對端可觀測性

### 5.1 Trace ID 流程

每個任務攜帶 `trace_id`，貫穿全流程：

```
用戶訊息 → bot.js 產生 trace_id=uuid4()
         → 寫入 records.json {id, trace_id, content, status}
         → process_messages.ps1 執行 claude -p 時帶入 --session trace_id
         → 完成後寫入 completion_log.jsonl {trace_id, elapsed, quality}
```

### 5.2 查詢指令

```powershell
# 查詢今日任務完成情況
Get-Content bot\logs\completion_log.jsonl | ConvertFrom-Json |
    Where-Object { $_.timestamp -gt (Get-Date).Date } |
    Select-Object trace_id, elapsed_seconds, quality_score, status

# 查詢失敗任務
Get-Content bot\logs\task_log_$(Get-Date -Format 'yyyy-MM-dd').log |
    Select-String "\[ERROR\]|\[FAIL\]"

# 查詢任務 SLA 違規
Get-Content bot\logs\task_log_$(Get-Date -Format 'yyyy-MM-dd').log |
    Select-String "SLA"
```

---

## 六、實作優先順序

### Phase 1（立即 - 本週）

| 任務 | 檔案 | 工時 |
|------|------|------|
| ✅ restart-bot.ps1 加指數退避 + ntfy | bot/restart-bot.ps1 | 已完成 |
| ✅ check-health.ps1 加 Bot/Scheduler 區塊 | check-health.ps1 | 已完成 |
| 🔲 建立 watchdog-chatroom.ps1 | bot/watchdog-chatroom.ps1 | 30min |
| 🔲 chatroom-scheduler.py 加心跳寫入 | chatroom-scheduler.py | 20min |
| 🔲 設定 Windows 排程 Claude_chatroom-watchdog | Task Scheduler | 10min |

### Phase 2（本週末）

| 任務 | 檔案 | 工時 |
|------|------|------|
| 🔲 Dead Letter Queue 實作 | bot/bot.js | 1h |
| 🔲 SLA 監控加入 process_messages.ps1 | bot/process_messages.ps1 | 30min |
| 🔲 Trace ID 貫穿流程 | bot.js + process_messages.ps1 | 1h |

### Phase 3（下週）

| 任務 | 檔案 | 工時 |
|------|------|------|
| 🔲 LINE Bot Webhook 實作 | bot/routes/line-webhook.js | 2h |
| 🔲 Cloudflare Tunnel 設定（HTTPS 公開） | Cloudflare dashboard | 1h |
| 🔲 完整端對端整合測試 | 手動測試 | 1h |

---

## 七、立即行動項目（今日執行）

1. **建立 `bot/watchdog-chatroom.ps1`**
2. **更新 `chatroom-scheduler.py`** 加入心跳寫入
3. **執行 `setup-scheduler.ps1`** 加入 watchdog 排程
4. **手動執行 `restart-bot.ps1`** 恢復今日服務

---

## 八、監控健康指標儀表板

```
check-health.ps1 新增 [Bot Server & Chatroom-Scheduler 健康] 區塊（已完成）：
  ┌─────────────────────────────────────────────┐
  │ Bot Server  : ✓ 運行中 (port 3001)          │
  │ Gun Relay   : ✓ 已連線                      │
  │ 任務佇列    : pending=0                      │
  │ Chatroom-Scheduler: ✓ 運行中 (已運行 02:15) │
  │ Scheduler 最後活動：2026-03-10 09:45 (3分前)│
  │ 排程任務狀態：                               │
  │   Claude_chatroom-every5min: Ready          │
  │   Claude_chatroom-watchdog: Ready           │
  └─────────────────────────────────────────────┘
```
