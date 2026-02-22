#!/usr/bin/env python3
"""
Configuration Migration Engine — 版本化配置遷移。

靈感來源：Gemini CLI 的 storageMigration.ts
為每個 YAML 配置檔提供版本化遷移路徑，確保配置格式升級的可靠性。

Usage:
  python hooks/config_migration.py --check    # 乾跑，顯示待遷移項目
  python hooks/config_migration.py --apply    # 執行遷移
  python hooks/config_migration.py --json     # JSON 輸出
"""
import json
import os
import sys
import shutil
from datetime import datetime


def _load_yaml(filepath):
    """載入 YAML 檔案。"""
    try:
        import yaml
    except ImportError:
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _save_yaml(filepath, data):
    """儲存 YAML 檔案。"""
    try:
        import yaml
    except ImportError:
        return False

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                      sort_keys=False)
        return True
    except Exception:
        return False


def _backup_file(filepath):
    """建立備份檔案。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup.{timestamp}"
    shutil.copy2(filepath, backup_path)
    return backup_path


# ============================================
# Migration Functions
# ============================================

def migrate_hook_rules_v1_to_v2(data):
    """hook-rules.yaml v1 → v2: 加入 presets + priority 欄位。"""
    # 加入 presets
    if "presets" not in data:
        data["presets"] = {
            "strict": {
                "description": "排程執行（預設）— 全部規則啟用",
                "disabled_rules": [],
            },
            "standard": {
                "description": "互動開發 — 放寬非關鍵規則",
                "disabled_rules": ["sensitive-env"],
            },
            "permissive": {
                "description": "除錯模式 — 僅保留 critical 規則",
                "disabled_rules": ["sensitive-env", "force-push"],
            },
        }

    # 為 bash_rules 加入 priority
    priority_map = {
        "nul-redirect": "critical",
        "scheduler-state-write": "critical",
        "destructive-delete": "critical",
        "exfiltration": "critical",
        "force-push": "high",
        "sensitive-env": "medium",
    }
    for section in ["bash_rules", "write_rules", "read_rules"]:
        rules = data.get(section, [])
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict) and "priority" not in rule:
                    rule_id = rule.get("id", "")
                    rule["priority"] = priority_map.get(rule_id, "high")

    data["version"] = 2
    return data


def migrate_timeouts_v1_to_v2(data):
    """timeouts.yaml v1 → v2: 加入 loop_detection 區段。"""
    if "loop_detection" not in data:
        data["loop_detection"] = {
            "tool_hash_threshold": 5,
            "tool_hash_window": 20,
            "content_threshold": 3,
            "content_window": 10,
            "max_turns": {
                "digest": 80,
                "todoist": 150,
                "research": 100,
                "audit": 120,
                "default": 120,
            },
        }

    data["version"] = 2
    return data


def migrate_cache_policy_v1_to_v2(data):
    """cache-policy.yaml v1 → v2: 加入 circuit_breaker 區段。"""
    if "circuit_breaker" not in data:
        data["circuit_breaker"] = {
            "failure_threshold": 3,
            "cooldown_minutes": 30,
            "half_open_max_tries": 1,
        }

    data["version"] = 2
    return data


# ============================================
# Migration Registry
# ============================================

MIGRATIONS = {
    "hook-rules.yaml": {
        2: migrate_hook_rules_v1_to_v2,
    },
    "timeouts.yaml": {
        2: migrate_timeouts_v1_to_v2,
    },
    "cache-policy.yaml": {
        2: migrate_cache_policy_v1_to_v2,
    },
}


def get_config_dir():
    """取得 config/ 目錄路徑。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "config")


def check_migrations(config_dir=None):
    """檢查所有待進行的遷移。

    Returns:
        list of dict: [{filename, current_version, target_version, migration_count}]
    """
    if config_dir is None:
        config_dir = get_config_dir()

    pending = []
    for filename, version_migrations in MIGRATIONS.items():
        filepath = os.path.join(config_dir, filename)
        if not os.path.exists(filepath):
            continue

        data = _load_yaml(filepath)
        if data is None:
            continue

        current_version = data.get("version", 1)
        target_versions = sorted(v for v in version_migrations.keys()
                                 if v > current_version)

        if target_versions:
            pending.append({
                "filename": filename,
                "current_version": current_version,
                "target_version": target_versions[-1],
                "migration_count": len(target_versions),
            })

    return pending


def apply_migrations(config_dir=None, dry_run=False):
    """執行所有待進行的遷移。

    Returns:
        list of dict: [{filename, from_version, to_version, status, backup_path}]
    """
    if config_dir is None:
        config_dir = get_config_dir()

    results = []
    for filename, version_migrations in MIGRATIONS.items():
        filepath = os.path.join(config_dir, filename)
        if not os.path.exists(filepath):
            continue

        data = _load_yaml(filepath)
        if data is None:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "YAML parse failed",
            })
            continue

        current_version = data.get("version", 1)
        target_versions = sorted(v for v in version_migrations.keys()
                                 if v > current_version)

        if not target_versions:
            continue

        from_version = current_version
        backup_path = None

        for target_version in target_versions:
            migrate_fn = version_migrations[target_version]

            if dry_run:
                results.append({
                    "filename": filename,
                    "from_version": from_version,
                    "to_version": target_version,
                    "status": "pending",
                })
                continue

            # 建立備份（只在第一次遷移時）
            if backup_path is None:
                backup_path = _backup_file(filepath)

            try:
                data = migrate_fn(data)
            except Exception as e:
                results.append({
                    "filename": filename,
                    "from_version": from_version,
                    "to_version": target_version,
                    "status": "error",
                    "error": str(e),
                    "backup_path": backup_path,
                })
                break

        if not dry_run and target_versions:
            if _save_yaml(filepath, data):
                results.append({
                    "filename": filename,
                    "from_version": from_version,
                    "to_version": target_versions[-1],
                    "status": "migrated",
                    "backup_path": backup_path,
                })
            else:
                results.append({
                    "filename": filename,
                    "from_version": from_version,
                    "to_version": target_versions[-1],
                    "status": "error",
                    "error": "YAML save failed",
                    "backup_path": backup_path,
                })

    return results


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    dry_run = "--check" in sys.argv
    do_apply = "--apply" in sys.argv
    json_output = "--json" in sys.argv

    if not dry_run and not do_apply:
        print("Usage:")
        print("  python hooks/config_migration.py --check    # 檢查待遷移項目")
        print("  python hooks/config_migration.py --apply    # 執行遷移")
        print("  python hooks/config_migration.py --json     # JSON 輸出")
        sys.exit(0)

    if dry_run:
        pending = check_migrations()
        if json_output:
            print(json.dumps(pending, indent=2, ensure_ascii=False))
        elif not pending:
            print("✅ 所有配置檔版本已是最新")
        else:
            print(f"📋 待遷移配置檔: {len(pending)} 個")
            for item in pending:
                print(f"  - {item['filename']}: v{item['current_version']} → v{item['target_version']} ({item['migration_count']} 步)")
        sys.exit(0)

    if do_apply:
        results = apply_migrations(dry_run=False)
        if json_output:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            for r in results:
                status = r["status"]
                if status == "migrated":
                    print(f"  ✅ {r['filename']}: v{r['from_version']} → v{r['to_version']} (備份: {r.get('backup_path', 'N/A')})")
                elif status == "error":
                    print(f"  ❌ {r['filename']}: {r.get('error', 'unknown error')}")
            if not results:
                print("✅ 無待遷移項目")


if __name__ == "__main__":
    main()
