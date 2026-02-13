# Daily Digest Prompt - 專案指引

## 專案概述
每日摘要 Agent：透過 Windows 排程器定時執行 Claude Code，自動彙整待辦事項、在地新聞與禪語，並推播通知。
具備跨次記憶、API 快取降級、排程狀態追蹤等機制（靈感來自 NanoClaw 架構）。

## ⚡ Skill-First 策略（最高原則）

本專案的 Agent 是 **Skill 驅動型**，所有行為都由 Skill 指引。

### 核心規則
1. **先讀 `skills/SKILL_INDEX.md`**：Agent 啟動的第一個動作就是載入 Skill 索引
2. **能用 Skill 就用 Skill**：禁止自行拼湊已有 Skill 覆蓋的邏輯
3. **先讀 SKILL.md 再動手**：每個步驟都必須先讀取對應的 SKILL.md
4. **Skill 鏈式組合**：積極串聯多個 Skill 實現更高價值
5. **Skill 匹配篩選**：Todoist Agent 篩選任務時，主動比對 SKILL_INDEX 觸發關鍵字

### Skill 索引
`skills/SKILL_INDEX.md` 包含：
- 12 個 Skill 的速查表（名稱、觸發關鍵字、用途）
- 路由決策樹（任務 → Skill 匹配邏輯）
- 鏈式組合模式（如：新聞 → 政策解讀 → 知識庫匯入 → 通知）
- 能力矩陣（依任務類型、依外部服務查找 Skill）
- 禁止行為清單

### Skill 使用強度
- **必用**（每次必定使用）：todoist、pingtung-news、pingtung-policy-expert、hackernews-ai-digest、atomic-habits、learning-mastery、ntfy-notify、digest-memory、api-cache、scheduler-state
- **積極用**（有機會就用）：knowledge-query、gmail
- **搭配用**：pingtung-policy-expert 必搭 pingtung-news、api-cache 必搭任何 API 呼叫

## 架構

```
daily-digest-prompt/
  daily-digest-prompt.md          # 每日摘要 Agent prompt（核心指令）
  hour-todoist-prompt.md          # Todoist 任務規劃 Agent prompt
  run-agent.ps1                   # 每日摘要執行腳本（單一模式，含重試）
  run-agent-team.ps1              # 每日摘要執行腳本（團隊並行模式）
  run-todoist-agent.ps1           # Todoist 任務規劃執行腳本
  setup-scheduler.ps1             # 排程設定工具
  check-health.ps1                # 健康檢查報告工具
  prompts/team/                   # 團隊模式 Agent prompts
    fetch-todoist.md              # Phase 1: Todoist 資料擷取
    fetch-news.md                 # Phase 1: 屏東新聞資料擷取
    fetch-hackernews.md           # Phase 1: HN AI 新聞資料擷取
    assemble-digest.md            # Phase 2: 摘要組裝 + 通知 + 狀態
  results/                        # 團隊模式 Phase 1 結果（Phase 2 清理）
  context/                        # 跨次記憶（持久化）
    digest-memory.json            # 摘要記憶（連續天數、待辦統計等）
    auto-tasks-today.json         # 自動任務頻率追蹤（每日歸零）
  cache/                          # API 回應快取
    todoist.json                  # Todoist 快取（TTL: 30 分鐘）
    pingtung-news.json            # 屏東新聞快取（TTL: 6 小時）
    hackernews.json               # HN 快取（TTL: 2 小時）
    knowledge.json                # 知識庫快取（TTL: 1 小時）
    gmail.json                    # Gmail 快取（TTL: 30 分鐘）
  state/                          # 排程執行狀態
    scheduler-state.json          # 執行記錄（最近 30 筆）
  skills/                         # 專案內 skill 指引（自包含）
    SKILL_INDEX.md                # Skill 索引與路由引擎（Agent 首先載入）
    todoist/SKILL.md              # Todoist API 查詢今日待辦
    pingtung-news/SKILL.md        # 屏東新聞 MCP 查詢
    hackernews-ai-digest/SKILL.md # HN AI 新聞摘要（curl 簡化版）
    atomic-habits/SKILL.md        # 原子習慣每日提示
    learning-mastery/SKILL.md     # 深度學習技術每日技巧
    pingtung-policy-expert/SKILL.md # 屏東新聞政策背景解讀
    knowledge-query/SKILL.md      # 個人知識庫查詢（可選）
    ntfy-notify/SKILL.md          # ntfy 通知發送
    digest-memory/SKILL.md        # 摘要記憶持久化
    api-cache/SKILL.md            # HTTP 回應快取
    scheduler-state/SKILL.md      # 排程狀態管理
    gmail/SKILL.md                # Gmail 郵件讀取（OAuth2）
  logs/                           # 執行日誌（自動清理 7 天）
```

## 執行流程

### 每日摘要（daily-digest-prompt.md）
1. Windows Task Scheduler 觸發 `run-agent.ps1`
2. 腳本自動建立 context/、cache/、state/ 目錄
3. 腳本讀取 `daily-digest-prompt.md` 作為 prompt
4. 透過 `claude -p --allowedTools "Read,Bash,Write"` 執行
5. **Agent 首先載入 `skills/SKILL_INDEX.md`（Skill-First）**
6. 載入記憶（digest-memory）與快取機制（api-cache）
7. 依序執行各步驟，每步嚴格依照對應 SKILL.md 操作
8. 主動觸發 Skill 鏈式組合（如：新聞 → 政策解讀 → 知識庫匯入）
9. 整理摘要（含連續報到、健康度、Skill 使用報告）→ ntfy 推播 → 寫入記憶與狀態
10. 若執行失敗，腳本自動重試一次（間隔 2 分鐘）

### 每日摘要 - 團隊並行模式（run-agent-team.ps1）
1. Windows Task Scheduler 觸發 `run-agent-team.ps1`
2. **Phase 1**：用 `Start-Job` 同時啟動 3 個 `claude -p`（Todoist + 新聞 + HN）
3. 各 Agent 獨立執行快取檢查 + API 呼叫，結果寫入 `results/*.json`
4. 等待全部完成（timeout 180s），收集各 Agent 狀態
5. **Phase 2**：啟動組裝 Agent 讀取 `results/*.json`
6. 組裝 Agent 加上政策解讀、習慣提示、學習技巧、知識庫查詢、禪語
7. 整理完整摘要 → ntfy 推播 → 更新記憶/狀態 → 清理 results/
8. Phase 2 失敗可自動重試一次（間隔 60 秒）
9. 預期耗時約 1 分鐘（單一模式約 3-4 分鐘）

### Todoist 任務規劃（hour-todoist-prompt.md）
1. Windows Task Scheduler 或手動觸發 `run-todoist-agent.ps1`
2. 腳本讀取 `hour-todoist-prompt.md` 作為 prompt
3. 透過 `claude -p --allowedTools "Read,Bash,Write"` 執行
4. **Agent 首先載入 `skills/SKILL_INDEX.md`（Skill-First）**
5. 查詢 Todoist → 用 SKILL_INDEX 觸發關鍵字比對任務 → 匹配 Skill 納入執行方案
6. 生成子 Agent prompt（含 SKILL.md 路徑引用）→ 執行 → 關閉任務 → ntfy 通知
7. **無可處理項目時**（含頻率限制，每日自動歸零）：
   - 楞嚴經研究（每日最多 **3 次**），將成果寫入 RAG 知識庫
   - 系統 Log 深度審查（每日最多 **1 次**），找出改善/優化項目並執行修正
   - 專案推送 GitHub（每日最多 **2 次**），自動 commit + push 變更至 GitHub
   - 頻率追蹤：`context/auto-tasks-today.json`（跨日自動歸零）

## 技術棧
- **執行環境**: Windows PowerShell
- **排程**: Windows Task Scheduler
- **Agent**: Claude Code CLI（`claude -p`）
- **通知**: ntfy.sh（topic: `wangsc2025`）

## NanoClaw 啟發的優化機制

### 1. 跨次記憶持久化
- 每次執行讀取/更新 `context/digest-memory.json`
- 追蹤：連續執行天數、待辦完成率、習慣/學習連續天數
- 摘要開頭顯示「連續報到第 N 天」

### 2. HTTP 回應快取
- API 成功回應存入 `cache/*.json`（含時間戳與 TTL）
- 每次 API 呼叫前先檢查快取有效性
- API 故障時自動降級使用過期快取（24 小時內）

### 3. 排程狀態管理
- `run-agent.ps1` 記錄每次執行狀態到 `state/scheduler-state.json`
- 失敗時自動重試一次（間隔 2 分鐘）
- `check-health.ps1` 提供近 7 天健康度報告

## 使用的 Skills（專案內自包含）
- `skills/SKILL_INDEX.md` - **Skill 索引與路由引擎**（Agent 啟動首先載入）
- `skills/todoist/SKILL.md` - Todoist REST API 查詢今日待辦
- `skills/pingtung-news/SKILL.md` - MCP 服務查詢屏東縣政府新聞
- `skills/hackernews-ai-digest/SKILL.md` - Hacker News API 篩選 AI 新聞（curl 簡化版）
- `skills/atomic-habits/SKILL.md` - 《原子習慣》每日提示（依星期輪替）
- `skills/learning-mastery/SKILL.md` - 《深度學習的技術》每日學習技巧（依星期輪替）
- `skills/pingtung-policy-expert/SKILL.md` - 屏東施政背景解讀（強化新聞區塊）
- `skills/knowledge-query/SKILL.md` - 個人知識庫查詢（localhost:3000，可選）
- `skills/ntfy-notify/SKILL.md` - ntfy 推播通知（Write 建 UTF-8 JSON + curl 發送）
- `skills/digest-memory/SKILL.md` - 摘要記憶持久化（跨次追蹤）
- `skills/api-cache/SKILL.md` - HTTP 回應快取（降級保護）
- `skills/scheduler-state/SKILL.md` - 排程狀態管理（執行記錄）
- `skills/gmail/SKILL.md` - Gmail 郵件讀取（OAuth2 認證，可選）

> Skills 來源：`D:\Source\skills\`，複製到專案內確保自包含，不依賴外部路徑。

## ntfy 通知注意事項
- Windows 環境必須用 JSON 檔案方式發送，不可用 inline JSON 字串（會亂碼）
- 必須加 `charset=utf-8` header：`curl -H "Content-Type: application/json; charset=utf-8" -d @file.json https://ntfy.sh`
- 用 Write 工具建立 JSON 檔確保 UTF-8 編碼，不可用 Bash echo 建檔
- 發送後刪除暫存 JSON 檔

## 慣例
- 全程使用正體中文
- 日誌檔名格式：`yyyyMMdd_HHmmss.log`
- 日誌保留 7 天，自動清理
- prompt 內容修改後無需重新部署，下次排程自動生效
- Windows 環境需設定 `chcp 65001` 確保 UTF-8 編碼
- `.ps1` 檔案必須使用 UTF-8 with BOM 編碼（PowerShell 5.1 無 BOM 會用系統預設編碼讀取，中文會亂碼）

### 嚴禁產生 nul 檔案（最高優先級）
以下行為全部禁止，違反將產生名為 `nul` 的垃圾檔案：
- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`（這是 cmd 語法，在 bash 中會建立實體檔案）
- 禁止使用 Write 工具寫入任何名為 `nul` 的檔案路徑
- 禁止在任何指令中將 `nul` 作為輸出目標
- 要抑制輸出請改用：`| Out-Null`（PowerShell）或 `> /dev/null`（bash）或直接不重導向
- 要丟棄 stderr 請用 `2>/dev/null`（bash）或 `2>$null`（PowerShell）

## 常用操作
```powershell
# 手動執行每日摘要（單一模式）
powershell -ExecutionPolicy Bypass -File run-agent.ps1

# 手動執行每日摘要（團隊並行模式，推薦）
powershell -ExecutionPolicy Bypass -File run-agent-team.ps1

# 手動執行 Todoist 任務規劃
powershell -ExecutionPolicy Bypass -File run-todoist-agent.ps1

# 設定排程（可自訂時間）
.\setup-scheduler.ps1 -Time "08:00"

# 查看排程狀態
schtasks /query /tn ClaudeDailyDigest /v

# 查看系統健康度
powershell -ExecutionPolicy Bypass -File check-health.ps1

# 查看最新日誌
Get-Content (Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
```
