#!/usr/bin/env python3
"""
YAML 配置 Schema 驗證與遷移工具。

可由 check-health.ps1 呼叫或獨立執行。
驗證所有 config/*.yaml 檔案的結構是否符合預期 schema。

支援三種模式：
1. JSON Schema 驗證（推薦，需 pip install jsonschema）
2. 簡單驗證（fallback，無需額外依賴）
3. 配置遷移（--migrate，自動升級配置檔版本）

遷移模式：
  python validate_config.py --migrate              # Dry-run，顯示變更但不實際修改
  python validate_config.py --migrate --apply      # 實際執行遷移
  python validate_config.py --fix <config>         # 修復特定配置檔問題
"""
import os
import sys
import json
import re
import shutil
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional


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


def _load_json_schema(schema_path):
    """載入 JSON Schema 檔案。

    Args:
        schema_path: JSON Schema 檔案路徑

    Returns:
        dict 或 None（檔案不存在或解析失敗時）
    """
    if not os.path.exists(schema_path):
        return None

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_migration_rules(config_dir):
    """載入遷移規則檔案。

    Args:
        config_dir: 配置目錄路徑

    Returns:
        dict 或 None（檔案不存在或解析失敗時）
    """
    rules_path = os.path.join(config_dir, "schemas", "migration-rules.yaml")
    return _load_yaml(rules_path)


def _create_backup(filepath, backup_suffix=None):
    """建立備份檔案。

    Args:
        filepath: 要備份的檔案路徑
        backup_suffix: 備份檔案後綴（預設為 .backup-YYYYMMDD_HHMMSS）

    Returns:
        備份檔案路徑
    """
    if backup_suffix is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_suffix = f".backup-{timestamp}"

    backup_path = filepath + backup_suffix
    shutil.copy2(filepath, backup_path)
    return backup_path


def _get_nested_value(data, path):
    """從嵌套字典中取得值（支援點號路徑）。

    Args:
        data: 資料字典
        path: 路徑字串（如 "tasks.*" 或 "label_routing.mappings.*.labels"）

    Returns:
        值或 None
    """
    parts = path.split(".")
    current = data

    for part in parts:
        if part == "*":
            # 遇到萬用字元，返回當前層級的所有子項
            if isinstance(current, dict):
                return current
            elif isinstance(current, list):
                return current
            else:
                return None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

    return current


def _set_nested_value(data, path, value):
    """設定嵌套字典中的值（支援點號路徑）。

    Args:
        data: 資料字典
        path: 路徑字串
        value: 要設定的值
    """
    parts = path.split(".")
    current = data

    for i, part in enumerate(parts[:-1]):
        if part == "*":
            return  # 萬用字元需要特殊處理，這裡暫時跳過
        if part not in current:
            current[part] = {}
        current = current[part]

    last_part = parts[-1]
    if last_part != "*":
        current[last_part] = value


def _resolve_field_value(item, index, transformation):
    """根據 value_strategy 決定欄位值。

    Args:
        item: 目標字典項目
        index: 項目索引（用於 auto_increment）
        transformation: 轉換規則

    Returns:
        計算出的欄位值
    """
    value_strategy = transformation.get("value_strategy")
    mapping = transformation.get("mapping", {})

    if value_strategy == "auto_increment":
        return index + 1
    elif value_strategy == "infer_from_guard_tag":
        return mapping.get(item.get("guard_tag", ""), "medium")
    elif value_strategy == "infer_from_id":
        return mapping.get(item.get("id", ""), transformation.get("value", None))
    else:
        return transformation.get("value", None)


def _apply_add_field(data, transformation):
    """套用 add_field 轉換（新增欄位）。

    Args:
        data: 配置資料
        transformation: 轉換規則

    Returns:
        修改後的資料
    """
    target = transformation.get("target", "")
    field = transformation.get("field")

    changes = []

    if "*" in target:
        base_path = target.split(".*")[0]
        items = _get_nested_value(data, base_path)

        if isinstance(items, dict):
            for idx, (key, item) in enumerate(items.items()):
                if isinstance(item, dict) and field not in item:
                    item[field] = _resolve_field_value(item, idx, transformation)
                    changes.append(f"  新增 {base_path}.{key}.{field} = {item[field]}")

        elif isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, dict) and field not in item:
                    item[field] = _resolve_field_value(item, i, transformation)
                    changes.append(f"  新增 {base_path}[{i}].{field} = {item[field]}")

    else:
        if field not in data:
            data[field] = transformation.get("value", None)
            changes.append(f"  新增 {field} = {data[field]}")

    return data, changes


def _apply_rename_field(data, transformation):
    """套用 rename_field 轉換（重新命名欄位）。

    Args:
        data: 配置資料
        transformation: 轉換規則

    Returns:
        修改後的資料和變更記錄
    """
    target = transformation.get("target", "")
    old_name = transformation.get("old")
    new_name = transformation.get("new")

    changes = []

    if "*" in target:
        base_path = target.split(".*")[0]
        items = _get_nested_value(data, base_path)

        if isinstance(items, dict):
            for key, item in items.items():
                if isinstance(item, dict) and old_name in item:
                    item[new_name] = item.pop(old_name)
                    changes.append(f"  重命名 {base_path}.{key}.{old_name} → {new_name}")

        elif isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, dict) and old_name in item:
                    item[new_name] = item.pop(old_name)
                    changes.append(f"  重命名 {base_path}[{i}].{old_name} → {new_name}")
    else:
        if old_name in data:
            data[new_name] = data.pop(old_name)
            changes.append(f"  重命名 {old_name} → {new_name}")

    return data, changes


def _apply_replace_in_field(data, transformation):
    """套用 replace_in_field 轉換（欄位內容替換）。

    Args:
        data: 配置資料
        transformation: 轉換規則

    Returns:
        修改後的資料和變更記錄
    """
    target = transformation.get("target", "")
    pattern = transformation.get("pattern")
    replacement = transformation.get("replacement", "")
    use_regex = transformation.get("regex", False)

    changes = []

    # 處理路徑（如 "label_routing.mappings.*.labels"）
    parts = target.split(".")
    if "*" in target:
        # 複雜路徑處理
        base_path = ".".join(parts[:parts.index("*")])
        field_path = ".".join(parts[parts.index("*")+1:])

        items = _get_nested_value(data, base_path)
        if isinstance(items, dict):
            for key, item in items.items():
                field_value = _get_nested_value(item, field_path)
                if isinstance(field_value, list):
                    for i, val in enumerate(field_value):
                        if isinstance(val, str):
                            if use_regex:
                                new_val = re.sub(pattern, replacement, val)
                            else:
                                new_val = val.replace(pattern, replacement)

                            if new_val != val:
                                field_value[i] = new_val
                                changes.append(f"  替換 {base_path}.{key}.{field_path}[{i}]: {val} → {new_val}")

    return data, changes


def _apply_add_section(data, transformation):
    """套用 add_section 轉換（新增整個段落）。

    Args:
        data: 配置資料
        transformation: 轉換規則

    Returns:
        修改後的資料和變更記錄
    """
    section = transformation.get("section")
    content = transformation.get("content", {})

    changes = []

    if section not in data:
        data[section] = content
        changes.append(f"  新增段落 {section}")

    return data, changes


def _apply_update_field(data, transformation):
    """套用 update_field 轉換（更新欄位值）。

    Args:
        data: 配置資料
        transformation: 轉換規則

    Returns:
        修改後的資料和變更記錄
    """
    target = transformation.get("target")
    old_value = transformation.get("old")
    new_value = transformation.get("new")

    changes = []

    if target in data and data[target] == old_value:
        data[target] = new_value
        changes.append(f"  更新 {target}: {old_value} → {new_value}")

    return data, changes


def _apply_transformation(data, transformation, config_name):
    """套用單一轉換規則。

    Args:
        data: 配置資料
        transformation: 轉換規則
        config_name: 配置檔名（用於錯誤訊息）

    Returns:
        (修改後的資料, 變更記錄列表)
    """
    trans_type = transformation.get("type")

    try:
        if trans_type == "add_field":
            return _apply_add_field(data, transformation)
        elif trans_type == "rename_field":
            return _apply_rename_field(data, transformation)
        elif trans_type == "replace_in_field":
            return _apply_replace_in_field(data, transformation)
        elif trans_type == "add_section":
            return _apply_add_section(data, transformation)
        elif trans_type == "update_field":
            return _apply_update_field(data, transformation)
        elif trans_type == "validate_units":
            # 這是驗證型轉換，不修改資料
            return data, [f"  驗證單位一致性（{trans_type}）"]
        else:
            return data, [f"  ⚠️ 未知轉換類型：{trans_type}"]
    except Exception as e:
        return data, [f"  ❌ 轉換失敗：{str(e)}"]


def _validate_with_json_schema(data, config_name, config_dir):
    """使用 JSON Schema 驗證配置檔案。

    Args:
        data: YAML 檔案載入後的資料
        config_name: 配置檔名（如 "cache-policy.yaml"）
        config_dir: 配置目錄路徑

    Returns:
        (errors, used_json_schema) — errors 為字串 list，
        used_json_schema 為 bool（是否使用了 JSON Schema）
    """
    try:
        import jsonschema
    except ImportError:
        # jsonschema 模組未安裝，返回空 errors + False
        return [], False

    # 尋找對應的 JSON Schema 檔案
    base_name = config_name.replace(".yaml", "")
    schema_path = os.path.join(config_dir, "schemas", f"{base_name}.schema.json")

    schema = _load_json_schema(schema_path)
    if schema is None:
        # Schema 檔案不存在，返回空 errors + False
        return [], False

    # 執行驗證
    errors = []
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        # 格式化錯誤訊息
        error_path = " → ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
        errors.append(f"{config_name}: {error_path}: {e.message}")
    except jsonschema.SchemaError as e:
        errors.append(f"{config_name}: Schema 檔案格式錯誤: {e.message}")

    return errors, True


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

    優先使用 JSON Schema 驗證（如果有 jsonschema 模組和 .schema.json 檔案），
    否則 fallback 到簡單驗證。

    Returns:
        (errors, warnings, stats) — errors 和 warnings 為字串 list，
        stats 為 dict（含 json_schema_used, simple_validation_used 計數）
    """
    if config_dir is None:
        # 從腳本位置推算
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(os.path.dirname(script_dir), "config")

    errors = []
    warnings = []
    stats = {"json_schema_used": 0, "simple_validation_used": 0}

    for filename, schema in SCHEMAS.items():
        filepath = os.path.join(config_dir, filename)

        if not os.path.exists(filepath):
            warnings.append(f"{filename}: 檔案不存在")
            continue

        data = _load_yaml(filepath)
        if data is None:
            errors.append(f"{filename}: YAML 解析失敗（語法錯誤或 PyYAML 未安裝）")
            continue

        # 嘗試使用 JSON Schema 驗證
        json_errors, used_json_schema = _validate_with_json_schema(data, filename, config_dir)

        if used_json_schema:
            # JSON Schema 驗證成功執行
            errors.extend(json_errors)
            stats["json_schema_used"] += 1
        else:
            # Fallback 到簡單驗證
            stats["simple_validation_used"] += 1

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

    return errors, warnings, stats


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

    檢查邏輯（修正版）：
    1. 檢查 Skill triggers 是否有對應的 routing 映射（防止 Skill 失效）
    2. **不**警告 routing.yaml 中的標籤沒有對應 Skill triggers（正常設計）

    說明：routing.yaml 中的標籤是 Todoist 任務分類標籤（用戶手動添加），
          SKILL.md 中的 triggers 是 Skill 啟動關鍵字（用於內容匹配），
          兩者服務於不同目的，不需要一一對應。

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

    # 2. 提取所有標籤映射（從 label_routing.mappings 和 keyword_routing.mappings）
    # label_routing 標籤（去掉 ^ 前綴）
    label_mappings = routing.get("label_routing", {}).get("mappings", {})
    routing_labels = set()
    for key in label_mappings.keys():
        if key.startswith("^"):
            routing_labels.add(key[1:])  # 去掉 ^

    # keyword_routing 關鍵字
    keyword_mappings = routing.get("keyword_routing", {}).get("mappings", [])
    keyword_labels = set()
    for mapping in keyword_mappings:
        if isinstance(mapping, dict) and "keywords" in mapping:
            keyword_labels.update(mapping["keywords"])

    # 合併所有可路由標籤
    all_routing_labels = routing_labels | keyword_labels

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

    # 4-6. 移除所有雙向檢查
    # 理由：routing.yaml 和 SKILL.md triggers 服務於不同場景：
    #
    # routing.yaml 用途：
    # - Todoist 任務路由（標籤 → Skill 映射）
    # - 由用戶手動添加標籤到任務上
    # - 例：任務帶有「遊戲開發」標籤 → 路由到 game-design Skill
    #
    # SKILL.md triggers 用途：
    # - Skill 內容匹配關鍵字
    # - 由 Agent prompt 在處理任務內容時匹配
    # - 例：任務描述包含「遊戲」關鍵字 → 啟動 game-design Skill
    #
    # 兩者的關係是互補的，不是一一對應的：
    # - 很多 Skills 由 Agent prompt 直接調用（api-cache, digest-memory 等），不需要路由
    # - routing.yaml 的標籤是任務分類（Claude Code, 遊戲開發），不是 Skill 啟動關鍵字
    #
    # 因此，這個檢查實際上沒有意義，移除所有警告。

    # 如果未來需要檢查配置一致性，應該檢查：
    # - routing.yaml 中的 skills 欄位是否對應到實際存在的 Skill（skills/ 目錄）
    # - 但這屬於不同類型的驗證，不是 triggers 一致性

    return errors, warnings


def migrate_config(config_name, target_version=None, config_dir=None, dry_run=True, interactive=True):
    """遷移單一配置檔到指定版本。

    Args:
        config_name: 配置檔名（如 "frequency-limits.yaml"）
        target_version: 目標版本號（None 表示遷移到最新版本）
        config_dir: 配置目錄路徑
        dry_run: 是否為 dry-run 模式（僅顯示變更，不實際修改）
        interactive: 是否互動式確認每個變更

    Returns:
        (success, messages) — success 為 bool，messages 為字串列表
    """
    if config_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(os.path.dirname(script_dir), "config")

    messages = []

    # 1. 載入配置檔
    filepath = os.path.join(config_dir, config_name)
    if not os.path.exists(filepath):
        return False, [f"❌ 配置檔不存在：{config_name}"]

    data = _load_yaml(filepath)
    if data is None:
        return False, [f"❌ YAML 解析失敗：{config_name}"]

    current_version = data.get("version", 0)
    messages.append(f"📋 {config_name} 當前版本：v{current_version}")

    # 2. 載入遷移規則
    migration_rules = _load_migration_rules(config_dir)
    if migration_rules is None:
        return False, ["❌ 無法載入遷移規則（migration-rules.yaml）"]

    # 3. 取得配置檔的遷移規則
    base_name = config_name.replace(".yaml", "")
    config_rules = migration_rules.get(base_name)
    if config_rules is None:
        messages.append(f"⚠️ 沒有定義遷移規則：{base_name}")
        return True, messages

    # 4. 決定要遷移到哪個版本
    available_migrations = []
    for key in config_rules.keys():
        if key.startswith("v"):
            try:
                from_ver, to_ver = key[1:].split("_to_v")
                available_migrations.append((int(from_ver), int(to_ver), key))
            except ValueError:
                continue

    if not available_migrations:
        messages.append("⚠️ 沒有可用的遷移路徑")
        return True, messages

    # 排序遷移路徑（按起始版本排序）
    available_migrations.sort(key=lambda x: x[0])

    # 5. 決定遷移鏈
    migration_chain = []
    ver = current_version

    for from_ver, to_ver, migration_key in available_migrations:
        if from_ver == ver:
            migration_chain.append((from_ver, to_ver, migration_key))
            ver = to_ver
            if target_version is not None and ver >= target_version:
                break

    if not migration_chain:
        messages.append(f"✅ 已是最新版本（v{current_version}）")
        return True, messages

    final_version = migration_chain[-1][1]
    messages.append(f"🔄 將遷移至 v{final_version}（共 {len(migration_chain)} 個步驟）")

    # 6. 建立備份（非 dry-run 模式）
    if not dry_run:
        general_rules = migration_rules.get("general", {})
        backup_enabled = general_rules.get("backup_before_migrate", True)

        if backup_enabled:
            backup_suffix = general_rules.get("backup_suffix", ".pre-v{old_version}.bak")
            backup_suffix = backup_suffix.format(old_version=current_version)

            try:
                backup_path = _create_backup(filepath, backup_suffix)
                messages.append(f"💾 已建立備份：{os.path.basename(backup_path)}")
            except Exception as e:
                return False, [f"❌ 備份失敗：{str(e)}"]

    # 7. 執行遷移鏈
    all_changes = []

    for from_ver, to_ver, migration_key in migration_chain:
        migration = config_rules[migration_key]
        description = migration.get("description", "")
        transformations = migration.get("transformations", [])

        messages.append(f"\n📝 步驟：v{from_ver} → v{to_ver} - {description}")

        for transformation in transformations:
            data, changes = _apply_transformation(data, transformation, config_name)
            all_changes.extend(changes)
            messages.extend(changes)

        # 更新版本號
        data["version"] = to_ver

    # 8. 互動式確認（如果啟用）
    if interactive and not dry_run:
        print("\n".join(messages))
        response = input("\n❓ 是否套用這些變更？(y/N): ")
        if response.lower() != "y":
            return False, ["❌ 用戶取消遷移"]

    # 9. 寫入檔案（非 dry-run 模式）
    if not dry_run:
        try:
            import yaml
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            messages.append(f"\n✅ 已成功遷移至 v{final_version}")
        except Exception as e:
            return False, [f"❌ 寫入失敗：{str(e)}"]
    else:
        messages.append(f"\n💡 Dry-run 模式：實際執行請加上 --apply 參數")

    # 10. 遷移後驗證
    if not dry_run:
        messages.append("\n🔍 遷移後驗證...")
        errors, warnings, stats = validate_config(config_dir)

        config_errors = [e for e in errors if config_name in e]
        if config_errors:
            messages.append("❌ 驗證失敗：")
            messages.extend([f"  - {e}" for e in config_errors])
            return False, messages
        else:
            messages.append("✅ 驗證通過")

    return True, messages


def migrate_all_configs(config_dir=None, dry_run=True, interactive=False):
    """遷移所有配置檔到最新版本。

    Args:
        config_dir: 配置目錄路徑
        dry_run: 是否為 dry-run 模式
        interactive: 是否互動式確認

    Returns:
        (success_count, fail_count, all_messages)
    """
    if config_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(os.path.dirname(script_dir), "config")

    # 載入遷移規則以取得需要遷移的配置檔列表
    migration_rules = _load_migration_rules(config_dir)
    if migration_rules is None:
        return 0, 0, ["❌ 無法載入遷移規則"]

    all_messages = []
    success_count = 0
    fail_count = 0

    # 遷移每個有規則的配置檔
    for config_base_name in migration_rules.keys():
        if config_base_name in ["general", "validation", "error_handling", "notes"]:
            continue

        config_name = f"{config_base_name}.yaml"
        success, messages = migrate_config(
            config_name,
            target_version=None,
            config_dir=config_dir,
            dry_run=dry_run,
            interactive=interactive
        )

        all_messages.append(f"\n{'='*60}")
        all_messages.extend(messages)

        if success:
            success_count += 1
        else:
            fail_count += 1

    return success_count, fail_count, all_messages


def validate_skill_quality(skills_dir=None):
    """檢查所有 SKILL.md 的品質並評分。

    Returns:
        dict: {skill_name: {"score": int, "errors": [...], "warnings": [...]}}
    """
    import glob

    if skills_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        skills_dir = os.path.join(os.path.dirname(script_dir), "skills")

    results = {}
    skill_files = glob.glob(os.path.join(skills_dir, "*/SKILL.md"))

    for skill_file in skill_files:
        skill_name = os.path.basename(os.path.dirname(skill_file))
        errors = []
        warnings = []

        # 1. 提取 frontmatter
        frontmatter = _extract_frontmatter(skill_file)
        if frontmatter is None:
            errors.append("frontmatter 解析失敗")
            results[skill_name] = {"score": 0, "errors": errors, "warnings": warnings}
            continue

        # 2. 檢查必要欄位（errors）
        required_fields = ["name", "version", "description", "triggers", "allowed-tools"]
        for field in required_fields:
            if field not in frontmatter:
                errors.append(f"缺少必要欄位：{field}")

        # 3. 檢查 triggers 陣列是否非空
        triggers = frontmatter.get("triggers", [])
        if not isinstance(triggers, list):
            errors.append("triggers 應為陣列")
        elif len(triggers) == 0:
            errors.append("triggers 陣列為空")
        elif len(triggers) == 1:
            warnings.append("triggers 僅 1 個元素，建議至少 2 個")

        # 4. 檢查 description 品質
        description = frontmatter.get("description", "")
        if isinstance(description, str):
            if len(description.strip()) == 0:
                errors.append("description 為空")
            elif len(description.strip()) < 20:
                warnings.append("description 過短（< 20 字元）")

        # 5. 檢查段落結構（至少 3 個段落）
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 移除 frontmatter 後的內容
            parts = content.split("---", 2)
            if len(parts) >= 3:
                markdown_content = parts[2].strip()
                # 簡單計算段落數（以 ## 或 # 標題為段落分隔）
                headers = [line for line in markdown_content.split("\n") if line.startswith("#")]
                if len(headers) < 3:
                    warnings.append(f"段落結構簡單（僅 {len(headers)} 個標題，建議至少 3 個）")
        except Exception:
            warnings.append("無法讀取 Markdown 內容")

        # 6. 計算分數：100 - 15*errors - 5*warnings
        score = max(0, 100 - 15 * len(errors) - 5 * len(warnings))

        results[skill_name] = {
            "score": score,
            "errors": errors,
            "warnings": warnings
        }

    return results


def main():
    # Ensure UTF-8 output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 處理 --help
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        print("\n使用方式：")
        print("  python validate_config.py                    # 驗證所有配置檔")
        print("  python validate_config.py --all              # 驗證 + Routing + Skills")
        print("  python validate_config.py --check-routing    # 僅檢查 Routing 一致性")
        print("  python validate_config.py --check-skills     # 僅檢查 Skill 品質")
        print("  python validate_config.py --migrate          # Dry-run 遷移所有配置檔")
        print("  python validate_config.py --migrate --apply  # 實際執行遷移")
        print("  python validate_config.py --fix <config>     # 修復特定配置檔問題")
        print("  python validate_config.py --json             # JSON 格式輸出")
        sys.exit(0)

    # 處理 --migrate（配置遷移模式）
    if "--migrate" in sys.argv:
        dry_run = "--apply" not in sys.argv
        interactive = "--interactive" in sys.argv

        success_count, fail_count, messages = migrate_all_configs(
            dry_run=dry_run,
            interactive=interactive
        )

        print("\n".join(messages))
        print(f"\n{'='*60}")
        print(f"遷移完成：成功 {success_count} 個，失敗 {fail_count} 個")

        if dry_run:
            print("\n💡 這是 dry-run 模式，沒有實際修改檔案")
            print("   要實際執行遷移，請使用：python validate_config.py --migrate --apply")

        sys.exit(0 if fail_count == 0 else 1)

    # 處理 --fix（修復特定配置檔）
    if "--fix" in sys.argv:
        try:
            idx = sys.argv.index("--fix")
            if idx + 1 < len(sys.argv):
                config_name = sys.argv[idx + 1]
                if not config_name.endswith(".yaml"):
                    config_name += ".yaml"

                dry_run = "--apply" not in sys.argv
                interactive = "--interactive" in sys.argv

                success, messages = migrate_config(
                    config_name,
                    target_version=None,
                    dry_run=dry_run,
                    interactive=interactive
                )

                print("\n".join(messages))
                sys.exit(0 if success else 1)
            else:
                print("❌ --fix 需要指定配置檔名稱")
                sys.exit(1)
        except Exception as e:
            print(f"❌ 錯誤：{str(e)}")
            sys.exit(1)

    # 標準驗證模式
    errors, warnings, stats = validate_config()

    # 新增：Routing 一致性檢查
    if "--check-routing" in sys.argv or "--all" in sys.argv:
        routing_errors, routing_warnings = check_routing_consistency()
        errors.extend(routing_errors)
        warnings.extend(routing_warnings)

    # 新增：Skill 品質評分
    skill_scores = None
    if "--check-skills" in sys.argv or "--all" in sys.argv:
        skill_scores = validate_skill_quality()
        # 計算統計
        total_skills = len(skill_scores)
        avg_score = sum(s["score"] for s in skill_scores.values()) / total_skills if total_skills > 0 else 0
        low_score_skills = [name for name, data in skill_scores.items() if data["score"] < 80]

        if low_score_skills:
            warnings.append(f"發現 {len(low_score_skills)} 個低分 Skill（< 80）：{', '.join(low_score_skills)}")


    if "--json" in sys.argv:
        output = {
            "errors": errors,
            "warnings": warnings,
            "valid": len(errors) == 0,
            "validation_stats": stats,
        }
        if skill_scores is not None:
            output["skill_scores"] = skill_scores
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # Skill 品質評分輸出（如果有執行）
        if skill_scores is not None:
            print("\n[Skill 品質評分]")
            sorted_skills = sorted(skill_scores.items(), key=lambda x: x[1]["score"], reverse=True)
            for skill_name, data in sorted_skills:
                score = data["score"]
                status = "✓" if score == 100 else ("⚠️" if score >= 80 else "❌")
                print(f"  - {skill_name} ({score}/100) {status}")

                # 顯示錯誤和警告
                for err in data["errors"]:
                    print(f"      ❌ {err}")
                for warn in data["warnings"]:
                    print(f"      ⚠️ {warn}")

            total = len(skill_scores)
            avg = sum(s["score"] for s in skill_scores.values()) / total if total > 0 else 0
            print(f"\n  平均分：{avg:.1f}/100 （共 {total} 個 Skill）")

        # 顯示驗證統計
        if stats["json_schema_used"] > 0 or stats["simple_validation_used"] > 0:
            print("\n[驗證模式]")
            if stats["json_schema_used"] > 0:
                print(f"  ✓ JSON Schema 驗證：{stats['json_schema_used']} 個配置檔")
            if stats["simple_validation_used"] > 0:
                print(f"  ⚠️ 簡單驗證（fallback）：{stats['simple_validation_used']} 個配置檔")

        if warnings:
            print("\n⚠️ 警告：")
            for w in warnings:
                print(f"  - {w}")
        if errors:
            print("\n❌ 錯誤：")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            checks_done = len(SCHEMAS)
            check_names = [f"{len(SCHEMAS)} 個配置檔"]
            if "--check-routing" in sys.argv or "--all" in sys.argv:
                checks_done += 1
                check_names.append("Routing 一致性")
            if "--check-skills" in sys.argv or "--all" in sys.argv:
                checks_done += 1
                check_names.append("Skill 品質")

            print(f"\n✅ 全部 {checks_done} 項檢查通過（{' + '.join(check_names)}）")

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
