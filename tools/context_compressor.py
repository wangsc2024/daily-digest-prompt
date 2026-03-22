#!/usr/bin/env python3
"""
Context Compression 閾值觸發機制（ADR-036）

追蹤 Claude Code Session 內的 token 累計，在超過 65% 閾值時
向 Agent 注入壓縮提示，防止 Context Window 截斷。

兩種壓縮策略：
  - BufferWindow（65-80%）：保留最近 N 次工具呼叫的關鍵結果
  - Summary（> 80%）：強制壓縮為任務摘要格式

此模組由 hooks/post_tool_logger.py 透過 dynamic import 呼叫，
所有操作必須 silent fail（不可拋出例外影響 Hook 主流程）。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
STATE_DIR = REPO_ROOT / "state"
CONTEXT_USAGE_PATH = STATE_DIR / "context-usage.json"
BUDGET_YAML_PATH = REPO_ROOT / "config" / "budget.yaml"

# 預設閾值（若 budget.yaml 讀取失敗則使用）
MAX_CONTEXT_TOKENS = 200_000     # Claude Sonnet 4.6 上下文視窗
WARN_THRESHOLD = 0.65            # 65% → BufferWindow 策略
CRITICAL_THRESHOLD = 0.80        # 80% → Summary 策略


class ContextState(str, Enum):
    NORMAL = "normal"      # < 65%
    WARNING = "warning"    # 65-80%：BufferWindow
    CRITICAL = "critical"  # > 80%：Summary


@dataclass
class SessionUsage:
    session_id: str
    phase: str
    total_input_chars: int
    total_output_chars: int
    estimated_tokens: int
    last_updated: str
    state: str = ContextState.NORMAL.value


# ── 配置載入 ─────────────────────────────────────────────────────────────────

def _load_thresholds() -> tuple[float, float, int]:
    """從 budget.yaml 載入壓縮閾值，失敗時使用預設值。"""
    try:
        import yaml
        with open(BUDGET_YAML_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        cc = config.get("context_compression", {})
        warn = float(cc.get("warn_threshold", WARN_THRESHOLD))
        critical = float(cc.get("critical_threshold", CRITICAL_THRESHOLD))
        max_tokens = int(cc.get("max_context_tokens", MAX_CONTEXT_TOKENS))
        return warn, critical, max_tokens
    except Exception:
        return WARN_THRESHOLD, CRITICAL_THRESHOLD, MAX_CONTEXT_TOKENS


# ── 狀態持久化 ────────────────────────────────────────────────────────────────

def _load_context_usage() -> dict:
    """讀取 state/context-usage.json，不存在時回傳空結構。"""
    try:
        with open(CONTEXT_USAGE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "sessions": {}, "updated": ""}


def _save_context_usage(data: dict) -> None:
    """原子寫入 state/context-usage.json。"""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = CONTEXT_USAGE_PATH.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp_path.replace(CONTEXT_USAGE_PATH)
    except OSError:
        pass  # Silent fail


# ── 公開 API ──────────────────────────────────────────────────────────────────

def get_or_create_session(session_id: str) -> SessionUsage:
    """取得或建立 Session 使用記錄。"""
    data = _load_context_usage()
    sessions = data.get("sessions", {})
    sid_key = session_id[:8]

    if sid_key in sessions:
        s = sessions[sid_key]
        return SessionUsage(
            session_id=s.get("session_id", sid_key),
            phase=s.get("phase", ""),
            total_input_chars=s.get("total_input_chars", 0),
            total_output_chars=s.get("total_output_chars", 0),
            estimated_tokens=s.get("estimated_tokens", 0),
            last_updated=s.get("last_updated", ""),
            state=s.get("state", ContextState.NORMAL.value),
        )

    return SessionUsage(
        session_id=sid_key,
        phase="",
        total_input_chars=0,
        total_output_chars=0,
        estimated_tokens=0,
        last_updated=datetime.now().isoformat(),
        state=ContextState.NORMAL.value,
    )


def update_session(
    session_id: str,
    input_chars: int,
    output_chars: int,
    phase: str = "",
) -> SessionUsage:
    """
    更新 Session token 累計並持久化。

    Args:
        session_id: Session ID（取前 8 字）
        input_chars: 本次工具呼叫的 input 字元數
        output_chars: 本次工具呼叫的 output 字元數
        phase: 當前 Phase（AGENT_PHASE 環境變數）

    Returns:
        更新後的 SessionUsage
    """
    data = _load_context_usage()
    sessions = data.setdefault("sessions", {})
    sid_key = session_id[:8]

    existing = sessions.get(sid_key, {})
    new_input = existing.get("total_input_chars", 0) + input_chars
    new_output = existing.get("total_output_chars", 0) + output_chars
    new_tokens = int((new_input + new_output) / 3.5)

    session = SessionUsage(
        session_id=sid_key,
        phase=phase or existing.get("phase", ""),
        total_input_chars=new_input,
        total_output_chars=new_output,
        estimated_tokens=new_tokens,
        last_updated=datetime.now().isoformat(),
        state=existing.get("state", ContextState.NORMAL.value),
    )

    # 計算新狀態
    _, _, max_tokens = _load_thresholds()
    threshold_result = check_threshold(session)
    session.state = threshold_result["state"]

    sessions[sid_key] = asdict(session)
    data["updated"] = datetime.now().isoformat()

    _save_context_usage(data)
    return session


def check_threshold(session: SessionUsage) -> dict:
    """
    依 Session token 使用率決定壓縮策略。

    Returns:
        {
            "state": str,            # "normal" | "warning" | "critical"
            "utilization": float,    # 0.0 - 1.0
            "action": str,           # "none" | "inject_buffer_window" | "inject_summary"
            "prompt_injection": str, # 壓縮提示文字（空字串表示無需注入）
        }
    """
    warn_thr, critical_thr, max_tokens = _load_thresholds()
    utilization = session.estimated_tokens / max_tokens if max_tokens > 0 else 0.0

    if utilization < warn_thr:
        return {
            "state": ContextState.NORMAL.value,
            "utilization": round(utilization, 4),
            "action": "none",
            "prompt_injection": "",
        }

    pct = utilization * 100

    if utilization < critical_thr:
        return {
            "state": ContextState.WARNING.value,
            "utilization": round(utilization, 4),
            "action": "inject_buffer_window",
            "prompt_injection": (
                f"[Context 優化提示] 目前 Session token 使用率 {pct:.0f}%，接近上限。\n"
                "請在繼續執行前，忘記本 Session 中早於 5 個工具呼叫前的細節，只保留：\n"
                "1. 當前任務的最終目標\n"
                "2. 最近 5 次工具呼叫的關鍵結果\n"
                "3. 尚未完成的步驟清單"
            ),
        }

    return {
        "state": ContextState.CRITICAL.value,
        "utilization": round(utilization, 4),
        "action": "inject_summary",
        "prompt_injection": (
            f"[Context 壓縮提示] Session token 使用率 {pct:.0f}%，已達壓縮門檻。\n"
            "請立即將工作記憶壓縮為以下格式，然後繼續執行：\n"
            "## 任務摘要（50 字以內）\n"
            "## 已完成步驟（條列）\n"
            "## 待完成步驟（條列）\n"
            "## 關鍵數據（必須記住的數字/ID）\n"
            "壓縮完成後繼續正常執行。"
        ),
    }


def cleanup_stale_sessions(max_age_hours: int = 4) -> int:
    """
    清除超過 max_age_hours 的舊 Session 記錄。

    Returns:
        清除的 Session 數量
    """
    data = _load_context_usage()
    sessions = data.get("sessions", {})
    cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

    stale_keys = [
        k for k, v in sessions.items()
        if v.get("last_updated", "") < cutoff
    ]

    for k in stale_keys:
        del sessions[k]

    if stale_keys:
        data["updated"] = datetime.now().isoformat()
        _save_context_usage(data)

    return len(stale_keys)
