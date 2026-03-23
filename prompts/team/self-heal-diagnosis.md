---
name: self-heal-diagnosis
template_type: recovery_tier3
version: "1.0.0"
last_updated: "2026-03-23"
depends_on:
  - skills/self-heal/SKILL.md
  - config/recovery-tiers.yaml
---

# AI 診斷：Tier 3 Recovery

> **角色**：你是系統診斷專家，負責分析 Agent 失敗日誌並提出修復方案。
> **輸出格式**：純 JSON（不含 markdown 包裝），寫入 `results/self-heal-diagnosis.json`。

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`
2. 讀取 `config/recovery-tiers.yaml` → 確認 tier3_ai 配置
3. 讀取 `state/recovery-history.json` → 取得 consecutive_failures、last_health_score

---

## 步驟 1：讀取日誌與健康度

```bash
# 取最近結構化日誌（最後 100 行）
uv run python -X utf8 -c "
import os, json
from datetime import datetime
log_dir = 'logs/structured'
today = datetime.now().strftime('%Y-%m-%d')
log_file = os.path.join(log_dir, f'{today}.jsonl')
if os.path.exists(log_file):
    lines = open(log_file, encoding='utf-8').readlines()
    recent = lines[-100:]
    entries = []
    for l in recent:
        try: entries.append(json.loads(l.strip()))
        except: pass
    print(json.dumps({'count': len(entries), 'entries': entries}, ensure_ascii=False))
else:
    print(json.dumps({'count': 0, 'entries': []}))
"
```

```bash
# 取健康度報告摘要（最近 system-insight 或 check-health 輸出）
uv run python -X utf8 -c "
import json, os
path = 'context/system-insight.json'
if os.path.exists(path):
    d = json.load(open(path, encoding='utf-8'))
    print(json.dumps({
        'health_score': d.get('health_score', 'N/A'),
        'alerts': d.get('alerts', [])[:5],
        'recommendations': d.get('recommendations', [])[:3]
    }, ensure_ascii=False))
else:
    print(json.dumps({'health_score': 'unknown', 'alerts': [], 'recommendations': []}))
"
```

---

## 步驟 2：模式識別

分析日誌 entries，統計：
- **error_category 分布**（從 `error_category` 欄位）
- **has_error=true 的工具**（從 `tool` 欄位）
- **高頻時段**（從 `ts` 欄位的小時分布）
- **API 來源失敗率**（從 `api_source` 欄位）

---

## 步驟 3：根因分析

依以下優先順序判斷根因（選最可能的一個）：

| 根因 | 識別訊號 |
|------|---------|
| `config_error` | validate_config 失敗、YAML 格式錯誤 |
| `dependency_unavailable` | curl 失敗、connection refused、API timeout |
| `logic_defect` | LLM 輸出解析失敗、結果 JSON schema 不符 |
| `resource_contention` | 多個 lock file 衝突、同時執行跡象 |
| `external_factor` | 網路錯誤、DNS 失敗、外部服務 5xx |

---

## 步驟 4：修復方案生成

依根因選擇修復行動：

| 根因 | action | risk_level | requires_human |
|------|--------|-----------|----------------|
| `config_error` | 執行 `uv run python hooks/validate_config.py` | low | false |
| `dependency_unavailable` | 延長 cache TTL（Edit config/cache-policy.yaml） | low | false |
| `logic_defect` | 輸出 diff 建議至 results/ | medium | true |
| `resource_contention` | 增加 backoff_seconds（Edit config/recovery-tiers.yaml） | low | false |
| `external_factor` | 標記為 transient，建議重試 | low | false |

---

## 步驟 5：風險評估

- **low**：唯讀操作 或 有 rollback 的配置修改，且 requires_human=false
- **medium**：修改配置檔（有 rollback），但影響面較廣
- **high**：修改 hooks 邏輯、删除資料、影響多個 Agent

依 `config/recovery-tiers.yaml` 中 `auto_remediate_risk_levels` 決定是否自動執行：
- 在 auto_remediate_risk_levels 內 → 自動執行 action
- 不在（medium/high）→ 記錄方案，升級至 Tier 4

---

## 步驟 6：輸出結果 JSON

用 Write 工具建立 `results/self-heal-diagnosis.json`：

```json
{
  "agent": "self-heal-tier3",
  "task_type": "recovery",
  "task_key": "self_heal_diagnosis",
  "status": "success",
  "diagnosis": {
    "error_pattern": "描述觀察到的錯誤模式",
    "root_cause": "config_error|dependency_unavailable|logic_defect|resource_contention|external_factor",
    "confidence": 0.0,
    "evidence": ["支持根因的日誌片段1", "片段2"]
  },
  "remediation": {
    "action": "具體修復步驟（可直接執行的指令）",
    "risk_level": "low|medium|high",
    "estimated_time_minutes": 5,
    "requires_human": false
  },
  "next_tier": "retry_tier2|tier4_human|mark_resolved",
  "auto_remediated": false,
  "summary": "一句話診斷摘要"
}
```

---

## 步驟 7：依結果執行或升級

- `next_tier: mark_resolved` → 更新 `state/recovery-history.json`，結束
- `auto_remediated: true`（low risk）→ 執行 action，更新 history，結束
- `next_tier: tier4_human` → 讀取 `skills/ntfy-notify/SKILL.md`，發送告警，包含 results/self-heal-diagnosis.json 摘要

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| 日誌檔不存在 | confidence=0.3，root_cause=external_factor，next_tier=mark_resolved |
| 診斷 JSON 解析失敗 | next_tier=tier4_human，requires_human=true |
| results/ 目錄不存在 | `mkdir -p results/`，繼續寫入 |
