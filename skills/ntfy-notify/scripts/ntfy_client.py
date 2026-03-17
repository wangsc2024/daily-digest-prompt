"""
ntfy.sh 通知客戶端 — 構建和驗證 ntfy 推播酬載

用途：
  - 封裝 ntfy payload 構建邏輯（可獨立測試，不依賴網路）
  - 提供 Agent 格式化通知的輔助函式
  - 實際發送仍使用 curl（Windows 環境 UTF-8 限制）

使用方式：
  from ntfy_client import NtfyClient, NtfyPayload
  client = NtfyClient(topic="wangsc2025")
  payload = client.build_payload("✅ 任務完成", "摘要組裝成功", priority=3)
  print(payload.to_json())
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List


PRIORITY_MIN = 1
PRIORITY_MAX = 5
PRIORITY_DEFAULT = 3
TITLE_MAX_LEN = 50
MESSAGE_MAX_LEN = 500


@dataclass
class NtfyPayload:
    """ntfy 通知酬載（value object）"""

    title: str
    message: str
    topic: str = "wangsc2025"
    priority: int = PRIORITY_DEFAULT
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """轉換為字典（JSON 序列化用）"""
        data: dict = {
            "topic": self.topic,
            "title": self.title,
            "message": self.message,
            "priority": self.priority,
        }
        if self.tags:
            data["tags"] = self.tags
        return data

    def to_json(self) -> str:
        """轉換為 JSON 字串（ensure_ascii=False 確保中文正確）"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def validate(self) -> List[str]:
        """驗證酬載欄位，回傳錯誤訊息列表（空列表表示合法）"""
        errors: List[str] = []
        if not self.title or not self.title.strip():
            errors.append("title 不可為空")
        elif len(self.title) > TITLE_MAX_LEN:
            errors.append(f"title 超過 {TITLE_MAX_LEN} 字元（{len(self.title)} 字元）")
        if not self.message or not self.message.strip():
            errors.append("message 不可為空")
        if self.priority not in range(PRIORITY_MIN, PRIORITY_MAX + 1):
            errors.append(
                f"priority 必須為 {PRIORITY_MIN}-{PRIORITY_MAX}（目前為 {self.priority}）"
            )
        if not self.topic or not self.topic.strip():
            errors.append("topic 不可為空")
        return errors

    def is_valid(self) -> bool:
        """快速有效性檢查"""
        return len(self.validate()) == 0


class NtfyClient:
    """ntfy.sh 通知客戶端 — payload 構建輔助工具"""

    BASE_URL = "https://ntfy.sh"

    STATUS_EMOJI = {
        "success": "✅",
        "failed": "❌",
        "partial": "⚠️",
        "running": "🔄",
        "timeout": "⏱️",
    }

    def __init__(self, topic: str = None, base_url: str = None):
        self.topic = topic or os.environ.get("NTFY_TOPIC", "wangsc2025")
        self.base_url = (base_url or os.environ.get("NTFY_BASE_URL", self.BASE_URL)).rstrip("/")

    # ── payload 構建 ──────────────────────────────────────────────────────────

    def build_payload(
        self,
        title: str,
        message: str,
        priority: int = PRIORITY_DEFAULT,
        tags: List[str] = None,
    ) -> NtfyPayload:
        """構建通知酬載"""
        return NtfyPayload(
            title=self.truncate_title(title),
            message=self._truncate_message(message),
            topic=self.topic,
            priority=priority,
            tags=list(tags) if tags else [],
        )

    def format_agent_notification(
        self,
        agent_name: str,
        status: str,
        summary: str,
        priority: int = PRIORITY_DEFAULT,
    ) -> NtfyPayload:
        """格式化 Agent 執行結果通知（標準格式）"""
        emoji = self.STATUS_EMOJI.get(status, "ℹ️")
        title = self.truncate_title(f"{emoji} {agent_name}")
        tags = [status, "robot"]
        if status == "failed":
            priority = max(priority, 4)  # 失敗至少 high 優先級
        return self.build_payload(title=title, message=summary, priority=priority, tags=tags)

    def format_daily_digest_notification(
        self,
        task_count: int,
        completed_count: int,
        headlines: List[str],
        priority: int = 3,
    ) -> NtfyPayload:
        """格式化每日摘要通知"""
        title = f"📋 每日摘要 — {task_count} 項任務"
        lines = []
        if completed_count > 0:
            lines.append(f"✅ 已完成 {completed_count}/{task_count} 項")
        if headlines:
            lines.append("📰 " + "、".join(headlines[:3]))
        message = "\n".join(lines) if lines else "今日摘要已更新"
        return self.build_payload(title=title, message=message, priority=priority, tags=["daily"])

    # ── 輔助函式 ──────────────────────────────────────────────────────────────

    def truncate_title(self, title: str, max_len: int = TITLE_MAX_LEN) -> str:
        """截斷標題至指定長度，用省略號結尾"""
        if len(title) <= max_len:
            return title
        return title[: max_len - 1] + "…"

    def _truncate_message(self, message: str, max_len: int = MESSAGE_MAX_LEN) -> str:
        """截斷訊息至指定長度"""
        if len(message) <= max_len:
            return message
        return message[: max_len - 1] + "…"

    def notification_url(self) -> str:
        """回傳通知 POST URL"""
        return f"{self.base_url}/{self.topic}"
