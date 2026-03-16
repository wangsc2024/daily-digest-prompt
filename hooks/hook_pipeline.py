#!/usr/bin/env python3
"""
Hook 中介軟體鏈（P1-A）— 借鑑 DeerFlow 11層中介軟體設計。

提供可組合的 HookPipeline 框架，不改變現有 stdin/stdout JSON 接口。

中介軟體函數簽章：
    (context: dict) -> dict

  context 必含：
    - decision:   "allow" | "block"（每層可改寫）
    - modified:   {} 附加修改（合入 context 後傳遞）

  短路機制：回傳 {"decision": "block", ...} 即中止後續中介軟體。

整合到 P5-A Agent Pool 時，可用 build_worker_pipeline() 組裝 Worker 專用管線。

使用範例：

    from hook_pipeline import HookPipeline, compose_pipeline

    pipeline = compose_pipeline([
        trace_middleware,
        my_guard_middleware,
        schema_validate_middleware,
    ])
    result = pipeline.execute({"tool": "Bash", "command": "ls"})
    # result: {"decision": "allow", "modified": {...}}
"""
from __future__ import annotations

from typing import Callable

# 中介軟體型別別名
Middleware = Callable[[dict], dict]


class HookPipeline:
    """
    DeerFlow 式中介軟體鏈。

    - 短路（short-circuit）：任一中介軟體回傳 decision=block 即停止
    - 累積修改：每層的 modified 欄位會合入 context 傳遞給下一層
    - 不可變輸入：使用 {**context, **result.get("modified", {})} 合併，不修改原始 dict
    """

    def __init__(self, middlewares: list[Middleware]) -> None:
        self._middlewares = list(middlewares)

    def execute(self, context: dict) -> dict:
        """
        依序執行中介軟體，遇到 block 即短路。

        Returns:
            {"decision": "allow"|"block", "modified": {...}, ...}
        """
        current = dict(context)
        for middleware in self._middlewares:
            result = middleware(current)
            if result.get("decision") == "block":
                return result
            # 合入 modified 欄位（下一層可看到累積修改）
            current = {**current, **result.get("modified", {})}

        return {"decision": "allow", "modified": current}

    def __len__(self) -> int:
        return len(self._middlewares)

    def __repr__(self) -> str:
        names = [getattr(m, "__name__", repr(m)) for m in self._middlewares]
        return f"HookPipeline([{', '.join(names)}])"


def compose_pipeline(middlewares: list[Middleware]) -> HookPipeline:
    """
    工廠函數：從中介軟體清單建立 HookPipeline。

    等同於 HookPipeline(middlewares)，提供更語義化的呼叫方式。

    Args:
        middlewares: 中介軟體函數列表，依序執行

    Returns:
        HookPipeline 實例
    """
    return HookPipeline(middlewares)


# ── 基礎中介軟體（內建，可直接組合）────────────────────────────────────────

def allow_all_middleware(context: dict) -> dict:
    """無條件放行（佔位用，或作為最後一層預設）"""
    return {"decision": "allow"}


def log_trace_middleware(context: dict) -> dict:
    """
    追蹤 middleware：注入 trace 資訊，供後續中介軟體引用。
    不阻擋任何請求，僅附加 _trace 欄位。
    """
    import datetime
    modified = {
        "_trace": {
            "timestamp": datetime.datetime.now().isoformat(),
            "tool": context.get("tool", "unknown"),
        }
    }
    return {"decision": "allow", "modified": modified}


def schema_validate_middleware(required_fields: list[str]):
    """
    工廠函數：回傳一個驗證 context 必填欄位的 middleware。

    Args:
        required_fields: 必須存在的欄位名稱列表

    Returns:
        Middleware 函數
    """
    def _validate(context: dict) -> dict:
        missing = [f for f in required_fields if f not in context]
        if missing:
            return {
                "decision": "block",
                "reason": f"缺少必填欄位：{missing}",
                "guard_tag": "schema-guard",
            }
        return {"decision": "allow"}

    _validate.__name__ = f"schema_validate({required_fields})"
    return _validate


def build_worker_pipeline(worker_type: str, pool_config: dict | None = None) -> HookPipeline:
    """
    P5-A Agent Pool：為指定 worker_type 組裝 Worker 專用中介軟體鏈。

    順序：log_trace → schema_validate（result_file 必填）→ allow_all
    未來可插入：cache → timeout → retry → done_cert

    Args:
        worker_type: "web_search" | "kb_import" | "file_sync" | "notification"
        pool_config: config/agent-pool.yaml 的 dict（可選，未來擴充用）

    Returns:
        HookPipeline 實例
    """
    required_by_type: dict[str, list[str]] = {
        "web_search":   ["task_id", "worker_type"],
        "kb_import":    ["task_id", "worker_type"],
        "file_sync":    ["task_id", "worker_type"],
        "notification": ["task_id", "worker_type"],
    }
    required = required_by_type.get(worker_type, ["task_id"])

    return compose_pipeline([
        log_trace_middleware,
        schema_validate_middleware(required),
        allow_all_middleware,
    ])
