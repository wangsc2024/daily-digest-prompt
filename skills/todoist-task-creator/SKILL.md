---
name: todoist-task-creator
version: "1.1.0"
description: |
  互動式新增符合系統排程路由規則的 Todoist 任務。
  確保標籤、優先級、截止日期正確設定，使任務被 Todoist Agent 自動識別與執行。
  Use when: 新增 Todoist 排程任務、建立可自動執行的待辦、add todoist task、新增待辦排程。
  Note: 此為互動式工具 Skill，由使用者在 Claude Code 對話中手動觸發。
allowed-tools: Bash, Read, Write
cache-ttl: N/A
depends-on:
  - todoist
  - "config/dependencies.yaml"
triggers:
  - "新增 Todoist 任務"
  - "建立排程任務"
  - "add todoist task"
  - "新增待辦排程"
  - "todoist 新增"
  - "新增可執行任務"
  - "todoist-task-creator"
  - "新增排程待辦"
  - "建立 todoist"
---

# Todoist Task Creator — 互動式任務新增

> **端點來源**：`config/dependencies.yaml`（deps key: `todoist`）— ADR-001 Phase 3

## 使用場景

在 Claude Code 互動對話中，新增可被系統排程自動執行的 Todoist 任務。

每個任務必須正確設定**標籤（labels）**、**優先級（priority）**、**截止日期（due）**，才能被 `hour-todoist-prompt.md` Agent 識別並路由執行。

**不適用場景**：新增 auto-task 到 round-robin 系統（使用 `task-manager` Skill）。

---

## 前置讀取（必做）

```bash
# 讀取最新路由規則，確保標籤映射是當前版本
# Read config/routing.yaml
```

---

## 步驟 1：收集任務規格

向用戶收集或從上下文推斷以下資訊：

| 欄位 | 必填 | 說明 | 範例 |
|------|------|------|------|
| `task_title` | ✅ | 任務標題（Todoist content 欄位） | 「研究 Python asyncio 最佳實踐」 |
| `task_description` | ⬜ | 任務描述（有此欄位計分 ×1.2） | 「整理 asyncio 事件迴圈、協程、Task 的用法差異」 |
| `labels` | ✅ | 標籤清單（決定路由，見步驟 2） | `["研究", "知識庫"]` |
| `priority` | ✅ | 優先級（p1~p4） | `p2` |
| `due_string` | ✅ | 截止日期字串（Todoist 格式） | `"tomorrow at 09:00"` |
| `recurring` | ⬜ | 循環週期（可選） | `"every day at 10:00"` |

---

## 步驟 2：標籤選擇（核心）

> **動態讀取**：以下為嵌入的參考速查表。執行前必須讀取 `config/routing.yaml` 取得最新映射。

### 可用標籤速查表

| Todoist 標籤 | 路由 Skill | 模板 | 適用任務類型 |
|-------------|-----------|------|------------|
| **`研究`** | web-research + knowledge-query | research-task.md | 研究、調查、技術分析（**最高覆寫**） |
| **`深度思維`** | web-research + knowledge-query | research-task.md | 深度分析、洞察報告（**最高覆寫**） |
| `邏輯思維` | web-research + knowledge-query | research-task.md | 邏輯分析、推理 |
| `知識庫` | knowledge-query | 修飾標籤（不選模板） | 結果寫入 KB（搭配其他標籤） |
| `Claude Code` | 程式開發 | code-task.md | Claude Code 相關開發 |
| `GitHub` | 程式開發 | code-task.md | GitHub 操作、專案相關 |
| `專案優化` | 程式開發 | code-task.md | 專案程式優化、重構 |
| `網站優化` | 程式開發 | code-task.md | 網站效能、功能優化 |
| `UI` | 程式開發 | code-task.md | UI 元件開發 |
| `UI/UX` | 程式開發 | code-task.md | UI/UX 設計實作 |
| `Cloudflare` | 程式開發 | code-task.md | Cloudflare Pages/Workers 相關 |
| `遊戲優化` | game-workflow-design | game-task.md | 遊戲品質優化 |
| `遊戲開發` | game-workflow-design | game-task.md | 遊戲新功能開發 |
| `AI` | hackernews-ai-digest | skill-task.md | AI/LLM 研究 |
| `創意` | game-workflow-design | game-task.md | 創意遊戲開發與優化 |
| `遊戲研究` | game-workflow-design + knowledge-query | research-task.md | 遊戲設計研究、技術調研 |
| `系統審查` | system-audit | skill-task.md | 系統審查、評分 |
| `品質評估` | system-audit | skill-task.md | 品質評估 |
| `Chat系統` | 程式開發 | code-task.md | 聊天系統開發 |
| `專案規劃` | 程式開發 | code-task.md | 專案規劃與架構 |
| `@news` | pingtung-news + pingtung-policy-expert | skill-task.md | 屏東新聞相關 |
| `@write` | 文件撰寫 | skill-task.md | 文件撰寫任務 |

### 標籤組合規則

1. **最高優先（任務類型覆寫）**：含 `研究` 或 `深度思維` → 無論其他標籤，一律使用 research-task.md
2. **模板優先級**（無覆寫時）：game(1) > code(2) > research(3) > skill(4) > general(5)
3. **修飾標籤** `知識庫`：不參與模板選擇，但加入 knowledge-query Skill 和 Write 工具權限
4. **多標籤加成**：3+ 個標籤 → 計分 ×1.15（代表任務更被重視）

### 標籤建議邏輯

```
用戶說「研究 XXX」         → labels: ["研究"] 或 ["研究", "知識庫"]
用戶說「優化遊戲 XXX」    → labels: ["遊戲優化"]
用戶說「重構/開發 XXX」   → labels: ["Claude Code"] 或 ["專案優化"]
用戶說「分析/洞察 XXX」   → labels: ["深度思維"]
用戶說「寫入知識庫」       → 加入 "知識庫" 修飾標籤
```

### 絕對排除類型（pre_filter）

以下任務**無論標籤設定**，排程系統均會跳過。如用戶試圖建立此類任務，需提醒：

- 實體行動：買東西、運動、打掃、出門、取件
- 人際互動：打電話、開會、面談、聚餐、拜訪
- 個人事務：繳費（非自動化）、看醫生、接送

---

## 步驟 3：截止日期設定

### due_string 格式參考

| 場景 | due_string | UTC 說明（+08:00 時區） |
|------|-----------|----------------------|
| 今天全天（隨時執行） | `"today"` | 無時間限制，立即可執行 |
| 今天 10:00 執行 | `"today at 10:00"` | UTC 02:00Z |
| 明天早上 9 點 | `"tomorrow at 09:00"` | UTC 01:00Z |
| 後天下午 3 點 | `"in 2 days at 15:00"` | UTC 07:00Z |
| 每天固定時間 | `"every day at 10:00"` | 循環任務 |
| 指定日期全天 | `"2026-02-20"` | 全天任務 |
| 指定日期時間 | `"2026-02-20 at 14:00"` | UTC 06:00Z |

> **時區換算**：本地時間（+08:00） → UTC = 本地 - 8 小時
> 範例：本地 10:00 = UTC 02:00Z = `"today at 10:00"` 或 `due.datetime: "2026-02-18T02:00:00.000000Z"`

> **重要**：若設定有時間的 due，排程系統會等到該 UTC 時間才執行此任務。

### 優先級指南

| API 值 | 顯示 | Emoji | 計分 | 建議場景 |
|--------|------|-------|------|---------|
| 4 | p1 | 🔴 | 4 分 | 今日必完成、逾期任務、緊急 |
| 3 | p2 | 🟡 | 3 分 | 重要但不緊急、今明兩天 |
| 2 | p3 | 🔵 | 2 分 | 一般重要性（預設建議） |
| 1 | p4 | ⚪ | 1 分 | 低優先級、有空再做 |

> **計分公式**：綜合分 = priority分 × 路由信心度 × 描述加成 × 時間接近度 × 標籤數加成
> 逾期 ×1.5、今天到期 ×1.3，排名越高越先被執行。

---

## 步驟 4：建立 Todoist 任務（Windows 相容）

### 4.1 建立 JSON 檔案（Write 工具）

```json
{
  "content": "任務標題",
  "description": "任務描述（可選，計分加成 ×1.2）",
  "priority": 3,
  "due_string": "tomorrow at 09:00",
  "labels": ["研究", "知識庫"]
}
```

> **注意**：`labels` 直接填標籤名稱字串陣列（Todoist API v1 不需要標籤 ID）。

> **循環任務**：加入 `"due_string": "every day at 10:00"` 即可設定循環。

### 4.2 呼叫 Todoist API v1

```bash
curl -s -X POST "https://api.todoist.com/api/v1/tasks" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @task_create.json
```

> **Windows 強制規範**：POST 請求必須使用 JSON 檔案方式（`-d @file.json`），
> 不可用 inline JSON（`-d '{...}'`），Windows Bash 會失敗（error_code 42）。

### 4.3 解析回應

成功回應包含 `id` 欄位（任務已建立）：

```json
{
  "id": "6fv24RhCvXv9hcvX",
  "content": "任務標題",
  "labels": ["研究", "知識庫"],
  "priority": 3,
  "due": { "date": "2026-02-19", "datetime": "2026-02-19T01:00:00.000000Z", "is_recurring": false }
}
```

### 4.4 清理暫存檔

```bash
rm task_create.json
```

---

## 步驟 5：確認 + 路由預覽

任務建立成功後，輸出以下摘要：

```
✅ 任務已建立：
  ID: 6fv24RhCvXv9hcvX
  標題：研究 Python asyncio 最佳實踐
  描述：整理事件迴圈、協程、Task 的用法差異（計分 ×1.2）
  標籤：[研究, 知識庫]（3+ 標籤 ×1.15）
  優先級：p2 🟡（3 分）
  截止日期：2026-02-19 09:00（本地）→ 2026-02-19T01:00Z（UTC）

🔄 排程執行預覽：
  路由層級：Tier 1 標籤路由（信心度 100%）
  模板觸發：「研究」標籤 → 任務類型覆寫 → research-task.md
  匹配 Skill：web-research + knowledge-query（含 KB 去重）
  allowedTools：Read,Bash,Write,WebSearch,WebFetch
  下次執行：2026-02-19 09:00 後的第一個整點/半點觸發
  綜合分估算：3 × 1.0 × 1.2 × 1.1 × 1.15 × 1.0 ≈ 4.57
```

---

## 快速範例

### 範例 1：研究任務（寫入知識庫）

```
用戶：新增 Todoist 任務 - 研究 Python asyncio 最佳實踐，明天早上 9 點，p2，結果寫入知識庫

Claude 操作：
  content: "研究 Python asyncio 最佳實踐"
  labels: ["研究", "知識庫"]
  priority: 3 (p2)
  due_string: "tomorrow at 09:00"
```

### 範例 2：遊戲優化任務

```
用戶：新增任務 - 優化太空侵略者碰撞偵測效能，今天下午 3 點執行

Claude 操作：
  content: "優化太空侵略者碰撞偵測效能"
  description: "分析現有碰撞檢測算法，優化為空間分割法"
  labels: ["遊戲優化"]
  priority: 2 (p3)
  due_string: "today at 15:00"
```

### 範例 3：程式開發任務（多標籤）

```
用戶：新增任務 - 重構 daily-digest-prompt 的 hook 系統，明天 p1 優先

Claude 操作：
  content: "重構 daily-digest-prompt 的 hook 系統"
  labels: ["Claude Code", "專案優化"]  ← 2 個標籤，code-task 優先
  priority: 4 (p1)
  due_string: "tomorrow"
```

### 範例 4：深度分析任務

```
用戶：新增任務 - 深度分析 MCP 協議的安全架構，後天下午，加入知識庫

Claude 操作：
  content: "深度分析 MCP 協議的安全架構"
  labels: ["深度思維", "知識庫"]  ← 深度思維覆寫，knowledge-query 加入
  priority: 3 (p2)
  due_string: "in 2 days at 14:00"
```

### 範例 5：循環研究任務

```
用戶：建立每天早上 8 點研究 Unsloth 微調技術的循環任務

Claude 操作：
  content: "研究 Unsloth 微調技術"
  labels: ["研究", "AI"]
  priority: 2 (p3)
  due_string: "every day at 08:00"
  ⚠️ 注意：循環任務失敗時不修改 due_string（否則清除週期設定）
```

---

## 錯誤處理

| 錯誤狀況 | 原因 | 解決方式 |
|----------|------|---------|
| 401 Unauthorized | Token 無效 | 確認 `TODOIST_API_TOKEN` 環境變數 |
| 403 Forbidden | 權限不足 | 確認 Token 有讀寫任務權限 |
| 400 Bad Request | JSON 格式錯誤 | 檢查 task_create.json 格式 |
| 標籤未顯示 | 標籤在 Todoist 不存在 | 先在 Todoist 建立對應標籤 |
| 任務被跳過 | 屬排除類型或時間未到 | 確認非個人事務類、due.datetime 時間已過 |
| 無路由匹配 | 標籤不在 routing.yaml 映射 | 使用 `routing.yaml` 的標籤或新增映射 |

> **標籤預建提醒**：Todoist 的 `labels` API 接受不存在的標籤名稱，但不會自動建立標籤。
> 若標籤尚未在 Todoist 建立，任務雖能新增但無法被標籤路由。
> 建議先確認 Todoist 中已有對應標籤，或用 API 建立：
> `curl -s -X POST "https://api.todoist.com/api/v1/labels" -H "Authorization: Bearer $TODOIST_API_TOKEN" -d @label.json`

---

## 補充：Todoist 標籤管理

### 查詢現有標籤

```bash
curl -s "https://api.todoist.com/api/v1/labels" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" | python -c "
import sys, json
data = json.load(sys.stdin)
labels = data.get('results', data) if isinstance(data, dict) else data
for l in labels:
    print(l['name'])
"
```

### 建立新標籤（Windows 方式）

```json
{"name": "研究"}
```

```bash
curl -s -X POST "https://api.todoist.com/api/v1/labels" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @label.json
rm label.json
```

---

## 參考

- Todoist API v1 文件：`skills/todoist/SKILL.md`
- 路由規則詳細定義：`config/routing.yaml`
- 計分公式詳細說明：`config/scoring.yaml`
- 通知配置：`config/notification.yaml`
