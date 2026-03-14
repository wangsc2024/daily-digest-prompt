---
name: todo-scanner
version: "0.1.0"
description: |
  ⚠️ 草稿版（KB 不可用時生成）
  TODO/FIXME 自動掃描與分類清理工具。掃描專案全部檔案的 TODO/FIXME 標記，
  自動分類為「規範性」（可直接移除）或「缺陷型」（需追蹤修復），
  生成結構化報告並追蹤清理進度。直接支援 ADR-017 的清理計畫。
  Use when: TODO 清理、FIXME 掃描、程式碼衛生檢查、技術債盤點、TODO 分類、待辦標記統計。
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
cache-ttl: "N/A"
triggers:
  - "TODO 清理"
  - "FIXME 掃描"
  - "todo-scanner"
  - "程式碼衛生"
  - "TODO 分類"
  - "待辦標記統計"
  - "技術債盤點"
depends-on: []
---

# todo-scanner：TODO/FIXME 自動掃描與分類清理

## 設計哲學

本 Skill 解決 ADR-017 的核心痛點：265 處 TODO/FIXME 分散 56 檔，需人工分類才能清理。
自動化分類邏輯將標記分為兩類，各有不同處理策略：

| 類型 | 關鍵詞特徵 | 處理策略 |
|------|-----------|---------|
| **規範性**（normative） | 「考慮」「可能」「未來」「建議」「也許」「或許」「理想上」 | 可直接移除或轉為設計文件 |
| **缺陷型**（defect） | 「修復」「修正」「bug」「broken」「hack」「workaround」「臨時」 | 轉 issue 追蹤，不可直接移除 |

**模板佔位符識別**：含 `<角括號>` 語法的 TODO 視為刻意設計的模板佔位符，不計入統計。

---

## 步驟 0：前置確認

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（確認無其他 Skill 可處理此任務）

---

## 步驟 1：全量掃描

使用 Grep 工具掃描專案目錄，排除不相關路徑：

```bash
uv run python -X utf8 -c "
import subprocess, json, os, re
from pathlib import Path

# 掃描目標副檔名
EXTENSIONS = ['*.md', '*.py', '*.ps1', '*.js', '*.yaml', '*.yml', '*.json']
# 排除目錄
EXCLUDE_DIRS = ['node_modules', '.git', 'cache', 'logs', 'backups', 'tmp', 'temp']

results = []
project_root = Path('.')

for ext in EXTENSIONS:
    for fpath in project_root.rglob(ext):
        # 排除目錄
        if any(excl in fpath.parts for excl in EXCLUDE_DIRS):
            continue
        try:
            content = fpath.read_text(encoding='utf-8', errors='ignore')
            for i, line in enumerate(content.splitlines(), 1):
                # 匹配 TODO / FIXME / HACK / XXX
                match = re.search(r'\b(TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE)
                if match:
                    results.append({
                        'file': str(fpath).replace(os.sep, '/'),
                        'line': i,
                        'marker': match.group(1).upper(),
                        'text': line.strip()[:200]
                    })
        except Exception:
            pass

print(json.dumps({'total': len(results), 'items': results}, ensure_ascii=False))
" > context/todo-scan-raw.json
```

**輸出**：`context/todo-scan-raw.json`（全量掃描結果）

**降級**：若 Python 執行失敗，改用 Grep 工具逐一搜尋 `TODO|FIXME|HACK|XXX`，手動組裝 JSON。

---

## 步驟 2：自動分類

讀取 `context/todo-scan-raw.json`，對每筆標記進行規則式分類：

```bash
uv run python -X utf8 -c "
import json, re

NORMATIVE_KEYWORDS = ['考慮', '可能', '未來', '建議', '也許', '或許', '理想上',
                       'consider', 'maybe', 'might', 'could', 'should consider',
                       'nice to have', 'optional', 'eventually', 'someday', 'later']
DEFECT_KEYWORDS = ['修復', '修正', 'bug', 'broken', 'hack', 'workaround', '臨時',
                    'fix', 'fixme', 'broken', 'regression', 'hotfix', 'temporary',
                    'ugly', 'kludge', 'wrong', 'incorrect', 'error']
TEMPLATE_PATTERN = re.compile(r'<[a-zA-Z_\-]+>')

with open('context/todo-scan-raw.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

classified = {'normative': [], 'defect': [], 'template': [], 'unclassified': []}
by_dir = {}

for item in data['items']:
    text_lower = item['text'].lower()

    # 模板佔位符
    if TEMPLATE_PATTERN.search(item['text']):
        classified['template'].append(item)
        continue

    # 缺陷型（優先判定）
    if any(kw in text_lower for kw in DEFECT_KEYWORDS):
        item['category'] = 'defect'
        classified['defect'].append(item)
    # 規範性
    elif any(kw in text_lower for kw in NORMATIVE_KEYWORDS):
        item['category'] = 'normative'
        classified['normative'].append(item)
    else:
        item['category'] = 'unclassified'
        classified['unclassified'].append(item)

    # 目錄統計
    dir_name = '/'.join(item['file'].split('/')[:2]) if '/' in item['file'] else item['file']
    by_dir.setdefault(dir_name, 0)
    by_dir[dir_name] += 1

report = {
    'scan_date': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'total': data['total'],
    'normative_count': len(classified['normative']),
    'defect_count': len(classified['defect']),
    'template_count': len(classified['template']),
    'unclassified_count': len(classified['unclassified']),
    'by_directory': dict(sorted(by_dir.items(), key=lambda x: -x[1])),
    'top_files': {},
    'normative': classified['normative'][:50],
    'defect': classified['defect'][:50],
    'unclassified': classified['unclassified'][:20]
}

# 計算 top files
file_counts = {}
for item in data['items']:
    file_counts.setdefault(item['file'], 0)
    file_counts[item['file']] += 1
report['top_files'] = dict(sorted(file_counts.items(), key=lambda x: -x[1])[:10])

with open('context/todo-scan-report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f'TOTAL: {data[\"total\"]}')
print(f'NORMATIVE: {len(classified[\"normative\"])}')
print(f'DEFECT: {len(classified[\"defect\"])}')
print(f'TEMPLATE: {len(classified[\"template\"])}')
print(f'UNCLASSIFIED: {len(classified[\"unclassified\"])}')
print(f'TOP_DIR: {list(by_dir.items())[:3]}')
"
```

**輸出**：`context/todo-scan-report.json`（分類報告）

---

## 步驟 3：生成清理建議

讀取 `context/todo-scan-report.json`，依以下規則生成清理行動清單：

### 3a. 規範性 TODO 清理建議

按目錄分組，優先處理 ADR-017 指定的三個目錄：
1. `docs/plans/`（最多規範性 TODO）
2. `templates/`
3. `prompts/`

每個目錄列出：
- 可直接移除的行數（含檔案路徑和行號）
- 預估清理後減少的 TODO 數量

### 3b. 缺陷型 TODO 轉 issue

對每筆缺陷型 TODO，建議轉為結構化 issue：
```
- 檔案：{file}:{line}
- 標記：{marker}
- 內容：{text}
- 建議 issue 標題：Fix: {text 摘要}
```

### 3c. 進度追蹤基準

將當前統計寫入 `context/todo-metrics.json`（追蹤歷史趨勢）：

```bash
uv run python -X utf8 -c "
import json
from datetime import datetime

metrics_path = 'context/todo-metrics.json'
try:
    with open(metrics_path, 'r', encoding='utf-8') as f:
        metrics = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    metrics = {'version': 1, 'history': []}

with open('context/todo-scan-report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

entry = {
    'date': datetime.now().strftime('%Y-%m-%d'),
    'total': report['total'],
    'normative': report['normative_count'],
    'defect': report['defect_count'],
    'template': report['template_count'],
    'unclassified': report['unclassified_count']
}

# 去重（同日只保留最新）
metrics['history'] = [h for h in metrics['history'] if h['date'] != entry['date']]
metrics['history'].append(entry)
# 保留最近 30 天
metrics['history'] = metrics['history'][-30:]

with open(metrics_path, 'w', encoding='utf-8') as f:
    json.dump(metrics, f, ensure_ascii=False, indent=2)

if len(metrics['history']) >= 2:
    prev = metrics['history'][-2]
    delta = entry['total'] - prev['total']
    print(f'TREND: {delta:+d} (vs {prev[\"date\"]})')
else:
    print('TREND: baseline (first scan)')
print(f'TARGET: {entry[\"total\"]} -> 80 (ADR-017 goal)')
"
```

---

## 步驟 4：輸出摘要

讀取 `context/todo-scan-report.json`，產生以下格式的摘要：

```
📋 TODO/FIXME 掃描報告
━━━━━━━━━━━━━━━━━━━━
總計：{total} 處（規範性 {normative} / 缺陷型 {defect} / 模板 {template} / 未分類 {unclassified}）

🔝 TOP 5 目錄：
{by_directory top 5}

📌 建議清理順序：
1. docs/plans/ — {count} 處規範性 TODO 可直接移除
2. templates/ — {count} 處
3. prompts/ — {count} 處

📈 趨勢：{trend}
🎯 ADR-017 目標：{total} → 80 處以下
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| Python 執行失敗 | 改用 Grep 工具逐一搜尋，手動計數 |
| 檔案編碼錯誤 | 跳過該檔案，記錄 `errors` 清單 |
| todo-metrics.json 損壞 | 重建空的 metrics 檔案，從當次開始追蹤 |
| 專案根目錄變更 | 依 PWD 動態決定掃描根目錄 |

---

## 清理暫存

步驟完成後刪除暫存：
```bash
rm -f context/todo-scan-raw.json
```

保留 `context/todo-scan-report.json`（供 check-health.ps1 參考）和 `context/todo-metrics.json`（歷史趨勢）。

---

## 與現有系統整合

- **check-health.ps1**：可新增 `[TODO/FIXME 衛生]` 區塊，讀取 `context/todo-scan-report.json` 顯示統計
- **system-audit**：7.1 功能完成度評分可參考 todo-metrics.json 的趨勢
- **arch-evolution**：ADR-017 進度追蹤可引用 todo-scan-report.json 的數據
- **self-heal 自動任務**：可排程定期掃描，持續追蹤清理進度
