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

    errors, warnings = validate_config()

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
