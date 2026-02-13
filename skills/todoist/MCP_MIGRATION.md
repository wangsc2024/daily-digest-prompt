# Todoist MCP 遷移指南

## 現況

目前使用 REST API v1（`/api/v1/`）+ Bearer Token 認證。此方式在 `claude -p` 管道模式下穩定運行。

## 目標

遷移至 Doist 官方 [todoist-ai](https://github.com/Doist/todoist-ai) MCP 伺服器，獲得：
- OAuth 安全認證（取代 Bearer Token）
- 框架無關的工具介面（`findTasksByDate`、`addTasks` 等）
- 官方長期維護

## MCP 伺服器設定

```bash
claude mcp add --transport http todoist https://ai.todoist.net/mcp
```

## 主要工具簽名

| 工具 | 說明 | 參數 |
|------|------|------|
| `findTasksByDate` | 查詢指定日期任務 | `date: string` |
| `addTasks` | 批次新增任務 | `tasks: Task[]` |
| `completeTask` | 完成任務 | `taskId: string` |
| `getProjects` | 列出專案 | — |

## OAuth 流程

1. 在 [Todoist App Console](https://developer.todoist.com/appconsole.html) 建立 App
2. 設定 redirect_uri
3. 瀏覽器引導用戶授權 → 取得 authorization code
4. 交換 access_token → 儲存至安全位置
5. Token 自動 refresh

## 遷移前置條件

- [ ] `claude -p` 管道模式支援 MCP 工具調用（目前不支援）
- [ ] OAuth Token 自動 refresh 機制（無頭環境無法手動授權）
- [ ] Windows Task Scheduler 無頭執行相容性驗證

## 遷移檢查清單

當上述前置條件滿足後：

1. [ ] 安裝 MCP 伺服器：`claude mcp add --transport http todoist https://ai.todoist.net/mcp`
2. [ ] 完成 OAuth 授權流程，儲存 token
3. [ ] 修改 `skills/todoist/SKILL.md`：新增 MCP 工具呼叫方式
4. [ ] 修改 `hour-todoist-prompt.md`：步驟 1 改用 MCP 工具
5. [ ] 修改 `prompts/team/fetch-todoist.md`：改用 MCP 工具
6. [ ] 保留 REST API 作為 fallback（MCP 失敗時降級）
7. [ ] 測試：完整執行一次 daily-digest-team + todoist-agent
8. [ ] 確認 Windows Task Scheduler 無頭執行正常

## 備選 MCP 伺服器

| 專案 | 特色 | 適用場景 |
|------|------|---------|
| [greirson/mcp-todoist](https://github.com/greirson/mcp-todoist) | Dry-run 模式 | 開發/測試 |
| [kydycode/todoist-mcp-server-ext](https://github.com/kydycode/todoist-mcp-server-ext) | 進階篩選+搜尋 | 需要複雜查詢 |

## 暫不遷移的理由

1. `claude -p` 管道模式目前不原生支援 MCP 工具
2. OAuth 需要瀏覽器互動授權，與無頭排程衝突
3. 現有 REST API v1 穩定運行，無急迫需求
