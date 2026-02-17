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
    "pipeline.yaml": {
        "required_keys": ["version", "init", "steps", "finalize"],
        "list_fields": {
            "steps": ["id", "name"],
        },
    },
    "topic-rotation.yaml": {
        "required_keys": ["version", "strategy", "habits_topics", "learning_topics"],
    },
    "health-scoring.yaml": {
        "required_keys": ["version", "ranges", "dimensions"],
    },
    "audit-scoring.yaml": {
        "required_keys": ["version", "weight_profiles", "grade_thresholds", "dimensions"],
    },
    "benchmark.yaml": {
        "required_keys": ["version", "metrics"],
        "list_fields": {
            "metrics": ["name", "target", "weight"],
        },
    },
    "timeouts.yaml": {
        "required_keys": ["version"],
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

    return errors, warnings


def _extract_frontmatter(filepath):
    """從 Markdown 檔案提取 YAML frontmatter。

    Returns:
        dict 或 None（解析失敗時）
    """
    try:
        import yaml
    except ImportError:
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 檢查是否以 --- 開頭
        if not content.startswith("---"):
            return None

        # 提取兩個 --- 之間的內容
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_yaml = parts[1]
        return yaml.safe_load(frontmatter_yaml)
    except Exception:
        return None


def check_routing_consistency(skills_dir=None, config_dir=None):
    """檢查 SKILL.md triggers 與 routing.yaml 的一致性。

    Returns:
        (errors, warnings) — 各為字串 list。
    """
    import glob

    if skills_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        skills_dir = os.path.join(os.path.dirname(script_dir), "skills")

    if config_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(os.path.dirname(script_dir), "config")

    errors = []
    warnings = []

    # 1. 載入 routing.yaml
    routing_path = os.path.join(config_dir, "routing.yaml")
    routing = _load_yaml(routing_path)
    if routing is None:
        errors.append("routing.yaml 載入失敗，無法檢查一致性")
        return errors, warnings

    # 2. 提取所有標籤映射（從 label_routing.mappings）
    mappings = routing.get("label_routing", {}).get("mappings", {})
    # 移除 ^ 前綴，得到純標籤列表
    routing_labels = set()
    for key in mappings.keys():
        if key.startswith("^"):
            routing_labels.add(key[1:])  # 去掉 ^

    # 3. 掃描所有 SKILL.md，提取 triggers
    skill_triggers = {}  # {skill_name: [triggers]}
    skill_files = glob.glob(os.path.join(skills_dir, "*/SKILL.md"))

    for skill_file in skill_files:
        frontmatter = _extract_frontmatter(skill_file)
        if frontmatter is None:
            warnings.append(f"{os.path.basename(os.path.dirname(skill_file))}/SKILL.md: frontmatter 解析失敗")
            continue

        skill_name = frontmatter.get("name", "unknown")
        triggers = frontmatter.get("triggers", [])

        if not isinstance(triggers, list):
            warnings.append(f"{skill_name}: triggers 應為陣列")
            continue

        skill_triggers[skill_name] = triggers

    # 4. 檢查：每個 trigger 是否在 routing.yaml 中有對應映射
    missing_in_routing = []
    for skill_name, triggers in skill_triggers.items():
        for trigger in triggers:
            if trigger not in routing_labels:
                missing_in_routing.append(f"{skill_name} 的 trigger '{trigger}' 未在 routing.yaml 中定義")

    # 5. 反向檢查：routing.yaml 中的標籤是否被任何 Skill 宣稱
    all_triggers = set()
    for triggers in skill_triggers.values():
        all_triggers.update(triggers)

    orphaned_labels = []
    for label in routing_labels:
        if label not in all_triggers:
            orphaned_labels.append(f"routing.yaml 中的標籤 '{label}' 未被任何 Skill 宣稱")

    # 6. 分類結果
    if missing_in_routing:
        warnings.extend(missing_in_routing)

    if orphaned_labels:
        warnings.extend(orphaned_labels)

    return errors, warnings


def main():
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    errors, warnings = validate_config()

    # 新增：Routing 一致性檢查
    if "--check-routing" in sys.argv or "--all" in sys.argv:
        routing_errors, routing_warnings = check_routing_consistency()
        errors.extend(routing_errors)
        warnings.extend(routing_warnings)

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
            checks_done = len(SCHEMAS)
            if "--check-routing" in sys.argv or "--all" in sys.argv:
                checks_done += 1
                print(f"✅ 全部 {checks_done} 項檢查通過（{len(SCHEMAS)} 個配置檔 + Routing 一致性）")
            else:
                print(f"✅ 全部 {checks_done} 個配置檔驗證通過")

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
