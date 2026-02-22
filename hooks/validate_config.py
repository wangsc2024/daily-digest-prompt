#!/usr/bin/env python3
"""
YAML 配置 Schema 驗證工具。

可由 check-health.ps1 呼叫或獨立執行。
驗證所有 config/*.yaml 檔案的結構是否符合預期 schema。
"""
import os
import sys
import json


def _load_yaml(filepath):
    """載入 YAML 檔案，失敗回傳 None。"""
    try:
        import yaml
    except ImportError:
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


# Schema 定義：每個配置檔的必要結構
SCHEMAS = {
    "hook-rules.yaml": {
        "required_keys": ["bash_rules", "write_rules"],
        "list_fields": {
            "bash_rules": ["id", "reason", "guard_tag"],
            "write_rules": ["id", "check", "reason|reason_template", "guard_tag"],
        },
    },
    "routing.yaml": {
        "required_keys": ["pre_filter", "label_routing"],
    },
    "cache-policy.yaml": {
        "required_keys": ["version"],
    },
    "frequency-limits.yaml": {
        "required_keys": ["version", "tasks"],
        "dict_fields": {
            "tasks": ["name", "daily_limit", "counter_field", "execution_order"],
        },
    },
    "scoring.yaml": {
        "required_keys": ["version"],
    },
    "notification.yaml": {
        "required_keys": ["version", "default_topic", "service_url"],
    },
    "dedup-policy.yaml": {
        "required_keys": ["version"],
    },
    # 新增：之前未覆蓋的配置檔
    "timeouts.yaml": {
        "required_keys": ["version"],
    },
    "audit-scoring.yaml": {
        "required_keys": ["version"],
    },
    "benchmark.yaml": {
        "required_keys": ["version"],
    },
    "health-scoring.yaml": {
        "required_keys": ["version"],
    },
    "topic-rotation.yaml": {
        "required_keys": ["version"],
    },
    "error-patterns.yaml": {
        "required_keys": ["version", "http_status_map", "backoff"],
    },
}


def _check_required_keys(data, required_keys, filepath):
    """檢查頂層必要鍵是否存在。"""
    errors = []
    for key in required_keys:
        if key not in data:
            errors.append(f"{filepath}: 缺少必要鍵 '{key}'")
    return errors


def _check_list_fields(data, list_fields, filepath):
    """檢查 list 欄位中每個項目是否含必要子鍵。"""
    errors = []
    for field_name, required_subkeys in list_fields.items():
        items = data.get(field_name)
        if not isinstance(items, list):
            errors.append(f"{filepath}: '{field_name}' 應為 list 類型")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(
                    f"{filepath}: '{field_name}[{i}]' 應為 dict 類型")
                continue
            for subkey in required_subkeys:
                # 支援 "key_a|key_b" 語法（任一存在即可）
                alternatives = subkey.split("|")
                if not any(alt in item for alt in alternatives):
                    errors.append(
                        f"{filepath}: '{field_name}[{i}]' 缺少 '{subkey}'")
    return errors


def validate_config(config_dir=None):
    """驗證所有配置檔案。

    Returns:
        (errors, warnings) — 各為字串 list。
    """
    if config_dir is None:
        # 從腳本位置推算
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(os.path.dirname(script_dir), "config")

    errors = []
    warnings = []

    for filename, schema in SCHEMAS.items():
        filepath = os.path.join(config_dir, filename)

        if not os.path.exists(filepath):
            warnings.append(f"{filename}: 檔案不存在")
            continue

        data = _load_yaml(filepath)
        if data is None:
            errors.append(f"{filename}: YAML 解析失敗（語法錯誤或 PyYAML 未安裝）")
            continue

        # 檢查必要鍵
        required = schema.get("required_keys", [])
        errors.extend(_check_required_keys(data, required, filename))

        # 檢查 list 欄位結構
        list_fields = schema.get("list_fields", {})
        errors.extend(_check_list_fields(data, list_fields, filename))

        # 檢查 dict 欄位結構（如 frequency-limits.yaml 的 tasks）
        dict_fields = schema.get("dict_fields", {})
        for field_name, required_subkeys in dict_fields.items():
            items = data.get(field_name)
            if not isinstance(items, dict):
                errors.append(f"{filename}: '{field_name}' 應為 dict 類型")
                continue
            for key, value in items.items():
                if not isinstance(value, dict):
                    continue
                for subkey in required_subkeys:
                    if subkey not in value:
                        errors.append(
                            f"{filename}: '{field_name}.{key}' 缺少 '{subkey}'")

    # Cross-file consistency checks
    cross_errors = _check_cross_references(config_dir)
    errors.extend(cross_errors)

    return errors, warnings


def _check_cross_references(config_dir):
    """跨檔一致性檢查。"""
    errors = []

    # 1. hook-rules.yaml: 所有規則 id 必須唯一
    hook_rules = _load_yaml(os.path.join(config_dir, "hook-rules.yaml"))
    if hook_rules:
        all_ids = []
        for section in ["bash_rules", "write_rules", "read_rules"]:
            rules = hook_rules.get(section, [])
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict):
                        all_ids.append(rule.get("id", ""))
        duplicates = [rid for rid in set(all_ids) if all_ids.count(rid) > 1 and rid]
        for dup in duplicates:
            errors.append(f"hook-rules.yaml: 規則 id '{dup}' 重複定義")

    # 2. cache-policy.yaml sources 應涵蓋主要 API（僅在 sources 區段存在時檢查）
    cache_policy = _load_yaml(os.path.join(config_dir, "cache-policy.yaml"))
    if cache_policy:
        sources = cache_policy.get("sources", {})
        if sources:  # 僅在有 sources 區段時檢查完整性
            expected_sources = ["todoist", "pingtung-news", "hackernews", "knowledge", "gmail"]
            for src in expected_sources:
                if src not in sources:
                    errors.append(f"cache-policy.yaml: 缺少來源 '{src}' 的快取定義")

    # 3. frequency-limits.yaml 任務總 daily_limit 應符合預期（僅在有多個任務時檢查）
    freq_limits = _load_yaml(os.path.join(config_dir, "frequency-limits.yaml"))
    if freq_limits:
        tasks = freq_limits.get("tasks", {})
        if isinstance(tasks, dict) and len(tasks) > 1:
            total_limit = sum(
                t.get("daily_limit", 0)
                for t in tasks.values()
                if isinstance(t, dict)
            )
            if total_limit > 0 and total_limit != 45:
                errors.append(
                    f"frequency-limits.yaml: 任務 daily_limit 總和為 {total_limit}，預期 45"
                )

    return errors


def main():
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    errors, warnings = validate_config()

    if "--json" in sys.argv:
        print(json.dumps({
            "errors": errors,
            "warnings": warnings,
            "valid": len(errors) == 0,
        }, ensure_ascii=False, indent=2))
    else:
        if warnings:
            print("⚠️ 警告：")
            for w in warnings:
                print(f"  - {w}")
        if errors:
            print("❌ 錯誤：")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print(f"✅ 全部 {len(SCHEMAS)} 個配置檔驗證通過（含跨檔一致性檢查）")

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
