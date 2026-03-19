---
name: hook-registry
version: "0.5.0"
description: |
  宣告式 Hook 規則盤點與 Registry 治理工具。掃描 hooks/*.py 提取所有 guard 規則，
  與 config/hook-rules.yaml 交叉比對，偵測規則漂移（程式碼有但 YAML 沒有）、
  覆蓋缺口（新增 hook 未宣告）與 stage 衝突（同 id 不同 priority），
  生成結構化審計報告與修復建議。
  Use when: Hook 規則盤點、guard 鏈審計、規則漂移偵測、hook 一致性檢查、hook registry 治理。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "hook-registry"
  - "hook 規則盤點"
  - "guard 鏈審計"
  - "hook 規則漂移"
  - "hook 一致性"
  - "hook registry"
  - "hook 治理"
depends-on:
  - system-insight
  - "config/hook-rules.yaml"
---

# Hook Registry — 宣告式 Guard 規則盤點與治理

> **端點來源**：純本地檔案操作，不依賴外部 API。

## 設計哲學

本 Skill 解決 ADR-031 提出的問題：guard 規則分散在多個 hooks 腳本中，
新增或停用規則時需在多支 hook 腳本重複修改，容易造成規則漂移。

**本 Skill 不修改 hooks/*.py**（那是安全邊界內的人工操作），
而是提供**審計與可視化**能力：掃描→比對→偵測→報告→建議。

執行鏈：
```
掃描 hooks/*.py（規則提取）→ 讀取 hook-rules.yaml（宣告 registry）
→ 交叉比對（漂移偵測）→ 覆蓋缺口分析 → stage 衝突檢查
→ 生成審計報告 → 修復建議
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（現有 Skill 認知地圖）

---

## 步驟 1：掃描 hooks/*.py 提取規則清單

使用 Grep 和 Read 工具掃描 `hooks/` 目錄下所有 Python 檔案，
提取以下三類規則定義模式：

### 1a. 靜態正則規則（pattern/patterns 欄位）

```bash
uv run python -X utf8 -c "
import os, re, json

hooks_dir = 'hooks'
rules_found = []

for fname in sorted(os.listdir(hooks_dir)):
    if not fname.endswith('.py'):
        continue
    fpath = os.path.join(hooks_dir, fname)
    with open(fpath, encoding='utf-8') as f:
        content = f.read()

    # 提取 re.compile 呼叫
    for m in re.finditer(r're\.compile\(r?[\"\\'](.+?)[\"\\']', content):
        rules_found.append({
            'source_file': fname,
            'type': 'regex',
            'pattern': m.group(1),
            'line': content[:m.start()].count('\n') + 1
        })

    # 提取字串比對（'xxx' in path 或 path.endswith）
    for m in re.finditer(r'(?:in\s+|endswith\()[\"\\']([\w./\\\\-]+)[\"\\']', content):
        rules_found.append({
            'source_file': fname,
            'type': 'string_match',
            'pattern': m.group(1),
            'line': content[:m.start()].count('\n') + 1
        })

print(json.dumps({'total': len(rules_found), 'rules': rules_found}, ensure_ascii=False, indent=2))
" > temp_hook_scan.json
```

### 1b. 從 hook-rules.yaml 載入宣告式規則

```bash
uv run python -X utf8 -c "
import yaml, json

with open('config/hook-rules.yaml', encoding='utf-8') as f:
    data = yaml.safe_load(f)

declared = []
for section_key in ['bash_rules', 'write_rules', 'read_rules']:
    rules = data.get(section_key, [])
    if isinstance(rules, list):
        for r in rules:
            declared.append({
                'id': r.get('id', 'unknown'),
                'section': section_key,
                'priority': r.get('priority', 'unknown'),
                'pattern': r.get('pattern', ''),
                'guard_tag': r.get('guard_tag', ''),
                'description': r.get('description', '')
            })

print(json.dumps({'total': len(declared), 'rules': declared}, ensure_ascii=False, indent=2))
" > temp_yaml_rules.json
```

---

## 步驟 2：交叉比對與漂移偵測

```bash
uv run python -X utf8 -c "
import json

with open('temp_hook_scan.json', encoding='utf-8') as f:
    code_rules = json.load(f)
with open('temp_yaml_rules.json', encoding='utf-8') as f:
    yaml_rules = json.load(f)

yaml_patterns = set()
for r in yaml_rules['rules']:
    if r['pattern']:
        yaml_patterns.add(r['pattern'])

# 漂移偵測：程式碼中有但 YAML 沒宣告的規則
drifted = []
for r in code_rules['rules']:
    if r['type'] == 'regex' and r['pattern'] not in yaml_patterns:
        drifted.append({
            'source_file': r['source_file'],
            'pattern': r['pattern'],
            'line': r['line'],
            'issue': 'code_not_in_yaml'
        })

# priority 衝突：同 id 不同 priority
from collections import defaultdict
id_priorities = defaultdict(set)
for r in yaml_rules['rules']:
    id_priorities[r['id']].add(r['priority'])
conflicts = [{'id': k, 'priorities': list(v)} for k, v in id_priorities.items() if len(v) > 1]

# 覆蓋缺口：hooks/*.py 檔案中沒有對應 yaml section
import os
hook_files = set(f for f in os.listdir('hooks') if f.endswith('.py'))
section_to_hook = {
    'bash_rules': 'pre_bash_guard.py',
    'write_rules': 'pre_write_guard.py',
    'read_rules': 'pre_read_guard.py'
}
coverage_gaps = []
for section, hook_file in section_to_hook.items():
    if hook_file not in hook_files:
        coverage_gaps.append({'section': section, 'expected_hook': hook_file, 'issue': 'hook_file_missing'})

report = {
    'code_rules_total': code_rules['total'],
    'yaml_rules_total': yaml_rules['total'],
    'drifted_rules': drifted,
    'drifted_count': len(drifted),
    'priority_conflicts': conflicts,
    'coverage_gaps': coverage_gaps,
    'health_score': max(0, 100 - len(drifted) * 5 - len(conflicts) * 10 - len(coverage_gaps) * 15)
}
print(json.dumps(report, ensure_ascii=False, indent=2))
" > temp_hook_audit.json
```

---

## 步驟 3：生成結構化審計報告

讀取 `temp_hook_audit.json`，生成 Markdown 格式的審計報告：

```bash
uv run python -X utf8 -c "
import json, datetime

with open('temp_hook_audit.json', encoding='utf-8') as f:
    audit = json.load(f)

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
lines = [
    f'# Hook Registry 審計報告（{now}）',
    '',
    f'## 概覽',
    f'- 程式碼規則數：{audit[\"code_rules_total\"]}',
    f'- YAML 宣告規則數：{audit[\"yaml_rules_total\"]}',
    f'- 漂移規則數：{audit[\"drifted_count\"]}',
    f'- Priority 衝突數：{len(audit[\"priority_conflicts\"])}',
    f'- 覆蓋缺口數：{len(audit[\"coverage_gaps\"])}',
    f'- 健康分數：{audit[\"health_score\"]}/100',
    '',
]

if audit['drifted_rules']:
    lines.append('## 漂移規則（程式碼有，YAML 無）')
    lines.append('')
    lines.append('| 來源檔案 | 行號 | Pattern |')
    lines.append('|---------|------|---------|')
    for d in audit['drifted_rules']:
        lines.append(f'| {d[\"source_file\"]} | {d[\"line\"]} | \`{d[\"pattern\"][:60]}\` |')
    lines.append('')

if audit['priority_conflicts']:
    lines.append('## Priority 衝突')
    lines.append('')
    for c in audit['priority_conflicts']:
        lines.append(f'- **{c[\"id\"]}**：{c[\"priorities\"]}')
    lines.append('')

if audit['coverage_gaps']:
    lines.append('## 覆蓋缺口')
    lines.append('')
    for g in audit['coverage_gaps']:
        lines.append(f'- Section \`{g[\"section\"]}\` 期望 Hook 檔案 \`{g[\"expected_hook\"]}\` 不存在')
    lines.append('')

lines.append('## 修復建議')
lines.append('')
if audit['drifted_count'] > 0:
    lines.append(f'1. 將 {audit[\"drifted_count\"]} 個漂移規則補入 config/hook-rules.yaml 對應 section')
if audit['priority_conflicts']:
    lines.append(f'2. 解決 {len(audit[\"priority_conflicts\"])} 個 priority 衝突（統一為單一 priority）')
if not audit['drifted_rules'] and not audit['priority_conflicts'] and not audit['coverage_gaps']:
    lines.append('所有規則一致，無需修復。')

report_text = '\n'.join(lines)
print(report_text)
"
```

將報告輸出到 `context/hook-registry-audit.md`（用 Write 工具）。

---

## 步驟 4：清理暫存檔

```bash
rm -f temp_hook_scan.json temp_yaml_rules.json temp_hook_audit.json
```

---

## 步驟 5：輸出格式

本 Skill 產生兩個輸出檔案：

| 檔案 | 用途 | 格式 |
|------|------|------|
| `context/hook-registry-audit.md` | 可讀審計報告（Markdown） | 表格 + 修復建議 |
| `context/hook-registry-snapshot.json` | 機器可讀快照（JSON） | 規則清單 + 健康分數 |

### hook-registry-snapshot.json 格式

```json
{
  "generated_at": "ISO 8601",
  "code_rules_total": 0,
  "yaml_rules_total": 0,
  "drifted_count": 0,
  "priority_conflicts_count": 0,
  "coverage_gaps_count": 0,
  "health_score": 100,
  "drifted_rules": [],
  "recommendations": []
}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `config/hook-rules.yaml` 不存在 | 僅掃描程式碼規則，報告「YAML registry 未建立」，建議建立 |
| `hooks/` 目錄為空 | 報告「無 Hook 腳本」，health_score = 0 |
| Python 解析失敗 | 記錄錯誤行號，跳過該檔案，繼續處理其他檔案 |
| 漂移規則超過 20 個 | 僅列出 Top 20，完整清單寫入 snapshot JSON |

---

## 與其他 Skill 的關係

| Skill | 關係 | 說明 |
|-------|------|------|
| system-audit | 上游 | system-audit 發現 Hook 相關問題時，觸發本 Skill 深入分析 |
| arch-evolution | 下游 | 本 Skill 的審計結果可作為 ADR-031 實施的前置評估 |
| skill-registry-sync | 平行 | 本 Skill 管理 Hook registry，後者管理 Skill registry，互不重疊 |
| prompt-lint | 互補 | prompt-lint 分析模板品質，本 Skill 分析 guard 規則一致性 |

---

## 注意事項

- 本 Skill **不修改** hooks/*.py 或 config/hook-rules.yaml（唯讀分析）
- 修復建議需人工審核後執行
- 適合排程為定期審計（如每週一次），而非即時觸發
- Windows 環境下所有 Python 呼叫使用 `uv run python`
- 禁止 `> nul`，使用 `> /dev/null 2>&1`
