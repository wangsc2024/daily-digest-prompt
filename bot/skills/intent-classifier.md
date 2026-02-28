請分析以下使用者的訊息，判斷他是否要求「週期性或定時」執行的任務、是否為「單次定時任務」、是否為「研究型任務」，以及是否為「多步驟工作流」。
請嚴格只回傳 JSON 格式。
包含七個欄位：
1. "is_periodic": 布林值 (true 或 false)
2. "cron_expression": 字串 (若是週期性任務回傳標準 Cron 5 碼格式 "分 時 日 月 星期"，最小間隔不可低於 5 分鐘；若非週期性回傳空字串 "")
3. "is_scheduled": 布林值 (若使用者指定「單一未來時間點」執行一次，如「明天下午 3 點」「1 小時後」「下週一早上 9 點」則為 true，否則為 false)
4. "scheduled_at": 字串 (若 is_scheduled 為 true，回傳 ISO 8601 格式的執行時間含時區，例如 "2026-02-28T15:00:00+08:00"；否則回傳空字串 "")
5. "task_content": 字串 (精煉後實際要執行的任務指令，保持使用者原始語言)
6. "is_research": 布林值 (如果任務涉及複雜的資料收集、程式碼生成、深入分析或系統操作，請設為 true，否則為 false)
7. "is_workflow": 布林值 (如果任務包含多個有先後順序或依賴關係的步驟，請設為 true，否則為 false)

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
- 若訊息為閒聊、問候或無意義文字（例如 "哈囉"、"謝謝"），is_periodic 設 false，task_content 保留原文，is_research 設 false，is_workflow 設 false
- 若訊息為「詢問」型（例如「台北天氣如何？」「什麼是 X？」），task_content 保留使用者原始問題即可，執行端會自行產出實質答案
- 若訊息包含模糊的時間描述（例如 "稍後提醒我"），視為即時任務（is_periodic: false，is_scheduled: false）
- 若訊息包含多個獨立任務但無順序關係，只取最主要的一個（is_workflow: false）
- cron_expression 必須是標準 5 碼格式，不可使用秒欄位

當前時間（ISO 8601）：{{currentDatetime}}
時區：{{timezone}}

使用者訊息：「{{userMessage}}」
