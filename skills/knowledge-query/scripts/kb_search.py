"""
Knowledge Base 搜尋客戶端 — 構建搜尋請求與解析回應

用途：
  - 封裝 KB API 查詢邏輯（可獨立測試，不依賴真實服務）
  - 統一搜尋請求體構建與結果格式化
  - Agent 可透過此模組進行 KB 查詢

使用方式：
  from kb_search import KBSearchClient
  client = KBSearchClient("http://localhost:3000")
  body = client.build_hybrid_search_body("RAG 架構", limit=5)
  results = client.parse_search_results(api_response)
  print(client.format_results_for_agent(results))
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 100
SEARCH_LIMIT_DEFAULT = 10
THRESHOLD_MIN = 0.0
THRESHOLD_MAX = 1.0
THRESHOLD_DEFAULT = 0.7
CONTENT_PREVIEW_LEN = 300


class KBSearchClient:
    """Knowledge Base 搜尋客戶端 — 請求構建與回應解析工具"""

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip("/")

    # ── 請求體構建 ────────────────────────────────────────────────────────────

    def build_hybrid_search_body(
        self,
        query: str,
        limit: int = SEARCH_LIMIT_DEFAULT,
        threshold: float = THRESHOLD_DEFAULT,
    ) -> Dict[str, Any]:
        """構建混合搜尋（語義 + 關鍵字）請求體

        Args:
            query: 搜尋關鍵詞（不可為空）
            limit: 最多回傳筆數（1-100）
            threshold: 相關性門檻（0.0-1.0）
        """
        query = query.strip()
        if not query:
            raise ValueError("query 不可為空")
        if not (SEARCH_LIMIT_MIN <= limit <= SEARCH_LIMIT_MAX):
            raise ValueError(
                f"limit 必須在 {SEARCH_LIMIT_MIN}-{SEARCH_LIMIT_MAX} 之間（目前為 {limit}）"
            )
        if not (THRESHOLD_MIN <= threshold <= THRESHOLD_MAX):
            raise ValueError(
                f"threshold 必須在 {THRESHOLD_MIN}-{THRESHOLD_MAX} 之間（目前為 {threshold}）"
            )
        return {"query": query, "limit": limit, "threshold": threshold}

    def build_title_search_body(
        self, title: str, limit: int = 5
    ) -> Dict[str, Any]:
        """構建標題搜尋請求體"""
        title = title.strip()
        if not title:
            raise ValueError("title 不可為空")
        return {"query": title, "search_type": "title", "limit": limit}

    def build_keyword_search_body(
        self, keyword: str, limit: int = SEARCH_LIMIT_DEFAULT
    ) -> Dict[str, Any]:
        """構建關鍵字搜尋（BM25）請求體"""
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword 不可為空")
        return {"query": keyword, "limit": limit}

    # ── 回應解析 ──────────────────────────────────────────────────────────────

    def parse_search_results(self, response: Any) -> List[Dict[str, Any]]:
        """解析搜尋 API 回應，標準化輸出格式

        Args:
            response: API 回傳的 dict（包含 results 列表）

        Returns:
            標準化的筆記列表，每筆含 id/title/content/score/tags
        """
        if not isinstance(response, dict):
            return []
        raw_results = response.get("results", [])
        if not isinstance(raw_results, list):
            return []

        parsed: List[Dict[str, Any]] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            parsed.append(
                {
                    "id": str(item.get("id", "")),
                    "title": item.get("title") or "(無標題)",
                    "content": item.get("content", ""),
                    "score": round(float(item.get("score", 0.0)), 4),
                    "tags": list(item.get("tags", [])),
                }
            )
        return parsed

    def parse_note_ids(self, response: Any) -> List[str]:
        """從搜尋結果中提取所有 note ID"""
        results = self.parse_search_results(response)
        return [r["id"] for r in results if r["id"]]

    # ── 格式化輸出 ────────────────────────────────────────────────────────────

    def format_results_for_agent(
        self,
        results: List[Dict[str, Any]],
        max_chars_per_result: int = CONTENT_PREVIEW_LEN,
        show_score: bool = True,
    ) -> str:
        """格式化搜尋結果供 Agent 使用

        Args:
            results: parse_search_results 回傳的列表
            max_chars_per_result: 每筆結果的最大摘要字元數
            show_score: 是否顯示相關性分數
        """
        if not results:
            return "（無相關筆記）"

        lines: List[str] = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "(無標題)")
            note_id = r.get("id", "")
            score = r.get("score", 0.0)
            content = r.get("content", "")[:max_chars_per_result]

            score_str = f", score: {score}" if show_score else ""
            lines.append(f"{i}. {title} (id: {note_id}{score_str})")
            if content:
                lines.append(f"   {content}…")

        return "\n".join(lines)

    def format_dedup_check(
        self, results: List[Dict[str, Any]], threshold: float = 0.8
    ) -> Optional[str]:
        """檢查是否有高度相似的現有筆記（用於研究去重）

        Returns:
            若有相似筆記（score >= threshold）回傳警告訊息，否則回傳 None
        """
        high_similarity = [r for r in results if r.get("score", 0.0) >= threshold]
        if not high_similarity:
            return None
        titles = "、".join(r["title"] for r in high_similarity[:3])
        return f"⚠️ 去重提示：已有 {len(high_similarity)} 篇高度相似筆記（{titles}），建議先閱讀後決定是否新增"

    # ── URL 輔助 ──────────────────────────────────────────────────────────────

    def health_check_url(self) -> str:
        """回傳健康檢查 URL"""
        return f"{self.base_url}/api/health"

    def search_url(self, search_type: str = "hybrid") -> str:
        """回傳搜尋端點 URL"""
        return f"{self.base_url}/api/search/{search_type}"

    def notes_url(self) -> str:
        """回傳筆記 CRUD 端點 URL"""
        return f"{self.base_url}/api/notes"

    def import_url(self) -> str:
        """回傳批次匯入端點 URL"""
        return f"{self.base_url}/api/import"
