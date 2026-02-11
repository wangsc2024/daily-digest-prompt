# Skills Index - Daily Digest Prompt

本專案所有 Skills 存放在 `skills/` 目錄內，Agent 執行時用 Read 工具讀取。

## 專案內 Skills

| Skill | 路徑 | 用途 | 來源 |
|-------|------|------|------|
| todoist | `skills/todoist/SKILL.md` | 查詢/新增/完成 Todoist 待辦事項 | Todoist REST API v2 |
| pingtung-news | `skills/pingtung-news/SKILL.md` | 查詢屏東縣政府新聞 | MCP 服務 (ptnews-mcp) |
| pingtung-policy-expert | `skills/pingtung-policy-expert/SKILL.md` | 屏東新聞政策背景解讀 | 內建知識（無外部 API） |
| hackernews-ai-digest | `skills/hackernews-ai-digest/SKILL.md` | Hacker News AI 新聞摘要 | HN API (curl) |
| atomic-habits | `skills/atomic-habits/SKILL.md` | 《原子習慣》每日提示 | 內建知識（依星期輪替） |
| learning-mastery | `skills/learning-mastery/SKILL.md` | 《深度學習的技術》每日學習技巧 | 內建知識（依星期輪替） |
| knowledge-query | `skills/knowledge-query/SKILL.md` | 個人知識庫查詢與匯入 | localhost:3000 API |
| ntfy-notify | `skills/ntfy-notify/SKILL.md` | ntfy.sh 推播通知 | ntfy.sh HTTP API |

## Skill 詳細說明

### todoist
- **路徑**: `skills/todoist/SKILL.md`
- **功能**: 透過 Todoist REST API v2 查詢、新增、完成任務
- **需求**: TODOIST_API_TOKEN（寫在 prompt 中）
- **使用工具**: Bash (curl)
- **注意**: Windows POST 必須用 JSON 檔案方式（`-d @file.json`），inline JSON 會失敗

### pingtung-news
- **路徑**: `skills/pingtung-news/SKILL.md`
- **功能**: 查詢屏東縣政府新聞稿（最新/關鍵字/日期範圍）
- **來源**: MCP 端點 `https://ptnews-mcp.pages.dev/mcp`
- **使用工具**: Bash (curl)
- **資料範圍**: 2022-12-25 起
- **注意**: 縣府 API 間歇性不穩定，skill 內含重試機制

### pingtung-policy-expert
- **路徑**: `skills/pingtung-policy-expert/SKILL.md`
- **功能**: 為屏東新聞附加施政背景解讀（四軸心政策對照）
- **使用工具**: 無（內建知識，由 Agent 直接生成）

### hackernews-ai-digest
- **路徑**: `skills/hackernews-ai-digest/SKILL.md`
- **功能**: 從 Hacker News API 篩選 AI 相關熱門文章
- **使用工具**: Bash (curl)
- **輸出**: 3-5 則 AI 新聞，標題翻譯為正體中文

### atomic-habits
- **路徑**: `skills/atomic-habits/SKILL.md`
- **功能**: 依星期幾輪替《原子習慣》每日提示
- **使用工具**: 無（內建提示庫，由 Agent 直接選取）
- **內容**: 身份認同、兩分鐘法則、環境設計、習慣堆疊、絕不錯過兩次、複利效應、系統思維

### learning-mastery
- **路徑**: `skills/learning-mastery/SKILL.md`
- **功能**: 依星期幾輪替《深度學習的技術》每日學習技巧
- **使用工具**: 無（內建提示庫，由 Agent 直接選取）
- **內容**: 提取練習、費曼技巧、知識連結、間隔複習、類比遷移、刻意練習、學習反思

### knowledge-query
- **路徑**: `skills/knowledge-query/SKILL.md`
- **功能**: 查詢個人知識庫筆記 + 匯入研究成果
- **API**: `http://localhost:3000`
- **使用工具**: Bash (curl)
- **注意**: 服務未啟動時直接跳過，不報錯。匯入時 source 僅接受 `manual`/`web`/`import`

### ntfy-notify
- **路徑**: `skills/ntfy-notify/SKILL.md`
- **功能**: 透過 ntfy.sh 發送推播通知
- **Topic**: `wangsc2025`
- **使用工具**: Write (建立 JSON 檔) + Bash (curl 發送)
- **注意**: Windows 必須用 JSON 檔案方式 + charset=utf-8 header

## Skills 維護

Skills 原始來源：`D:\Source\skills\`
如需更新 skill，從來源複製最新版本到專案內對應目錄。
