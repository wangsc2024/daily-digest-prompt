請分析以下使用者的訊息，判斷他是否要求「週期性或定時」執行的任務、是否為「單次定時任務」、是否為「研究型任務」、是否為「多步驟工作流」，以及任務類型（一般／程式碼／遊戲／Podcast／詳細回答／從知識庫中回答）。
請嚴格只回傳 JSON 格式。
包含八個欄位：
1. "is_periodic": 布林值 (true 或 false)
2. "cron_expression": 字串 (若是週期性任務回傳標準 Cron 5 碼格式 "分 時 日 月 星期"，最小間隔不可低於 5 分鐘；若非週期性回傳空字串 "")
3. "is_scheduled": 布林值 (若使用者指定「單一未來時間點」執行一次，如「明天下午 3 點」「1 小時後」「下週一早上 9 點」則為 true，否則為 false)
4. "scheduled_at": 字串 (若 is_scheduled 為 true，回傳 ISO 8601 格式的執行時間含時區，例如 "2026-02-28T15:00:00+08:00"；否則回傳空字串 "")
5. "task_content": 字串 (精煉後實際要執行的任務指令，保持使用者原始語言)
6. "is_research": 布林值。**僅當任務以「研究、查詢、調查、分析、比較、評估」知識／技術／文獻為主**（需蒐集資料、閱讀文件、產出研究報告或寫入知識庫）時設為 true。**以下皆應設為 false**：寫程式、做遊戲、實作功能、除錯、重構、產出程式碼、寫腳本、做網頁／App 等「以產出可執行成果為主」的任務；此類應視內容設 task_type 為 "code"、"game" 或 "general"，絕不可設 is_research: true。
7. "is_workflow": 布林值 (如果任務包含多個有先後順序或依賴關係的步驟，請設為 true，否則為 false)
8. "task_type": 字串，僅限 "general" | "code" | "podcast" | "detail" | "kb_answer" | "game" 其一。**預設原則：有疑慮時一律設 "general"**，僅在下列條件**明確成立**時才使用其他類型。

**嚴格判斷規則（須同時符合「使用者明確表達」才可選用）：**
- **"game"**：**只要意圖是遊戲**即設為 "game"。包含：做遊戲、寫遊戲、網頁遊戲、小遊戲、打磚塊、具創意的 OO 遊戲、用 Vite/任何技術寫遊戲、部署到 Cloudflare Pages 的遊戲、在 game_web 產出遊戲等。此類一律 **is_research: false**。執行端會以遊戲型方案處理（Vite 建置、產出至 d:\\source\\game_web、推送 GitHub 部署 Cloudflare Pages）。**遊戲相關意圖一律用 "game"，不可用 "code"**。
- **"code"**：僅當訊息**明確**要求產出或修改**非遊戲**的程式碼、除錯、重構、寫腳本、API 串接、套件實作、程式語言語法等（例如「寫一段…程式」「幫我修這個 bug」「用 Python 實作」「重構這段 code」）。**若意圖為遊戲（做遊戲、寫遊戲、任何遊戲）→ 必須用 "game"，不可用 "code"**。此類一律 **is_research: false**。僅討論技術概念、問「怎麼做」但未明確要產出程式/腳本 → 用 "general" 或 "detail"，不可用 "code"。
- **"podcast"**：僅當訊息**明確**要求產出 Podcast／節目腳本、錄音、旁白、音訊檔、TTS、錄製、節目企劃等（例如「幫我寫這集的 podcast 腳本」「生成這段的旁白」「產出這主題的節目腳本」）。僅內容可當節目題材、或只說「講一個主題」但未明確要求腳本/音訊產出 → 用 "general" 或 "detail"，不可用 "podcast"。
- **"detail"**：僅當訊息**明確**要求詳細、逐步或長篇說明時（例如「詳細說明…」「step by step 教我」「完整分析」「逐步說明」「請長篇論述」）。單純「什麼是 X」「說明何謂 X」未加「詳細／完整／逐步」等 → 用 "general"，不可用 "detail"。
- **"kb_answer"**：僅當訊息**明確**要求從知識庫中找資料回答、根據知識庫回答、查知識庫後回答、用 RAG 回答等（例如「從知識庫中找…回答」「根據我的筆記回答…」「查知識庫後告訴我…」「用知識庫的資料回答…」）。單純問問題但未指明要「從知識庫」「根據筆記」→ 用 "general"，不可用 "kb_answer"。

其餘（提醒、簡單查詢、一般待辦、概念解釋、未明確符合上述任一類）→ "general"。

is_workflow 判斷規則：
- 訊息中包含「先...再...」「首先...然後...」「第一步...第二步...」等順序關係 → true
- 任務需要前一步的結果才能執行下一步 → true
- 單一步驟即可完成的任務 → false
- 週期性任務 (is_periodic=true) 不應同時為工作流 → is_workflow 設 false

is_scheduled 判斷規則：
- is_periodic 與 is_scheduled 互斥：重複執行的用 is_periodic，只執行一次的未來時間點用 is_scheduled
- 明確單一未來時間點（如「明天下午 3 點」「1 小時後」「下週一 9:00」）→ is_scheduled: true，scheduled_at 依當前時間與時區計算
- 模糊時間（「稍後」「之後」「有空時」）→ is_scheduled: false，scheduled_at 空字串
- is_workflow 可與 is_scheduled 並存（例如「明天下午 3 點，先做 A 再做 B」）
- 當前時間與時區供參考：{{currentDatetime}}，時區：{{timezone}}

邊界情況處理：
- **只要意圖是遊戲**（寫遊戲、做遊戲、網頁遊戲、小遊戲、打磚塊、具創意的 OO 遊戲、任何遊戲產出）：task_type 一律設 **"game"**，**is_research 必為 false**。與是否指明 Vite/Cloudflare/網頁無關。
- **程式碼/軟體意圖但非遊戲**（寫程式、除錯、重構、API、腳本、網頁或 App 但非遊戲）：task_type 設 "code"，**is_research 必為 false**。
- 若訊息為閒聊、問候或無意義文字（例如 "哈囉"、"謝謝"），is_periodic 設 false，task_content 保留原文，is_research 設 false，is_workflow 設 false
- 若訊息為「詢問」型（例如「台北天氣如何？」「什麼是 X？」），task_content 保留使用者原始問題即可，執行端會自行產出實質答案
- 若訊息包含模糊的時間描述（例如 "稍後提醒我"），視為即時任務（is_periodic: false，is_scheduled: false）
- 若訊息包含多個獨立任務但無順序關係，只取最主要的一個（is_workflow: false）
- cron_expression 必須是標準 5 碼格式，不可使用秒欄位

當前時間（ISO 8601）：{{currentDatetime}}
時區：{{timezone}}

使用者訊息：「{{userMessage}}」
