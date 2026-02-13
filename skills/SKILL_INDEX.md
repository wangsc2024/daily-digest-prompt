# Skills 索引與路由引擎

> **能用 Skill 就用 Skill，絕不自行拼湊。**

## 速查表（12 個核心 Skill + 1 個工具 Skill）

### 核心 Skill（每日摘要/Todoist Agent 使用）

| # | Skill | 用途 | 觸發關鍵字 |
|---|-------|------|-----------|
| 1 | todoist | 待辦事項查詢/新增/完成 | 待辦、任務、todo、todoist |
| 2 | pingtung-news | 屏東新聞查詢 | 屏東、新聞、縣政、周春米 |
| 3 | pingtung-policy-expert | 施政背景解讀（必搭 #2） | 政策、施政、長照、產業 |
| 4 | hackernews-ai-digest | HN AI 新聞篩選 | AI、LLM、GPT、技術動態 |
| 5 | atomic-habits | 原子習慣每日提示 | 習慣、行為改變 |
| 6 | learning-mastery | 深度學習技術每日技巧 | 學習、費曼、間隔複習 |
| 7 | knowledge-query | 知識庫查詢與匯入 | 知識庫、筆記、研究 |
| 8 | ntfy-notify | 推播通知 | 通知、提醒、notify |
| 9 | digest-memory | 摘要記憶持久化 | 記憶、連續天數 |
| 10 | api-cache | API 回應快取與降級 | 快取、cache、降級 |
| 11 | scheduler-state | 排程狀態追蹤（唯讀） | 狀態、健康度 |
| 12 | gmail | Gmail 郵件讀取 | gmail、email、郵件 |

### 工具 Skill（按需使用）

| # | Skill | 用途 | 觸發關鍵字 |
|---|-------|------|-----------|
| 13 | skill-scanner | AI 技能安全掃描（Cisco AI Defense） | 安全、掃描、scan、audit、稽核 |

**使用方式**：每個 Skill 的完整操作指南在 `skills/<name>/SKILL.md`，執行前必讀。

---

## 強制規則

1. **禁止繞過 Skill**：若任務可由現有 Skill 處理，必須先讀取對應 SKILL.md 再執行
2. **先查索引再動手**：執行前先比對觸發關鍵字，確認是否有 Skill 可用
3. **Skill 鏈式組合**：積極串聯多個 Skill（如：todoist → knowledge-query → ntfy-notify）
4. **失敗回報不跳過**：Skill 執行失敗應記錄原因，不可靜默跳過

---

## 標籤路由（Label Routing）— 最高優先

Todoist 標籤直接映射到 Skill，不需經過內容關鍵字分析。

| Todoist 標籤 | 映射 Skill | allowedTools |
|-------------|-----------|-------------|
| `@code` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep |
| `@research` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch |
| `@write` | 文件撰寫 | Read,Bash,Write |
| `@news` | pingtung-news + pingtung-policy-expert | Read,Bash,Write |
| `@ai` | hackernews-ai-digest | Read,Bash,Write |
| `@knowledge` | knowledge-query | Read,Bash,Write |

**路由優先順序**：標籤（100%）> 內容關鍵字（80%）> LLM 語義判斷（60%）

---

## 路由決策樹（無標籤任務）

```
任務內容
├── 涉及「待辦/任務/todo」？ → todoist + (可選) knowledge-query
├── 涉及「屏東/新聞/縣政」？ → pingtung-news + pingtung-policy-expert（必搭）
├── 涉及「AI/技術/LLM」？   → hackernews-ai-digest
├── 涉及「習慣/行為」？     → atomic-habits
├── 涉及「學習/技巧」？     → learning-mastery
├── 涉及「知識/筆記/研究」？ → knowledge-query
├── 涉及「郵件/email」？    → gmail + api-cache
├── 無可處理項目？          → knowledge-query（楞嚴經研究 → 匯入知識庫）
├── 需要「通知/提醒」？     → ntfy-notify
├── 任何 API 呼叫？         → api-cache（包裝所有外部 API）
├── 執行開始？              → digest-memory（讀取記憶）
└── 執行結束？              → digest-memory（寫入記憶）
```

> **注意**：`scheduler-state.json` 由 PowerShell 腳本負責寫入，Agent 僅讀取。

---

## Skill 鏈式組合模式

### 模式 A：新聞深度解讀鏈
```
pingtung-news → pingtung-policy-expert → knowledge-query（匯入）→ ntfy-notify
```

### 模式 B：任務智慧執行鏈
```
todoist → knowledge-query（查詢背景）→ [執行任務] → todoist（關閉）→ ntfy-notify
```

### 模式 C：研究與學習鏈
```
hackernews-ai-digest → knowledge-query（匯入）→ learning-mastery → ntfy-notify
```

### 模式 D：無待辦時自動任務鏈
```
todoist（確認無任務）→ [D1: 楞嚴經研究] → [D2: 系統 Log 審查] → ntfy-notify
```

**D1：楞嚴經自動研究**
1. 子 Agent 先用 `/api/notes?limit=100` + tag/title 篩選查詢知識庫已有筆記
2. 根據已有內容自主選擇下一個研究主題（不硬編碼主題表）
3. 用 WebSearch + WebFetch 蒐集資料
4. 用 knowledge-query 將研究成果匯入知識庫

**D2：系統 Log 深度審查**
1. 讀取 scheduler-state（唯讀）分析成功率與耗時
2. 掃描 logs/ 目錄搜尋 ERROR/WARN/TIMEOUT
3. 若有可改善項目 → 擬定修正方案 → 執行修正 → 驗證通過
4. 用 knowledge-query 匯入審查報告
5. 用 ntfy-notify 通報結果

### 模式 E：全流程保護鏈（每次執行必用）
```
digest-memory（讀取）→ api-cache（包裝所有 API）→ [主要流程] → digest-memory（寫入）
```

---

## 外部服務對應表

| 外部服務 | 對應 Skill | API 端點 |
|---------|-----------|---------|
| Todoist | todoist | `api.todoist.com/api/v1` |
| 屏東新聞 MCP | pingtung-news | `ptnews-mcp.pages.dev/mcp` |
| Hacker News | hackernews-ai-digest | `hacker-news.firebaseio.com/v0` |
| 知識庫 | knowledge-query | `localhost:3000` |
| ntfy | ntfy-notify | `ntfy.sh` |
| Gmail | gmail | `gmail.googleapis.com/gmail/v1` |

---

## 團隊模式（Agent Teams）

### 架構
```
run-agent-team.ps1 (PowerShell 並行協調器)
│
├── Phase 1: 並行資料擷取（3 個 claude -p 同時啟動）
│   ├── fetch-todoist.md    → results/todoist.json
│   ├── fetch-news.md       → results/news.json
│   └── fetch-hackernews.md → results/hackernews.json
│
└── Phase 2: 摘要組裝（1 個 claude -p）
    └── assemble-digest.md  → 讀取 results/*.json → 通知 + 記憶
```

### Agent 分工表

| Agent | Prompt | 使用的 Skill | 輸出 |
|-------|--------|-------------|------|
| fetch-todoist | `prompts/team/fetch-todoist.md` | todoist, api-cache | `results/todoist.json` |
| fetch-news | `prompts/team/fetch-news.md` | pingtung-news, api-cache | `results/news.json` |
| fetch-hackernews | `prompts/team/fetch-hackernews.md` | hackernews-ai-digest, api-cache | `results/hackernews.json` |
| assemble-digest | `prompts/team/assemble-digest.md` | policy-expert, habits, learning, knowledge, ntfy, memory | ntfy 通知 |

### 結果檔案統一格式
```json
{
  "agent": "fetch-todoist",
  "status": "success | failed",
  "source": "api | cache | cache_degraded | failed",
  "fetched_at": "ISO-8601",
  "skills_used": ["todoist", "api-cache"],
  "data": { ... },
  "error": null
}
```

### Skill 分配
- **Phase 1**：todoist、pingtung-news、hackernews-ai-digest、api-cache
- **Phase 2**：pingtung-policy-expert、atomic-habits、learning-mastery、knowledge-query、ntfy-notify、digest-memory
- **Phase 2 不使用**（已由 Phase 1 完成）：todoist、pingtung-news、hackernews-ai-digest

---

## 禁止行為

1. **禁止不讀 SKILL.md 就直接呼叫 API**
2. **禁止自行拼 curl 指令而不參考 SKILL.md**
3. **禁止跳過 api-cache** — 所有外部 API 呼叫都必須經過快取流程
4. **禁止查新聞不加政策解讀** — pingtung-news 必須搭配 pingtung-policy-expert
5. **禁止執行結束不寫記憶** — digest-memory 是必要的
6. **禁止有通知需求卻不用 ntfy-notify**
