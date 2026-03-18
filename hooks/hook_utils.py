#!/usr/bin/env python3
"""
Hook 共用工具模組 — 提供 YAML 配置載入與結構化日誌記錄。

所有 PreToolUse guard 共用此模組，避免重複實作。
"""
import json
import os
import re
import sys
from datetime import datetime

# 模組層級正則編譯快取（避免重複編譯 hot path 中的 pattern）
# 設有上限防止長時間運行進程記憶體膨脹
_REGEX_CACHE_MAXSIZE = 512
_compiled_regex_cache: dict = {}

# 模組層級 YAML 配置快取（避免同一進程多次開檔讀取 hook-rules.yaml）
_yaml_config_cache: dict = {"loaded": False, "data": None}

# 模組層級 PyYAML 可用性旗標（避免 hot path 中 try/except ImportError）
try:
    import yaml as _yaml_module
    _YAML_AVAILABLE = True
except ImportError:
    _yaml_module = None
    _YAML_AVAILABLE = False


def get_compiled_regex(pattern: str, flags: int = 0):
    """從快取取得已編譯正則，未命中時編譯並快取。

    快取上限 _REGEX_CACHE_MAXSIZE，超過時清除最舊一半條目，
    防止長時間運行的團隊模式進程記憶體膨脹。
    """
    key = (pattern, flags)
    if key not in _compiled_regex_cache:
        if len(_compiled_regex_cache) >= _REGEX_CACHE_MAXSIZE:
            # 淘汰前半快取（近似 LRU）
            keys_to_remove = list(_compiled_regex_cache.keys())[:_REGEX_CACHE_MAXSIZE // 2]
            for k in keys_to_remove:
                del _compiled_regex_cache[k]
        _compiled_regex_cache[key] = re.compile(pattern, flags)
    return _compiled_regex_cache[key]


# API 來源偵測 patterns（供 post_tool_logger 和 agent_guardian 共用）
API_SOURCE_PATTERNS = {
    "todoist": ["todoist.com", "todoist"],
    "pingtung-news": ["ptnews-mcp", "pingtung"],
    "hackernews": ["hacker-news.firebaseio", "hn.algolia"],
    "knowledge": ["localhost:3000"],
    "ntfy": ["ntfy.sh"],
    "gmail": ["gmail.googleapis"],
}


# Prompt Injection 偵測 patterns（供 hook 或 Python 腳本引用）
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s*:\s*you\s+are",
    r"<\s*/?\s*system",
    r"ADMIN\s*MODE",
    r"forget\s+(everything|all)",
    r"you\s+are\s+now\s+a",
    r"disregard\s+(all|any)\s+(previous|prior)",
]


# Pre-compiled regex for sensitive data sanitization (shared by post_tool_logger + behavior_tracker)
_RE_SANITIZE_AUTH = re.compile(
    r'(-H\s+["\']?Authorization:\s*)(Bearer|Basic)\s+\S+',
    re.IGNORECASE
)
_RE_SANITIZE_TOKEN_HEADER = re.compile(
    r'(-H\s+["\']?[Xx][-\w]*(?:Token|Key|Secret):\s*)\S+',
    re.IGNORECASE
)
_RE_SANITIZE_ENV_VAR = re.compile(
    r'(\$(?:env:)?[A-Z_]*(?:TOKEN|SECRET|KEY|PASSWORD)(?:\s*=\s*|\s+))\S+',
    re.IGNORECASE
)


def sanitize_sensitive_data(text: str) -> str:
    """Remove sensitive tokens/keys/secrets from text for safe logging.

    Strips:
      - Authorization: Bearer/Basic <token>
      - X-...-Token/Key/Secret: <value>
      - $env:TOKEN / $TOKEN = <value>
    """
    result = _RE_SANITIZE_AUTH.sub(r'\1\2 <REDACTED>', text)
    result = _RE_SANITIZE_TOKEN_HEADER.sub(r'\1<REDACTED>', result)
    result = _RE_SANITIZE_ENV_VAR.sub(r'\1<REDACTED>', result)
    return result


def get_project_root() -> str:
    """取得專案根目錄（hooks/ 的上層目錄）。

    所有 hook 模組共用此函式，消除重複的路徑推算邏輯。
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_config_path(filename="hook-rules.yaml"):
    """從 hooks/ 上層或 cwd 尋找配置檔，找不到回傳 None。"""
    # 優先：以本腳本位置推算 hooks/../config/
    project_root = get_project_root()
    candidate = os.path.join(project_root, "config", filename)
    if os.path.isfile(candidate):
        return candidate

    # 備援：以 cwd 為基準
    candidate = os.path.join("config", filename)
    if os.path.isfile(candidate):
        return candidate

    return None


def clear_yaml_config_cache():
    """清除 YAML 配置快取，下次呼叫將重新載入。"""
    _yaml_config_cache["loaded"] = False
    _yaml_config_cache["data"] = None


def _load_yaml_config():
    """載入 hook-rules.yaml 完整配置（含模組層級快取）。

    單次 YAML 開檔供 load_yaml_rules + filter_rules_by_preset 共用，
    避免同一 hook 呼叫中重複開檔讀取。快取在進程生命週期內有效，
    可透過 clear_yaml_config_cache() 手動清除。
    """
    if _yaml_config_cache["loaded"]:
        return _yaml_config_cache["data"]

    config_path = find_config_path()
    if config_path is None:
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = None
        return None

    if not _YAML_AVAILABLE:
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = None
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = _yaml_module.safe_load(f)
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = data
        return data
    except (OSError, _yaml_module.YAMLError) as exc:
        print(f"[hook_utils] YAML 載入失敗: {exc}", file=sys.stderr)
        _yaml_config_cache["loaded"] = True
        _yaml_config_cache["data"] = None
        return None


def load_yaml_rules(section_key, fallback_rules):
    """載入 YAML 配置中指定區段的規則，失敗時回傳 fallback。

    Args:
        section_key: YAML 頂層鍵名（如 "bash_rules"、"write_rules"）
        fallback_rules: YAML 不可用時的預設規則清單
    """
    config = _load_yaml_config()
    if config is None:
        return fallback_rules

    rules = config.get(section_key)
    if not isinstance(rules, list) or not rules:
        return fallback_rules
    return rules


def load_yaml_section(section_key, fallback=None):
    """載入 YAML 配置中指定區段（通用版，不限於規則清單）。

    與 load_yaml_rules 不同，此函數不要求值為 list，
    可用於取得任意型別的配置值（list/dict/str 等）。

    Args:
        section_key: YAML 頂層鍵名（如 "benign_output_patterns"）
        fallback: YAML 不可用或區段不存在時的預設值
    """
    config = _load_yaml_config()
    if config is None:
        return fallback

    value = config.get(section_key)
    if value is None:
        return fallback
    return value


def filter_rules_by_preset(rules, section_key="bash_rules"):
    """根據環境變數 HOOK_SECURITY_PRESET 過濾規則。

    讀取 hook-rules.yaml 的 presets 配置，根據當前 preset 的 enabled_priorities
    過濾規則清單，僅保留符合優先級的規則。

    Args:
        rules: 規則清單（必須含 priority 欄位）
        section_key: 規則區段名稱（用於日誌）

    Returns:
        過濾後的規則清單
    """
    preset_name = os.environ.get("HOOK_SECURITY_PRESET", "normal").lower()

    if preset_name == "normal":
        return rules

    config = _load_yaml_config()
    if config is None:
        return rules

    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        return rules

    preset_config = presets.get(preset_name)
    if not preset_config or not isinstance(preset_config, dict):
        return rules

    enabled_priorities = preset_config.get("enabled_priorities", ["critical", "high", "medium", "low"])

    filtered = [r for r in rules if r.get("priority", "medium") in enabled_priorities]

    if not filtered:
        return rules

    return filtered


def get_rule_patterns(rule):
    """從規則取得 pattern 清單（支援單一 pattern 或多個 patterns）。

    供 pre_bash_guard、pre_read_guard 等 guard 共用，避免重複實作。
    """
    patterns = rule.get("patterns", [])
    single = rule.get("pattern")
    if single and not patterns:
        return [single]
    return patterns


def get_rule_re_flags(rule):
    """從規則取得 regex flags。

    供 pre_bash_guard、pre_read_guard 等 guard 共用，避免重複實作。
    """
    return re.IGNORECASE if rule.get("flags") == "IGNORECASE" else 0


def log_blocked_event(session_id, tool, summary, reason, guard_tag, level: str = "block"):
    """將攔截事件寫入結構化 JSONL 日誌。

    Args:
        level: 嚴重程度，"block"（攔截）或 "warn"（警告，不攔截）
    """
    log_dir = os.path.join("logs", "structured")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".jsonl")

    entry = {
        "ts": datetime.now().astimezone().isoformat(),
        "sid": (session_id or "")[:12],
        "tool": tool,
        "event": "blocked" if level == "block" else "warn",
        "reason": reason,
        "summary": sanitize_sensitive_data(summary[:200]),
        "tags": [level, guard_tag],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_stdin_json():
    """從 stdin 讀取 JSON，解析失敗回傳 None。"""
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def output_decision(decision, reason=None, protocol_version="1.0"):
    """輸出 Hook 決策 JSON 並結束（含協議版本）。

    Args:
        decision: "allow" 或 "block"
        reason: 選填的原因說明
        protocol_version: 協議版本號（預設 "1.0"）
    """
    result = {
        "protocol_version": protocol_version,
        "decision": decision,
        "timestamp": datetime.now().isoformat()
    }
    if reason:
        result["reason"] = reason
    print(json.dumps(result))
    sys.exit(0)


class file_lock:
    """跨平台檔案鎖 context manager（Windows msvcrt / POSIX fcntl）。

    用於保護 read-modify-write 序列的互斥性，防止團隊並行模式下
    多個 Agent 進程同時更新同一 JSON 檔案導致資料遺失。

    使用方式：
        with file_lock(filepath):
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            data["count"] += 1
            atomic_write_json(filepath, data)

    鎖定機制：
      - Windows: msvcrt.locking(LK_NBLCK)
      - POSIX: fcntl.flock(LOCK_EX | LOCK_NB)
      - 兩者皆不可用時：退化為無鎖模式（不中斷流程）

    注意：鎖檔案（{filepath}.lock）在釋放後自動清理。
    """

    def __init__(self, filepath: str):
        self.lock_path = filepath + ".lock"
        self._lock_fd = None

    def __enter__(self):
        self._lock_fd = open(self.lock_path, "w")
        try:
            import msvcrt
            # 使用 LK_LOCK（阻塞等待）而非 LK_NBLCK，避免競態時靜默退化為無鎖
            msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_LOCK, 1)
        except ImportError:
            try:
                import fcntl
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass  # 無鎖可用時退化為無鎖模式
        except OSError:
            pass  # Windows 上鎖定失敗時退化為無鎖（避免中斷 Agent 流程）
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._lock_fd:
            # Windows msvcrt 必須先解鎖再關閉檔案，否則鎖可能殘留
            try:
                import msvcrt
                msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
            except (ImportError, OSError, ValueError):
                pass
            self._lock_fd.close()
            try:
                os.remove(self.lock_path)
            except OSError:
                pass
        return False  # 不吞掉例外


def atomic_write_json(filepath: str, data) -> None:
    """原子寫入 JSON 檔案（write-to-temp + os.replace()）。

    防止多個 Agent 並行寫入同一 JSON 導致資料損壞。
    在 POSIX 和 Windows NTFS 上 os.replace() 均為原子操作。

    注意：此函數保證目標檔案不會處於半寫入狀態，
    但不保護 read-modify-write 序列的互斥性。
    若需要累積計數，請在外層使用 file_lock 保護。
    """
    import tempfile
    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=dirpath, suffix=".tmp", delete=False
        ) as tf:
            tmp_path = tf.name
            json.dump(data, tf, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
        tmp_path = None  # 成功替換後清除引用，避免 finally 誤刪
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def atomic_write_lines(filepath: str, lines: list) -> None:
    """原子寫入多行文字檔案（write-to-temp + os.replace()）。

    與 atomic_write_json 相同的原子替換策略，但用於 JSONL 等
    逐行格式的檔案。每行自帶換行符或由呼叫者確保。

    Args:
        filepath: 目標檔案路徑
        lines: 字串列表，每個元素寫為一行（自動加換行符）
    """
    import tempfile
    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=dirpath, suffix=".tmp", delete=False
        ) as tf:
            tmp_path = tf.name
            for line in lines:
                tf.write(line + "\n")
        os.replace(tmp_path, filepath)
        tmp_path = None
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


# 通用 YAML 檔案快取（任意路徑，與 _yaml_config_cache 的 hook-rules.yaml 分開）
_yaml_file_cache: dict = {}


def load_yaml_file(filename: str, fallback=None):
    """載入任意 YAML 配置檔案（含模組層級快取）。

    支援兩種路徑模式：
      1. 相對於 config/ 目錄的檔名（如 "benchmark.yaml"）
      2. 絕對路徑

    Args:
        filename: 檔名或絕對路徑
        fallback: 載入失敗時的預設值

    Returns:
        解析後的 YAML 資料，或 fallback
    """
    if filename in _yaml_file_cache:
        return _yaml_file_cache[filename]

    if not _YAML_AVAILABLE:
        _yaml_file_cache[filename] = fallback
        return fallback

    # 解析檔案路徑
    if os.path.isabs(filename):
        config_path = filename
    else:
        config_path = find_config_path(filename)

    if config_path is None or not os.path.isfile(config_path):
        _yaml_file_cache[filename] = fallback
        return fallback

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = _yaml_module.safe_load(f)
        _yaml_file_cache[filename] = data
        return data
    except Exception:
        _yaml_file_cache[filename] = fallback
        return fallback


def clear_yaml_file_cache():
    """清除通用 YAML 檔案快取。"""
    _yaml_file_cache.clear()


def safe_load_json(filepath: str, default=None):
    """安全載入 JSON 檔案，失敗時回傳預設值。

    統一的 JSON 載入函數，取代散布在各模組中的重複 try/except 模式：
      - 檔案不存在 → 回傳 default
      - JSON 解析失敗 → 回傳 default
      - IO 錯誤 → 回傳 default

    Args:
        filepath: JSON 檔案路徑
        default: 載入失敗時的預設值（預設 None）

    Returns:
        解析後的 JSON 資料，或 default
    """
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def cleanup_stale_state_files(max_age_hours: int = 48) -> dict:
    """清理過期的 loop-state-*.json 和 stop-alert-*.json 檔案。

    Args:
        max_age_hours: 檔案最大保留時間（預設 48 小時）

    Returns:
        {"removed": [...], "errors": [...]} 清理結果摘要
    """

    project_root = get_project_root()
    state_dir = os.path.join(project_root, "state")
    result = {"removed": [], "errors": []}

    if not os.path.isdir(state_dir):
        return result

    cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
    patterns = ["loop-state-*.json", "stop-alert-*.json"]

    import glob as _glob
    for pattern in patterns:
        for filepath in _glob.glob(os.path.join(state_dir, pattern)):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    result["removed"].append(os.path.basename(filepath))
            except OSError as e:
                result["errors"].append(f"{os.path.basename(filepath)}: {e}")

    return result


# ── P1-A：中介軟體組合工廠（委派到 hook_pipeline）────────────────────────

def compose_middlewares(middlewares: list) -> "object":
    """
    工廠函數：從中介軟體清單建立 HookPipeline。

    委派至 hooks/hook_pipeline.py 的 compose_pipeline()，
    讓 hook_utils 使用者無需直接 import hook_pipeline。

    Args:
        middlewares: 中介軟體函數列表（每個函數簽章為 (context: dict) -> dict）

    Returns:
        HookPipeline 實例
    """
    from hook_pipeline import compose_pipeline  # noqa: F401
    return compose_pipeline(middlewares)


# ── ADR-026：JSON Schema 驗證工具函數 ────────────────────────────────────────

def validate_json_schema(data: dict, schema: dict) -> tuple[bool, list[str]]:
    """
    以 JSON Schema 驗證資料，優先使用 jsonschema 套件，不可用時退回基本必填欄位檢查。

    Args:
        data: 待驗證的 dict 資料
        schema: JSON Schema dict（Draft-7 格式）

    Returns:
        (is_valid, errors) — errors 為空串列表示驗證通過
    """
    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        errors = [e.message for e in validator.iter_errors(data)]
        return (len(errors) == 0, errors)
    except ImportError:
        pass

    # Fallback：只檢查頂層 required 欄位
    errors: list[str] = []
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"缺少必填欄位: {field}")

    # anyOf：只要有一組必填欄位存在即可
    for any_of_item in schema.get("anyOf", []):
        sub_required = any_of_item.get("required", [])
        if sub_required and all(f in data for f in sub_required):
            break
    else:
        any_of_list = schema.get("anyOf", [])
        if any_of_list:
            options = " 或 ".join(
                str(item.get("required", [])) for item in any_of_list
            )
            errors.append(f"anyOf 不滿足，需提供以下其中一組欄位: {options}")

    return (len(errors) == 0, errors)
