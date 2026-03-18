---
name: skill-registry-sync
version: "0.5.0"
description: |
  Machine-readable Skill Registry 同步器。掃描所有 skills/*/SKILL.md 的 frontmatter，
  生成結構化 JSON registry（context/skill-registry.json），提供 O(1) 觸發詞查找、
  依賴圖驗證、版本追蹤與一致性檢查。取代人工維護 SKILL_INDEX.md 的手動比對流程。
  Use when: Skill 路由優化、觸發詞衝突偵測、依賴圖驗證、SKILL_INDEX.md 一致性檢查、
  新增 Skill 後的索引同步、cross-agent Skill discovery。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "skill-registry-sync"
  - "Skill 索引同步"
  - "Skill registry"
  - "觸發詞衝突"
  - "依賴圖驗證"
  - "Skill manifest"
  - "Skill 一致性"
depends-on:
  - knowledge-query
---

# Skill Registry Sync — Machine-readable Skill 索引同步器

## 設計哲學

SKILL_INDEX.md 是人類可讀的 Markdown 索引，適合快速瀏覽但無法程式化查詢。
本 Skill 生成 `context/skill-registry.json`——一個 machine-readable 的結構化索引，
支援 O(1) 觸發詞查找、依賴圖驗證、觸發詞衝突偵測與版本追蹤。

**核心價值**：
- skill-forge 步驟 3 去重確認可直接讀取 registry，無需 Explore 子 Agent 掃描全部 SKILL.md
- 路由決策可程式化比對觸發詞，取代文字搜尋
- 新增 Skill 後自動偵測觸發詞衝突與依賴缺失

---

## 步驟 0：前置檢查

1. 確認 `skills/` 目錄存在且含子目錄
2. 讀取 `templates/shared/preamble.md`（遵守 Skill-First 規則）

---

## 步驟 1：掃描所有 SKILL.md frontmatter

使用 Python 腳本掃描 `skills/*/SKILL.md`，解析 YAML frontmatter：

```bash
uv run python -X utf8 -c "
import yaml, json, glob, os, sys
from datetime import datetime

skills = []
errors = []

for path in sorted(glob.glob('skills/*/SKILL.md')):
    dirname = os.path.basename(os.path.dirname(path))
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
        parts = content.split('---')
        if len(parts) < 3:
            errors.append({'skill': dirname, 'error': 'no frontmatter'})
            continue
        fm = yaml.safe_load(parts[1])
        if not fm or not isinstance(fm, dict):
            errors.append({'skill': dirname, 'error': 'invalid frontmatter'})
            continue

        skills.append({
            'name': fm.get('name', dirname),
            'dir': dirname,
            'version': fm.get('version', 'unknown'),
            'description_summary': (fm.get('description', '') or '')[:120].strip(),
            'triggers': fm.get('triggers', []),
            'depends_on': fm.get('depends-on', []),
            'allowed_tools': fm.get('allowed-tools', []),
            'cache_ttl': fm.get('cache-ttl', 'N/A'),
            'path': path.replace(os.sep, '/')
        })
    except Exception as e:
        errors.append({'skill': dirname, 'error': str(e)[:100]})

print(json.dumps({'count': len(skills), 'errors': len(errors), 'skills': skills, 'parse_errors': errors}, ensure_ascii=False, indent=2))
" > temp_registry_scan.json
```

**失敗處理**：若 Python 腳本失敗（exit code != 0），記錄錯誤並跳至步驟 6（降級輸出）。

---

## 步驟 2：建立觸發詞索引（Trigger Index）

從掃描結果建立反向索引，每個觸發詞映射到對應的 Skill 名稱：

```bash
uv run python -X utf8 -c "
import json

with open('temp_registry_scan.json', encoding='utf-8') as f:
    data = json.load(f)

trigger_index = {}
conflicts = []

for skill in data['skills']:
    for trigger in skill['triggers']:
        key = trigger.strip().lower()
        if key in trigger_index:
            conflicts.append({
                'trigger': trigger,
                'skills': [trigger_index[key], skill['name']]
            })
            # 保留第一個，記錄衝突
        else:
            trigger_index[key] = skill['name']

print(json.dumps({
    'total_triggers': len(trigger_index),
    'conflicts': conflicts,
    'conflict_count': len(conflicts)
}, ensure_ascii=False, indent=2))
" > temp_trigger_index.json
```

---

## 步驟 3：建立依賴圖並驗證

驗證所有 `depends-on` 引用的 Skill 是否存在於 registry：

```bash
uv run python -X utf8 -c "
import json

with open('temp_registry_scan.json', encoding='utf-8') as f:
    data = json.load(f)

known = {s['name'] for s in data['skills']}
known_dirs = {s['dir'] for s in data['skills']}
dep_graph = {}
missing_deps = []

for skill in data['skills']:
    deps = skill.get('depends_on', [])
    # 過濾 config 檔案路徑（非 Skill 依賴）
    skill_deps = [d for d in deps if not d.startswith('config/')]
    dep_graph[skill['name']] = skill_deps
    for dep in skill_deps:
        if dep not in known and dep not in known_dirs:
            missing_deps.append({
                'skill': skill['name'],
                'missing_dep': dep
            })

print(json.dumps({
    'dep_graph_size': len(dep_graph),
    'missing_deps': missing_deps,
    'missing_count': len(missing_deps)
}, ensure_ascii=False, indent=2))
" > temp_dep_validation.json
```

---

## 步驟 4：SKILL_INDEX.md 一致性檢查

比對 registry 與 SKILL_INDEX.md，找出不一致：

```bash
uv run python -X utf8 -c "
import json, re

with open('temp_registry_scan.json', encoding='utf-8') as f:
    data = json.load(f)

with open('skills/SKILL_INDEX.md', encoding='utf-8') as f:
    index_content = f.read()

registry_names = {s['name'] for s in data['skills']}
# 從 SKILL_INDEX.md 表格中提取 Skill 名稱（| N | name | ... 格式）
index_names = set()
for line in index_content.split('\n'):
    m = re.match(r'\|\s*\d+\s*\|\s*(\S+)\s*\|', line)
    if m:
        index_names.add(m.group(1))

in_registry_not_index = registry_names - index_names
in_index_not_registry = index_names - registry_names

print(json.dumps({
    'registry_count': len(registry_names),
    'index_count': len(index_names),
    'in_registry_not_index': sorted(in_registry_not_index),
    'in_index_not_registry': sorted(in_index_not_registry),
    'consistent': len(in_registry_not_index) == 0 and len(in_index_not_registry) == 0
}, ensure_ascii=False, indent=2))
" > temp_consistency.json
```

---

## 步驟 5：組裝並寫入 Registry JSON

整合步驟 1-4 的結果，生成最終 registry：

```bash
uv run python -X utf8 -c "
import json
from datetime import datetime

with open('temp_registry_scan.json', encoding='utf-8') as f:
    scan = json.load(f)
with open('temp_trigger_index.json', encoding='utf-8') as f:
    triggers = json.load(f)
with open('temp_dep_validation.json', encoding='utf-8') as f:
    deps = json.load(f)
with open('temp_consistency.json', encoding='utf-8') as f:
    consistency = json.load(f)

registry = {
    'schema_version': 1,
    'generated_at': datetime.now().astimezone().isoformat(),
    'total_skills': scan['count'],
    'skills': {s['name']: {
        'dir': s['dir'],
        'version': s['version'],
        'description_summary': s['description_summary'],
        'triggers': s['triggers'],
        'depends_on': s['depends_on'],
        'allowed_tools': s['allowed_tools'],
        'cache_ttl': s['cache_ttl'],
        'path': s['path']
    } for s in scan['skills']},
    'trigger_index': {k: v for k, v in sorted(triggers.get('_raw', {}).items())} if '_raw' in triggers else {},
    'diagnostics': {
        'trigger_conflicts': triggers['conflicts'],
        'missing_dependencies': deps['missing_deps'],
        'index_consistency': consistency,
        'parse_errors': scan['parse_errors']
    }
}

with open('context/skill-registry.json', 'w', encoding='utf-8') as f:
    json.dump(registry, f, ensure_ascii=False, indent=2)

print(f'REGISTRY_OK: {scan[\"count\"]} skills, {triggers[\"conflict_count\"]} conflicts, {deps[\"missing_count\"]} missing deps')
"
```

清理暫存檔：
```bash
rm -f temp_registry_scan.json temp_trigger_index.json temp_dep_validation.json temp_consistency.json
```

---

## 步驟 6：輸出 Registry 摘要

讀取 `context/skill-registry.json`，輸出摘要：

```
📋 Skill Registry 同步完成
- 總 Skills：{total_skills}
- 觸發詞衝突：{conflict_count}（列出衝突詳情）
- 缺失依賴：{missing_count}（列出缺失詳情）
- SKILL_INDEX.md 一致性：{consistent ? "✅ 一致" : "⚠️ 不一致"}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `skills/` 目錄不存在 | 記錄錯誤，不生成 registry |
| 個別 SKILL.md frontmatter 解析失敗 | 記錄到 `parse_errors`，跳過該 Skill，繼續處理其他 |
| YAML 套件不可用 | 改用 regex 解析 frontmatter（降級精確度） |
| SKILL_INDEX.md 不存在 | 跳過步驟 4 一致性檢查 |

---

## Registry JSON Schema

```json
{
  "schema_version": 1,
  "generated_at": "ISO 8601",
  "total_skills": 46,
  "skills": {
    "<skill-name>": {
      "dir": "skill-dir-name",
      "version": "1.0.0",
      "description_summary": "前 120 字",
      "triggers": ["觸發詞1", "觸發詞2"],
      "depends_on": ["other-skill"],
      "allowed_tools": ["Bash", "Read"],
      "cache_ttl": "60min",
      "path": "skills/xxx/SKILL.md"
    }
  },
  "trigger_index": {
    "觸發詞（小寫）": "skill-name"
  },
  "diagnostics": {
    "trigger_conflicts": [],
    "missing_dependencies": [],
    "index_consistency": {},
    "parse_errors": []
  }
}
```

---

## 使用場景

| 場景 | 如何使用 registry |
|------|-----------------|
| skill-forge 步驟 3 去重 | 直接讀取 `skills` dict，比對 triggers 重疊率 |
| Todoist 路由匹配 | 讀取 `trigger_index`，O(1) 查找觸發詞 |
| 新增 Skill 後驗證 | 檢查 `diagnostics.trigger_conflicts` 與 `missing_dependencies` |
| 系統審查 | 檢查 `diagnostics.index_consistency` |
| cross-agent discovery | 外部 Agent 讀取 registry 取得可用 Skill 清單 |

---

## 注意事項

- `context/skill-registry.json` 是生成檔，不應手動編輯
- 每次執行會完整覆寫 registry（非增量更新）
- frontmatter 解析依賴 PyYAML（已在 pyproject.toml 中）
- 觸發詞索引以小寫正規化，確保大小寫不敏感匹配
- 依賴驗證排除 `config/` 開頭的路徑（配置檔案依賴，非 Skill 依賴）
