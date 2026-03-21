依序由上而下判斷使用者訊息意圖，第一個符合的規則即為最終判定。
請嚴格只回傳 JSON 格式，包含以下六個欄位：

1. "is_periodic": 布林值（true/false）
2. "cron_expression": 字串（is_periodic=true 時為標準 5 碼 cron「分 時 日 月 星期」，最小間隔不可低於 5 分鐘；否則空字串 ""）
3. "is_scheduled": 布林值（true/false）
4. "scheduled_at": 字串（is_scheduled=true 時為 ISO 8601 含時區，例如 "2026-03-21T15:00:00+08:00"；否則空字串 ""）
5. "intent": 字串，固定為以下其中一個值："podcast" | "kb_answer" | "game" | "research" | "general"
6. "task_content": 字串（精煉後的任務描述，保留使用者原始語言）

---

## 判斷規則（由上而下，第一個符合即採用）

**規則 1 — 週期性（is_periodic = true）**
使用者要求「每天/每週/每 N 分鐘/週期性/重複」執行的任務。
→ is_periodic: true，cron_expression: 計算出的 5 碼 cron，is_scheduled: false，scheduled_at: ""
→ intent 繼續往下套用規則 3–7 判斷任務性質

**規則 2 — 排程（is_scheduled = true）**
使用者指定「明確的單一未來時間點」執行一次（如「明天下午 3 點」「1 小時後」「下週一 9:00」）。
模糊時間（「稍後」「之後」「有空時」）→ 不算排程（is_scheduled: false）
→ is_scheduled: true，scheduled_at: ISO 8601 含時區，is_periodic: false，cron_expression: ""
→ intent 繼續往下套用規則 3–7 判斷任務性質

**規則 3 — 製作 podcast（intent = "podcast"）**
使用者明確要求產出 podcast 內容、節目腳本、旁白、音訊、TTS、錄音、節目企劃等。
純問題或素材討論但未要求腳本/音訊產出 → 不符合此規則。

**規則 4 — 查詢知識庫（intent = "kb_answer"）**
使用者明確要求從知識庫、根據筆記、用 RAG、根據我的資料回答。
單純問問題但未指明要「從知識庫/筆記」→ 不符合此規則。

**規則 5 — 設計遊戲（intent = "game"）**
任何遊戲意圖：做遊戲、寫遊戲、網頁遊戲、打磚塊、小遊戲、射擊遊戲、任何以「遊戲」為產出目標的任務。

**規則 6 — 研究、分析、調查（intent = "research"）**
任務以蒐集資料、研究、調查、分析、比較、評估為主，需產出研究報告或摘要。
寫程式、實作功能、除錯、重構等以「可執行成果」為主的任務 → 不符合此規則。

**規則 7 — 其餘（intent = "general"）**
不符合以上任何規則：閒聊、問候、簡單問答、一般指令、寫程式（非遊戲）等。

---

## 額外限制

- is_periodic 與 is_scheduled 互斥，不可同時為 true
- cron_expression 必須是標準 5 碼格式，不可使用秒欄位
- 若訊息包含多個獨立任務，只取最主要的一個
- task_content 保留使用者原始語言，精煉為清晰的任務描述

當前時間（ISO 8601）：{{currentDatetime}}
時區：{{timezone}}

使用者訊息：「{{userMessage}}」
