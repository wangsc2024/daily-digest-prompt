---
name: skill-lifecycle-manager
version: "0.5.0"
description: |
  Skill 生命週期管理器。追蹤所有 Skill 的生命週期狀態（草稿→正式→穩定→退役），
  執行版本升級評估、退役候選識別、穩定度評分、分層分級（core/shared/workspace），
  並產出結構化報告與 ADR 建議。
  Use when: Skill 版本升級評估、退役候選識別、Skill 分層管理、穩定度評分、Skill 清理規劃。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "skill-lifecycle-manager"
  - "Skill 生命週期"
  - "Skill 退役"
  - "Skill 升級"
  - "Skill 分層"
  - "lifecycle"
  - "deprecation"
  - "版本升級評估"
  - "穩定度評分"
depends-on:
  - skill-registry-sync
  - system-insight
  - arch-evolution
  - "config/dependencies.yaml"
---

# Skill Lifecycle Manager — Skill 生命週期管理器

> **信號來源**：improvement-backlog P1（openclaw 三層 Skill 系統提案）+ system-insight（49 個 Skill 缺乏統一生命週期追蹤）

## 設計哲學

本 Skill 管理 Skill 的「出生到退役」全週期。不生成新 Skill（那是 skill-forge 的職責），而是追蹤、評估、分層、退役現有 Skill，確保 Skill 生態系統的健康與可持續性。

執行鏈：
```
掃描（frontmatter + 執行統計）→ 評估（穩定度 + 使用頻率 + 品質）
→ 分層（core/shared/workspace）→ 退役候選識別 → 升級建議 → 報告
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（遵守共用規則）
2. 讀取 `skills/SKILL_INDEX.md`（現有 Skill 認知地圖）
3. 讀取 `context/system-insight.json`（取得 skill_heatmap 與 unused_skills_list）

---

## 步驟 1：Skill 狀態掃描

### 1a. Frontmatter 掃描（委派子 Agent 或直接 Grep）

掃描所有 `skills/*/SKILL.md` 的 frontmatter，提取：

```bash
uv run python -X utf8 -c "
import os, yaml, json, glob

skills = []
for path in sorted(glob.glob('skills/*/SKILL.md')):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    parts = content.split('---')
    if len(parts) >= 3:
        try:
            data = yaml.safe_load(parts[1])
            skills.append({
                'name': data.get('name', os.path.basename(os.path.dirname(path))),
                'version': data.get('version', 'unknown'),
                'triggers_count': len(data.get('triggers', [])),
                'depends_on': data.get('depends-on', []),
                'has_use_when': 'Use when' in data.get('description', ''),
                'dir': os.path.basename(os.path.dirname(path))
            })
        except yaml.YAMLError:
            skills.append({'name': os.path.basename(os.path.dirname(path)), 'version': 'parse_error'})

print(json.dumps(skills, ensure_ascii=False, indent=2))
"
```

### 1b. 使用頻率統計

從 `context/system-insight.json` 讀取 `skill_heatmap`（top 使用次數）和 `unused_skills_list`。

### 1c. 版本歷史（若有 skill-registry-sync 產出的 registry）

讀取 `context/skill-registry.json`（若存在），取得每個 Skill 的版本記錄。

---

## 步驟 2：穩定度評分（每個 Skill 0-100 分）

對每個 Skill 計算穩定度分數：

```
穩定度評分公式（滿分 100）：

版本成熟度（0-30 分）：
  v1.0.0+           → 30 分
  v0.5.0-v0.9.x     → 20 分
  v0.1.0-v0.4.x     → 10 分
  unknown/parse_error → 0 分

使用頻率（0-30 分，依 skill_heatmap）：
  top 5 使用量       → 30 分
  top 10 使用量      → 20 分
  有使用記錄         → 10 分
  unused_skills_list → 0 分

品質指標（0-20 分）：
  has_use_when = true    → 10 分
  triggers_count >= 5    → 5 分
  depends-on 有定義      → 5 分

測試覆蓋（0-20 分）：
  tests/skills/{name}/ 存在  → 20 分
  無測試                     → 0 分
```

### 穩定度分級

| 分級 | 分數範圍 | 意義 |
|------|---------|------|
| S（穩定） | 80-100 | 核心 Skill，穩定可靠 |
| A（正常） | 60-79 | 正常運作，可考慮升級 |
| B（觀察） | 40-59 | 需關注，可能需補強 |
| C（風險） | 0-39 | 退役候選 |

---

## 步驟 3：分層分級（core / shared / workspace）

依穩定度與使用模式，將每個 Skill 分類至三個層級：

| 層級 | 判定規則 | 特徵 |
|------|---------|------|
| **core** | 穩定度 S 級 + SKILL_INDEX.md「核心 Skill」列 | 每日必用，不可退役 |
| **shared** | 穩定度 A/B 級 + 被 ≥2 個其他 Skill depends-on | 跨 Skill 共用基礎設施 |
| **workspace** | 其餘（穩定度 B/C 級，或使用率低） | 實驗性，可考慮退役或升級 |

```bash
uv run python -X utf8 -c "
import json

# 讀取步驟 2 產出的評分結果
with open('context/skill-lifecycle-report.json', encoding='utf-8') as f:
    report = json.load(f)

core_skills = [s['name'] for s in report['skills'] if s['tier'] == 'core']
shared_skills = [s['name'] for s in report['skills'] if s['tier'] == 'shared']
workspace_skills = [s['name'] for s in report['skills'] if s['tier'] == 'workspace']

print(f'Core ({len(core_skills)}): {core_skills}')
print(f'Shared ({len(shared_skills)}): {shared_skills}')
print(f'Workspace ({len(workspace_skills)}): {workspace_skills}')
"
```

---

## 步驟 4：退役候選識別

識別符合退役條件的 Skill：

**退役候選標準（任一即列入）**：
1. 穩定度 C 級（0-39 分）**且** 連續 14 天未使用
2. 功能完全被另一個 Skill 覆蓋（需人工確認）
3. depends-on 的依賴已不存在

**安全護欄**：
- core 層級 Skill **不可**被標記為退役候選
- 被其他 Skill depends-on 的 Skill **不可**退役（需先遷移依賴方）

```bash
uv run python -X utf8 -c "
import json

with open('context/skill-lifecycle-report.json', encoding='utf-8') as f:
    report = json.load(f)

candidates = []
for s in report['skills']:
    if s['tier'] == 'core':
        continue
    if s['stability_score'] < 40 and s.get('days_since_last_use', 0) > 14:
        # 檢查是否被其他 Skill 依賴
        dependents = [
            other['name'] for other in report['skills']
            if s['name'] in other.get('depends_on_names', [])
        ]
        if not dependents:
            candidates.append({
                'name': s['name'],
                'score': s['stability_score'],
                'tier': s['tier'],
                'reason': f'穩定度 {s[\"stability_score\"]} 分 + 超過 14 天未使用',
                'action': 'recommend_retire'
            })
        else:
            candidates.append({
                'name': s['name'],
                'score': s['stability_score'],
                'tier': s['tier'],
                'reason': f'穩定度低但仍被 {dependents} 依賴',
                'action': 'recommend_upgrade'
            })

print(json.dumps(candidates, ensure_ascii=False, indent=2))
"
```

---

## 步驟 5：版本升級建議

對穩定度 B 級（40-59 分）的 Skill 產出升級建議：

| 缺失項 | 升級建議 |
|--------|---------|
| version < v1.0.0 | 檢閱內容品質，若已穩定則升級版本號 |
| triggers_count < 5 | 補充觸發關鍵字至 ≥5 個 |
| 無 depends-on | 評估是否需要宣告依賴 |
| 無測試 | 用 skill-test-scaffolder 生成測試骨架 |
| unused（7 天內） | 檢查觸發詞是否被路由正確匹配 |

---

## 步驟 6：產出報告

用 Write 工具建立 `context/skill-lifecycle-report.json`：

```json
{
  "generated_at": "ISO 8601",
  "total_skills": 49,
  "tier_distribution": {
    "core": 15,
    "shared": 12,
    "workspace": 22
  },
  "stability_distribution": {
    "S": 10,
    "A": 15,
    "B": 14,
    "C": 10
  },
  "skills": [
    {
      "name": "todoist",
      "version": "2.1.0",
      "tier": "core",
      "stability_score": 95,
      "stability_grade": "S",
      "usage_7d": 117,
      "has_tests": true,
      "depends_on_names": ["config/dependencies.yaml"],
      "depended_by": ["todoist-task-creator"],
      "lifecycle_status": "stable",
      "upgrade_suggestions": []
    }
  ],
  "retirement_candidates": [],
  "upgrade_recommendations": [],
  "adr_suggestions": [
    {
      "title": "Skill 分層管理（core/shared/workspace）",
      "priority": "P2",
      "rationale": "49 個 Skill 需系統化分層管理"
    }
  ]
}
```

---

## 步驟 7：匯入知識庫（可選）

若報告有重要發現（退役候選 ≥1 或穩定度 C 級 ≥3），匯入 KB：

用 Write 建立 `kb_lifecycle_note.json`：
```json
{
  "notes": [{
    "title": "Skill 生命週期報告（YYYY-MM-DD）",
    "contentText": "## 報告摘要\n...",
    "tags": ["skill-lifecycle", "系統治理", "Skill管理"],
    "source": "import"
  }],
  "autoSync": true
}
```

```bash
curl -s -X POST "http://localhost:3000/api/import" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @kb_lifecycle_note.json > /dev/null 2>&1
rm kb_lifecycle_note.json
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| system-insight.json 不存在 | 僅使用 frontmatter 掃描，使用頻率設為 unknown |
| skill-registry-sync 未執行 | 跳過版本歷史分析，僅用當前 frontmatter 版本 |
| SKILL_INDEX.md 格式異常 | 用 Grep 掃描替代，以 `skills/*/SKILL.md` 為真相來源 |
| 測試目錄不存在 | 測試覆蓋分數設為 0 |

---

## 錯誤處理

- YAML 解析失敗：記錄 `parse_error`，該 Skill 穩定度設為 0 分
- 檔案讀取失敗：跳過該 Skill，在報告中標記 `scan_failed`
- 輸出 JSON 寫入失敗：降級為純文字輸出到 stdout

---

## 與其他 Skill 的協作

| Skill | 關係 | 互動方式 |
|-------|------|---------|
| **skill-registry-sync** | 上游（提供 JSON registry） | 讀取 `context/skill-registry.json` |
| **skill-forge** | 下游（生成新 Skill） | lifecycle 報告可指出需要新 Skill 的缺口 |
| **skill-test-scaffolder** | 協作（提升穩定度） | 升級建議中推薦用 scaffolder 補測試 |
| **system-insight** | 上游（提供使用統計） | 讀取 `skill_heatmap` 與 `unused_skills_list` |
| **arch-evolution** | 下游（產出 ADR） | 分層結果可轉化為架構決策 |
