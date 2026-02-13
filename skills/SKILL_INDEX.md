# Skills 索引與路由引擎

## 核心原則：Skill-First（技能優先）

> **能用 Skill 就用 Skill，絕不自行拼湊。**
> Skill 是經過驗證的標準化操作流程，優於任何臨時邏輯。

### 強制規則
1. **禁止繞過 Skill**：若任務可由現有 Skill 處理，必須先讀取對應 SKILL.md 再執行，禁止自行拼寫 API 呼叫或邏輯
2. **先查索引再動手**：執行任何步驟前，先比對本索引的觸發關鍵字，確認是否有 Skill 可用
3. **Skill 鏈式組合**：一個任務可串聯多個 Skill（如：todoist → knowledge-query → ntfy-notify）
4. **失敗回報不跳過**：Skill 執行失敗應記錄原因，不可靜默跳過

---

## Skills 速查表

| # | Skill | 目錄 | 用途 | 觸發關鍵字 |
|---|-------|------|------|-----------|
| 1 | todoist | `skills/todoist/` | 待辦事項查詢/新增/完成 | 待辦、任務、todo、task、todoist、今日、過期 |
| 2 | pingtung-news | `skills/pingtung-news/` | 屏東新聞查詢 | 屏東、新聞、縣政、周春米、縣府、公告 |
| 3 | pingtung-policy-expert | `skills/pingtung-policy-expert/` | 屏東施政背景解讀 | 政策、施政、長照、托育、交通、產業、治水 |
| 4 | hackernews-ai-digest | `skills/hackernews-ai-digest/` | HN AI 新聞篩選 | AI、LLM、GPT、Claude、機器學習、技術動態 |
| 5 | atomic-habits | `skills/atomic-habits/` | 原子習慣每日提示 | 習慣、行為改變、原子習慣、每日提示 |
| 6 | learning-mastery | `skills/learning-mastery/` | 深度學習技術每日技巧 | 學習、技巧、費曼、刻意練習、間隔複習 |
| 7 | knowledge-query | `skills/knowledge-query/` | 知識庫查詢與匯入 | 知識庫、筆記、搜尋筆記、匯入、研究 |
| 8 | ntfy-notify | `skills/ntfy-notify/` | 推播通知 | 通知、提醒、notify、推播 |
| 9 | digest-memory | `skills/digest-memory/` | 摘要記憶持久化 | 記憶、連續天數、上次執行 |
| 10 | api-cache | `skills/api-cache/` | API 回應快取 | 快取、cache、降級 |
| 11 | scheduler-state | `skills/scheduler-state/` | 排程狀態追蹤 | 狀態、健康度、執行記錄 |
| 12 | gmail | `skills/gmail/` | Gmail 郵件讀取 | gmail、email、郵件、信箱、未讀、收件匣 |

---

## 標籤路由（Label Routing）— 最高優先

Todoist 標籤是最優先的路由信號。若任務含有以下標籤，**直接映射到 Skill**，不需經過內容關鍵字分析。

| Todoist 標籤 | 映射 Skill | allowedTools | 說明 |
|-------------|-----------|-------------|------|
| `@code` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | 先規劃再執行，含驗證閘門 |
| `@research` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | 研究成果匯入知識庫 |
| `@write` | 文件撰寫 | Read,Bash,Write | 文件/報告產出 |
| `@news` | pingtung-news + pingtung-policy-expert | Read,Bash,Write | 新聞查詢+政策解讀 |
| `@ai` | hackernews-ai-digest | Read,Bash,Write | AI 技術動態查詢 |
| `@knowledge` | knowledge-query | Read,Bash,Write | 知識庫查詢/匯入 |

**路由優先順序**：標籤路由（信心度 100%）> 內容關鍵字（信心度 80%）> LLM 語義判斷（信心度 60%）

> 無標籤任務仍走原有的內容關鍵字比對流程（見下方決策樹）。

---

## Skill 路由決策樹（內容關鍵字比對）

遇到**無標籤**任務時，按以下順序比對：

```
任務內容
├── 涉及「待辦/任務/todo」？
│   └── → todoist + (可選) knowledge-query
├── 涉及「屏東/新聞/縣政」？
│   └── → pingtung-news + pingtung-policy-expert（必須搭配）
├── 涉及「AI/技術/LLM」？
│   └── → hackernews-ai-digest
├── 涉及「習慣/行為」？
│   └── → atomic-habits
├── 涉及「學習/技巧」？
│   └── → learning-mastery
├── 涉及「知識/筆記/研究」？
│   └── → knowledge-query
├── 涉及「郵件/email/收件匣」？
│   └── → gmail + (可選) api-cache
├── Todoist 無可處理項目？
│   └── → knowledge-query（楞嚴經自動研究 → 匯入知識庫）
├── 需要「通知/提醒」？
│   └── → ntfy-notify
├── 任何 API 呼叫？
│   └── → api-cache（包裝所有外部 API 呼叫）
├── 執行開始？
│   └── → digest-memory（讀取記憶）
└── 執行結束？
    └── → digest-memory（寫入記憶）+ scheduler-state（寫入狀態）
```

---

## Skill 鏈式組合模式

### 模式 A：新聞深度解讀鏈
```
pingtung-news → pingtung-policy-expert → knowledge-query（匯入）→ ntfy-notify
```
1. 用 pingtung-news 取得新聞
2. 用 pingtung-policy-expert 加上政策背景
3. 用 knowledge-query 將有價值的新聞匯入知識庫（可選）
4. 用 ntfy-notify 推播

### 模式 B：任務智慧執行鏈
```
todoist → knowledge-query（查詢背景）→ [執行任務] → todoist（關閉）→ ntfy-notify
```
1. 用 todoist 取得待辦
2. 用 knowledge-query 查詢相關知識（可選）
3. 執行任務
4. 用 todoist 關閉已完成任務
5. 用 ntfy-notify 通報結果

### 模式 C：研究與學習鏈
```
hackernews-ai-digest → knowledge-query（匯入）→ learning-mastery → ntfy-notify
```
1. 用 hackernews-ai-digest 取得 AI 動態
2. 用 knowledge-query 將重要發現匯入知識庫
3. 搭配 learning-mastery 提供學習方法提示

### 模式 D：無待辦時自動任務鏈（Todoist 無待辦時觸發）
```
todoist（確認無任務）→ [D1: 楞嚴經研究] → [D2: 系統 Log 審查] → ntfy-notify
```

**D1：楞嚴經自動研究**
1. 用 knowledge-query 查詢已有楞嚴經筆記，避免重複
2. 選取未研究的主題，用 WebSearch + WebFetch 蒐集資料
3. 用 knowledge-query 將研究成果匯入知識庫

**D2：系統 Log 深度審查**
1. 用 scheduler-state 讀取執行記錄，分析成功率與耗時
2. 掃描 logs/ 目錄的日誌檔，搜尋 ERROR/WARN/TIMEOUT 等問題
3. 若有可改善項目 → WebSearch 搜尋參考案例 → 擬定修正方案 → 執行修正 → 驗證通過
4. 用 knowledge-query 將審查報告匯入知識庫
5. 用 ntfy-notify 通報結果

### 模式 E：全流程保護鏈（每次執行必用）
```
digest-memory（讀取）→ api-cache（包裝所有 API）→ [主要流程] → digest-memory（寫入）→ scheduler-state（寫入）
```

---

## Skill 能力矩陣

### 依任務類型速查

| 我要做的事 | 用哪個 Skill | 讀取 SKILL.md |
|-----------|-------------|--------------|
| 查今天要做什麼 | todoist | ✅ 必讀 |
| 新增一個待辦 | todoist | ✅ 必讀 |
| 完成一個待辦 | todoist | ✅ 必讀 |
| 查屏東發生什麼事 | pingtung-news | ✅ 必讀 |
| 理解新聞背後的政策 | pingtung-policy-expert | ✅ 必讀 |
| 查最新 AI 技術動態 | hackernews-ai-digest | ✅ 必讀 |
| 給一個習慣建議 | atomic-habits | ✅ 必讀 |
| 給一個學習技巧 | learning-mastery | ✅ 必讀 |
| 查知識庫有什麼筆記 | knowledge-query | ✅ 必讀 |
| 把研究結果存起來 | knowledge-query | ✅ 必讀 |
| 發通知給用戶 | ntfy-notify | ✅ 必讀 |
| 呼叫外部 API | api-cache | ✅ 必讀 |
| 知道上次執行結果 | digest-memory | ✅ 必讀 |
| 記錄這次執行 | scheduler-state | ✅ 必讀 |
| 查收件匣郵件 | gmail | ✅ 必讀 |
| 查未讀/重要郵件 | gmail | ✅ 必讀 |

### 依外部服務速查

| 外部服務 | 對應 Skill | API 端點 |
|---------|-----------|---------|
| Todoist | todoist | `api.todoist.com/api/v1` |
| 屏東新聞 MCP | pingtung-news | `ptnews-mcp.pages.dev/mcp` |
| Hacker News | hackernews-ai-digest | `hacker-news.firebaseio.com/v0` |
| 知識庫 | knowledge-query | `localhost:3000` |
| ntfy | ntfy-notify | `ntfy.sh` |
| Gmail | gmail | `gmail.googleapis.com/gmail/v1` |

---

## Skill 使用檢查清單

每次執行前，Agent 應自問：

- [ ] 我讀過 SKILL_INDEX.md 了嗎？
- [ ] 這個步驟有對應的 Skill 嗎？（查速查表）
- [ ] 我讀過該 Skill 的 SKILL.md 了嗎？
- [ ] 這個 API 呼叫有經過 api-cache 包裝嗎？
- [ ] 屏東新聞有搭配 pingtung-policy-expert 嗎？
- [ ] 有值得匯入知識庫的內容嗎？（knowledge-query）
- [ ] 執行開始時讀了 digest-memory 嗎？
- [ ] 執行結束時寫了 digest-memory 和 scheduler-state 嗎？
- [ ] 最後有用 ntfy-notify 通知嗎？

---

## 禁止行為

1. **禁止不讀 SKILL.md 就直接呼叫 API** — 每個 API 都有 Skill 包裝
2. **禁止自行拼 curl 指令而不參考 SKILL.md** — Skill 中有正確的參數格式
3. **禁止跳過 api-cache** — 所有外部 API 呼叫都必須經過快取流程
4. **禁止查新聞不加政策解讀** — pingtung-news 必須搭配 pingtung-policy-expert
5. **禁止執行結束不寫記憶和狀態** — digest-memory 和 scheduler-state 是必要的
6. **禁止有通知需求卻不用 ntfy-notify** — 所有通知都經過 Skill 標準化流程

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
    └── assemble-digest.md  → 讀取 results/*.json → 通知 + 狀態
```

### Agent 分工表

| Agent | Prompt 檔案 | 使用的 Skill | 輸出 |
|-------|-------------|-------------|------|
| fetch-todoist | `prompts/team/fetch-todoist.md` | todoist, api-cache | `results/todoist.json` |
| fetch-news | `prompts/team/fetch-news.md` | pingtung-news, api-cache | `results/news.json` |
| fetch-hackernews | `prompts/team/fetch-hackernews.md` | hackernews-ai-digest, api-cache | `results/hackernews.json` |
| assemble-digest | `prompts/team/assemble-digest.md` | policy-expert, habits, learning, knowledge, ntfy, memory, state | ntfy 通知 |

### 結果檔案統一格式
```json
{
  "agent": "fetch-todoist",
  "status": "success | failed",
  "source": "api | cache | cache_degraded | failed",
  "fetched_at": "ISO-8601",
  "data": { ... },
  "error": null
}
```

### Skill 在團隊模式中的分配
- **Phase 1 Agent 使用**：todoist、pingtung-news、hackernews-ai-digest、api-cache
- **Phase 2 Agent 使用**：pingtung-policy-expert、atomic-habits、learning-mastery、knowledge-query、ntfy-notify、digest-memory、scheduler-state
- **Phase 2 不使用**（已由 Phase 1 完成）：todoist、pingtung-news、hackernews-ai-digest
