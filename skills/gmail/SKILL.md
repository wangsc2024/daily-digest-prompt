---
name: gmail
version: "1.0.0"
description: |
  Gmail 郵件讀取整合 - 查詢未讀郵件、重要郵件、特定寄件者郵件摘要。
  透過 Gmail API (OAuth2) 讀取郵件，支援快取與降級機制。
  Use when: 讀取郵件、檢查收件匣、郵件摘要、未讀郵件，or when user mentions gmail, email, 郵件, 信箱.
  Triggers: "gmail", "email", "郵件", "信箱", "未讀", "收件匣", "inbox", "mail"
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

## 快速使用（Python 腳本）

### 查詢未讀郵件（預設）

```python
# 檔案：skills/gmail/scripts/gmail.py
import os
from gmail_client import GmailClient

client = GmailClient()
messages = client.get_unread_messages(max_results=10)

for msg in messages:
    print(f"From: {msg['from']}")
    print(f"Subject: {msg['subject']}")
    print(f"Date: {msg['date']}")
    print("---")
```

### 執行方式

```bash
# 在專案根目錄執行
python skills/gmail/scripts/gmail.py
```

## API 使用（Python）

### 完整的 GmailClient 類別

```python
import os
import base64
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

class GmailClient:
    def __init__(self):
        self.creds = self._get_credentials()
        self.service = build("gmail", "v1", credentials=self.creds)

    def _get_credentials(self):
        """取得或刷新 OAuth2 憑證"""
        creds = None
        token_path = os.environ.get("GMAIL_TOKEN_PATH", "token.json")
        creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        return creds

    def get_messages(self, query="", max_results=10):
        """查詢郵件列表"""
        try:
            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            return [self._get_message_detail(msg["id"]) for msg in messages]
        except HttpError as error:
            raise Exception(f"Gmail API 錯誤: {error}")

    def get_unread_messages(self, max_results=10):
        """查詢未讀郵件"""
        return self.get_messages(query="is:unread", max_results=max_results)

    def get_important_messages(self, max_results=10):
        """查詢重要郵件"""
        return self.get_messages(query="is:important is:unread", max_results=max_results)

    def get_messages_from(self, sender, max_results=10):
        """查詢特定寄件者的郵件"""
        return self.get_messages(query=f"from:{sender} is:unread", max_results=max_results)

    def _get_message_detail(self, msg_id):
        """取得郵件詳細資訊"""
        msg = self.service.users().messages().get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        return {
            "id": msg_id,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", [])
        }
```

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

## 格式化輸出

```python
def format_messages(messages):
    """格式化郵件列表為摘要文字"""
    if not messages:
        return "📭 無未讀郵件"

    lines = [f"📬 {len(messages)} 封未讀郵件：", ""]

    for msg in messages:
        # 解析寄件者（取名稱部分）
        from_addr = msg.get("from", "")
        if "<" in from_addr:
            from_name = from_addr.split("<")[0].strip().strip('"')
        else:
            from_name = from_addr.split("@")[0]

        subject = msg.get("subject", "(無主旨)")
        snippet = msg.get("snippet", "")[:50]

        # 判斷是否重要
        is_important = "IMPORTANT" in msg.get("labels", [])
        prefix = "⭐ " if is_important else "• "

        lines.append(f"{prefix}{from_name}")
        lines.append(f"  📌 {subject}")
        if snippet:
            lines.append(f"  💬 {snippet}...")
        lines.append("")

    return "\n".join(lines)
```

## 與 Daily Digest 整合

### 在摘要中加入郵件區塊

```python
from gmail_client import GmailClient, format_messages

def get_email_digest():
    """取得郵件摘要區塊"""
    try:
        client = GmailClient()

        # 優先查重要郵件
        important = client.get_important_messages(max_results=5)
        if important:
            return format_messages(important)

        # 否則查所有未讀
        unread = client.get_unread_messages(max_results=5)
        return format_messages(unread)

    except Exception as e:
        return f"⚠️ 郵件讀取失敗：{e}"
```

### 快取整合

配合 `api-cache` Skill 使用：

```python
# 快取 key
CACHE_KEY = "gmail"
CACHE_TTL = 1800  # 30 分鐘

# 檢查快取 → API 呼叫 → 更新快取
# 詳見 skills/api-cache/SKILL.md
```

## 錯誤處理

| 錯誤 | 原因 | 解決方案 |
|------|------|---------|
| `credentials.json not found` | 憑證檔案不存在 | 確認 GMAIL_CREDENTIALS_PATH 設定正確 |
| `token.json invalid` | Token 過期或損壞 | 刪除 token.json 重新授權 |
| `HttpError 401` | 認證失敗 | 重新執行授權流程 |
| `HttpError 403` | 權限不足 | 檢查 OAuth scope 設定 |
| `HttpError 429` | API 配額超限 | 減少請求頻率或等待 |

### Token 刷新失敗處理

```python
def refresh_or_reauth():
    """嘗試刷新 token，失敗則重新授權"""
    token_path = os.environ.get("GMAIL_TOKEN_PATH", "token.json")

    # 刪除舊 token 強制重新授權
    if os.path.exists(token_path):
        os.remove(token_path)

    # 重新初始化會觸發授權流程
    return GmailClient()
```

## Windows 環境注意事項

1. **路徑設定**：使用反斜線或 raw string
   ```python
   GMAIL_CREDENTIALS_PATH = r"C:\Users\user\.config\gmail\credentials.json"
   ```

2. **首次授權**：需要有瀏覽器環境，排程執行前應先手動完成一次授權

3. **環境變數**：在 PowerShell 中設定
   ```powershell
   [Environment]::SetEnvironmentVariable("GMAIL_CREDENTIALS_PATH", "...", "User")
   ```

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
