---
name: self-heal
version: "1.0.0"
description: |
  漸進式自我修復（Progressive Recovery Tiers）。依失敗次數與健康度自動升級
  修復層級：Tier 0 預檢 → Tier 1 立即重試 → Tier 2 健康診斷 → Tier 3 AI 診斷
  → Tier 4 人工告警。向後相容：config 不存在時使用預設單層修復邏輯。
  Use when: Agent 失敗後需要自我修復、排程執行前預檢、系統健康度異常。
allowed-tools: [Read, Write, Edit, Bash, Glob]
cache-ttl: "N/A"
triggers:
  - "self-heal"
  - "自我修復"
  - "系統修復"
  - "漸進式恢復"
  - "recovery tiers"
  - "tier 修復"
  - "失敗重試"
depends-on:
  - "config/recovery-tiers.yaml"
  - "state/recovery-history.json"
  - cache-optimizer
  - task-fairness-analyzer
  - ntfy-notify
---

# Self-Heal — 漸進式恢復 Skill

> 架構靈感來自 OpenClaw Self-Healing（31 stars）。Proposal 001 落實，2026-03-23。

---

## 前置條件

讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）。

---

## 步驟 0：讀取配置（向後相容）

```bash
uv run python -X utf8 -c "
import yaml, os
path = 'config/recovery-tiers.yaml'
if os.path.exists(path):
    cfg = yaml.safe_load(open(path, encoding='utf-8'))
    print('CONFIG_FOUND: true')
    print('TIER3_ENABLED:', cfg.get('tiers',{}).get('tier3_ai',{}).get('enabled', False))
else:
    print('CONFIG_FOUND: false')
    print('TIER3_ENABLED: false')
"
```

- `CONFIG_FOUND: false` → 使用預設單層修復（立即重試一次 + ntfy 告警），跳至步驟 5（Tier 4）
- `CONFIG_FOUND: true` → 繼續步驟 1

---

## 步驟 1：讀取恢復歷史，判定當前 Tier

讀取 `state/recovery-history.json`（不存在則初始化預設結構）：

```bash
uv run python -X utf8 -c "
import json, os
path = 'state/recovery-history.json'
default = {
    'schema_version': 1,
    'write_authority': 'agent',
    'sessions': [],
    'stats': {
        'consecutive_failures': 0,
        'last_health_score': 100,
        'tier2_triggers_7d': 0,
        'tier3_triggers_7d': 0
    }
}
if os.path.exists(path):
    d = json.load(open(path, encoding='utf-8'))
else:
    d = default
    os.makedirs('state', exist_ok=True)
    json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
stats = d.get('stats', {})
print('CONSECUTIVE_FAILURES:', stats.get('consecutive_failures', 0))
print('LAST_HEALTH_SCORE:', stats.get('last_health_score', 100))
"
```

**Tier 選擇邏輯**：

| 條件 | 選用 Tier |
|------|---------|
| `CONSECUTIVE_FAILURES = 0`，`LAST_HEALTH_SCORE >= 80` | Tier 0（預檢）|
| `CONSECUTIVE_FAILURES = 1` | Tier 1（立即重試）|
| `CONSECUTIVE_FAILURES >= 2` 或 `LAST_HEALTH_SCORE < 80` | Tier 2（健康診斷）|
| `CONSECUTIVE_FAILURES >= 3` 且 `tier3_ai.enabled = true` | Tier 3（AI 診斷）|
| Tier 2/3 修復失敗 | Tier 4（人工告警）|

---

## 步驟 2：Tier 0 — Preflight Validation

**觸發條件**：每次 Agent 啟動前執行。

```bash
# 配置一致性檢查
uv run python hooks/validate_config.py
```

- 通過（exit 0）→ 繼續執行
- 失敗 → 記錄失敗，升級至 Tier 4 發送告警，阻止執行

---

## 步驟 3：Tier 1 — Immediate Restart

**觸發條件**：`consecutive_failures = 1`。

- 等待 `backoff_seconds`（預設 10 秒）
- 重試執行（max 1 次）
- 成功 → 重置 consecutive_failures → 步驟 7
- 失敗 → consecutive_failures + 1 → 升級至 Tier 2

---

## 步驟 4：Tier 2 — Health Monitoring

**觸發條件**：`consecutive_failures >= 2` 或 `health_score < 80`。

1. 讀取 `skills/cache-optimizer/SKILL.md`，執行快取診斷
2. 讀取 `skills/task-fairness-analyzer/SKILL.md`，執行公平性診斷
3. 依診斷結果修復
4. 修復成功 → 步驟 7；修復失敗 → 升級至 Tier 3（若啟用）或 Tier 4

---

## 步驟 4.5：Tier 3 — AI Diagnosis（需 tier3_ai.enabled=true）

**觸發條件**：`consecutive_failures >= 3` 且配置中 `tier3_ai.enabled: true`。

1. 執行診斷 prompt：
   ```bash
   claude -p prompts/team/self-heal-diagnosis.md
   ```
2. 讀取 `results/self-heal-diagnosis.json`，解析 `risk_level` 與 `next_tier`
3. 依 `config/recovery-tiers.yaml` 的 `auto_remediate_risk_levels` 決定：
   - `risk_level: low`，在 auto_remediate 清單內 → 自動執行 `remediation.action`
   - `risk_level: medium/high` 或 `requires_human: true` → 升級至 Tier 4
4. 記錄診斷結果至 `state/recovery-history.json`（tier3_triggers_7d +1）
5. 若 token 消耗 > 5000（從 `state/token-usage.json` 估算）→ 發送 ntfy 提醒

完整 prompt 定義：`prompts/team/self-heal-diagnosis.md`

---

## 步驟 5：Tier 4 — Human Alert

**觸發條件**：Tier 2/3 失敗，或 `risk_level: high`。

讀取 `skills/ntfy-notify/SKILL.md`，發送詳細告警：

```bash
# 建立告警 JSON（用 Write 工具）
# 包含：失敗原因、consecutive_failures、最近 100 行日誌摘要、建議人工介入步驟
```

---

## 步驟 6：更新 state/recovery-history.json

每次修復後記錄：

```bash
uv run python -X utf8 -c "
import json, os
from datetime import datetime
path = 'state/recovery-history.json'
d = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {'schema_version':1,'write_authority':'agent','sessions':[],'stats':{'consecutive_failures':0,'last_health_score':100,'tier2_triggers_7d':0,'tier3_triggers_7d':0}}
# 追加 session 記錄（由呼叫方填入 tier_used/result/duration_seconds）
d['sessions'] = d.get('sessions', [])[-99:]  # 保留最近 100 筆
# 更新 stats（由呼叫方依結果更新 consecutive_failures）
json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('UPDATED: OK')
"
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `config/recovery-tiers.yaml` 不存在 | 使用預設單層修復（Tier 1 + Tier 4），向後相容 |
| `state/recovery-history.json` 損壞 | 重置為預設結構，consecutive_failures=0 |
| Tier 2 Skill 不可用 | 跳過該 Skill，嘗試下一個 Skill |
| ntfy 不可用 | 記錄到本地日誌（`logs/structured/`），靜默繼續 |
