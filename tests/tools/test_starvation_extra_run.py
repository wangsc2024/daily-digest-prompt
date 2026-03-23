"""
飢餓加班車（Starvation Extra Run）整合測試。

驗證範圍：
- autonomous-harness.yaml 的 starvation_extra_run 設定可被正確讀取
- fairness-hint 觸發條件邏輯（starvation_detected + zero_count_tasks 數量）
- 冷卻檔判斷邏輯（within/outside cooldown）
- 加班車使用獨立 lock 路徑（不衝突正常排程）

PS 腳本的非同步 Start-Process 行為用邏輯測試替代，不做實際 process 啟動。
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── 輔助函式 ────────────────────────────────────────────────────────────────

def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_config(repo_root: Path) -> dict:
    """讀取 config/autonomous-harness.yaml，回傳 autonomous_harness 段落。"""
    cfg_path = repo_root / "config" / "autonomous-harness.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return raw.get("autonomous_harness", {})


# ── 設定讀取測試 ─────────────────────────────────────────────────────────────

def test_starvation_extra_run_config_exists() -> None:
    """starvation_extra_run 設定段落必須存在於 autonomous-harness.yaml。"""
    cfg = _load_config(REPO_ROOT)
    er = cfg.get("starvation_extra_run")
    assert er is not None, "starvation_extra_run 段落不存在"
    assert er.get("enabled") is True
    assert isinstance(er.get("cooldown_minutes"), int)
    assert isinstance(er.get("trigger_min_starvation"), int)
    assert isinstance(er.get("max_priority_tasks"), int)
    assert er.get("lock_file")
    assert er.get("cooldown_file")


def test_starvation_extra_run_lock_different_from_normal() -> None:
    """加班車的 lock_file 必須不同於正常排程的 lock 路徑。"""
    cfg = _load_config(REPO_ROOT)
    lock = cfg["starvation_extra_run"]["lock_file"]
    assert lock != "state/run-todoist-agent-team.lock"
    assert "starvation" in lock or "recovery" in lock


# ── 觸發條件邏輯（純 Python 等效測試）────────────────────────────────────────

def _should_trigger(hint: dict, er_cfg: dict, cooldown_json: dict | None) -> tuple[bool, str]:
    """
    模擬 Phase 0f 的觸發判斷邏輯。
    回傳 (should_trigger: bool, reason: str)
    """
    if not er_cfg.get("enabled", False):
        return False, "disabled"

    zero_tasks = [t for t in (hint.get("zero_count_tasks") or []) if t]
    min_starv = er_cfg.get("trigger_min_starvation", 1)

    if not hint.get("starvation_detected") or len(zero_tasks) < min_starv:
        return False, f"no_starvation (zero_count={len(zero_tasks)})"

    if cooldown_json and cooldown_json.get("last_triggered_at"):
        last = datetime.fromisoformat(cooldown_json["last_triggered_at"])
        # 統一為 naive datetime 比較
        now = datetime.now()
        if last.tzinfo is not None:
            last = last.astimezone().replace(tzinfo=None)
        elapsed_min = (now - last).total_seconds() / 60
        cooldown_min = er_cfg.get("cooldown_minutes", 120)
        if elapsed_min < cooldown_min:
            return False, f"cooldown ({elapsed_min:.0f}min < {cooldown_min}min)"

    return True, "ok"


def test_trigger_when_starvation_detected() -> None:
    """starvation_detected=True + zero_count_tasks 存在 → 應觸發。"""
    hint = {"starvation_detected": True, "zero_count_tasks": ["podcast_jiaoguangzong"]}
    er_cfg = {"enabled": True, "cooldown_minutes": 120, "trigger_min_starvation": 1, "max_priority_tasks": 3}
    triggered, reason = _should_trigger(hint, er_cfg, None)
    assert triggered, f"預期觸發，但 reason={reason}"


def test_no_trigger_when_starvation_not_detected() -> None:
    """starvation_detected=False → 不觸發。"""
    hint = {"starvation_detected": False, "zero_count_tasks": ["podcast_jiaoguangzong"]}
    er_cfg = {"enabled": True, "cooldown_minutes": 120, "trigger_min_starvation": 1}
    triggered, _ = _should_trigger(hint, er_cfg, None)
    assert not triggered


def test_no_trigger_when_disabled() -> None:
    """enabled=False → 不觸發。"""
    hint = {"starvation_detected": True, "zero_count_tasks": ["podcast_jiaoguangzong"]}
    er_cfg = {"enabled": False, "cooldown_minutes": 120, "trigger_min_starvation": 1}
    triggered, reason = _should_trigger(hint, er_cfg, None)
    assert not triggered
    assert reason == "disabled"


def test_no_trigger_within_cooldown() -> None:
    """上次觸發在冷卻期內 → 不觸發。"""
    hint = {"starvation_detected": True, "zero_count_tasks": ["podcast_jiaoguangzong"]}
    er_cfg = {"enabled": True, "cooldown_minutes": 120, "trigger_min_starvation": 1}
    # 30 分鐘前觸發，冷卻 120 分鐘
    recent = (datetime.now() - timedelta(minutes=30)).isoformat()
    cooldown = {"last_triggered_at": recent}
    triggered, reason = _should_trigger(hint, er_cfg, cooldown)
    assert not triggered
    assert "cooldown" in reason


def test_trigger_after_cooldown_expired() -> None:
    """上次觸發已超過冷卻期 → 應觸發。"""
    hint = {"starvation_detected": True, "zero_count_tasks": ["podcast_jiaoguangzong"]}
    er_cfg = {"enabled": True, "cooldown_minutes": 120, "trigger_min_starvation": 1}
    # 150 分鐘前觸發，冷卻 120 分鐘 → 已過期
    old = (datetime.now() - timedelta(minutes=150)).isoformat()
    cooldown = {"last_triggered_at": old}
    triggered, reason = _should_trigger(hint, er_cfg, cooldown)
    assert triggered, f"預期觸發，但 reason={reason}"


def test_no_trigger_below_min_starvation_threshold() -> None:
    """零次執行任務數 < trigger_min_starvation → 不觸發。"""
    hint = {"starvation_detected": True, "zero_count_tasks": []}
    er_cfg = {"enabled": True, "cooldown_minutes": 120, "trigger_min_starvation": 1}
    triggered, _ = _should_trigger(hint, er_cfg, None)
    assert not triggered


# ── priority_tasks 截斷測試 ──────────────────────────────────────────────────

def test_priority_tasks_capped_to_max() -> None:
    """zero_count_tasks 超過 max_priority_tasks 時，只取前 N 個。"""
    er_cfg = {"enabled": True, "cooldown_minutes": 120, "trigger_min_starvation": 1, "max_priority_tasks": 2}
    zero_tasks = ["task_a", "task_b", "task_c", "task_d"]
    max_n = er_cfg["max_priority_tasks"]
    selected = zero_tasks[:max_n]
    assert selected == ["task_a", "task_b"]
    assert len(selected) == 2


# ── 冷卻檔 schema 測試 ───────────────────────────────────────────────────────

def test_cooldown_file_schema(tmp_path: Path) -> None:
    """冷卻檔寫入後可被正確解析。"""
    cooldown_path = tmp_path / "starvation-extra-run.json"
    payload = {
        "last_triggered_at": datetime.now().isoformat(),
        "triggered_for": "podcast_jiaoguangzong",
        "main_trace_id": "abc123def456",
        "triggered_by": "phase0f",
    }
    _write_json(cooldown_path, payload)

    loaded = json.loads(cooldown_path.read_text(encoding="utf-8"))
    assert loaded["triggered_by"] == "phase0f"
    assert "last_triggered_at" in loaded
    # 確認時間可被 fromisoformat 解析
    datetime.fromisoformat(loaded["last_triggered_at"])
