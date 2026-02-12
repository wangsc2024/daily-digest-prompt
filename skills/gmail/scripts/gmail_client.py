"""
Gmail Client - OAuth2 認證的 Gmail 唯讀客戶端
"""

import os
from typing import Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# 專案根目錄下的 key/ 資料夾
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DEFAULT_CREDENTIALS = os.path.join(_PROJECT_ROOT, "key", "credentials.json")
_DEFAULT_TOKEN = os.path.join(_PROJECT_ROOT, "key", "token.json")


class GmailClient:
    """Gmail API 唯讀客戶端"""

    def __init__(
        self,
        credentials_path: str = None,
        token_path: str = None,
    ):
        self.credentials_path = credentials_path or os.environ.get(
            "GMAIL_CREDENTIALS_PATH", _DEFAULT_CREDENTIALS
        )
        self.token_path = token_path or os.environ.get(
            "GMAIL_TOKEN_PATH", _DEFAULT_TOKEN
        )
        self.creds = self._get_credentials()
        self.service = build("gmail", "v1", credentials=self.creds)

    def _get_credentials(self) -> Credentials:
        """取得或刷新 OAuth2 憑證"""
        creds = None

        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"找不到憑證檔案: {self.credentials_path}\n"
                        "請到 Google Cloud Console 下載 OAuth 2.0 用戶端 JSON，\n"
                        f"並存放到 {self.credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # 儲存 token
            token_dir = os.path.dirname(self.token_path)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        return creds

    # ==================== 查詢方法 ====================

    def get_messages(self, query: str = "", max_results: int = 10) -> List[Dict]:
        """查詢郵件列表

        Args:
            query: Gmail 搜尋語法（如 "is:unread", "from:boss@company.com"）
            max_results: 最多回傳筆數
        """
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])
            return [self._get_message_detail(msg["id"]) for msg in messages]
        except HttpError as error:
            raise RuntimeError(f"Gmail API 錯誤: {error}") from error

    def get_unread_messages(self, max_results: int = 10) -> List[Dict]:
        """查詢未讀郵件"""
        return self.get_messages(query="is:unread", max_results=max_results)

    def get_important_messages(self, max_results: int = 10) -> List[Dict]:
        """查詢重要未讀郵件"""
        return self.get_messages(
            query="is:important is:unread", max_results=max_results
        )

    def get_messages_from(self, sender: str, max_results: int = 10) -> List[Dict]:
        """查詢特定寄件者的未讀郵件"""
        return self.get_messages(
            query=f"from:{sender} is:unread", max_results=max_results
        )

    def _get_message_detail(self, msg_id: str) -> Dict:
        """取得郵件詳細資訊（metadata only）"""
        msg = (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        headers = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        return {
            "id": msg_id,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
        }

    # ==================== 格式化輸出 ====================

    @staticmethod
    def format_messages(messages: List[Dict]) -> str:
        """格式化郵件列表為摘要文字"""
        if not messages:
            return "無未讀郵件"

        lines = [f"{len(messages)} 封未讀郵件：", ""]

        for msg in messages:
            from_addr = msg.get("from", "")
            if "<" in from_addr:
                from_name = from_addr.split("<")[0].strip().strip('"')
            else:
                from_name = from_addr.split("@")[0]

            subject = msg.get("subject") or "(無主旨)"
            snippet = msg.get("snippet", "")[:50]

            is_important = "IMPORTANT" in msg.get("labels", [])
            prefix = "[重要] " if is_important else "- "

            lines.append(f"{prefix}{from_name}")
            lines.append(f"  主旨: {subject}")
            if snippet:
                lines.append(f"  摘要: {snippet}...")
            lines.append("")

        return "\n".join(lines)
