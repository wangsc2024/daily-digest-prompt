# Skills 索引與路由引擎

> **能用 Skill 就用 Skill，絕不自行拼湊。**

## 速查表（17 個核心 Skill + 4 個工具 Skill = 21 個）

### 核心 Skill（每日摘要/Todoist Agent 使用）

| # | Skill | 用途 | 觸發關鍵字 |
|---|-------|------|-----------|
| 1 | todoist | 待辦事項查詢/新增/完成 | todoist、待辦事項、todo、任務、to-do list、待辦清單、待辦 |
| 2 | pingtung-news | 屏東新聞查詢 | 屏東新聞、屏東縣政、周春米、縣府公告、屏東最新消息、屏東縣長、新聞稿、地方新聞 |
| 3 | pingtung-policy-expert | 施政背景解讀（depends-on: pingtung-news） | 政策、施政、長照、托育、產業、醫療、交通、農業、觀光、治水、教育、施政報告、政策解讀、社會福利 |
| 4 | hackernews-ai-digest | HN AI 新聞篩選 | AI 新聞、LLM、GPT、Claude、機器學習、HN、人工智慧、深度學習、ML、Transformer |
| 5 | atomic-habits | 原子習慣每日提示 | 習慣、行為改變、原子習慣、好習慣、壞習慣、行為設計、James Clear、身份認同、兩分鐘法則 |
| 6 | learning-mastery | 深度學習技術每日技巧 | 學習、費曼、刻意練習、間隔複習、學習方法、學習技巧、記憶法、楊大輝、提取練習 |
| 7 | knowledge-query | 知識庫查詢與匯入 | 知識庫、筆記、搜尋筆記、匯入、KB、knowledge base、查詢筆記、知識管理 |
| 8 | ntfy-notify | 推播通知 | 通知、提醒、notify、完成後通知、做完通知、完成後提醒、推播、ntfy、訊息推送、告警 |
| 9 | digest-memory | 摘要記憶持久化 | 記憶、連續天數、上次執行、跨次追蹤、記憶追蹤、連續報到、streak、執行統計、趨勢 |
| 10 | api-cache | API 回應快取與降級 | 快取、cache、降級、API 故障、快取策略、TTL、降級服務、API 快取、cache hit、快取命中 |
| 11 | scheduler-state | 排程狀態追蹤（唯讀） | 狀態、健康度、執行記錄、排程狀態、成功率、系統狀態、scheduler、平均耗時 |
| 12 | gmail | Gmail 郵件讀取 | gmail、email、郵件、信箱、未讀、收件匣、inbox、Google 信箱、重要郵件、郵件摘要 |
| 13 | game-design | 遊戲設計與優化（HTML5/JS） | 遊戲、game、遊戲優化、遊戲設計、HTML5 遊戲、遊戲品質、Canvas 遊戲、JavaScript 遊戲、遊戲部署、遊戲效能 |
| 14 | system-insight | 系統自省分析（執行品質/Skill 使用/失敗模式） | 系統分析、執行報告、效能分析、Skill 使用統計、健康檢查、system-insight、自省、洞察、趨勢分析、統計報告、執行品質 |
| 15 | web-research | 網路研究標準化框架（搜尋/篩選/品質評分/KB匯入，depends-on: knowledge-query） | 研究、WebSearch、web research、來源品質、研究報告、網路搜尋、技術調查、趨勢分析、深度研究、資料蒐集、文獻回顧、調研 |
| 16 | kb-curator | 知識庫治理（去重/品質評分/過期清理） | 知識庫治理、KB 去重、筆記品質、過期清理、主題分佈、kb-curator、清理、重複筆記、品質檢查、知識庫清理、筆記統計 |
| 17 | github-scout | GitHub 靈感蒐集（熱門專案分析） | GitHub 趨勢、熱門專案、開源靈感、最佳實踐、github-scout、系統改進、架構借鑑、開源分析、GitHub trending、trending repos、專案靈感、改進建議 |

### 工具 Skill（按需使用，互動式觸發）

| # | Skill | 用途 | 觸發關鍵字 |
|---|-------|------|-----------|
| 18 | task-manager | 新增自動/排程/單次任務標準化（互動式） | 新增任務、新增自動任務、增加排程、新增排程任務、單次執行、任務管理、add task、round-robin |
| 19 | skill-scanner | AI 技能安全掃描（Cisco AI Defense） | 安全掃描、skill 掃描、security scan、安全稽核、安全檢查、漏洞掃描、Cisco AI Defense、YARA |
| 20 | system-audit | 系統審查評分（7 維度 38 子項） | 系統審查、系統評分、品質評估、system audit、安全評分、架構評審、完成度檢查、系統健檢 |
| 21 | todoist-task-creator | 互動式新增符合路由規則的 Todoist 任務（標籤/優先級/截止日期，depends-on: todoist） | 新增 Todoist 任務、建立排程任務、add todoist task、新增待辦排程、todoist 新增、新增可執行任務、todoist-task-creator、新增排程待辦、建立 todoist |

**使用方式**：每個 Skill 的完整操作指南在 `skills/<name>/SKILL.md`，執行前必讀。

---

## 強制規則

1. **禁止繞過 Skill**：若任務可由現有 Skill 處理，必須先讀取對應 SKILL.md 再執行
2. **先查索引再動手**：執行前先比對觸發關鍵字，確認是否有 Skill 可用
3. **Skill 鏈式組合**：積極串聯多個 Skill（如：todoist -> knowledge-query -> ntfy-notify）
4. **失敗回報不跳過**：Skill 執行失敗應記錄原因，不可靜默跳過

---

## 標籤路由（Label Routing）— 最高優先

Todoist 標籤直接映射到 Skill，不需經過內容關鍵字分析。

> **^prefix 匹配邏輯**：去掉 `^` 後與 Todoist labels 完全比對。多標籤命中多個映射時，合併 skills 和取最寬 allowedTools。
>
> **模板衝突解決**：多標籤命中不同模板時，按優先級取最具體者：game-task(1) > code-task(2) > research-task(3) > skill-task(4)。
>
> **修飾標籤**：`知識庫` 為跨切面修飾標籤 — 僅合併 skills/tools，不參與模板選擇。

| Todoist 標籤 | 映射 Skill | allowedTools | 模板 |
|-------------|-----------|-------------|------|
| `^Claude Code` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^GitHub` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^研究` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^深度思維` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^邏輯思維` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^知識庫` | knowledge-query | Read,Bash,Write | skill-task.md |
| `^AI` | hackernews-ai-digest | Read,Bash,Write | skill-task.md |
| `^遊戲優化` | game-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^遊戲開發` | game-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^專案優化` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^網站優化` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^UI` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^UI/UX` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^Cloudflare` | web-research | Read,Bash,Write,Edit,Glob,Grep,WebSearch,WebFetch | code-task.md |
| `^系統審查` | system-audit | Read,Bash,Write,Glob,Grep,WebSearch,WebFetch | skill-task.md |
| `^品質評估` | system-audit | Read,Bash,Write,Glob,Grep,WebSearch,WebFetch | skill-task.md |
| `^Chat系統` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^專案規劃` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
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
├── 涉及「遊戲/game」？     -> game-design + (可選) knowledge-query
├── 涉及「習慣/行為」？     -> atomic-habits
├── 涉及「學習/技巧」？     -> learning-mastery
├── 涉及「知識/筆記/研究」？ -> knowledge-query
├── 涉及「郵件/email」？    -> gmail + api-cache
├── 涉及「系統審查/評分」？ -> system-audit
├── 無可處理項目？          -> knowledge-query（楞嚴經研究 -> 匯入知識庫）
├── 需要「通知/提醒」？     -> ntfy-notify
├── 任何 API 呼叫？         -> api-cache（包裝所有外部 API）
├── 執行開始？              -> digest-memory（讀取記憶）
└── 執行結束？              -> digest-memory（寫入記憶）
```

> **注意**：`scheduler-state.json` 由 PowerShell 腳本負責寫入，Agent 僅讀取。

---

## Skill 鏈式組合模式

### 模式 A：新聞深度解讀鏈
```
pingtung-news -> pingtung-policy-expert -> knowledge-query（匯入）-> ntfy-notify
```

### 模式 B：任務智慧執行鏈
```
todoist -> knowledge-query（查詢背景）-> [執行任務] -> todoist（關閉）-> ntfy-notify
```

### 模式 C：研究與學習鏈
```
hackernews-ai-digest -> knowledge-query（匯入）-> learning-mastery -> ntfy-notify
```

### 模式 D：無待辦時自動任務鏈
```
todoist（確認無任務）-> [D1: 楞嚴經研究] -> [D2: 系統 Log 審查] -> ntfy-notify
```

**D1：楞嚴經自動研究**
1. 子 Agent 先用 `/api/notes?limit=100` + tag/title 篩選查詢知識庫已有筆記
2. 根據已有內容自主選擇下一個研究主題（不硬編碼主題表）
3. 用 WebSearch + WebFetch 蒐集資料
4. 用 knowledge-query 將研究成果匯入知識庫

**D2：系統 Log 深度審查**
1. 讀取 scheduler-state（唯讀）分析成功率與耗時
2. 掃描 logs/ 目錄搜尋 ERROR/WARN/TIMEOUT
3. 若有可改善項目 -> 擬定修正方案 -> 執行修正 -> 驗證通過
4. 用 knowledge-query 匯入審查報告
5. 用 ntfy-notify 通報結果

### 模式 E：全流程保護鏈（每次執行必用）
```
digest-memory（讀取）-> api-cache（包裝所有 API）-> [主要流程] -> digest-memory（寫入）
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
| Cloudflare Pages | game-design | `pages.cloudflare.com`（自動部署） |

---

## 團隊模式（Agent Teams）

### 架構
```
run-agent-team.ps1 (PowerShell 並行協調器)
│
├── Phase 1: 並行資料擷取（3 個 claude -p 同時啟動）
│   ├── fetch-todoist.md    -> results/todoist.json
│   ├── fetch-news.md       -> results/news.json
│   └── fetch-hackernews.md -> results/hackernews.json
│
└── Phase 2: 摘要組裝（1 個 claude -p）
    └── assemble-digest.md  -> 讀取 results/*.json -> 通知 + 記憶
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
