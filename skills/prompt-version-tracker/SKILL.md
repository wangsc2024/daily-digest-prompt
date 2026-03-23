---
name: prompt-version-tracker
version: "1.0.0"
description: |
  Prompt 模板主動版本管理（Proposal 005 × #57 合併升級）。
  涵蓋：版本掃描（全部 prompt + template）、content hash registry、
  語義版本遞增（Major/Minor/Patch）、frontmatter 初始化、changelog 管理、
  品質-版本因果分析、自主回歸偵測。
  Use when: 追蹤 prompt 版本變更、遞增版本號、補齊 frontmatter、
  分析版本與品質因果、自主偵測品質回歸。
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
cache-ttl: "N/A"
triggers:
  - "prompt 版本"
  - "模板版本追蹤"
  - "prompt version"
  - "版本回溯"
  - "prompt history"
  - "模板變更追蹤"
  - "版本-品質分析"
  - "bump version"
  - "版本遞增"
  - "prompt changelog"
  - "版本覆蓋率"
depends-on:
  - tools/prompt-versioning.py
  - system-insight
  - agent-result-validator
---

# Prompt Version Tracker — 主動版本管理

> **v1.0.0（2026-03-23）**：Proposal 005 × prompt-version-tracker 合併升級。
> 從「被動追蹤器」升級為「主動版本管理工具」。

---

## 工具核心：`tools/prompt-versioning.py`

所有操作均透過 CLI 工具執行：

```bash
# 掃描版本狀態
uv run python tools/prompt-versioning.py check --dir prompts/team

# 遞增版本號
uv run python tools/prompt-versioning.py bump \
  --prompt prompts/team/xxx.md \
  --type patch \
  --changes "修正步驟 3 的範例" \
  --impact low

# 補齊 frontmatter
uv run python tools/prompt-versioning.py init --prompt prompts/team/xxx.md

# 完整報告（含品質回歸偵測）
uv run python tools/prompt-versioning.py report
```

---

## 步驟 0：前置讀取

讀取 `templates/shared/preamble.md`，確認工具存在：

```bash
uv run python -X utf8 -c "
import os; ok = os.path.isfile('tools/prompt-versioning.py')
print('TOOL_OK:', ok)
"
```

---

## 步驟 1：掃描版本分佈

掃描範圍：`prompts/team/*.md` + `templates/auto-tasks/*.md` + `templates/sub-agent/*.md`

```bash
uv run python tools/prompt-versioning.py check
```

輸出重點：
- **版本覆蓋率**：有 frontmatter version 的 prompt 比例（目標 ≥ 90%）
- **缺版本清單**：列出需補齊的 prompt

---

## 步驟 2：Content Hash Registry 更新

掃描後自動更新 `context/prompt-version-registry.json`：

```bash
uv run python -X utf8 -c "
import glob, hashlib, json
from pathlib import Path
from datetime import datetime, timezone

root = Path('.')
patterns = ['prompts/team/*.md', 'templates/auto-tasks/*.md', 'templates/sub-agent/*.md']
entries = {}
for pat in patterns:
    for f in glob.glob(pat):
        p = Path(f)
        h = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        entries[f.replace(chr(92),'/')]  = {'content_hash': h, 'size': p.stat().st_size}

registry = {
    'generated_at': datetime.now(timezone.utc).astimezone().isoformat(),
    'total': len(entries),
    'entries': entries
}
Path('context/prompt-version-registry.json').write_text(
    json.dumps(registry, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'REGISTRY_UPDATED: {len(entries)} entries')
"
```

---

## 步驟 3：變更偵測

比對 registry prev/curr，識別有變更但版本未更新的 prompt：

```bash
uv run python tools/prompt-versioning.py report
```

輸出「自上次 registry 有變更」清單 → 需執行 `bump` 的目標。

---

## 步驟 4：版本遞增（主動管理）

語義版本規則：

| type | 觸發情境 | 範例 |
|------|---------|------|
| `major` | 輸出格式大幅變更、移除必填欄位 | 重寫步驟結構 |
| `minor` | 新增步驟或可選欄位 | 加入 KB 查詢步驟 |
| `patch` | 措辭修正、範例更新 | 調整指令描述 |

對每個有變更的 prompt 執行：

```bash
uv run python tools/prompt-versioning.py bump \
  --prompt {prompt相對路徑} \
  --type {major|minor|patch} \
  --changes "{變更描述}" \
  --impact {low|medium|high}
```

---

## 步驟 5：補齊 Frontmatter（自主初始化）

對缺少版本 frontmatter 的 prompt，批次執行 init：

```bash
uv run python -X utf8 -c "
import glob, subprocess, sys
missing = []
for f in glob.glob('prompts/team/*.md') + glob.glob('templates/auto-tasks/*.md'):
    content = open(f, encoding='utf-8').read()
    if not content.startswith('---') or 'version:' not in content[:500]:
        missing.append(f)
print(f'需 init 的 prompt：{len(missing)} 個')
for f in missing[:5]:  # 每次批次處理最多 5 個，避免大量覆寫
    result = subprocess.run(
        ['uv', 'run', 'python', 'tools/prompt-versioning.py', 'init', '--prompt', f],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
"
```

---

## 步驟 6：品質-版本因果分析（自主審核）

比對 results/*.json 中的 `quality_score.average` 與 `prompt_version`，偵測回歸：

```bash
uv run python tools/prompt-versioning.py report
```

**回歸判定規則**：
- 品質分下降 > 1.0（Δ < -1.0）→ 標記為回歸
- 同時有 content hash 變更 → 高度疑似 prompt 變更所致

**自主行動規則**：

| 情境 | 自主行動 |
|------|---------|
| 回歸 + prompt 有變更 | 輸出 diff 建議，發送 ntfy 告警 |
| 回歸 + prompt 無變更 | 標記為「外部因素」，記錄至 context/quality-regression-log.json |
| 覆蓋率 < 90% | 自動對前 5 個缺版本 prompt 執行 init |

---

## 步驟 7：注入 prompt_version 至結果檔

確保每個 results/todoist-auto-*.json 含 `prompt_version` 欄位：

```bash
uv run python -X utf8 -c "
import json, glob, hashlib
from pathlib import Path

for rf in glob.glob('results/todoist-auto-*.json'):
    try:
        r = json.loads(Path(rf).read_text(encoding='utf-8'))
        task_key = r.get('task_key', '')
        if task_key and 'prompt_version' not in r:
            pf = Path(f'prompts/team/todoist-auto-{task_key}.md')
            if pf.exists():
                h = hashlib.sha256(pf.read_bytes()).hexdigest()[:12]
                r['prompt_version'] = h
                Path(rf).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f'INJECTED: {rf} [{h}]')
    except Exception as e:
        print(f'SKIP: {rf} ({e})')
"
```

---

## 步驟 8：輪替 Registry

```bash
cp context/prompt-version-registry.json context/prompt-version-registry-prev.json 2>/dev/null || true
```

---

## 步驟 9：自主審核報告輸出

寫入 `results/prompt-version-report.json`（供 system-audit 引用）：

```bash
uv run python -X utf8 -c "
import json, glob, hashlib
from pathlib import Path
from datetime import datetime, timezone

files = glob.glob('prompts/team/*.md') + glob.glob('templates/auto-tasks/*.md')
total = len(files)
has_ver = 0
for f in files:
    c = open(f, encoding='utf-8').read()
    if c.startswith('---') and 'version:' in c[:500]:
        has_ver += 1

report = {
    'agent': 'prompt-version-tracker',
    'task_type': 'auto',
    'task_key': 'prompt_version_tracker',
    'status': 'success',
    'coverage': {'total': total, 'has_version': has_ver, 'pct': round(has_ver/max(total,1)*100, 1)},
    'generated_at': datetime.now(timezone.utc).astimezone().isoformat(),
    'summary': f'版本覆蓋率 {round(has_ver/max(total,1)*100)}%（{has_ver}/{total}）'
}
Path('results').mkdir(exist_ok=True)
Path('results/prompt-version-report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('REPORT_WRITTEN: results/prompt-version-report.json')
"
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `tools/prompt-versioning.py` 不存在 | 使用步驟 1-3 的內嵌 Python 替代（無 bump/init 功能）|
| results/ 為空 | 跳過步驟 6 品質分析，僅執行掃描 |
| registry 損壞 | 重新生成（步驟 2），視為首次掃描 |
| 批次 init 超過 5 個 | 分批執行，每批最多 5 個，避免大規模覆寫 |

---

## 版本歷史

- v0.5.0（2026-03）：初版，被動追蹤（scan/hash/detect/inject）
- v1.0.0（2026-03-23）：主動版本管理（新增 bump/init/report CLI，品質回歸自主偵測，自動注入 frontmatter）
