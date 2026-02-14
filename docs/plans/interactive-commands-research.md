# 互動式指令取得方案研究

## 背景

目前專案唯一的指令來源是 **Windows Task Scheduler 定時輪詢 Todoist**（每小時一次，09:00-22:00）。這種模式有兩個根本限制：

1. **延遲高**：最長需等 59 分鐘才會被處理
2. **單向性**：只能被動等待排程觸發，無法即時互動

本文件研究 9 種互動式指令取得方案，評估其對本專案的適用性。

---

## 現有架構摘要

```
Windows Task Scheduler (cron)
    ↓ 每小時觸發
run-todoist-agent.ps1
    ↓ claude -p
Agent 讀取 Todoist → 路由 Skill → 執行 → ntfy 通知（單向推播）
```

**已有基礎設施**：ntfy.sh（推播通知）、Gmail OAuth2、Todoist REST API v1、PowerShell 執行環境

---

## 方案總覽

| # | 方案 | 複雜度 | 延遲 | 手機可用 | 無需公開 URL | 推薦度 |
|---|------|--------|------|----------|-------------|--------|
| 1 | ntfy 雙向通訊 | **低** | 1-3s | 是 | 是 | ★★★★★ |
| 2 | Telegram Bot | 中 | 1-2s | 是 | 是 | ★★★★☆ |
| 3 | 檔案監控 + 雲端同步 | 低-中 | 5-60s | 是 | 是 | ★★★☆☆ |
| 4 | Todoist Webhook | 中-高 | <1s | 是 | 否 | ★★★☆☆ |
| 5 | n8n 自架 | 中 | 1-3s | 透過網頁 | 是* | ★★★☆☆ |
| 6 | Claude Code Hooks | **低** | N/A | 否 | 是 | ★★★☆☆ |
| 7 | Email 觸發 | 中 | 1-15min | 是 | 是 | ★★☆☆☆ |
| 8 | Web 儀表板 | 高 | 1-2s | 是 | 是 | ★★☆☆☆ |
| 9 | 語音介面 | 中-高 | 2-5s | 否 | 是 | ★☆☆☆☆ |

---

## 方案 1：ntfy.sh 雙向通訊（最推薦）

### 核心概念

專案已用 ntfy 做**單向推播**（Agent → 手機）。ntfy 同時支援**訂閱**功能，可反向使用（手機 → Agent），形成雙向指令通道。

### 運作原理

```
手機 ntfy App                    Windows 電腦
    ↓ 發送訊息到                     ↑ ntfy subscribe 持續監聽
    wangsc2025-cmd                  wangsc2025-cmd
                                        ↓ 收到訊息
                                    解析指令 → 啟動對應腳本
                                        ↓ 執行完畢
                                    ntfy publish → wangsc2025（結果通知）
                                        ↓
手機收到執行結果通知 ←────────────────────┘
```

### 訂閱方式

ntfy 提供多種訂閱機制：

| 方式 | 說明 | 適用場景 |
|------|------|---------|
| CLI 訂閱 | `ntfy subscribe topic "command"` | 最簡單，直接執行命令 |
| JSON 串流 | `curl -s ntfy.sh/topic/json` | 持續連線，逐行接收 JSON |
| WebSocket | `ntfy.sh/topic/ws` | 雙向即時通訊 |
| SSE | `ntfy.sh/topic/sse` | Server-Sent Events |
| 一次性輪詢 | `ntfy.sh/topic/json?poll=1` | 搭配排程器定期檢查 |

### 實作概念

**PowerShell 指令監聽器**（`watch-commands.ps1`）：

```powershell
# 概念示意 - 持續監聽 ntfy 指令頻道
$topic = "wangsc2025-cmd"
$streamUrl = "https://ntfy.sh/$topic/json?poll=1&since=10s"

while ($true) {
    try {
        $messages = Invoke-RestMethod -Uri $streamUrl -TimeoutSec 30
        foreach ($msg in $messages) {
            $command = $msg.message.Trim().ToLower()
            switch -Wildcard ($command) {
                "digest*"   { Start-Process powershell "-File run-agent.ps1" }
                "todoist*"  { Start-Process powershell "-File run-todoist-agent.ps1" }
                "gmail*"    { Start-Process powershell "-File run-gmail-agent.ps1" }
                "health*"   { Start-Process powershell "-File check-health.ps1" }
                "status*"   { # 回傳系統狀態到通知頻道 }
                default     { # 未知指令，回傳提示 }
            }
        }
    } catch { Start-Sleep -Seconds 5 }
    Start-Sleep -Seconds 10
}
```

**或使用 ntfy CLI 訂閱**：

```bash
# 每收到一條訊息就執行對應腳本
ntfy subscribe wangsc2025-cmd "powershell -ExecutionPolicy Bypass -File dispatch.ps1 '$m'"
```

### 指令設計範例

從手機 ntfy App 發送：

| 指令 | 觸發動作 | 說明 |
|------|---------|------|
| `digest` | `run-agent.ps1` | 立即執行每日摘要 |
| `todoist` | `run-todoist-agent.ps1` | 立即檢查 Todoist |
| `gmail` | `run-gmail-agent.ps1` | 立即檢查 Gmail |
| `health` | `check-health.ps1` | 回傳系統健康狀態 |
| `status` | 讀取 scheduler-state.json | 回傳最近執行記錄 |
| `run 自訂 prompt` | `claude -p "prompt"` | 執行任意 prompt |
| `skill scan` | `scan-skills.ps1` | 執行技能掃描 |

### 安全考量

- ntfy 公開 topic 任何人都可以發送，建議：
  - 使用不易猜測的 topic 名稱（如 `wangsc2025-cmd-a7x9k2`）
  - 加入簡單的驗證 token（訊息前綴 `[TOKEN] 指令`）
  - 或使用 ntfy 的 Access Token 認證機制
  - 或自架 ntfy 伺服器（Docker 一行搞定）

### 優點

- **零新依賴**：ntfy 已在專案中使用，手機 App 已安裝
- **實作最簡單**：核心邏輯約 30-50 行 PowerShell
- **手機即可操作**：打開 ntfy App → 輸入指令 → 等待結果通知
- **無需公開 URL**：ntfy 使用 outbound 連線
- **天然的雙向通道**：指令頻道 + 通知頻道已具備

### 缺點

- 無內建對話/會話管理
- 公開 topic 的安全性需額外處理
- 訊息格式為純文字，無豐富 UI

---

## 方案 2：Telegram Bot

### 核心概念

建立一個 Telegram Bot，透過對話介面遠端控制 Claude Code Agent。Telegram Bot 使用 **long-polling**（不需要公開 URL），是目前生態最成熟的方案。

### 現有專案

| 專案 | 特色 | GitHub |
|------|------|--------|
| **claude-code-telegram** | 最完整：會話持久化、內建排程器、Webhook API、串流回應、外掛系統 | RichardAtCT/claude-code-telegram |
| **Claude-Code-Remote** | 支援 Email/Discord/Telegram 多通道遠端控制 | JessyTsui/Claude-Code-Remote |
| **claudecode-telegram** | 輕量級：用 tmux 橋接 Telegram 與 Claude Code | hanxiao/claudecode-telegram |

### 運作原理

```
手機 Telegram App
    ↓ 發送訊息給 Bot
Telegram Server（long-polling，Bot 主動拉取）
    ↓
Windows 上的 Bot 程式（Python/Node.js）
    ↓ 解析指令
claude -p "指令內容" → 執行 → 回傳結果
    ↓
Bot 發送結果回 Telegram
```

### claude-code-telegram 功能亮點

- **對話式 Agent 模式**：保持上下文的多輪對話
- **內建 Webhook API**：可接收 GitHub/Todoist webhook（HMAC-SHA256 驗證）
- **Job 排程器**：cron 表達式排程，持久化儲存
- **串流回應**：即時看到 Agent 執行進度
- **外掛系統**：可擴展新功能
- **CLI 與 SDK 雙模式**：支援 subprocess 或 Python SDK

### 與本專案的整合方式

```
Telegram Bot（持續運行）
    ├── /digest → run-agent.ps1
    ├── /todoist → run-todoist-agent.ps1
    ├── /gmail → run-gmail-agent.ps1
    ├── /health → check-health.ps1
    ├── /ask <問題> → claude -p "問題"
    └── /schedule → 管理排程任務
```

### 優點

- **最豐富的互動體驗**：對話式、串流回應、按鈕選單
- **無需公開 URL**：long-polling 模式
- **會話持久化**：跨次對話保持上下文
- **手機體驗優秀**：Telegram App 通知即時
- **生態成熟**：多個現成專案可直接使用

### 缺點

- 需持續運行 Bot 程式（Node.js 或 Python）
- 多一個 API Token 要管理（Telegram Bot Token）
- 依賴 Telegram 第三方服務
- 安裝與設定比 ntfy 方案複雜

### 複雜度

中等。使用 claude-code-telegram 專案可在 1-2 小時內完成基本設定。需要 Python 環境和 Telegram Bot Token（透過 @BotFather 申請）。

---

## 方案 3：檔案監控 + 雲端同步

### 核心概念

在本機建立一個「指令投遞資料夾」，使用 PowerShell 的 `FileSystemWatcher` 監控資料夾變化。搭配 OneDrive/Dropbox 雲端同步，可從任何裝置投遞指令。

### 運作原理

```
手機/其他裝置
    ↓ 在 OneDrive 建立 command.json
雲端同步（5-30 秒）
    ↓
本機 commands/ 資料夾出現新檔案
    ↓ FileSystemWatcher 偵測到
解析 JSON → 啟動對應腳本
    ↓ 執行完畢後刪除指令檔
ntfy 通知結果
```

### 實作概念

```powershell
# 概念示意 - FileSystemWatcher
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = "D:\Source\daily-digest-prompt\commands"
$watcher.Filter = "*.json"
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher "Created" -Action {
    $path = $Event.SourceEventArgs.FullPath
    $cmd = Get-Content $path | ConvertFrom-Json
    # 根據 cmd.action 路由到對應腳本
    Remove-Item $path  # 處理後刪除
}
```

### 指令檔案格式

```json
{
  "action": "todoist",
  "priority": "normal",
  "params": {},
  "timestamp": "2026-02-14T10:30:00"
}
```

### 優點

- **原生 Windows 支援**：.NET FileSystemWatcher
- **零外部依賴**：不需要任何第三方服務
- **離線可用**：本機操作不需網路
- **搭配雲端同步即可遠端觸發**

### 缺點

- 雲端同步延遲 5-60 秒
- FileSystemWatcher 在高頻事件下可能遺漏
- 無內建回應機制（需搭配 ntfy）
- 檔案鎖定問題需處理
- 不適合即時互動場景

### 複雜度

低-中。基本監控器約 20 行 PowerShell。加上錯誤處理、重複偵測、清理邏輯後約 80-100 行。

---

## 方案 4：Todoist Webhook（事件驅動取代輪詢）

### 核心概念

Todoist 支援原生 Webhook，可在任務新增/更新/完成時即時推送事件到指定 URL。這可以將目前的「每小時輪詢」升級為「即時事件驅動」。

### 運作原理

```
Todoist App（新增任務）
    ↓ Webhook POST（即時）
公開 HTTPS 端點
    ↓
本機 Webhook 接收器
    ↓ 驗證 HMAC + 解析事件
啟動 Agent 處理任務
```

### 問題：需要公開 URL

Todoist Webhook 要求一個可從外部存取的 HTTPS 端點。在家用 Windows 電腦上，需要額外方案：

| 方案 | 費用 | 穩定性 | 說明 |
|------|------|--------|------|
| ngrok | 免費/付費 | 中 | 免費版 URL 每次重啟會變 |
| Cloudflare Tunnel | 免費 | 高 | 需要 Cloudflare 帳號 + 設定 |
| n8n 自架 | 免費 | 高 | 內建 Webhook 節點 |

### n8n 整合模式

```
Todoist Webhook → n8n → HMAC 驗證 → 專案路由 → Claude Code
```

參考專案：DeadBranches/n8n-Todoist-to-Notion（展示 Todoist webhook → n8n → HMAC 驗證 → 基於專案 ID 路由的完整鏈路）

### 優點

- **即時性最高**：任務建立即觸發，零延遲
- **保留 Todoist 作為指令入口**：不改變使用習慣
- **事件驅動更高效**：不浪費資源輪詢

### 缺點

- **需要公開 URL**：最大障礙
- 需要持續運行 Webhook 接收器
- ngrok 免費版 URL 不穩定
- HMAC 簽名驗證增加實作複雜度

### 複雜度

中-高。Webhook 接收器本身簡單，但公開 URL 的維護是持續性開銷。

---

## 方案 5：n8n 自架工作流程引擎

### 核心概念

n8n 是開源的工作流程自動化平台，提供視覺化編輯器。它可以同時承擔 Webhook 接收、排程觸發、多步驟編排等角色。

### 架構

```
各種觸發源
    ├── Todoist Webhook → n8n
    ├── GitHub Webhook → n8n
    ├── 排程 (cron) → n8n
    ├── Email 觸發 → n8n
    └── 手動觸發 → n8n Web UI
            ↓
    n8n 工作流程（視覺化編排）
            ↓
    Claude Code（SSH 或社群節點）
            ↓
    結果 → ntfy / Slack / Email
```

### 相關資源

| 專案 | 說明 |
|------|------|
| n8n-nodes-claudecode | 社群節點，直接包裝 Claude Code SDK |
| n8n-mcp | 讓 Claude 理解 n8n 的 1,084 個節點 |
| n8n-skills | 7 個互補的 Claude Code skill |

### 優點

- **統一觸發入口**：Webhook、排程、手動觸發全部整合
- **視覺化工作流程**：易於理解和修改
- **豐富的整合**：1,000+ 內建節點（Todoist、Gmail、Slack...）
- **可取代 Windows Task Scheduler**

### 缺點

- 需要持續運行 Node.js 服務
- 學習曲線（n8n 工作流程設計）
- 資源消耗（記憶體約 200-500MB）
- 增加系統複雜度

### 複雜度

中等。Docker 一行啟動 n8n，但設計工作流程和維護需要持續投入。

---

## 方案 6：Claude Code Hooks（原生事件系統）

### 核心概念

Claude Code 內建的 Hooks 系統，可在 Agent 生命週期事件觸發自訂 shell 命令。這不是「取得指令」的方案，而是**強化現有流程的回應能力**。

### 支援的事件

| 事件 | 觸發時機 | 用途 |
|------|---------|------|
| `SessionStart` | 會話開始 | 環境初始化 |
| `PreToolUse` | 工具使用前 | 安全閘門（攔截危險操作） |
| `PostToolUse` | 工具使用後 | 記錄操作日誌 |
| `Stop` | Agent 完成 | 結果通知、狀態更新 |
| `Notification` | Claude 發出通知 | 轉發到外部通道 |

### 與本專案的搭配

在 `.claude/settings.json` 中設定：

```json
{
  "hooks": {
    "Stop": [{
      "command": "powershell -File notify-completion.ps1"
    }],
    "Notification": [{
      "command": "powershell -File forward-notification.ps1"
    }]
  }
}
```

### 優點

- **零依賴**：Claude Code 原生功能
- **輕量**：只是設定檔修改
- **安全閘門**：PreToolUse 可攔截危險操作

### 缺點

- **不是指令取得方案**：只能在已運行的會話中觸發
- 不提供跨會話互動能力
- 適合補強，不適合作為主要互動通道

### 複雜度

低。修改設定檔即可。適合作為其他方案的補充。

---

## 方案 7：Email 觸發

### 核心概念

監控 Gmail 收件匣，當收到特定格式的郵件時觸發 Agent。專案已有 Gmail OAuth2 Skill 可作為基礎。

### 實作方式

| 方式 | 延遲 | 複雜度 |
|------|------|--------|
| Gmail API 輪詢 | 1-15 分鐘 | 中 |
| Google Cloud Pub/Sub | 即時 | 高 |
| IMAP IDLE | 即時 | 中 |

### 優點

- 任何裝置都能發 Email
- 專案已有 Gmail OAuth2 基礎
- 自然的稽核軌跡

### 缺點

- 輪詢延遲高（除非用 Pub/Sub，但那需要 Google Cloud 設定）
- OAuth2 Token 管理
- 郵件格式解析較複雜
- 體驗不夠直覺

### 複雜度

中-高。不推薦作為主要互動通道，延遲和複雜度都不理想。

---

## 方案 8：Web 儀表板

### 核心概念

自架一個 Web 介面，提供瀏覽器/手機存取，整合指令發送、狀態監控、結果查看。

### 現有專案

| 專案 | 說明 |
|------|------|
| CloudCLI (claudecodeui) | 開源 Web/手機 UI，遠端管理 Claude Code 會話 |
| claude-code-webui | Web 介面 + 串流回應 |
| Claudia GUI | 桌面視覺化介面 + 分析 |

### 優點

- 豐富的視覺化介面
- 可從任何瀏覽器/裝置存取
- 整合監控 + 指令 + 結果查看

### 缺點

- 需持續運行 Web 服務
- 前後端 + WebSocket 架構複雜
- 安全性（認證、HTTPS）
- 維護成本高

### 複雜度

高。適合專案規模擴大後考慮，目前 overkill。

---

## 方案 9：語音介面

### 核心概念

透過麥克風擷取語音，用 Whisper 轉錄後觸發 Agent。

### 優點

- 免手操作

### 缺點

- 需要實體在電腦旁
- 正體中文辨識準確率有限
- 無法遠端使用
- 技術門檻高

### 複雜度

中-高。對本專案的使用情境（遠端/手機觸發）幫助不大。

---

## 推薦實施順序

### 第一階段：ntfy 雙向通訊（最高優先）

**理由**：零新依賴、最低複雜度、手機 App 已安裝、自然延伸現有架構。

**實施步驟**：
1. 建立 `watch-commands.ps1` 指令監聽器
2. 設定專用指令 topic（如 `wangsc2025-cmd-<隨機碼>`）
3. 實作指令路由（digest/todoist/gmail/health/status）
4. 加入簡單的 token 驗證
5. 用 Windows Task Scheduler 或 Windows Service 保持監聽器運行
6. 建立 `skills/ntfy-command/SKILL.md`

**預期成果**：從手機 ntfy App 發送一個詞，數秒內觸發 Agent 執行，結果透過原有通知頻道回傳。

### 第二階段：Claude Code Hooks（補強）

**理由**：零依賴、原生支援、強化現有流程。

**實施步驟**：
1. 設定 Stop hook → 自動回報執行結果
2. 設定 PreToolUse hook → 安全閘門（危險操作前驗證）
3. 設定 Notification hook → 轉發到 ntfy

### 第三階段：Telegram Bot（進階互動）

**理由**：需要更豐富的對話式互動時採用。

**時機**：當 ntfy 雙向通訊無法滿足需求時（例如需要多輪對話、串流回應、會話持久化）。

**推薦專案**：RichardAtCT/claude-code-telegram

### 第四階段：n8n 統一編排（長期）

**理由**：當觸發源增加到 3 個以上（ntfy + Telegram + Todoist webhook + GitHub），使用 n8n 統一管理更有效率。

---

## 與現有 Skill 系統的整合

無論採用哪種方案，都應建立對應的 Skill：

```
skills/
  ntfy-command/SKILL.md      # ntfy 指令監聽（方案 1）
  telegram-bot/SKILL.md      # Telegram Bot（方案 3）
  command-dispatch/SKILL.md   # 統一指令路由器
```

指令路由器應整合進 SKILL_INDEX.md 的路由決策樹，確保 Skill-First 原則不被破壞。

---

## 結論

**ntfy 雙向通訊是最佳首選方案**。它完美符合本專案的設計哲學：

1. **最小變更**：不改變現有架構，只增加一個監聽器
2. **零新依賴**：完全複用已有基礎設施
3. **即時互動**：從手機發指令到收到結果，全程數秒
4. **自然閉環**：指令頻道（cmd topic）+ 結果頻道（通知 topic）= 完整雙向迴路

其他方案（Telegram、n8n、Web Dashboard）可作為後續階段的升級路徑，但 ntfy 方案應作為第一步實施。
