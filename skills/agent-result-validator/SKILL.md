---
name: agent-result-validator
version: "0.5.0"
description: |
  Agent 結果檔案 Schema 驗證器。驗證 results/*.json 是否符合標準 schema，
  偵測格式漂移（欄位缺失、類型錯誤、命名不一致），產出結構化驗證報告。
  支援 pre-assembly 驗證（Phase 3 組裝前檢查）與趨勢追蹤。
  Use when: 驗證結果檔案格式、偵測格式漂移、Phase 3 組裝前檢查、agent handoff 品質保證。
  ⚠️ 知識基礎薄弱，建議透過 skill-audit 補強
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "結果驗證"
  - "result validation"
  - "schema 驗證"
  - "格式漂移"
  - "format drift"
  - "agent-result-validator"
  - "結果檔案檢查"
  - "handoff 驗證"
depends-on:
  - system-insight
---

# Agent Result Validator — 結果檔案 Schema 驗證器

## 設計哲學

本 Skill 實現 ADR-003（Agent Handoff 控制轉移機制）的核心需求：
標準化 `results/*.json` 的格式，在 Phase 3 組裝前自動驗證，
防止格式漂移導致的靜默組裝失敗。

執行鏈：
```
載入 Schema → 掃描結果檔案 → 逐檔驗證 → 分類問題 → 產出報告 → 趨勢追蹤
```

---

## 步驟 0：前置準備

1. 讀取 `templates/shared/preamble.md`（遵守 Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立 Skill 認知地圖）

---

## 步驟 1：載入或初始化 Schema

讀取 `config/schemas/agent-result.schema.json`。

**若不存在**，用 Write 工具建立標準 schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Agent Result File",
  "description": "results/todoist-auto-{task_key}.json 標準格式（ADR-003）",
  "type": "object",
  "required": ["agent", "status", "summary"],
  "properties": {
    "agent": {
      "type": "string",
      "pattern": "^todoist-auto-[a-z_]+$",
      "description": "Agent 識別符，必須符合 todoist-auto-{task_key} 格式"
    },
    "task_type": {
      "type": "string",
      "enum": ["auto", "manual", "research", "game", "code"],
      "description": "任務類型分類"
    },
    "task_key": {
      "type": "string",
      "pattern": "^[a-z_]+$",
      "description": "任務鍵（底線分隔，禁止連字號）"
    },
    "status": {
      "type": "string",
      "enum": ["success", "partial", "failed", "quality_rejected", "format_failed", "in_progress", "skipped"],
      "description": "執行結果狀態"
    },
    "summary": {
      "type": "string",
      "minLength": 5,
      "description": "執行摘要（≥5 字元）"
    },
    "error": {
      "type": ["string", "null"],
      "description": "錯誤訊息（成功時為 null）"
    }
  },
  "additionalProperties": true
}
```

Schema 建立後，記錄 `schema_initialized: true`。

---

## 步驟 2：掃描結果檔案

用 Glob 工具掃描 `results/todoist-auto-*.json`，取得所有結果檔案路徑清單。

**排除規則**：
- 忽略 `results/spans-*.json`（Span 追蹤檔，非 agent 結果）
- 忽略 `results/digest-*.json`（摘要組裝結果，schema 不同）

若無結果檔案 → 記錄 `no_files_found: true`，跳至步驟 5（產出空報告）。

---

## 步驟 3：逐檔驗證

對每個結果檔案執行 Python 驗證：

```bash
uv run python -X utf8 -c "
import json, re, sys, glob

schema_path = 'config/schemas/agent-result.schema.json'
with open(schema_path, encoding='utf-8') as f:
    schema = json.load(f)

required_fields = schema.get('required', [])
properties = schema.get('properties', {})
results = []

for fpath in sorted(glob.glob('results/todoist-auto-*.json')):
    try:
        with open(fpath, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        results.append({'file': fpath, 'valid': False, 'errors': [f'JSON parse error: {e}']})
        continue

    errors = []
    # 必填欄位檢查
    for field in required_fields:
        if field not in data:
            errors.append(f'missing required field: {field}')

    # 類型與格式檢查
    for field, spec in properties.items():
        if field not in data:
            continue
        value = data[field]
        # pattern 檢查
        if 'pattern' in spec and isinstance(value, str):
            if not re.match(spec['pattern'], value):
                errors.append(f'{field} pattern mismatch: {value!r} vs {spec[\"pattern\"]}')
        # enum 檢查
        if 'enum' in spec and value not in spec['enum']:
            errors.append(f'{field} not in enum: {value!r}')
        # minLength 檢查
        if 'minLength' in spec and isinstance(value, str) and len(value) < spec['minLength']:
            errors.append(f'{field} too short: {len(value)} < {spec[\"minLength\"]}')

    results.append({
        'file': fpath.replace('\\\\', '/'),
        'valid': len(errors) == 0,
        'errors': errors,
        'fields_present': list(data.keys())
    })

# 彙總
valid_count = sum(1 for r in results if r['valid'])
total = len(results)
print(json.dumps({
    'total_files': total,
    'valid_count': valid_count,
    'invalid_count': total - valid_count,
    'pass_rate': round(valid_count / total * 100, 1) if total > 0 else 0,
    'details': results
}, ensure_ascii=False, indent=2))
"
```

---

## 步驟 4：格式漂移偵測

在步驟 3 的結果基礎上，進一步分析漂移模式：

**漂移類型分類**：

| 類型 | 判定條件 | 嚴重度 |
|------|---------|--------|
| `missing_required` | 必填欄位缺失 | high |
| `pattern_mismatch` | agent 欄位不符 `todoist-auto-{task_key}` 格式 | high |
| `unknown_status` | status 不在 enum 列表中 | medium |
| `summary_too_short` | summary < 5 字元 | low |
| `extra_fields_only` | 有額外欄位但必填完整 | info |

**命名一致性檢查**：
- 比對檔名中的 `task_key` 與 JSON 內 `agent` 欄位的 `task_key` 部分
- 不一致 → `naming_drift`（嚴重度 high）

---

## 步驟 5：產出驗證報告

用 Write 工具建立 `context/result-validation-report.json`：

```json
{
  "generated_at": "<ISO 8601>",
  "schema_version": "1.0.0",
  "total_files": 5,
  "valid_count": 4,
  "invalid_count": 1,
  "pass_rate": 80.0,
  "drift_summary": {
    "high": 1,
    "medium": 0,
    "low": 0,
    "info": 2
  },
  "issues": [
    {
      "file": "results/todoist-auto-example.json",
      "drift_type": "missing_required",
      "severity": "high",
      "detail": "missing required field: status",
      "suggested_fix": "在結果 JSON 中加入 status 欄位"
    }
  ],
  "naming_consistency": {
    "consistent": 4,
    "inconsistent": 0,
    "details": []
  }
}
```

---

## 步驟 6：趨勢追蹤（可選）

若 `context/result-validation-report.json` 的歷史版本存在（透過 `generated_at` 比對），
計算與上次驗證的差異：

- pass_rate 變化（上升/下降/持平）
- 新增的漂移類型
- 已修復的漂移類型

趨勢資訊附加至報告的 `trend` 欄位。

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| Schema 檔案不存在 | 自動建立標準 schema（步驟 1） |
| 結果目錄無檔案 | 產出空報告（pass_rate=100，total=0） |
| JSON 解析失敗 | 記錄為 invalid，不中斷其他檔案驗證 |
| Python 執行失敗 | 記錄錯誤，status 設為 partial |

---

## 輸出檔案

| 檔案 | 用途 | 生命週期 |
|------|------|---------|
| `config/schemas/agent-result.schema.json` | 標準 schema 定義 | 永久 |
| `context/result-validation-report.json` | 驗證報告 | 每次覆寫 |

---

## 注意事項

- 本 Skill 僅驗證格式，不修改結果檔案內容
- Schema 的 `additionalProperties: true` 允許各任務擴展自訂欄位
- 驗證用 Python 內建模組（json、re、glob），不引入 jsonschema 依賴
- Windows 環境下路徑分隔符統一為 `/`（Python 內處理）
- 禁止使用 `> nul`，用 `> /dev/null 2>&1` 替代
