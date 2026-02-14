# 互動式指令取得方案與 Long-Polling 技術解析

## 摘要

本文整理 Daily Digest Prompt 專案在「定時輪詢 Todoist」之外，可採用的互動式指令取得方案。涵蓋 9 種方案的評估，深入介紹前 4 名推薦方案及 Claude Code Hooks 與 Todoist 整合，並以完整圖解說明 Long-Polling 通訊機制。

---

## 一、問題背景

### 現有架構的限制

目前專案唯一的指令來源是 Windows Task Scheduler 定時輪詢 Todoist（每小時一次，09:00-22:00）：

```
Windows Task Scheduler (cron)
    ↓ 每小時觸發
run-todoist-agent.ps1
    ↓ claude -p
Agent 讀取 Todoist → 路由 Skill → 執行 → ntfy 通知（單向推播）
```

兩個根本限制：

1. **延遲高**：最長需等 59 分鐘才會被處理
2. **單向性**：只能被動等待排程觸發，無法即時互動

### 已有基礎設施

- ntfy.sh（推播通知，topic: `wangsc2025`）
- Gmail OAuth2
- Todoist REST API v1
- PowerShell 執行環境
- Claude Code CLI（`claude -p`）

---

## 二、9 種方案總覽

| # | 方案 | 複雜度 | 延遲 | 手機可用 | 無需公開 URL | 推薦度 |
|---|------|--------|------|----------|-------------|--------|
| 1 | ntfy 雙向通訊 | **低** | 1-3s | 是 | 是 | ★★★★★ |
| 2 | Telegram Bot | 中 | 1-2s | 是 | 是 | ★★★★☆ |
| 3 | 檔案監控 + 雲端同步 | 低-中 | 5-60s | 是 | 是 | ★★★☆☆ |
| 4 | Todoist Webhook | 中-高 | <1s | 是 | 否 | ★★★☆☆ |
| 5 | n8n 自架 | 中 | 1-3s | 透過網頁 | 是 | ★★★☆☆ |
| 6 | Claude Code Hooks | **低** | N/A | 否 | 是 | ★★★☆☆ |
| 7 | Email 觸發 | 中 | 1-15min | 是 | 是 | ★★☆☆☆ |
| 8 | Web 儀表板 | 高 | 1-2s | 是 | 是 | ★★☆☆☆ |
| 9 | 語音介面 | 中-高 | 2-5s | 否 | 是 | ★☆☆☆☆ |

---

## 三、方案 1：ntfy 雙向通訊（最推薦）

### 核心概念

專案已用 ntfy 做單向推播（Agent → 手機）。ntfy 同時支援訂閱功能，可反向使用（手機 → Agent），形成雙向指令通道。

### 架構

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

兩個 topic 形成閉環：
- `wangsc2025-cmd`：指令頻道（手機 → 電腦）
- `wangsc2025`：通知頻道（電腦 → 手機，已有）

### ntfy 訂閱方式

| 方式 | 說明 | 適用場景 |
|------|------|---------|
| CLI 訂閱 | `ntfy subscribe topic "command"` | 最簡單，直接執行命令 |
| JSON 串流 | `curl -s ntfy.sh/topic/json` | 持續連線，逐行接收 JSON |
| WebSocket | `ntfy.sh/topic/ws` | 雙向即時通訊 |
| SSE | `ntfy.sh/topic/sse` | Server-Sent Events |
| 一次性輪詢 | `ntfy.sh/topic/json?poll=1&since=30s` | 搭配排程器定期檢查 |

### 指令路由

| 手機發送 | 觸發動作 | 說明 |
|---------|---------|------|
| `digest` | `run-agent-team.ps1` | 立即執行每日摘要 |
| `todoist` | `run-todoist-agent.ps1` | 立即檢查 Todoist |
| `gmail` | `run-gmail-agent.ps1` | 立即檢查 Gmail |
| `health` | `check-health.ps1` | 回傳系統健康狀態 |
| `status` | 讀取 scheduler-state.json | 回傳最近執行記錄 |
| `run 自訂 prompt` | `claude -p "prompt"` | 執行任意 prompt |

### 安全性

三層防護：

1. **隨機 topic 名**：`wangsc2025-cmd-a7x9k2`，不易猜中
2. **訊息 token**：指令前加 `[mytoken] digest`，監聽器驗證前綴
3. **ntfy Access Token**：ntfy 內建的認證機制

### 優勢

- 零新依賴（ntfy 已在用，App 已安裝）
- 監聽器核心邏輯約 30-50 行 PowerShell
- 延遲 1-3 秒
- 不需要公開 URL

---

## 四、方案 2：Telegram Bot

### 架構

```
手機 Telegram App
    ↓ 對 Bot 發送訊息
Telegram Server（Bot 用 long-polling 主動拉取，不需公開 URL）
    ↓
Windows 上的 Bot 程式（Python）
    ↓ 解析指令
claude -p "指令內容" → 執行 → 回傳結果
    ↓
Bot 發送結果回 Telegram 對話
```

### 關鍵：Long-Polling 不需要公開 URL

Telegram Bot 使用 long-polling 模式，Bot 主動向 Telegram Server 發起 GET 請求拉取訊息，純 outbound 連線，NAT/防火牆完全不影響。詳見本文第七節「Long-Polling 技術解析」。

### 現成專案

| 專案 | 特色 |
|------|------|
| claude-code-telegram (RichardAtCT) | 最完整：會話持久化、內建排程器、Webhook API、串流回應、外掛系統 |
| Claude-Code-Remote (JessyTsui) | 支援 Email/Discord/Telegram 多通道遠端控制 |
| claudecode-telegram (hanxiao) | 輕量級：用 tmux 橋接 |

### 與 ntfy 的差異

| 比較點 | ntfy 雙向 | Telegram Bot |
|--------|----------|-------------|
| 互動豐富度 | 低（純文字） | 高（按鈕、選單、串流、對話） |
| 會話持久化 | 無 | 有（跨次保持上下文） |
| 設定複雜度 | 低 | 中（Python + Bot Token） |
| 新依賴 | 無 | Python + Telegram Bot Token |
| 適合場景 | 快速觸發 | 深度互動、多輪對話 |

---

## 五、方案 3：檔案監控 + 雲端同步

### 架構

```
手機 OneDrive App → 建立 cmd.json → 雲端同步 → Windows FileSystemWatcher 偵測 → 執行
```

利用 .NET 原生的 `System.IO.FileSystemWatcher` 監控指令資料夾。搭配 OneDrive/Dropbox 即可從任何裝置投遞指令。

### 特性

- 零外部依賴（.NET 原生）
- 離線可用
- 延遲 5-60 秒（受雲端同步速度影響）
- 適合作為備援通道

---

## 六、方案 4：Todoist Webhook + Claude Code Hooks

### Todoist Webhook

將目前的「每小時輪詢」升級為「即時事件驅動」。Todoist 在任務新增/更新/完成時即時 POST 事件到指定 URL。

**主要障礙**：需要公開 HTTPS 端點。解決方案包括 ngrok、Cloudflare Tunnel、或 n8n 自架。

可監聽事件：`item:added`（新增任務）、`item:updated`（修改）、`item:completed`（完成）。

### Claude Code Hooks

Claude Code 內建的生命週期事件系統，可在 Agent 會話中的特定時刻自動執行 shell 命令。

5 個 Hook 點：

| Hook | 觸發時機 | 用途 |
|------|---------|------|
| SessionStart | 會話開始 | 環境初始化、自動載入 Todoist |
| PreToolUse | 工具使用前 | 安全閘門（攔截危險操作） |
| PostToolUse | 工具使用後 | 進度追蹤、Todoist 評論 |
| Stop | Agent 完成 | 自動關閉 Todoist 任務 + ntfy 通知 |
| Notification | Claude 發出通知 | 轉發到外部通道 |

### 整合場景

**Stop Hook 自動關閉任務**：Agent 完成工作 → Stop Hook 觸發 → 自動關閉 Todoist 任務 + 新增完成評論 + ntfy 通知。

**PreToolUse 安全閘門**：Agent 想執行 `rm -rf` → Hook 檢查 → exit 2 攔截。

**PostToolUse 進度追蹤**：每執行一步 → 自動在 Todoist 任務添加評論（如「步驟 3/5 完成」）。

### Hook 資料流

```
Claude Code ──stdin JSON──→ Hook Script ──exit code──→ Claude Code
                                                        0 = 繼續
                                                        2 = 攔截
```

### Hooks 的定位

Hooks 不是獨立的「指令取得」方案，而是**強化任何方案的利器**，與方案 1-4 互補而非互斥。

---

## 七、Long-Polling 技術解析

### 三種通訊模式比較

#### 1. 短輪詢（Short Polling）

```
客戶端              伺服器
  │── 有新訊息嗎？ ──→│
  │←── 沒有 ─────────│   ← 立刻回應
  │  （等 N 分鐘）     │   ← 空等
  │── 有新訊息嗎？ ──→│
  │←── 有！給你 ─────│
```

問題：間隔太長延遲高，間隔太短浪費資源。

#### 2. Long-Polling（長輪詢）

```
客戶端              伺服器
  │── 有新訊息嗎？ ──→│
  │                   │   ← 伺服器不回應，保持連線
  │   （連線掛著...）   │   ← 等待中...
  │←── 有！給你 ─────│   ← 有新訊息才回應
  │── 有新訊息嗎？ ──→│   ← 立刻發下一個請求
```

伺服器「故意不回應」，直到有新資料才送回。

#### 3. WebSocket（全雙工）

```
客戶端 ←═══════════→ 伺服器
       持久雙向通道，隨時互發訊息
```

### Long-Polling 完整流程（以 Telegram Bot 為例）

**步驟 1：Bot 發起請求**

```
GET https://api.telegram.org/bot<TOKEN>/getUpdates?timeout=30&offset=12345
```

這是普通的 HTTPS GET 請求（outbound），不需要公開 URL、不需要開 port、NAT/防火牆不影響。

**步驟 2：伺服器持有連線**

```
if (有新訊息) → 立刻回應
else → 不回應，保持 TCP 連線，直到：
  a) 有新訊息到達 → 回傳 JSON
  b) timeout 到了（30 秒）→ 回傳空陣列 []
```

**步驟 3：收到回應，立刻再發請求**

```
有訊息 → 處理 → 立刻發下一個 getUpdates
空陣列 → 直接發下一個 getUpdates
形成無限迴圈，但幾乎不消耗資源
```

### 延遲對比

| 模式 | 延遲 | 每分鐘請求數 | 說明 |
|------|------|------------|------|
| 短輪詢（60 分鐘間隔） | 0-3600 秒（平均 30 分鐘） | 0.017 | 現有 Todoist 排程 |
| 短輪詢（5 秒間隔） | 0-5 秒 | 12 | 低延遲但浪費 |
| **Long-Polling（30s timeout）** | **0.1-0.3 秒** | **~2（無訊息時）** | **最佳平衡** |
| WebSocket | < 0.1 秒 | 0（事件驅動） | 最低延遲但實作複雜 |

### 網路行為

**沒有新訊息時：**

```
0:00  → GET /getUpdates?timeout=30
0:30  ← 200 OK { "result": [] }        ← 30 秒超時，空回應
0:30  → GET /getUpdates?timeout=30      ← 立刻再發
1:00  ← 200 OK { "result": [] }
```

每 30 秒一個請求，幾乎不消耗資源。

**有新訊息時：**

```
0:00  → GET /getUpdates?timeout=30
0:07  ← 200 OK { "result": [訊息!] }    ← 第 7 秒收到，立刻回應
0:07  處理訊息...
0:07  → GET /getUpdates?timeout=30      ← 處理完立刻再發
```

從用戶發送到 Bot 收到：< 1 秒。

### offset 防重複機制

```
請求 1：GET /getUpdates?offset=0
回應 1：[{ "update_id": 100, "message": "digest" },
         { "update_id": 101, "message": "health" }]

Bot 處理完後，下次帶 offset = 101 + 1 = 102

請求 2：GET /getUpdates?offset=102
→ 只回傳 update_id ≥ 102 的訊息
→ 100、101 不會再出現
```

類似 Kafka 的 consumer offset，保證不重複處理。

### 與 Webhook 的根本差異

```
Webhook（Push）：伺服器 ──POST──→ 你的電腦（需要公開 URL、HTTPS、開 port）
Long-Polling（Pull）：你的電腦 ──GET──→ 伺服器（只有 outbound，零暴露）
```

Long-Polling 的本質：客戶端問「有新消息嗎？」，伺服器回答「等一下，有了再告訴你」——然後保持連線直到有消息或超時。

### ntfy 的 Long-Polling 等價物

```bash
# JSON 串流（持久連線，類似 long-polling）
curl -s ntfy.sh/wangsc2025-cmd/json

# SSE（Server-Sent Events）
curl -s ntfy.sh/wangsc2025-cmd/sse

# 短輪詢 + since（手動模擬）
curl -s "ntfy.sh/wangsc2025-cmd/json?poll=1&since=30s"
```

---

## 八、推薦實施順序

| 階段 | 方案 | 投入 | 效益 |
|------|------|------|------|
| **1** | ntfy 雙向通訊 | 數小時 | 即時指令、零新依賴 |
| **2** | Claude Code Hooks | 1 小時 | 自動通知、安全閘門 |
| **3** | Telegram Bot | 1-2 天 | 對話式互動、串流回應 |
| **4** | n8n 統一編排 | 2-3 天 | 多觸發源統一管理 |

---

## 九、五個方案的關係

```
指令來源 ─→ 方案1(ntfy) / 方案2(Telegram) / 方案3(檔案監控) / 方案4(Todoist Webhook)
               ↓
         指令路由器 (dispatch)
               ↓
         現有 Agent 執行（run-agent.ps1 / run-todoist-agent.ps1）
               ↓
         方案5: Claude Code Hooks（Stop/PreToolUse/PostToolUse）
               ↓
         結果回傳（ntfy / Telegram / Todoist 評論）
```

方案 1-4 解決「怎麼收指令」，方案 5 解決「Agent 執行中的自動化」。它們互相補充，不互相排斥。

---

## 參考資源

- ntfy CLI subscribe：https://docs.ntfy.sh/subscribe/cli/
- ntfy Subscription API：https://docs.ntfy.sh/subscribe/api/
- claude-code-telegram：github.com/RichardAtCT/claude-code-telegram
- Claude-Code-Remote：github.com/JessyTsui/Claude-Code-Remote
- Claude Code Hooks：code.claude.com/docs/en/hooks-guide
- Claude Code Agent SDK：code.claude.com/docs/en/headless
- n8n Claude Code 整合：n8n.io/integrations/webhook/and/claude/
