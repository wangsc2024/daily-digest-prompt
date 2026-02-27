---
name: gmail
version: "1.1.0"
description: |
  Gmail 郵件讀取整合 - 查詢未讀郵件、重要郵件、特定寄件者郵件摘要。
  透過 Gmail API (OAuth2) 讀取郵件，支援快取與降級機制。
  Use when: 讀取郵件、檢查收件匣、郵件摘要、未讀郵件。
allowed-tools: Bash, Read, Write
cache-ttl: 30min
triggers:
  - "gmail"
  - "email"
  - "郵件"
  - "信箱"
  - "未讀"
  - "收件匣"
  - "inbox"
  - "mail"
  - "Google 信箱"
  - "重要郵件"
  - "郵件摘要"
---

# Gmail 郵件讀取整合

透過 Gmail API 讀取郵件摘要，支援多種過濾條件。

## 環境設定

### 1. Google Cloud 專案設定

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立或選擇專案
3. 啟用 Gmail API：
   - 導航到「API 和服務」→「程式庫」
   - 搜尋 "Gmail API" 並啟用

### 2. OAuth 2.0 憑證

1. 在 Google Cloud Console 中，前往「API 和服務」→「憑證」
2. 建立 OAuth 2.0 用戶端 ID：
   - 應用程式類型：「桌面應用程式」
   - 下載 JSON 檔案
3. 將檔案重新命名並存放：

```bash
# 建議路徑（環境變數設定）
export GMAIL_CREDENTIALS_PATH="$HOME/.config/gmail/credentials.json"
export GMAIL_TOKEN_PATH="$HOME/.config/gmail/token.json"
```

Windows PowerShell：
```powershell
$env:GMAIL_CREDENTIALS_PATH = "$env:USERPROFILE\.config\gmail\credentials.json"
$env:GMAIL_TOKEN_PATH = "$env:USERPROFILE\.config\gmail\token.json"
```

### 3. 安裝 Python 套件

```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 4. 首次授權

首次執行會開啟瀏覽器要求授權，授權後會自動產生 `token.json`。

## 快速使用（CLI 命令列工具）

`skills/gmail/scripts/gmail.py` 提供 4 個子命令：

```bash
# 查詢未讀郵件（預設 10 封）
cd d:/Source/daily-digest-prompt/skills/gmail/scripts && python gmail.py unread

# 查詢 5 封未讀
cd d:/Source/daily-digest-prompt/skills/gmail/scripts && python gmail.py unread -n 5

# 查詢重要未讀郵件
cd d:/Source/daily-digest-prompt/skills/gmail/scripts && python gmail.py important

# 使用 Gmail 搜尋語法查詢（今日郵件，JSON 輸出）
cd d:/Source/daily-digest-prompt/skills/gmail/scripts && python gmail.py search "newer_than:1d" -n 20 --json

# 查詢特定寄件者未讀郵件
cd d:/Source/daily-digest-prompt/skills/gmail/scripts && python gmail.py from boss@company.com
```

> **團隊模式**：`fetch-gmail.md` 使用 `search "newer_than:1d" -n 20 --json` 取得今日郵件。

## API 使用（Python）

### GmailClient 類別

完整實作在 `skills/gmail/scripts/gmail_client.py`。

**憑證路徑優先順序**（建構子參數 > 環境變數 > 預設路徑）：
1. 建構子 `credentials_path` / `token_path` 參數
2. 環境變數 `GMAIL_CREDENTIALS_PATH` / `GMAIL_TOKEN_PATH`
3. 預設路徑 `<專案根目錄>/key/credentials.json` 和 `key/token.json`

**主要方法**：

| 方法 | 用途 |
|------|------|
| `get_messages(query, max_results)` | 用 Gmail 搜尋語法查詢 |
| `get_unread_messages(max_results)` | 查詢未讀郵件 |
| `get_important_messages(max_results)` | 查詢重要未讀郵件 |
| `get_messages_from(sender, max_results)` | 查詢特定寄件者未讀郵件 |
| `format_messages(messages)` | 靜態方法，格式化郵件為摘要文字 |

## 查詢語法

Gmail API 支援與 Gmail 搜尋相同的查詢語法：

| 查詢 | 說明 |
|------|------|
| `is:unread` | 未讀郵件 |
| `is:important` | 重要郵件 |
| `is:starred` | 已加星號 |
| `from:example@gmail.com` | 特定寄件者 |
| `to:me` | 寄給我的 |
| `subject:報告` | 主旨包含關鍵字 |
| `after:2025/01/01` | 指定日期之後 |
| `before:2025/12/31` | 指定日期之前 |
| `newer_than:7d` | 最近 7 天 |
| `has:attachment` | 有附件 |
| `label:工作` | 特定標籤 |
| `category:primary` | 主要收件匣 |

組合範例：`is:unread from:boss@company.com newer_than:1d`

## 郵件物件結構

```json
{
  "id": "18d5a1b2c3d4e5f6",
  "from": "sender@example.com",
  "subject": "會議通知",
  "date": "Thu, 12 Feb 2026 09:30:00 +0800",
  "snippet": "提醒您明天下午 2 點有部門會議...",
  "labels": ["INBOX", "UNREAD", "IMPORTANT"]
}
```

## 與 Daily Digest 整合

### 快取與降級流程

配合 `api-cache` Skill（快取 key: `gmail`，TTL: 30min）：

1. **先讀快取**：用 Read 讀取 `cache/gmail.json`，檢查 `cached_at` 是否在 30 分鐘內
2. **快取有效** → 直接使用快取資料（source: `cache`）
3. **快取過期或不存在** → 呼叫 Gmail API → 成功後用 Write 寫入快取
4. **API 失敗** → 嘗試讀取過期快取（24 小時內），source 標記 `cache_degraded`
5. **完全無資料** → status 標記 `failed`，不影響整體摘要流程

## 錯誤處理

| 錯誤 | 原因 | 解決方案 |
|------|------|---------|
| `credentials.json not found` | 憑證檔案不存在 | 確認 GMAIL_CREDENTIALS_PATH 設定正確 |
| `token.json invalid` | Token 過期或損壞 | 刪除 token.json 重新授權 |
| `HttpError 401` | 認證失敗 | 重新執行授權流程 |
| `HttpError 403` | 權限不足 | 檢查 OAuth scope 設定 |
| `HttpError 429` | API 配額超限 | 減少請求頻率或等待 |

## Windows 環境注意事項

1. **憑證路徑**：預設使用 `<專案根目錄>/key/credentials.json` 和 `key/token.json`
2. **首次授權**：需要有瀏覽器環境，排程執行前應先手動完成一次授權
3. **Token 刷新**：若 token 過期，GmailClient 會自動刷新；若刷新失敗，刪除 `key/token.json` 後手動重新授權

## 配額限制

- 每日配額：10 億配額單位
- messages.list：5 單位/次
- messages.get：5 單位/次
- 建議：每次查詢不超過 10-20 封，避免過度消耗配額

## 參考資料

- [Gmail API 官方文檔](https://developers.google.com/workspace/gmail/api)
- [Python Quickstart](https://developers.google.com/gmail/api/quickstart/python)
- [查詢語法參考](https://support.google.com/mail/answer/7190)
- [API 配額說明](https://developers.google.com/gmail/api/reference/quota)
