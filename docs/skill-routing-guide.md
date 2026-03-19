# Skill 路由指南

> 本文件接收 SKILL_INDEX.md 的路由詳細內容。速查表見 `skills/SKILL_INDEX.md`。

## 標籤路由（Label Routing）— 最高優先級

Todoist 標籤直接映射到 Skill，不需經過內容關鍵字分析。

> **^prefix 匹配邏輯**：去掉 `^` 後與 Todoist labels 完全比對。多標籤命中多個映射時，合併 skills 和取最寬 allowedTools。
>
> **模板衝突解決**：多標籤命中不同模板時，按優先級取最具體者：`game-task(1)` > `code-task(2)` > `research-task(3)` > `skill-task(4)`。
>
> **修飾標籤**：`知識庫` 為跨切面修飾標籤 — 僅合併 skills/tools，不參與模板選擇。

| Todoist 標籤 | 映射 Skill | allowedTools | 模板 |
|-------------|-----------|-------------|------|
| `^Claude Code` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^GitHub` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^研究` | web-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^深度思維` | web-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^邏輯思維` | web-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^知識庫` | knowledge-query | Read,Bash,Write | skill-task.md |
| `^AI` | hackernews-ai-digest | Read,Bash,Write | skill-task.md |
| `^遊戲優化` | game-workflow-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^遊戲開發` | game-workflow-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^專案優化` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^網站優化` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^UI` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^UI/UX` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^Cloudflare` | web-research | Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch | code-task.md |
| `^系統審查` | system-audit | Read,Bash,Write,Glob,Grep,WebSearch,WebFetch | skill-task.md |
| `^品質評估` | system-audit | Read,Bash,Write,Glob,Grep,WebSearch,WebFetch | skill-task.md |
| `^Chat系統` | chatroom-query | Read,Bash,Write,Edit,Glob,Grep | chatroom-task.md |
| `^專案規劃` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^創意` | game-workflow-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^遊戲研究` | game-workflow-design + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `@news` | pingtung-news + pingtung-policy-expert | Read,Bash,Write | skill-task.md |
| `@write` | 文件撰寫 | Read,Bash,Write | skill-task.md |

**路由優先順序**：標籤（100%）> 內容關鍵字（80%）> LLM 語義判斷（60%）

---

## 路由決策樹（無標籤任務）

```
任務內容
├── 涉及「待辦/任務/todo」？ -> todoist + (可選) knowledge-query
├── 涉及「屏東/新聞/縣政」？ -> pingtung-news + pingtung-policy-expert（必搭）
├── 涉及「AI/技術/LLM」？   -> hackernews-ai-digest
├── 涉及「遊戲/game」？ -> game-workflow-design + (可選) knowledge-query
├── 涉及「習慣/行為」？     -> atomic-habits
├── 涉及「學習/技巧」？     -> learning-mastery
├── 涉及「知識/筆記/研究」？ -> knowledge-query
├── 涉及「郵件/email」？    -> gmail + api-cache
├── 涉及「系統審查/評分」？ -> system-audit
├── 無可處理項目？          -> knowledge-query（楞嚴經研究 -> 匯入知識庫）
├── 涉及「聊天室/chatroom」？-> chatroom-query（查詢/認領/執行 bot.js 任務）
├── 需要「通知/提醒」？     -> ntfy-notify
├── 任何 API 呼叫？         -> api-cache（包裝所有外部 API）
├── 執行開始？              -> digest-memory（讀取記憶）
├── 執行結束？              -> digest-memory（寫入記憶）
└── 用 Cursor CLI / agent -p 執行單次任務、重構、審查、腳本化？ -> cursor-cli
```

> **注意**：`scheduler-state.json` 由 PowerShell 腳本負責寫入，Agent 僅讀取。

---

## Skill 鏈式組合模式

### 模式 A：新聞深度解讀鏈
```
pingtung-news → pingtung-policy-expert → knowledge-query（匯入） → ntfy-notify
```

### 模式 B：任務智慧執行鏈
```
todoist → knowledge-query（查詢背景） → [執行任務] → todoist（關閉） → ntfy-notify
```

### 模式 C：研究與學習鏈
```
hackernews-ai-digest → knowledge-query（匯入） → learning-mastery → ntfy-notify
```

### 模式 D：無待辦時自動任務鏈
```
todoist（確認無任務） → [D1: 楞嚴經研究] → [D2: 系統 Log 審查] → ntfy-notify
```

**D1：楞嚴經自動研究**
1. 子 Agent 先用 `/api/notes?limit=100` + tag/title 篩選查詢知識庫已有筆記
2. 根據已有內容自主選擇下一個研究主題（不硬編碼主題表）
3. 用 WebSearch + WebFetch 蒐集資料
4. 用 `knowledge-query` 將研究成果匯入知識庫

**D2：系統 Log 深度審查**
1. 讀取 `scheduler-state`（唯讀）分析成功率與耗時
2. 掃描 `logs/` 目錄搜尋 ERROR/WARN/TIMEOUT
3. 若有可改善項目 → 擬定修正方案 → 執行修正 → 驗證通過
4. 用 `knowledge-query` 匯入審查報告
5. 用 `ntfy-notify` 通報結果

### 模式 E：全流程保護鏈（每次執行必用）
```
digest-memory（讀取） → api-cache（包裝所有 API） → [主要流程] → digest-memory（寫入）
```

---

## 能力矩陣

### 依外部服務

| 外部服務 | 對應 Skill | API 端點 |
|---------|-----------|---------|
| Todoist | `todoist` | `api.todoist.com/api/v1` |
| 屏東新聞 MCP | `pingtung-news` | `ptnews-mcp.pages.dev/mcp` |
| Hacker News | `hackernews-ai-digest` | `hacker-news.firebaseio.com/v0` |
| 知識庫 | `knowledge-query` | `localhost:3000` |
| ntfy | `ntfy-notify` | `ntfy.sh` |
| Gmail | `gmail` | `gmail.googleapis.com/gmail/v1` |
| Cloudflare Pages | `game-design` | `pages.cloudflare.com`（自動部署） |
| Groq API | `groq` | `localhost:11435/groq/v1`（本機 Relay） |

### 依任務類型

| 任務類型 | 推薦 Skill | 模板 |
|---------|-----------|------|
| 程式開發/修改 | - | code-task.md |
| 知識研究 | web-research + knowledge-query | research-task.md |
| 遊戲設計/優化 | game-workflow-design | game-task.md |
| 有 Skill 匹配 | [對應 Skill] | skill-task.md |
| 一般任務 | - | general-task.md |

---

## 團隊模式 Agent 分工

### 每日摘要架構
```
run-agent-team.ps1 (PowerShell 並行協調器)
│
├── Phase 0: PS 預計算快取狀態 → cache/status.json
├── Phase 1: 並行資料擷取（5-6 個 claude -p 同時啟動）
│   ├── fetch-todoist.md    → results/todoist.json
│   ├── fetch-news.md       → results/news.json
│   ├── fetch-hackernews.md → results/hackernews.json
│   ├── fetch-gmail.md      → results/gmail.json
│   └── fetch-security.md   → results/security.json
│
└── Phase 2: 摘要組裝（1 個 claude -p）
    └── assemble-digest.md  → 讀取 results/*.json → 通知 + 記憶
```

### Agent 分工表

| Agent | Prompt | 使用的 Skill | 輸出 |
|-------|--------|-------------|------|
| fetch-todoist | `prompts/team/fetch-todoist.md` | `todoist`, `api-cache` | `results/todoist.json` |
| fetch-news | `prompts/team/fetch-news.md` | `pingtung-news`, `api-cache` | `results/news.json` |
| fetch-hackernews | `prompts/team/fetch-hackernews.md` | `hackernews-ai-digest`, `api-cache` | `results/hackernews.json` |
| fetch-gmail | `prompts/team/fetch-gmail.md` | `gmail`, `api-cache` | `results/gmail.json` |
| fetch-security | `prompts/team/fetch-security.md` | `skill-scanner` | `results/security.json` |
| assemble-digest | `prompts/team/assemble-digest.md` | `policy-expert`, `habits`, `learning`, `knowledge`, `ntfy`, `memory` | ntfy 通知 |

### 結果檔案統一格式
```json
{
  "agent": "fetch-todoist",
  "status": "success | failed",
  "source": "api | cache | cache_degraded | failed",
  "data_freshness": "fresh | stale",
  "cache_age_minutes": 0,
  "fetched_at": "ISO-8601",
  "skills_used": ["todoist", "api-cache"],
  "data": { ... },
  "error": null
}
```

---

## 禁止行為

1. **禁止不讀 `SKILL.md` 就直接呼叫 API**
2. **禁止自行拼 curl 指令而不參考 `SKILL.md`**
3. **禁止跳過 `api-cache`** — 所有外部 API 呼叫都必須經過快取流程
4. **禁止查新聞不加政策解讀** — `pingtung-news` 必須搭配 `pingtung-policy-expert`
5. **禁止執行結束不寫記憶** — `digest-memory` 是必要的
6. **禁止有通知需求卻不用 `ntfy-notify`**
7. **禁止忽略依賴關係** — `depends-on` 標註的 Skill 必須先執行依賴項
