# Skills 索引與路由引擎

> **能用 Skill 就用 Skill，絕不自行拼湊。**

## 速查表（19 個核心 + 7 個工具 = 26 個 Skills）

### 核心 Skill（每日摘要 / Todoist Agent 使用）

| # | Skill | 用途 | 觸發關鍵字 |
|---|-------|------|-----------|
| 1 | todoist | 待辦事項查詢/新增/完成 | todoist、待辦事項、todo、任務、to-do list、待辦清單、待辦 |
| 2 | pingtung-news | 屏東新聞查詢 | 屏東新聞、屏東縣政、周春米、縣府公告、屏東最新消息、屏東縣長、新聞稿、地方新聞 |
| 3 | pingtung-policy-expert | 施政背景解讀（depends-on: pingtung-news） | 政策、施政、長照、托育、產業、醫療、交通、農業、觀光、治水、教育、施政報告、政策解讀、社會福利 |
| 4 | hackernews-ai-digest | HN AI 新聞篩選（depends-on: api-cache, groq） | AI 新聞、LLM、GPT、Claude、機器學習、HN、人工智慧、深度學習、ML、Transformer |
| 5 | atomic-habits | 原子習慣每日提示 | 習慣、行為改變、原子習慣、好習慣、壞習慣、行為設計、James Clear、身份認同、兩分鐘法則 |
| 6 | learning-mastery | 深度學習技術每日技巧 | 學習、費曼、刻意練習、間隔複習、學習方法、學習技巧、記憶法、楊大輝、提取練習 |
| 7 | knowledge-query | 知識庫查詢與匯入 | 知識庫、筆記、搜尋筆記、匯入、KB、knowledge base、查詢筆記、知識管理 |
| 8 | ntfy-notify | 推播通知 | 通知、提醒、notify、完成後通知、做完通知、完成後提醒、推播、ntfy、訊息推送、告警 |
| 9 | digest-memory | 摘要記憶持久化 | 記憶、連續天數、上次執行、跨次追蹤、記憶追蹤、連續報到、streak、執行統計、趨勢 |
| 10 | api-cache | API 回應快取與降級 | 快取、cache、降級、API 故障、快取策略、TTL、降級服務、API 快取、cache hit、快取命中 |
| 11 | scheduler-state | 排程狀態追蹤（唯讀） | 狀態、健康度、執行記錄、排程狀態、成功率、系統狀態、scheduler、平均耗時 |
| 12 | gmail | Gmail 郵件讀取 | gmail、email、郵件、信箱、未讀、收件匣、inbox、Google 信箱、重要郵件、郵件摘要 |
| 13 | game-design | 遊戲設計與優化（HTML5/JS） | 遊戲、game、遊戲優化、遊戲設計、HTML5 遊戲、遊戲品質、Canvas 遊戲、JavaScript 遊戲、遊戲部署、遊戲效能 |
| 14 | system-insight | 系統自省分析（執行品質/Skill 使用/失敗模式/自動任務公平性） | 系統分析、執行報告、效能分析、Skill 使用統計、健康檢查、system-insight、自省、洞察、趨勢分析、統計報告、執行品質 |
| 15 | web-research | 網路研究標準化框架（搜尋/篩選/品質評分/KB匯入，depends-on: knowledge-query） | 研究、WebSearch、web research、來源品質、研究報告、網路搜尋、技術調查、趨勢分析、深度研究、資料蒐集、文獻回顧、調研 |
| 16 | kb-curator | 知識庫治理（去重/品質評分/過期清理） | 知識庫治理、KB 去重、筆記品質、過期清理、主題分佈、kb-curator、清理、重複筆記、品質檢查、知識庫清理、筆記統計 |
| 17 | github-scout | GitHub 靈感蒐集（熱門專案分析） | GitHub 趨勢、熱門專案、開源靈感、最佳實踐、github-scout、系統改進、架構借鑑、開源分析、GitHub trending、trending repos、專案靈感、改進建議 |
| 18 | kb-research-strategist | 研究前 KB 全文分析 + 長期系列研究管理（五階段進度追蹤，無 TTL）+ 結構化深化計畫 | 研究策略、系列研究、深化研究、知識差距分析、研究計畫、KB 擴充、知識系列、kb-research-strategist |
| 19 | groq | Groq 快速推理前處理層（透過本機 Relay，supports 摘要/翻譯/分類/萃取，depends-on: bot/groq-relay.js） | groq、快速摘要、快速翻譯、en_to_zh、英文摘要、批次翻譯、輕量分類、groq-relay、前處理 |

### 工具 Skill（按需使用，互動式觸發）

| # | Skill | 用途 | 觸發關鍵字 |
|---|-------|------|-----------|
| 20 | task-manager | 新增自動/排程/單次任務標準化（互動式） | 新增任務、新增自動任務、增加排程、新增排程任務、單次執行、任務管理、add task、round-robin |
| 21 | skill-scanner | AI 技能安全掃描（Cisco AI Defense） | 安全掃描、skill 掃描、security scan、安全稽核、安全檢查、漏洞掃描、Cisco AI Defense、YARA |
| 22 | system-audit | 系統審查評分（7 維度 38 子項） | 系統審查、系統評分、品質評估、system audit、安全評分、架構評審、完成度檢查、系統健檢 |
| 23 | todoist-task-creator | 互動式新增符合路由規則的 Todoist 任務（depends-on: todoist） | 新增 Todoist 任務、建立排程任務、add todoist task、新增待辦排程、todoist 新增、新增可執行任務、todoist-task-creator、新增排程待辦、建立 todoist |
| 24 | arch-evolution | 架構演化追蹤器（ADR/技術債/依賴圖/OODA，depends-on: system-audit、system-insight） | 架構決策、ADR、技術債、依賴圖、OODA、arch-evolution、架構治理、漸進式改進、改進計畫、架構演化 |
| 25 | git-smart-commit | 智慧分群提交（Conventional Commit） | git commit、smart commit、智慧提交、conventional commit、分群提交、git push、自動提交 |
| 26 | chatroom-query | bot.js REST API 互動（查詢/認領/執行 Gun.js 聊天室任務，depends-on: api-cache） | chatroom、聊天室、bot.js、Gun.js 任務、任務佇列、pending 任務、wsc-bot、聊天室任務、bot 任務 |

> **使用方式**：每個 Skill 的完整操作指南在 `skills/<name>/SKILL.md`，執行前必讀。

---

## 使用強度

- **必用**（每次必定使用）：todoist、pingtung-news、pingtung-policy-expert、hackernews-ai-digest、atomic-habits、learning-mastery、ntfy-notify、digest-memory、api-cache、scheduler-state
- **積極用**（有機會就用）：knowledge-query、gmail
- **搭配用**：pingtung-policy-expert 必搭 pingtung-news、api-cache 必搭任何 API 呼叫、skill-scanner 搭配 Log 審查時、arch-evolution 搭配 system-audit 後轉化 ADR、groq 搭配 hackernews-ai-digest（批次翻譯）+ pingtung-news（快速摘要）作前處理

---

## 強制規則

1. **禁止繞過 Skill**：若任務可由現有 Skill 處理，必須先讀取對應 `SKILL.md` 再執行
2. **先查索引再動手**：執行前先比對觸發關鍵字，確認是否有 Skill 可用
3. **Skill 鏈式組合**：積極串聯多個 Skill（如：`todoist` → `knowledge-query` → `ntfy-notify`）
4. **失敗回報不跳過**：Skill 執行失敗應記錄原因，不可靜默跳過
5. **依賴關係必須遵守**：有 `depends-on` 的 Skill 必須先執行依賴項

---

> 詳細路由邏輯（標籤路由表、無標籤決策樹、鏈式組合模式、能力矩陣、禁止行為清單）見 [docs/skill-routing-guide.md](../docs/skill-routing-guide.md)
