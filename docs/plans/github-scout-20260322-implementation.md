# GitHub Scout 落實方案計畫

**建立日期**: 2026-03-22
**來源**: github-scout 自動任務（第 2 次執行）
**狀態**: 5 個全部落實（001、002、003、004、005）

---

## 背景

本次 GitHub Scout 蒐集到 3 個高相關性專案：
1. **OpenClaw Self-Healing** (31 stars) - AI-powered 4-5 tier autonomous recovery
2. **SigNoz** (26.2k stars) - OpenTelemetry native observability platform
3. **Langfuse** (23.5k stars) - LLM engineering platform with prompt management

經分析產出 7 個改進建議（3 個 P0, 4 個 P1），並研擬 5 個具體落實方案。

經過 2 輪審查，5 個方案全部通過可行性與穩定性評估（feasibility_score >= 7, stability_score >= 7）。

**已落實方案**：
- ✅ **Proposal 002**: LLM-as-a-Judge Evaluation（低工作量，低風險）

**待人工審核方案**（4 個）：
- ✅ **Proposal 001**: Progressive Recovery Tiers（2026-03-23 落實，skills/self-heal/ 新建）
- ✅ **Proposal 003**: AI-Driven Diagnosis（2026-03-23 落實，prompts/team/self-heal-diagnosis.md 新建，tier3_ai.enabled=true 已啟用）
- ✅ **Proposal 004**: OpenTelemetry Instrumentation（2026-03-23 落實，enabled=false 待驗證後啟用）
- ✅ **Proposal 005**: Prompt Versioning（2026-03-23 合併升級完成，prompt-version-tracker v1.0.0 + tools/prompt-versioning.py）

---

## ✅ 已落實方案

### Proposal 002: LLM-as-a-Judge Evaluation

**狀態**: 已落實（2026-03-22 12:50）
**來源**: Langfuse LLM Engineering Platform
**風險等級**: low
**工作量**: low

**已完成**：
- ✅ 建立 `skills/task-quality-gate/SKILL.md`
- ✅ 建立 `config/evaluation-criteria.yaml`
- ✅ 驗證配置檔格式正確

**待整合**（人工執行）：
- ⏳ 在 `prompts/team/todoist-assemble.md` 步驟 6 後新增步驟 6.5（品質評估）
- ⏳ 執行完整驗證（建立測試結果 JSON，執行 Skill，驗證評分機制）

**rollback 方法**：
```bash
# 若需回退
rm -rf skills/task-quality-gate/
rm config/evaluation-criteria.yaml
# 從 prompts/team/todoist-assemble.md 移除步驟 6.5（若已整合）
```

---

## ⏳ Proposal 001: Progressive Recovery Tiers（漸進式恢復層級）

**狀態**: 待人工審核
**來源**: OpenClaw Self-Healing System
**風險等級**: medium
**工作量**: medium
**審查評分**: feasibility=8/10, stability=8/10

### 目標

引入 4 層漸進式恢復架構（參考 OpenClaw），從簡單到複雜的升級機制：
- **Tier 0**: Preflight Validation（現有 validate_config.py 強化）
- **Tier 1**: Immediate Restart（新增）
- **Tier 2**: Health Monitoring（現有 check-health.ps1 整合）
- **Tier 3**: AI Diagnosis（見 Proposal 003，依賴此方案）
- **Tier 4**: Human Alert（現有 ntfy 強化）

### 實施步驟

#### 1. 建立 skills/self-heal/ 目錄與 SKILL.md（目錄尚不存在，需新建）

```bash
mkdir -p skills/self-heal
```

用 Write 工具建立 `skills/self-heal/SKILL.md`（最小可用版本，frontmatter + 執行流程佔位，步驟 3 再擴充）。

#### 2. 建立 config/recovery-tiers.yaml
```yaml
version: 1
tiers:
  tier0_preflight:
    enabled: true
    checks: [config_consistency, dependency_availability, permission_check]
    on_failure: block_execution
  tier1_restart:
    enabled: true
    max_retries: 1
    backoff_seconds: 10
  tier2_health:
    enabled: true
    triggers:
      - consecutive_failures: 2
      - health_score_below: 80
    remediation_skills: [cache-optimizer, task-fairness-analyzer]
  tier3_ai:
    enabled: false  # 待 Proposal 003 實施後啟用
    model: claude-haiku-4-5-20251001
    max_diagnosis_time: 300
  tier4_human:
    enabled: true
    ntfy_topic: wangsc2025
    include_logs: last_100_lines
```

#### 3. 修改 skills/self-heal/SKILL.md

在 `## 執行流程` 後新增：

```markdown
## 漸進式恢復層級

本 Skill 使用 4-5 層漸進式恢復架構（參考 OpenClaw Self-Healing），依失敗次數和健康度自動升級修復策略。

### 層級定義

| Tier | 名稱 | 觸發條件 | 修復策略 |
|------|------|---------|---------|
| 0 | Preflight Validation | Agent 啟動時 | 配置驗證、依賴檢查、權限檢查 |
| 1 | Immediate Restart | 1 次失敗 | 立即重試（max 1 次） |
| 2 | Health Monitoring | 2 次連續失敗或健康度 < 80% | 執行 cache-optimizer / task-fairness-analyzer |
| 3 | AI Diagnosis | 3 次連續失敗或 Tier 2 失敗 | LLM 分析日誌並生成修復方案（見 Proposal 003） |
| 4 | Human Alert | Tier 3 無法修復 | ntfy 詳細報告 + 人工介入建議 |

### 執行流程（修改後）

#### 步驟 1：讀取 tier 配置
用 Read 讀取 `config/recovery-tiers.yaml`（不存在則使用預設配置，向後相容）。

#### 步驟 2：判定當前 tier
根據失敗次數（從 state/recovery-history.json 讀取）和健康度（執行 check-health.ps1）選擇 tier。

#### 步驟 3-6：依次執行各 tier
依序嘗試 Tier 0 → 1 → 2 → 3 → 4，每層成功則停止升級，失敗則升級到下一層。

#### 步驟 7：更新恢復歷史
將本次恢復記錄（使用的 tier、結果）寫入 `state/recovery-history.json`，用於下次判定。
```

#### 4. 補充：state/recovery-history.json Schema

初始結構（首次執行時由 Skill 建立，PS1 唯讀）：
```json
{
  "schema_version": 1,
  "write_authority": "agent",
  "last_updated": "2026-03-23T00:00:00+08:00",
  "sessions": [
    {
      "ts": "ISO8601",
      "tier_used": 1,
      "trigger": "consecutive_failures|health_score|manual",
      "result": "resolved|escalated|failed",
      "duration_seconds": 0
    }
  ],
  "stats": {
    "consecutive_failures": 0,
    "last_health_score": 100,
    "tier2_triggers_7d": 0,
    "tier3_triggers_7d": 0
  }
}
```

#### 5. 驗證

```bash
# 驗證配置檔格式
uv run python hooks/validate_config.py

# 驗證 SKILL.md frontmatter
uv run python -X utf8 -c "
import yaml; content = open('skills/self-heal/SKILL.md', encoding='utf-8').read()
parts = content.split('---'); data = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
print('name:', data.get('name')); print('version:', data.get('version'))
"

# 驗證 recovery-history.json schema（首次執行後）
uv run python -X utf8 -c "
import json; d = json.load(open('state/recovery-history.json', encoding='utf-8'))
assert 'schema_version' in d and 'stats' in d, 'Schema 不符'
print('Schema OK, consecutive_failures:', d['stats']['consecutive_failures'])
"
```

### Rollback 方法

```bash
# 刪除新建目錄（若全部是新建）
rm -rf skills/self-heal/

# 或只刪配置檔（回退到無 tier 架構）
rm config/recovery-tiers.yaml

# 用 git revert（若已 commit）
git log --oneline | head -5
git revert <commit-hash>
```

### 驗證清單

- [ ] skills/self-heal/ 目錄與 SKILL.md 已建立（含完整 frontmatter）
- [ ] config/recovery-tiers.yaml 格式正確（`validate_config.py`）
- [ ] self-heal Skill 能正確讀取 tier 配置（config 不存在時使用預設舊邏輯，向後相容）
- [ ] **recovery-history.json schema 符合定義（schema_version + stats + sessions）**
- [ ] 模擬 consecutive_failures=2 情境，驗證 Tier 2 自動觸發
- [ ] state/recovery-history.json 正確記錄 tier 使用統計
- [ ] Tier 4 ntfy 告警包含完整 context
- [ ] **config/recovery-tiers.yaml 不存在時，Agent 行為不受影響（向後相容）**

---

## ⏳ Proposal 003: AI-Driven Diagnosis（AI 驅動診斷）

**狀態**: 待人工審核
**來源**: OpenClaw Self-Healing System
**風險等級**: high
**工作量**: high
**審查評分**: feasibility=7/10, stability=7/10
**依賴**: Proposal 001 (Progressive Recovery Tiers)

### 目標

強化 AI 診斷能力（Tier 3），目前 self-heal 僅執行預定義修復腳本。引入 AI 診斷層：分析日誌、識別根因、生成修復方案。

### 實施步驟

#### 1. 建立 prompts/team/self-heal-diagnosis.md

**完整內容見 `tmp/implementation-plans.json` → Proposal 003 → implementation_plan.changes_summary**

核心邏輯：
- 步驟 1-2：讀取最近日誌（tail -100）和健康度報告
- 步驟 3：模式識別（錯誤類型統計、觸發時段分析）
- 步驟 4：根因分析（5 種根因分類）
- 步驟 5：修復方案生成（依根因類型提出方案）
- 步驟 6：風險評估（low/medium/high）

輸出 JSON：
```json
{
  "diagnosis": {
    "error_pattern": "描述",
    "root_cause": "配置錯誤/依賴不可用/...",
    "confidence": 0.0-1.0
  },
  "remediation": {
    "action": "具體修復步驟",
    "risk_level": "low/medium/high",
    "estimated_time": "分鐘",
    "requires_human": true/false
  },
  "next_tier": "tier4_human/retry_tier2/mark_resolved"
}
```

#### 2. 修改 skills/self-heal/SKILL.md（新增 Tier 3 段落）

在「漸進式恢復層級」的「執行流程」中新增：

```markdown
### Tier 3: AI Diagnosis

**觸發條件**：
- consecutive_failures >= 3
- 或 Tier 2 修復失敗

**執行流程**：
1. 用 claude -p 執行 `prompts/team/self-heal-diagnosis.md`
2. 解析診斷結果 JSON
3. 若 risk_level=low 且 requires_human=false → 自動執行修復
4. 若 risk_level=medium → 執行修復 + 發送 ntfy 通知
5. 若 risk_level=high 或 requires_human=true → 升級到 Tier 4
6. 更新 `state/recovery-history.json`（記錄診斷結果與修復成功率）
```

#### 3. 修改 config/recovery-tiers.yaml（啟用 tier3）

用 Edit 工具將 `tier3_ai.enabled` 從 `false` 改為 `true`，並補充：
```yaml
tier3_ai:
  enabled: true  # 從 false 改為 true
  model: claude-haiku-4-5-20251001
  max_diagnosis_time: 300
  auto_remediate_risk_levels: [low]  # 僅自動執行 low risk 修復
  requires_human_approval: [medium, high]  # medium/high 需人工審核
```

#### 4. 驗證

```bash
# 確認 tier3_ai.enabled = true
uv run python -X utf8 -c "
import yaml; d = yaml.safe_load(open('config/recovery-tiers.yaml', encoding='utf-8'))
print('tier3 enabled:', d['tiers']['tier3_ai']['enabled'])
"

# 驗證 self-heal-diagnosis.md 已建立
uv run python -X utf8 -c "
import os; exists = os.path.isfile('prompts/team/self-heal-diagnosis.md')
print('diagnosis prompt exists:', exists)
"

# 檢查 state/recovery-history.json 記錄診斷結果與成功率（不用 jq，改用 Python）
uv run python -X utf8 -c "
import json; d = json.load(open('state/recovery-history.json', encoding='utf-8'))
print('tier3_triggers_7d:', d.get('stats', {}).get('tier3_triggers_7d', 0))
"
```

### Rollback 方法

```bash
# 停用 tier3（用 Edit 工具將 enabled: true 改回 enabled: false）
# 或刪除 prompt
rm prompts/team/self-heal-diagnosis.md

# 用 git revert（最安全）
git log --oneline | head -5
git revert <commit-hash>
```

### 驗證清單

- [ ] 模擬 consecutive_failures=3 情境，觸發 Tier 3
- [ ] self-heal-diagnosis.md 能正確分析日誌並輸出 JSON
- [ ] low risk 修復（如延長 cache TTL）能自動執行
- [ ] high risk 修復能正確升級到 Tier 4 發送 ntfy
- [ ] state/recovery-history.json 記錄診斷結果與成功率
- [ ] Tier 3 呼叫的 token 消耗（預期 < 5000 tokens/次）

---

## ⏳ Proposal 004: OpenTelemetry Instrumentation（OpenTelemetry 儀表化）

**狀態**: 待人工審核
**來源**: SigNoz Observability Platform
**風險等級**: medium（優化後，原 high）
**工作量**: high
**審查評分**: feasibility=8/10, stability=7/10（第 2 輪優化後）

### 目標

分階段引入 OpenTelemetry instrumentation，第一階段使用 file exporter 避免外部依賴（無需 OTEL Collector）。

### 實施步驟

#### 1. 備份現有檔案
```bash
cp hooks/post_tool_logger.py hooks/post_tool_logger.py.bak_$(date +%Y%m%d%H%M%S)
cp pyproject.toml pyproject.toml.bak_$(date +%Y%m%d%H%M%S)
```

#### 2. 修改 pyproject.toml（新增依賴）

在 `[project.dependencies]` 新增：
```toml
opentelemetry-api = "^1.22.0"
opentelemetry-sdk = "^1.22.0"
```

執行：
```bash
uv sync
```

#### 3. 建立 config/otel-config.yaml

```yaml
version: 1
enabled: false  # 預設關閉，待驗證穩定後啟用
exporter:
  type: file  # 使用 file exporter（無需外部服務）
  file_path: logs/otel/traces.jsonl  # OTLP JSON Lines 格式
  rotation:
    max_bytes: 10485760  # 10MB
    backup_count: 3
resource:
  service.name: daily-digest-agent
  service.version: 1.0.0
  deployment.environment: production
sampling:
  rate: 0.1  # 10% 採樣（降低效能影響）
fallback:
  on_export_failure: continue  # export 失敗時繼續執行（不中斷 Agent）
  max_retry: 0  # 不重試（避免阻塞）
```

#### 4. 修改 hooks/post_tool_logger.py

**完整修改內容見 `tmp/implementation-plans.json` → Proposal 004 → implementation_plan.changes_summary**

核心修改：
- 新增 `FileSpanExporter` class（簡單的 file-based exporter）
- 在現有 `log_tool_use()` 函數中新增 OTLP span 記錄（雙寫模式）
- 使用 `SimpleSpanProcessor`（同步，低 overhead）
- 10% 採樣（`random.random() < sampling_rate`）
- 靜默失敗（try-except 包裹，不拋出異常）

#### 5. logs/otel/ 已含於 .gitignore

`.gitignore` 第 9 行已有 `logs/`，`logs/otel/` 自動排除，**無需額外修改 .gitignore**。

#### 6. 驗證

```bash
# 啟用 OTEL（用 Edit 工具將 enabled: false 改為 enabled: true）
# 然後執行一個簡單 Agent
pwsh -File run-todoist-agent.ps1

# 驗證 logs/otel/traces.jsonl 有新增 span 記錄
uv run python -X utf8 -c "
import os, json
path = 'logs/otel/traces.jsonl'
if os.path.exists(path):
    lines = open(path, encoding='utf-8').readlines()
    print(f'traces.jsonl 存在，共 {len(lines)} 行')
    if lines: print('最新一筆:', lines[-1][:200])
else:
    print('traces.jsonl 不存在（OTEL 未啟用或採樣未命中）')
"

# 驗證 JSONL 日誌仍正常寫入（雙寫確認）
uv run python -X utf8 -c "
import os, glob
files = glob.glob('logs/structured/*.jsonl')
print(f'structured 日誌檔數量: {len(files)}')
"

# 模擬 file write 失敗（刪除 logs/otel/ 目錄），驗證 Agent 不中斷
# Windows: rmdir /s /q logs\otel 或 Remove-Item -Recurse logs/otel
pwsh -Command "if (Test-Path logs/otel) { Remove-Item -Recurse logs/otel }; pwsh -File run-todoist-agent.ps1"
```

### Rollback 方法

```bash
# 停用 OTEL（即時生效，用 Edit 工具將 enabled: true 改回 enabled: false）

# 還原 post_tool_logger.py（git checkout 最安全）
git checkout hooks/post_tool_logger.py

# 還原 pyproject.toml + 移除 opentelemetry 依賴
git checkout pyproject.toml
uv sync

# 清理 trace 輸出（可選）
pwsh -Command "if (Test-Path logs/otel) { Remove-Item -Recurse logs/otel }"

# 用 git revert（完整還原）
git log --oneline | head -5
git revert <commit-hash>
```

### 驗證清單

- [ ] enabled=true 時，logs/otel/traces.jsonl 有新增 span 記錄
- [ ] JSONL 日誌仍正常寫入（雙寫確認）
- [ ] 刪除 logs/otel/ 目錄，Agent 仍正常執行（靜默失敗 fallback 生效）
- [ ] OTLP export 的效能影響（預期 < 10ms overhead/次，因 10% 採樣）
- [ ] enabled=false 時，logs/otel/ 目錄不產生任何新檔案

---

## ✅ Proposal 005: Prompt Versioning（Prompt 版本控制）— 合併升級完成

**狀態**: ✅ 合併升級完成（2026-03-23）
**決策**: 不另建平行實作，改將 Proposal 005 的 `tools/prompt-versioning.py` 功能合併至 `prompt-version-tracker` Skill v1.0.0，遵守「單一定義處」原則。
**交付物**:
- `tools/prompt-versioning.py`（bump/init/check/report CLI）
- `skills/prompt-version-tracker/SKILL.md`（v0.5.0→v1.0.0，主動版本管理）
- `config/benchmark.yaml` 新增 `prompt_version_coverage` + `quality_regression_rate` Fitness Functions
- `check-health.ps1` 新增 [Prompt 版本覆蓋率] 健康度區塊
**來源**: Langfuse LLM Engineering Platform
**風險等級**: medium
**工作量**: medium
**審查評分**: feasibility=8/10, stability=8/10

### 目標

引入 prompt versioning 系統，每個 prompt 檔案加入版本號 frontmatter、變更追蹤、影響分析。

### 實施步驟

#### 1. 建立 tools/prompt-versioning.py

**完整程式碼見 `tmp/implementation-plans.json` → Proposal 005 → implementation_plan.changes_summary**

核心功能：
- `bump_version(prompt_path, change_type, changes, impact)`：遞增版本號並更新 changelog
- `check_versions(directory)`：檢查目錄下所有 prompt 的版本狀態

版本號語義（Semantic Versioning）：
- **Major (X.0.0)**: 破壞性變更（輸出格式大幅調整、移除必填欄位）
- **Minor (x.Y.0)**: 新增功能（新增步驟、新增可選欄位）
- **Patch (x.y.Z)**: 修正或優化（措辭調整、範例更新）

#### 2. 為所有 prompt 檔案新增 frontmatter（工作量大，建議分批）

**範例 frontmatter**：
```markdown
---
name: "todoist-assemble"
version: "1.0.0"
last_updated: "2026-03-22T10:00:00+08:00"
updated_by: "manual"
changelog:
  - version: "1.0.0"
    date: "2026-03-22"
    changes: "初版"
    impact: "n/a"
---

# Prompt 內容...
```

**建議分批順序**：
1. 核心 prompts（`prompts/team/todoist-assemble.md`, `todoist-query.md`）
2. 自動任務 prompts（`prompts/team/todoist-auto-*.md`）
3. 模板（`templates/auto-tasks/*.md`, `templates/sub-agent/*.md`）

#### 3. 驗證

```bash
# 檢查所有 prompt 版本狀態
uv run python tools/prompt-versioning.py check --dir prompts/team

# 手動修改一個 prompt，執行 bump --type patch
uv run python tools/prompt-versioning.py bump \
  --prompt prompts/team/todoist-assemble.md \
  --type patch \
  --changes "修正步驟 3 的範例" \
  --impact low

# 驗證版本號正確遞增且 changelog 更新
cat prompts/team/todoist-assemble.md | head -20

# 檢查修改後的 prompt 檔案能正常被讀取（frontmatter 不影響 claude -p 執行）
# 注意：claude -p 無 --dry-run 旗標，改用 Python 驗證 frontmatter 格式
uv run python -X utf8 -c "
content = open('prompts/team/todoist-assemble.md', encoding='utf-8').read()
has_fm = content.startswith('---')
print('有 frontmatter:', has_fm)
if has_fm:
    end = content.find('---', 3)
    print('frontmatter 內容:', content[3:end].strip()[:200])
"

# 測試 bump --type major 和 --type minor 的版本遞增邏輯
# （建立測試 prompt 檔案）
```

### Rollback 方法

```bash
# 從所有 prompt 檔案移除 version/changelog frontmatter（保留 name frontmatter）
# （需手動編輯或寫腳本批次處理）

# 刪除工具
rm tools/prompt-versioning.py

# 用 git revert
git revert <commit-hash>
```

### 驗證清單

- [ ] `uv run python tools/prompt-versioning.py check --dir prompts/team` 正常執行
- [ ] 能正確列出所有 prompt 的版本狀態
- [ ] 手動修改 prompt + 執行 bump --type patch，版本號正確遞增
- [ ] Changelog 更新正確
- [ ] 修改後的 prompt 檔案能正常被 claude -p 執行（frontmatter 不影響執行）
- [ ] bump --type major 和 --type minor 的版本遞增邏輯正確

---

## 實施優先序建議

### 第一波（已完成）
- ✅ **Proposal 002**: LLM-as-a-Judge Evaluation（低工作量，低風險，立即價值高）

### 第二波（人工審核後確定執行順序）

1. **Proposal 004**: OpenTelemetry Instrumentation（高工作量，中風險）✅ 核准優先執行
   - 理由：預設關閉、靜默失敗、最完善，風險最低
   - 預估時間：2-3 小時

2. **Proposal 001**: Progressive Recovery Tiers（中工作量，中風險）⚠️ 有條件核准
   - 理由：基礎架構改進，為 Proposal 003 鋪路
   - 前提：需先建立 skills/self-heal/ 目錄與 SKILL.md
   - 預估時間：2-3 小時

### 第三波（依賴第二波完成）

3. **Proposal 003**: AI-Driven Diagnosis（高工作量，高風險，依賴 001）⏸️ 延後
   - 理由：需先完成 Proposal 001 + 補完 prompt 完整內容
   - 預估時間：3-4 小時

### 全部完成

- **Proposal 005**: Prompt Versioning ✅ 合併升級完成（2026-03-23）— `prompt-version-tracker` v1.0.0 + `tools/prompt-versioning.py`

---

## 風險提示

| 方案 | 風險等級 | 主要風險 | 降低風險措施 |
|------|---------|---------|------------|
| 001 | medium | 影響 self-heal 核心邏輯 | 向後相容設計（config 不存在時使用舊邏輯） |
| 003 | high | AI 診斷可能誤判，自動執行錯誤修復 | 僅自動執行 low risk 修復，medium/high 需人工審核 |
| 004 | medium | 效能影響不確定 | 10% 採樣 + 預設關閉 + 靜默失敗 |
| 005 | medium | 批次修改大量 prompt 檔案，可能引入格式錯誤 | 分批執行 + 每批驗證 |

---

## 相關資源

- **改進建議來源**: `context/improvement-backlog.json` (entries[3])
- **落實方案詳情**: `tmp/implementation-plans.json`
- **KB 研究報告**: ~~http://localhost:3000/note/f3a91516-a05a-494a-9bcc-1f961896e1ef~~ （Note ID 已失效，回傳 404）
- **參考專案**:
  - [OpenClaw Self-Healing](https://github.com/Ramsbaby/openclaw-self-healing)
  - [SigNoz](https://github.com/SigNoz/signoz)
  - [Langfuse](https://github.com/langfuse/langfuse)

---

**建立者**: todoist-auto-github_scout (github-scout Skill)
**最後更新**: 2026-03-22T13:00:00+08:00
