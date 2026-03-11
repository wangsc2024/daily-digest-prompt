# 系統自愈機制強化計畫

> 計畫 ID：cuddly-prancing-dove
> 建立日期：2026-03-11
> 狀態：**全部完成** ✅（所有 P0/P1/P2/P3/B2/E 項目均已落地）
> 最後更新：2026-03-11（第三次實施，B2/E/P3-b 低優先項目全部完成）

---

## Context

**為何需要此計畫？**

本專案每日執行 44 次排程（6 種排程類型 × 每小時/每日觸發），現有 OODA 閉環架構（Observe→Orient→**Decide→Act**）的 Decide 步驟因缺乏專屬 prompt 而永久停用，導致：
- system-insight 偵測到問題（快取命中率 14.57% < 40%）卻無決策機制轉化為修復行動
- improvement-backlog.json 積累 5+ 項改善待辦，無法自動演化
- 排程失敗時僅能重試 1 次（無指數退避），瞬間網路抖動即導致整日無摘要

**期望結果：**
建立完整的四層自愈架構（預防→偵測→診斷→修復），使排程任務能「如實如質」完成，並在意外發生時自我發現並解決問題，無需人工介入。

**2026-03-11 執行進度更新：**
**第一次實施（2026-03-11 早）：**
- ✅ OODA Decide 步驟完全啟用（arch-evolution prompt + ooda-workflow.yaml enabled:true）
- ✅ 首次手動 arch-evolution 執行完成（11 個 ADR，9 項決策，3 個 immediate_fix）
- ✅ self-heal 新增步驟 g（執行 arch-decision.json immediate_fix 項目）
- ✅ notification-events.yaml 建立（11 個事件集中配置，含去重規則）
- ✅ run-agent-team.ps1 已有指數退避重試（backoff = min(60×2^n, 300) + jitter）

**第二次實施（2026-03-11 晚，閉環修復設計 v2 全部落地）：**
- ✅ state/alert-registry.json 建立（去重 bootstrap）
- ✅ frequency-limits.yaml：self_heal trigger_condition + arch_evolution skip_if_condition（防雙重觸發）
- ✅ todoist-auto-arch-evolution.md：步驟 1a 三狀態判斷 + source_audit_score + 步驟 1b 首次執行初始化 + schema execution_status/retry_count
- ✅ self-heal.md：步驟 g 四分支判斷 + execution_status 狀態機（含重試邏輯）+ 步驟 5c act:completed OODA 日誌
- ✅ todoist-query.md：OODA Act 優先覆蓋邏輯（workflow-state.json current_step=act 時強制觸發 self_heal）
- ✅ check-health.ps1：新增 [OODA 閉環健康] 區塊（SH01/SH02/SH03）
- ✅ run-system-audit-team.ps1：新增 Phase 3（Orient 完成後直接觸發 arch-evolution，含今日防重複保護）
- ✅ system-insight.md：新增驗證閉環子步驟（validation loop，驗證 execution_status=success 的修復仍有效）
- ✅ audit-scoring.yaml：dimension 4 新增子項 4.6/4.7/4.8（OODA 週期完整性/immediate_fix 執行率/自愈修復成功率）
- ✅ api-health.json：新增 gun-bot/chatroom-scheduler Circuit Breaker 條目

**剩餘低優先待辦（不影響系統正常運作）：**
- ✅ B2：缺席補執行機制（check-health.ps1 + state/makeup-needed.json）
- ✅ E：Groq-Relay 哨兵進程（bot/watchdog-groq-relay.ps1）
- ✅ P3-b：circuit-breaker-utils.ps1 新增 Test-GunBotHealth 函式

---

## 一、自愈系統理論基礎

### 1.1 業界定義與四大核心組成

根據 digital.ai 的自愈程式碼定義，自愈系統由四大組件構成：

| 組件 | 業界定義 | 本專案對應實作 |
|------|---------|--------------|
| **監測與偵測** | 持續追蹤 KPI、分析日誌、統計演算法偵測異常 | health-scoring（6維度）+ system-insight（7指標）+ LoopDetector |
| **自動錯誤恢復** | 自動重啟服務、回復已知良好狀態、故障轉移 | self-heal（6步驟修復）+ Circuit Breaker 降級 + FSM 殭屍偵測 |
| **機器學習與 AI** | 預測故障、最佳化恢復策略、從歷史學習 | behavior-patterns.json（**待激活**）+ OODA 閉環推理 |
| **設計模式** | 斷路器、重試、超時、艙壁（Bulkhead）隔離 | CircuitBreaker + ErrorClassifier + FSM timeout + Phase 獨立隔離 |

**AI 驅動自愈的核心原則**（來自 digital.ai）：
- 機率匹配閾值：只有當恢復方案匹配機率 > 60% 才執行（本專案對應：arch-evolution 的 priority 評估）
- 暫停/恢復控制：可透過開關控制自愈積極程度（本專案對應：`enabled` 旗標 + `daily_limit`）
- 最小化誤操作：自動修復範圍設有安全邊界，超出邊界通知人工介入

### 1.2 SRE 核心指標

| 指標 | 含義 | 本專案目標 |
|------|------|-----------|
| **MTTD** (Mean Time to Detect) | 問題出現到偵測的平均時間 | < 30 分鐘（下次排程間隔） |
| **MTTR** (Mean Time to Recover) | 問題出現到恢復的平均時間 | < 2 小時（self-heal 自動修復） |
| **Error Budget** | 允許的不可用時間預算 | 99.5% SLO → 每月 3.6 小時 |
| **Toil** | 人工重複操作量 | 目標：所有可自動修復的問題零手動操作 |

### 1.3 五層自愈能力模型

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 4: Evolve（演化學習）                                   │
│  ← behavior-patterns 激活 → 新 Skill 候選識別                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Recover（智慧修復）                                  │
│  ← self-heal（6+步驟）+ arch-evolution（Decide 步驟）          │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Diagnose（根因診斷）                                 │
│  ← system-audit（38子項）+ OODA Orient/Decide                 │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: Detect（異常偵測）                                   │
│  ← health-scoring + system-insight + LoopDetector + FSM       │
├──────────────────────────────────────────────────────────────┤
│  Layer 0: Prevent（預防隔離）                                  │
│  ← Circuit Breaker + Cache 降級 + Hook Guard + 配置驗證       │
└──────────────────────────────────────────────────────────────┘
```

**艙壁（Bulkhead）隔離原則**：本專案的 Phase 獨立執行機制天然實現了艙壁隔離——Phase 1 的 6 個 Agent 彼此獨立，單一 Agent 失敗不影響其他 Agent（不全阻斷）。

### 1.4 OODA 閉環作為自愈引擎

OODA（Boyd 循環）是本專案自愈的核心引擎：
- **Observe**：system-insight Skill → `context/system-insight.json`（7 維度指標）
- **Orient**：system-audit Skill → `context/improvement-backlog.json`（38 子項評分）
- **Decide**：arch-evolution Skill → `context/adr-registry.json`（**目前停用 — 計畫最高優先修復**）
- **Act**：self-heal Skill → 執行修復（6 種自動修復動作）

---

## 二、現況評估

### 2.1 已實施覆蓋（✅ 完成）

| 層級 | 機制 | 狀態 |
|------|------|------|
| Prevent | Hook Guard（pre_bash/write/read_guard） | ✅ 完整 |
| Prevent | Circuit Breaker（5 個 API） | ✅ 完整 |
| Prevent | Cache 降級（4 種 API 快取） | ✅ 完整 |
| Prevent | 排程指數退避重試（backoff+jitter） | ✅ 完整（run-agent-team.ps1） |
| Detect | Health Scoring（6 維度） | ✅ 完整 |
| Detect | FSM 殭屍偵測（running > 2h） | ✅ 完整 |
| Detect | LoopDetector（跨進程持久化） | ✅ 完整 |
| Diagnose | system-insight（Observe 步驟） | ✅ 完整 |
| Diagnose | system-audit（Orient 步驟） | ✅ 完整 |
| Diagnose | arch-evolution（Decide 步驟） | ✅ 2026-03-11 啟用 |
| Recover | self-heal（7 步驟含 arch-decision 執行） | ✅ 完整（步驟 a-g） |
| Evolve | notification-events.yaml（11 事件集中配置） | ✅ 2026-03-11 建立 |

### 2.2 剩餘缺口（❌ 待實施）

| 優先 | 缺口 | 影響 | 對應層級 |
|------|------|------|---------|
| **P1** | `state/alert-registry.json` 缺失 | notification-events.yaml 去重機制無法運作 | Detect |
| **P1** | Gun-Bot/Chatroom 無 Circuit Breaker | Chatroom 離線無告警（api-health.json 缺條目）| Detect |
| **P2** | 缺席補執行機制（makeup-run） | 長時間停機後無補救 | Recover |
| **P2** | behavior-patterns.json 無自動產出 | 行為模式學習功能未激活 | Evolve |
| **P3** | Skill 級別無降級機制 | Skill 永久失敗無回退 | Recover |
| **P3** | Groq-Relay 進程無 watchdog | hackernews 摘要單點故障 | Prevent |

---

## 三、實施方案

### Phase A：完成 OODA 決策閉環（P0）✅ **已完成**

> **2026-03-11**：全部完成。
> - `prompts/team/todoist-auto-arch-evolution.md` ✅（7 步驟，含 ntfy 通知）
> - `config/ooda-workflow.yaml` decide.enabled=true ✅
> - `templates/auto-tasks/self-heal.md` 步驟 g ✅（arch-decision 執行 + executed 追蹤）
> - `config/frequency-limits.yaml` arch_evolution 任務 ✅（order=17, daily_limit=1）

#### A1. 建立 `prompts/team/todoist-auto-arch-evolution.md`

**職責**（根據首次手動執行驗證的流程）：
1. 讀取 `context/improvement-backlog.json`（問題清單）
2. 讀取 `context/adr-registry.json`（已有決策歷史，避免重複）
3. 對每個 backlog 項目，決定分類（參考 2026-03-11 執行經驗）：
   - `immediate_fix`：low effort + 操作明確 + 不影響核心架構（如 YAML 注釋、pip-audit 新增）
   - `schedule_adr`：medium/high effort 或需人工確認（如 CI 建立、覆蓋率提升）
   - `wontfix`：明確不符合現有架構選擇（如跨平台排程）
   - `deferred`：高效益但需 POC 驗證（如依賴注入）
4. 更新 `context/adr-registry.json`（新增或更新 ADR 條目）
5. 寫入 `context/arch-decision.json`（act 步驟讀取，含 immediate_fix 的詳細操作指令）
6. 更新 `context/workflow-state.json` 標記 decide=completed
7. 輸出 `task_result.txt` + `DONE_CERT`

**決策規則**（決策樹，納入 prompt 中）：
```
effort=low AND 無架構影響 → immediate_fix
effort=medium AND 需確認環境 → schedule_adr（加 note 說明前提條件）
effort=high AND 影響範圍廣 → deferred（分階段計畫）
與現有 ADR 架構原則衝突 → wontfix（明確記錄理由）
```

**`context/arch-decision.json` schema**：
```json
{
  "version": 1,
  "generated_at": "ISO 8601",
  "generated_by": "arch-evolution",
  "decisions": [
    {
      "backlog_id": "ADR-YYYYMMDD-NNN",
      "action": "immediate_fix | schedule_adr | wontfix | deferred",
      "priority": "high | medium | low",
      "fix_instructions": "給 self-heal 的具體操作說明（immediate_fix 必填）",
      "estimated_minutes": 15,
      "verification": "如何驗證修復成功"
    }
  ],
  "immediate_fix_summary": {
    "count": 3,
    "safe_to_automate": true
  }
}
```

#### A2. 啟用 `config/ooda-workflow.yaml` 的 Decide 步驟

修改：`enabled: false` → `enabled: true`

#### A3. 強化 `templates/auto-tasks/self-heal.md`（步驟 g）

新增步驟 g：讀取 `context/arch-decision.json`，執行 `action=immediate_fix` 的項目，每次執行限 3 項以確保安全性。每完成一項後在 arch-decision.json 標記 `executed: true`，避免重複執行。

---

### Phase B：強化排程韌性（P0）✅ **B1 已完成，B2 待實施**

#### B1. 排程重試策略升級 ✅ **已完成**

> `run-agent-team.ps1` 已實作指數退避：`backoff = min(60 × 2^attempt, 300) + jitter(0~15s)`
> 無需再建立 `retry-policy.yaml`（邏輯已硬編碼在 PS1 中，屬合理範圍）

#### B2. 缺席偵測與補執行（Makeup Run）❌ **待實施**

在 `check-health.ps1` 新增偵測邏輯：
- 若 daily-digest-am（08:00）超過 2 小時未執行 → 觸發 ntfy urgent 通知
- 自動寫入 `state/makeup-needed.json`，下次 todoist 排程啟動時先讀取並補執行

新建 `templates/shared/makeup-run-check.md`（共用前言元素）：
```
在執行本次任務前，先讀取 state/makeup-needed.json：
- 若存在且 pending=true → 先執行缺席的摘要任務，再繼續本次任務
```

---

### Phase C：擴展監控覆蓋（P1）❌ **待實施**

> **最關鍵缺口**：`state/alert-registry.json` 未建立，導致 notification-events.yaml 去重機制無法運作。
> 建議優先建立此 bootstrap 檔案（純 JSON，幾乎無風險）。

#### C0. 建立 `state/alert-registry.json`（新增，最高優先）

新建 bootstrap 檔案，供 notification-events.yaml 的去重邏輯使用：
```json
{
  "version": 1,
  "updated_at": "2026-03-11T00:00:00+08:00",
  "alerts": {},
  "self_healing": {
    "last_decide_notify": null,
    "last_heal_notify": null,
    "total_heals_today": 0,
    "total_fixes_today": 0
  }
}
```

#### C1. Gun-Bot API 加入 Circuit Breaker

修改 `state/api-health.json` schema，新增 `gun-bot` 和 `chatroom-scheduler` 兩個 API 的 circuit breaker 條目。

修改 `circuit-breaker-utils.ps1`，新增 `Test-GunBotHealth` 函式：
- 呼叫 `http://localhost:3001/health`（bot healthcheck 端點）
- 回傳 open/closed/half_open 狀態

修改 `run-agent-team.ps1` 的 Phase 0 預檢查，新增 gun-bot 健康確認。

#### C2. 行為模式自動產出

修改 `templates/auto-tasks/system-insight.md`，新增步驟：
- 分析 `logs/structured/` 最近 7 天 JSONL，識別高頻工具組合（≥5 次相同序列）
- 將置信度 ≥ 80% 的模式寫入 `context/behavior-patterns.json`
- 格式：`{ "pattern_id", "sequence", "frequency", "confidence", "suggested_skill" }`

#### C3. 告警去重機制

新建 `state/alert-registry.json`（告警去重表）：
```json
{
  "alerts": {
    "cache_hit_ratio_low": {
      "first_seen": "2026-03-09T00:00:00+08:00",
      "last_seen": "2026-03-11T00:00:00+08:00",
      "count": 3,
      "suppressed_until": "2026-03-14T00:00:00+08:00"
    }
  }
}
```

修改 `hooks/on_stop_alert.py`：相同問題的 warning 告警，每 3 天最多推送 1 次。critical 告警不受去重限制。

---

### Phase D：智慧修復強化（P1-P2）

#### D1. 快取命中率自動優化

在 self-heal 步驟 g（執行 arch-decision 後）新增子步驟：
- 讀取 `system-insight.json` 的 cache_hit_ratio
- 若 < 30%（critical）→ 讀取 `config/cache-policy.yaml`，自動延長 TTL（原值 × 1.5，上限 48h）
- 寫入修改並記錄到修復報告

修改的關鍵檔案：
- `templates/auto-tasks/self-heal.md`（新增步驟 h）
- `config/cache-policy.yaml`（TTL 上限定義）

#### D2. Skill 級別降級機制

新建 `config/skill-fallback.yaml`：
```yaml
version: 1
fallbacks:
  groq:
    on_failure: claude  # Groq 失敗 → 改用 Claude
    max_latency_ms: 5000
  hackernews-ai-digest:
    on_failure: cached  # API 故障 → 使用昨日快取
  knowledge-query:
    on_failure: skip    # KB 離線 → 跳過（不中斷流程）
```

修改 `skills/SKILL_INDEX.md` 加入 fallback 欄位，方便各 Skill 查詢降級策略。

---

### Phase E：Groq-Relay 哨兵（P3）

新增 `bot/watchdog-groq-relay.ps1`：
- 每 5 分鐘檢查 Groq-Relay 進程（Get-Process groq-relay）
- 若不存在 → 等待 10 秒重試 → 仍不存在 → 自動重啟 + ntfy 通知
- 整合到 HEARTBEAT.md 的排程

---

### Phase F：ntfy 自主通知層（P0 — 貫穿所有 Phase）

**目標**：讓自愈機制的每個關鍵決策與動作都透過 ntfy 即時告知，實現「透明自主運作」。

#### F1. 集中式通知事件配置

新建 `config/notification-events.yaml`，集中定義所有自愈相關通知規則：

```yaml
version: 1
topic: "wangsc2025"  # 與現有 ntfy 配置一致
# 以下事件在對應 prompt/script 中讀取此配置發送通知

events:
  # OODA 閉環事件
  ooda_decide_start:
    title: "🔍 arch-evolution 啟動"
    message_template: "OODA Decide 步驟開始 | 審查分數 {score} | 待處理 {backlog_count} 項"
    priority: 2   # low — 進度通知，不打擾
    tags: ["computer", "chart"]
    condition: "always"

  ooda_decide_done:
    title: "📋 架構決策完成"
    message_template: "immediate_fix {fix_count} 項 | schedule_adr {adr_count} 項 | wontfix {wontfix_count} 項"
    priority: 3   # default
    tags: ["white_check_mark", "computer"]
    condition: "always"

  # self-heal 事件
  self_heal_start:
    title: "🔧 自愈迴圈啟動"
    message_template: "計畫修復 {planned} 項（含 arch-decision {arch_count} 項）"
    priority: 2
    tags: ["hourglass_flowing_sand"]
    condition: "has_repairs"  # 有待修復項才通知

  self_heal_done_success:
    title: "✅ 自愈完成"
    message_template: "修復 {success}/{total} 項 | {details}"
    priority: 2
    tags: ["white_check_mark"]
    condition: "always"

  self_heal_done_partial:
    title: "⚠️ 自愈部分失敗"
    message_template: "成功 {success}/{total} 項 | 失敗：{failed_items}"
    priority: 3
    tags: ["warning"]
    condition: "has_failures"

  self_heal_done_failed:
    title: "❌ 自愈失敗 — 需人工介入"
    message_template: "全部 {total} 項修復失敗 | 錯誤：{error_summary}"
    priority: 5   # urgent
    tags: ["fire", "x"]
    condition: "all_failed"

  # Circuit Breaker 事件
  circuit_breaker_open:
    title: "🔴 API 斷路"
    message_template: "{api_name} 連續失敗 {count} 次 → 斷路器開啟 | 使用快取降級"
    priority: 4
    tags: ["x", "warning"]
    condition: "on_state_change"

  circuit_breaker_recovered:
    title: "✅ API 恢復"
    message_template: "{api_name} 恢復正常 | 斷路器關閉"
    priority: 2
    tags: ["white_check_mark"]
    condition: "on_state_change"

  # 排程事件
  schedule_retry:
    title: "🔄 排程重試"
    message_template: "{schedule_name} 失敗 → 第 {attempt}/{max} 次重試（{delay}s 後）"
    priority: 3
    tags: ["warning"]
    condition: "on_retry"

  schedule_makeup_needed:
    title: "⏳ 補執行提醒"
    message_template: "{schedule_name} 超過 {elapsed_hours}h 未執行 → 已標記補執行"
    priority: 4
    tags: ["warning", "hourglass_flowing_sand"]
    condition: "always"

  schedule_all_retries_failed:
    title: "❌ 排程徹底失敗"
    message_template: "{schedule_name} 重試 {max} 次全部失敗 | 今日摘要中斷"
    priority: 5
    tags: ["fire", "x"]
    condition: "always"
```

#### F2. 各組件的通知整合點

| 組件 | 事件 | 實作位置 |
|------|------|---------|
| `prompts/team/todoist-auto-arch-evolution.md` | ooda_decide_start / ooda_decide_done | prompt 步驟 1（開始）、步驟 7（結束） |
| `templates/auto-tasks/self-heal.md` | self_heal_start / done_{outcome} | 步驟開始前、步驟 5（現有修復報告升級） |
| `hooks/on_stop_alert.py` | circuit_breaker_open/recovered | 已有 API 告警機制，整合 notification-events.yaml |
| `run-agent-team.ps1` | schedule_retry / schedule_makeup_needed / schedule_all_retries_failed | Phase retry 邏輯（Phase B1/B2） |

#### F3. 通知格式規範

所有自愈通知遵循 ntfy-notify SKILL 標準（JSON 檔案 + charset=utf-8），額外規範：
- **標題**：≤ 20 字，含 emoji 前綴快速識別事件類型
- **內容**：≤ 100 字，含關鍵數字（修復 M/N 項）與失敗原因摘要
- **去重**：warning 級別事件同一問題每 3 天最多 1 次（讀取 `state/alert-registry.json`）
- **不通知**：observe 完成（太頻繁）、orient 完成（已有現有系統審查通知）

#### F4. 通知狀態追蹤

在 `state/alert-registry.json` 新增 `self_healing` 區塊：
```json
{
  "self_healing": {
    "last_decide_notify": "2026-03-11T01:10:00+08:00",
    "last_heal_notify": "2026-03-11T01:30:00+08:00",
    "total_heals_today": 1,
    "total_fixes_today": 3
  }
}
```

---

## 四、關鍵檔案

### 需修改的現有檔案

| 檔案 | 修改內容 |
|------|---------|
| `config/ooda-workflow.yaml` | `decide.enabled: false` → `true` |
| `templates/auto-tasks/self-heal.md` | 新增步驟 g（arch-decision 執行）、步驟 h（快取 TTL 自動調整） |
| `templates/auto-tasks/system-insight.md` | 新增行為模式分析段落 |
| `run-agent-team.ps1` | 重試邏輯改為讀 retry-policy.yaml |
| `run-system-audit-team.ps1` | 同上 |
| `circuit-breaker-utils.ps1` | 新增 Test-GunBotHealth、Gun-Bot 條目 |
| `state/api-health.json` | 新增 gun-bot、chatroom-scheduler 條目 |
| `hooks/on_stop_alert.py` | 告警去重邏輯 |
| `check-health.ps1` | 缺席偵測區塊 |

### 需新建的檔案

| 檔案 | 說明 |
|------|------|
| `prompts/team/todoist-auto-arch-evolution.md` | ✅ 已建立（2026-03-11） |
| `config/retry-policy.yaml` | ❌ 不需建立（指數退避已硬編碼於 PS1） |
| `config/notification-events.yaml` | ✅ 已建立（2026-03-11） |
| `config/skill-fallback.yaml` | ❌ 待建立（P3 低優先） |
| `context/arch-decision.json` | ✅ 已建立（2026-03-11 首次 arch-evolution） |
| `state/alert-registry.json` | ❌ **待建立（P1 — 去重機制 bootstrap 檔）** |
| `state/makeup-needed.json` | 缺席補執行觸發標記 |
| `bot/watchdog-groq-relay.ps1` | Groq-Relay 哨兵進程 |

---

## 五、實施順序（依優先級）

```
Phase A（完成 OODA 閉環）
  ├─ A1: 建立 arch-evolution.md prompt（最重要，解鎖整個 OODA 閉環）
  ├─ A2: 啟用 ooda-workflow.yaml decide 步驟
  └─ A3: self-heal 新增步驟 g（讀取 arch-decision.json）

Phase B（排程韌性）
  ├─ B1: 建立 retry-policy.yaml + 修改重試邏輯
  └─ B2: check-health.ps1 缺席偵測 + makeup-needed.json

Phase C（監控擴展）
  ├─ C1: Gun-Bot Circuit Breaker
  ├─ C2: 行為模式自動產出
  └─ C3: alert-registry.json 去重機制

Phase D（智慧修復）
  ├─ D1: 快取 TTL 自動調整（self-heal 步驟 h）
  └─ D2: skill-fallback.yaml

Phase E（哨兵）
  └─ E1: watchdog-groq-relay.ps1

Phase F（ntfy 自主通知層）— 貫穿所有 Phase
  ├─ F1: 建立 config/notification-events.yaml ✅（2026-03-11 完成）
  ├─ F2: arch-evolution prompt 加入通知 ✅（prompt 內已實作）
  ├─ F3: self-heal.md 升級步驟 5 ✅（始終通知，3 種 outcome 分級）
  ├─ F4: run-agent-team.ps1 加入 schedule_retry/makeup 通知 ← 配合 B2 實施
  └─ F5: state/alert-registry.json 建立（去重狀態持久化）← C0 實施
```

---

## 六、驗證方法

### 端到端驗證清單

| 驗證點 | 方法 | 預期結果 |
|--------|------|---------|
| OODA 閉環完整性 | 手動觸發 run-system-audit-team.ps1 → 觀察 workflow-state.json | steps: observe→orient→decide→act，decide 不再是 skip |
| arch-evolution 執行 | 確認 context/arch-decision.json 生成 | 包含 decisions 陣列，每項有 action 欄位 |
| self-heal 步驟 g | 觀察修復報告 | repairs_attempted 包含 arch-decision 項目 |
| 排程重試 | 手動中斷網路 30 秒，觀察日誌 | 出現 retry attempt 2/3，後續成功執行 |
| Gun-Bot 監控 | 停止 gun-bot 進程 → 執行 check-health.ps1 | 出現 [Gun-Bot: OPEN] 告警 |
| 告警去重 | 連續 3 天 cache_hit_ratio < 40% | ntfy 每 3 天僅推送 1 次 warning |
| 快取 TTL 優化 | system-insight 顯示 cache_hit_ratio < 30% → 下次 self-heal 後 | config/cache-policy.yaml TTL 值自動延長 |
| behavior-patterns | 執行後觀察 context/behavior-patterns.json | 出現 ≥1 個 confidence ≥ 0.8 的模式 |

### 健康分數目標

實施完成後，預期健康分數從 **85 → 92+**：
- cache_hit_rate: 14.57% → 40%（+8 分）
- streak_continuity: 因補執行機制提升（+3 分）
- error_rate: 因重試策略改善（+2 分）

---

## 七、設計決策

### 為何 arch-evolution 使用 Todoist 自動任務模式？

與其建立全新執行機制，arch-evolution 沿用 `todoist-auto-*.md` 的既有 round-robin 觸發框架，優點：
1. 不需修改 PS 腳本層，只需新增 prompt 檔案
2. 自動受 frequency-limits.yaml 的 daily_limit 保護（預設 1 次/日）
3. OODA 的 decide 步驟由 ooda-workflow.yaml 的 `on_success: "decide"` 觸發，不是 Todoist 任務，兩者不衝突

### 為何採用 `arch-decision.json` 作為中介檔案？

Decide（arch-evolution）與 Act（self-heal）是分開的 Agent 執行：
- arch-evolution 決策 → 寫入 arch-decision.json
- self-heal 讀取 arch-decision.json → 執行 immediate_fix 項目
- 符合文件驅動架構原則（ADR-002）：資料交換透過檔案而非記憶體

### 為何 Phase E（Groq-Relay 哨兵）排最後？

Groq-Relay 僅影響 hackernews 摘要（非核心），且現有 Circuit Breaker 已能優雅降級（使用昨日快取）。Phase A-D 的改善影響面更廣，優先實施效益更高。

---

## 八、工作流審查發現問題（2026-03-11）

深度審查 OODA 工作流程後，發現以下斷點與邊界不清問題：

### 8.1 嚴重問題（P0/P1 — 必修）

| # | 嚴重度 | 標題 | 影響 | 修復位置 |
|---|--------|------|------|---------|
| 3 | **P0** | self_heal 缺 trigger_condition | 每日強制執行，不管 OODA 狀態 | `config/frequency-limits.yaml` |
| 1 | **P1** | arch-evolution 步驟 1b 無初始化 fallback | 首次執行（adr-registry.json 不存在）直接崩潰 | `prompts/team/todoist-auto-arch-evolution.md` |
| 2 | **P1** | source_audit_score 來源不明 | prompt 未說明從 backlog.total_score 取得 | `prompts/team/todoist-auto-arch-evolution.md` |
| 5 | **P1** | 雙重觸發機制（round-robin + OODA on_success） | arch-evolution 可能同日被啟動 2 次 | `config/frequency-limits.yaml` |
| 4 | **P1** | self_heal 步驟 g 缺 arch-decision 三分支判斷 | 降級行為定義不清 | `templates/auto-tasks/self-heal.md` |
| 9 | **P2** | immediate_fix 失敗後不重試 | executed=true 標記即使 result=failed | `templates/auto-tasks/self-heal.md` |
| 8 | **P2** | backlog 為空 vs 不存在/損壞 視為相同 | 掩蓋系統審查失敗 | `prompts/team/todoist-auto-arch-evolution.md` |

### 8.2 具體修復指引

**修復 #3（P0）** — `config/frequency-limits.yaml`：
```yaml
self_heal:
  trigger_condition: "每日常規輪轉，若 workflow-state current_step=act 優先觸發"
```

**修復 #1（P1）** — `prompts/team/todoist-auto-arch-evolution.md` 步驟 1b：
```
若 adr-registry.json 不存在 → 建立初始結構：
{"version": 2, "records": [], "summary": {"total":0,"proposed":0,"accepted":0,"deferred":0,"wontfix":0}}
```

**修復 #2（P1）** — `prompts/team/todoist-auto-arch-evolution.md` 步驟 1a：
```
記錄 backlog.total_score 作為 source_audit_score；若欄位缺失，使用 0 並備註「audit_score 不可用」
```

**修復 #5（P1）** — `config/frequency-limits.yaml`：
```yaml
arch_evolution:
  daily_limit: 1  # 保持，但新增：
  skip_if_condition: "adr-registry.json 最新條目 decided_at 距今 < 4h（避免重複執行）"
```

**修復 #4（P1）** — `templates/auto-tasks/self-heal.md` 步驟 g：
```
狀態三分支：
1. 存在 + <= 48h → 執行 immediate_fix
2. 存在 + > 48h  → 跳過 + warning 告警
3. 不存在 + workflow-state decide=completed → critical 告警（決策結果遺失）
4. 不存在 + 無 decide 記錄 → info 記錄（OODA 尚未執行到 Decide）
```

**修復 #9（P2）** — `templates/auto-tasks/self-heal.md` 步驟 g：
```
成功：executed=true, execution_result="success"
失敗：保留 executed=false（允許下次重試）；記錄 execution_result="failed", retry_count++
若 retry_count >= 3：execution_result="failed_max_retry"，不再重試
```

**修復 #8（P2）** — `prompts/team/todoist-auto-arch-evolution.md` 步驟 1a：
```
三分支判斷：
1. 存在 + items > 0 → 正常執行
2. 存在 + items = [] → 跳到步驟 6（backlog 清空），priority=2 info 通知
3. 不存在或 JSON 解析失敗 → 跳到步驟 6，priority=4 error 通知（審查失敗）
```

### 8.3 剩餘工作優先序（含審查新增）

| 優先 | 工作項 | 檔案 | 風險 | 估時 |
|------|--------|------|------|------|
| **P0** | 修復 #3：self_heal trigger_condition | `config/frequency-limits.yaml` | 極低 | 5 分 |
| **P1-a** | 修復 #1：arch-evolution 步驟 1b fallback | `prompts/team/todoist-auto-arch-evolution.md` | 低 | 10 分 |
| **P1-b** | 修復 #2：source_audit_score 來源說明 | `prompts/team/todoist-auto-arch-evolution.md` | 低 | 5 分 |
| **P1-c** | 修復 #5：arch_evolution skip_if 條件 | `config/frequency-limits.yaml` | 低 | 10 分 |
| **P1-d** | 修復 #4：self_heal 步驟 g 三分支 | `templates/auto-tasks/self-heal.md` | 低 | 15 分 |
| **P1-e** | 建立 `state/alert-registry.json`（去重 bootstrap） | 新建 JSON | 極低 | 5 分 |
| **P2-a** | 修復 #9：immediate_fix 失敗不標記 executed | `templates/auto-tasks/self-heal.md` | 低 | 10 分 |
| **P2-b** | 修復 #8：backlog 三狀態判斷 | `prompts/team/todoist-auto-arch-evolution.md` | 低 | 10 分 |
| **P2-c** | `state/api-health.json` 新增 gun-bot/chatroom | Edit JSON | 低 | 10 分 |
| **P3-a** | `circuit-breaker-utils.ps1` `Test-GunBotHealth` | Edit PS1 | 中 | 20 分 |
| **P3-b** | 行為模式自動產出（system-insight.md 新增段落） | Edit MD | 低 | 15 分 |
| **P3-c** | `config/skill-fallback.yaml` 建立 | 新建 YAML | 極低 | 10 分 |
| **P3-d** | `bot/watchdog-groq-relay.ps1` 建立 | 新建 PS1 | 低 | 20 分 |

---

## 九、完整閉環重設計（2026-03-11 深度審查後修正）

### 9.1 架構真相：OODA 是 round-robin 驅動，非狀態機驅動

深度審查發現前次設計基於錯誤假設。實際機制如下：

```
【設計預期（ooda-workflow.yaml）】     【實際執行機制】
Observe → Orient → Decide → Act        run-system-audit-team.ps1（00:40 daily）
   ↕ 狀態機轉移                              Phase 1+2: Observe + Orient
workflow-state.json 驅動執行              PS1: Set-OodaState（純日誌記錄）

                                         Todoist round-robin（每 30 分）
                                           → arch-evolution（order 17）
                                           → self-heal（order 18）
                                           ← 無 OODA 狀態檢查
```

**關鍵發現**：
1. `workflow-state.json` 是**純觀測日誌**，不驅動任何任務的觸發或跳過
2. `ooda-workflow.yaml` 是**設計文件**（描述願景），無任何程式碼讀取其 `on_success` 鏈
3. `arch-evolution`（order 17）和 `self-heal`（order 18）由 round-robin 按日輪轉

**前次設計的誤修復**（需撤回）：
- ~~NEW-1：self-heal 重置 current_step 到 "observe"~~ → workflow-state 只是日誌，重置無效果
- ~~NEW-2：system-insight 更新 workflow-state~~ → PS1 已處理，LLM 重複寫入產生衝突

### 9.2 真正的閉環問題：Decide/Act 延遲

系統審查（Orient）在 00:40 完成後：
- arch-evolution 最快在下次 Todoist 半點執行時被選中
- 若前 16 個任務（order 1-16）當日未執行，arch-evolution 可能推遲到**下午才執行**
- self-heal（order 18）又在 arch-evolution 之後，可能延遲到**晚上**

**延遲問題量化**：21 個任務 × round-robin，最壞情況 arch-evolution 等待 ~10 小時

### 9.3 閉環修復設計 v2（正確版）

**核心策略**：在 `todoist-query.md` 加入 OODA 優先權覆蓋，當 workflow-state 顯示 decide/act pending 時，下一次 Todoist 執行優先選取對應任務，將延遲從「數小時」壓縮到「< 30 分鐘」。

#### 修復 NEW-1（最終版）：run-system-audit-team.ps1 Phase 3 直接觸發 arch-evolution

**為何不改 todoist-query.md**：todoist-query.md 是 LLM 執行的 prompt，優先覆蓋邏輯依賴 LLM 判斷，不夠可靠（LLM 可能忽略或誤判）。更可靠的機制是 PS1 腳本層的直接觸發。

**在 `run-system-audit-team.ps1` Phase 2 成功後（第 614 行之後）新增 Phase 3**：

```powershell
# === Phase 3: Decide（arch-evolution，若 improvement-backlog 非空）===
Write-Host "[Phase 3] OODA Decide 階段" -ForegroundColor Cyan
$backlogFile = Join-Path $AgentDir "context\improvement-backlog.json"
$archDecisionFile = Join-Path $AgentDir "context\arch-decision.json"

# 防重複執行：若今日已產出 arch-decision.json，跳過
$skipArch = $false
if (Test-Path $archDecisionFile) {
    $ad = Get-Content $archDecisionFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($ad -and $ad.generated_at) {
        $genDate = ([datetime]$ad.generated_at).ToString("yyyy-MM-dd")
        if ($genDate -eq (Get-Date -Format "yyyy-MM-dd")) {
            Write-Host "  [Phase 3] arch-decision.json 今日已產出，跳過" -ForegroundColor Yellow
            $skipArch = $true
        }
    }
}

if (-not $skipArch -and (Test-Path $backlogFile)) {
    $backlog = Get-Content $backlogFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($backlog -and $backlog.items.Count -gt 0) {
        Write-Host "  [Phase 3] backlog $($backlog.items.Count) 項，觸發 arch-evolution..." -ForegroundColor Green
        $archPrompt = Get-Content (Join-Path $AgentDir "prompts\team\todoist-auto-arch-evolution.md") -Raw -Encoding UTF8
        $archOutput = $archPrompt | claude -p --allowedTools "Read,Write,Edit,Bash,Glob,Grep" 2>$null
        Write-Host "  [Phase 3] arch-evolution 完成" -ForegroundColor Green
    } else {
        Write-Host "  [Phase 3] backlog 為空，跳過 arch-evolution" -ForegroundColor Yellow
    }
} elseif (-not (Test-Path $backlogFile)) {
    Write-Host "  [Phase 3] improvement-backlog.json 不存在，跳過" -ForegroundColor Yellow
}
```

**觸發效果**：system-audit（00:40 ~ 01:00 完成）→ 立即觸發 arch-evolution（Phase 3，~01:15 完成）→ 無需等待 round-robin。

**防重複保護**：若 arch-decision.json 今日已存在，Phase 3 跳過（避免 round-robin 再次觸發時重複）。

**注意**：`auto-tasks-today.json` 目前無 `arch_evolution_count` 欄位，需在 `context/auto-tasks-today.json` 新增此欄位（預設 0），確保 Todoist round-robin 的去重機制能正確追蹤。

#### 修復 NEW-1b：todoist-query.md 加入 OODA Act 優先覆蓋（限 Decide→Act 步驟）

arch-evolution（Decide）由 PS1 直接觸發，self-heal（Act）仍由 Todoist round-robin 觸發，但需優先：

在 `prompts/team/todoist-query.md` 步驟 2.5（自動任務選擇）前新增：
```markdown
**OODA Act 優先覆蓋**（在 round-robin 之前執行）：
讀取 `context/workflow-state.json`：
- 若 current_step="act" 且 status="pending" 且 context/arch-decision.json 存在且 <= 48h
  → 強制將 self_heal 加入本次任務清單（即使不在本輪 round-robin 輪次）
  → 記錄：「OODA Act 覆蓋：arch-decision 待執行」
- 其他情況：正常 round-robin 邏輯
```

**觸發效果**：arch-evolution（PS1 Phase 4）完成寫入 arch-decision.json 後，下一次 Todoist 半點執行（最多 30 分鐘後）即自動執行 self-heal。

#### 修復 NEW-2（重新定義）：self-heal 正確記錄 Act 完成

`self-heal.md` 步驟 5 末尾：追加 history 條目 + 更新 current_step（觀測目的）：

```markdown
**5c. 記錄 Act 完成（OODA 日誌）**
用 Read 讀取 `context/workflow-state.json`，追加：
{ "status": "completed", "step": "act", "ts": "ISO 8601", "repairs": "M/N" }
更新：current_step="complete"，status="completed"
（備註：下次 run-system-audit-team.ps1 執行時自動開始新週期，無需手動重置）
```

#### 修復 NEW-3：check-health.ps1 OODA 健康監控

```powershell
Write-Host "[OODA 閉環健康]" -ForegroundColor Cyan
$wf = Get-Content "context\workflow-state.json" | ConvertFrom-Json
$staleH = ([datetime]::Now - [datetime]$wf.updated_at).TotalHours

# 停滯超過 25 小時（正常 24h 週期 + 1h 容忍）
if ($staleH -gt 25) {
    Write-Host "  ⚠️ OODA 停滯 $([int]$staleH)h - 步驟：$($wf.current_step)" -ForegroundColor Red
}
# decide pending 超過 2 小時（2 次 Todoist 輪轉未執行 arch-evolution）
$decideEntry = $wf.history | Where-Object { $_.step -eq "decide" -and $_.status -eq "pending" } | Select-Object -Last 1
if ($decideEntry) {
    $waitH = ([datetime]::Now - [datetime]$decideEntry.ts).TotalHours
    if ($waitH -gt 2) {
        Write-Host "  ⚠️ arch-evolution 等待 $([int]$waitH)h 尚未執行" -ForegroundColor Yellow
    }
}
# arch-decision.json 過期但 self-heal 仍未執行
if (Test-Path "context\arch-decision.json") {
    $ad = Get-Content "context\arch-decision.json" | ConvertFrom-Json
    $ageH = ([datetime]::Now - [datetime]$ad.generated_at).TotalHours
    $unexecuted = ($ad.decisions | Where-Object { $_.action -eq "immediate_fix" -and $_.execution_status -notin @("success","failed_max_retry") }).Count
    if ($ageH -gt 48 -and $unexecuted -gt 0) {
        Write-Host "  ❌ arch-decision 過期 ($([int]$ageH)h)，$unexecuted 項未執行" -ForegroundColor Red
    }
}
```

### 9.4 Meta-監控：自愈機制監控自身健康

**為何不新增第 8 維度**：`config/audit-scoring.yaml` 現有 7 維度權重加總精確 100%，新增維度必須重新分配所有權重，破壞現有評分基準線和歷史比對。

**替代方案：擴充現有「系統工作流」維度（dimension 4，weight: 15%）**，新增 3 個自愈子項：

```yaml
# config/audit-scoring.yaml 現有 dimension 4 的末尾新增
- id: "4.6"
  name: "OODA 週期完整性"
  max_score: 5
  check: "workflow-state.json history 最近 7 天有 orient+act 週期各 ≥ 4 次"
  scoring: "5=7天完整/4=5-6天/3=3-4天/1=1-2天/0=無"

- id: "4.7"
  name: "immediate_fix 執行率"
  max_score: 5
  check: "arch-decision.json 中 execution_status=success 的比例"
  scoring: "5=>=80%/3=>=50%/1=>=20%/0=<20%（或 arch-decision 不存在）"

- id: "4.8"
  name: "自愈修復成功率"
  max_score: 5
  check: "最近 7 天 self-heal 的 repairs_succeeded / repairs_attempted 平均"
  scoring: "5=>=80%/3=>=50%/1=>=20%/0=無資料"
```

**注意**：這會把「系統工作流」維度的子項數從 5→8，max_score 增加。需同時調整 audit-scoring.yaml 的 `dimension_max_score` 計算方式，確保 7 維度總權重仍為 100%。

### 9.4b arch-decision.json 執行狀態精煉

**問題**：目前 `executed: true/false` 是布林值，無法追蹤重試次數和失敗原因。

**改為枚舉狀態** `execution_status`（修改 `prompts/team/todoist-auto-arch-evolution.md` 步驟 4 的 schema）：

```json
{
  "backlog_id": "ADR-20260311-012",
  "action": "immediate_fix",
  "execution_status": "pending",  // pending | success | failed_retry | failed_max_retry
  "retry_count": 0,               // 0-3
  "executed_at": null,
  "execution_result": null,
  "execution_note": null
}
```

**self-heal 步驟 g 的篩選邏輯更新**：
```
執行條件：execution_status="pending" OR (execution_status="failed_retry" AND retry_count < 3)
執行成功後：execution_status="success"
執行失敗後：
  - retry_count < 2 → execution_status="failed_retry", retry_count++
  - retry_count >= 2 → execution_status="failed_max_retry"（放棄，記錄告警）
```

### 9.4c 驗證閉環（Validation Loop）

**缺失的閉環步驟**：目前 OODA 沒有「驗證修復是否有效」的機制。修復後的分數改善應反映在下次 system-audit 評分中。

**在 system-insight.md（Observe 步驟）新增驗證子步驟**：
```markdown
**驗證子步驟（若 arch-decision.json 有 execution_status=success 的項目）**：
對每個最近執行成功的 immediate_fix 項目：
1. 讀取其 verification 欄位描述的驗證方法
2. 重新執行驗證（Grep/Read 確認修改已生效）
3. 記錄驗證結果到 arch-decision.json 的 validation_result 欄位
4. 若驗證失敗（修復已執行但效果消失）→ 重置 execution_status="pending"（觸發重修）
```

這個驗證閉環確保「執行過」的修復是真正有效的，不是靜默失敗的假修復。

### 9.5 最終完整實施優先序

| 優先 | 修復 ID | 工作項 | 修改檔案 | 估時 |
|------|---------|--------|---------|------|
| **P0-1** | NEW-1 | run-system-audit-team.ps1 Phase 4：直接觸發 arch-evolution | `run-system-audit-team.ps1` | 20 分 |
| **P0-2** | NEW-1b | todoist-query.md：OODA Act 優先覆蓋（Decide→Act） | `prompts/team/todoist-query.md` | 15 分 |
| **P1-a** | NEW-2 | self-heal 步驟 5c：記錄 act 完成（workflow-state 日誌） | `templates/auto-tasks/self-heal.md` | 10 分 |
| **P1-b** | NEW-3 | check-health.ps1：OODA 健康監控區塊 | `check-health.ps1` | 20 分 |
| **P1-c** | #1 | arch-evolution 步驟 1b：adr-registry 首次執行初始化 | `prompts/team/todoist-auto-arch-evolution.md` | 10 分 |
| **P1-d** | #2+#8 | arch-evolution 步驟 1a：source_audit_score + backlog 三狀態 | `prompts/team/todoist-auto-arch-evolution.md` | 15 分 |
| **P1-e** | #4+9b | self-heal 步驟 g：四分支判斷 + execution_status 狀態機（棄布林 executed） | `templates/auto-tasks/self-heal.md` | 25 分 |
| **P1-f** | 9b | arch-evolution 步驟 4 schema：execution_status 欄位 | `prompts/team/todoist-auto-arch-evolution.md` | 10 分 |
| **P1-g** | — | 建立 `state/alert-registry.json`（去重 bootstrap） | 新建 JSON | 5 分 |
| **P1-h** | #3 | frequency-limits.yaml self_heal trigger_condition 補充 | `config/frequency-limits.yaml` | 5 分 |
| **P2-a** | 9c | system-insight.md：驗證閉環子步驟（validation loop） | `templates/auto-tasks/system-insight.md` | 20 分 |
| **P2-b** | 9.4 | audit-scoring.yaml dimension 4 新增 4.6/4.7/4.8 子項 | `config/audit-scoring.yaml` | 15 分 |
| **P2-c** | — | `state/api-health.json` 新增 gun-bot/chatroom 條目 | `state/api-health.json` | 10 分 |
| **P3-a** | #5 | frequency-limits.yaml arch_evolution skip_if 防重複觸發 | `config/frequency-limits.yaml` | 10 分 |
| **P3-b** | — | circuit-breaker-utils.ps1 Test-GunBotHealth | `circuit-breaker-utils.ps1` | 20 分 |

### 9.6 閉環完整度評估（修復後預期）

| 閉環層面 | 修復前 | 修復後 |
|---------|--------|--------|
| **Orient→Decide 延遲** | ❌ round-robin，最壞 10h | ✅ PS1 直接觸發，0 分鐘延遲 |
| **Decide→Act 延遲** | ❌ round-robin，最壞 10h | ✅ OODA Act 覆蓋，< 30 分 |
| **Act→Observe 閉環** | ❌ workflow-state 停滯 "act" | ✅ act:completed 日誌，次日自動新週期 |
| **修復驗證** | ❌ 無 validation loop | ✅ system-insight 驗證子步驟 |
| **修復重試** | ❌ executed=true 不重試 | ✅ execution_status 狀態機（retry_count < 3）|
| **Meta-監控** | ❌ 無 | ✅ check-health OODA 健康區塊 + SH01/02/03 |
| **self-heal 觸發時機** | ❌ 無 trigger_condition | ✅ OODA Act 覆蓋保障及時觸發 |
| **arch-evolution 重複** | ❌ 可能雙重觸發 | ✅ skip_if 防重複 |

### 9.7 完整閉環時序（修復後）

```
00:40 — run-system-audit-team.ps1 啟動
  Phase 0: Circuit Breaker 預檢查            +2 分
  Phase 1: Observe (4 並行 audit agents)     +12 分  ← 原有
  Phase 2: Orient 組裝 + improvement-backlog +15 分  ← 原有
  Phase 3 (NEW): arch-evolution (Decide)     +20-30 分
    → 產出 arch-decision.json（3 個 immediate_fix）
    → 寫入 workflow-state：current_step="act", status="pending"
    → 防重複：今日已執行 → 跳過
≈01:30 — run-system-audit-team.ps1 完成

≈01:30 or 02:00 — 下一次 Todoist 半點執行
  todoist-query.md OODA Act 覆蓋：
    讀 workflow-state → current_step="act" → 強制選取 self_heal
  self-heal: 執行 immediate_fix (最多 3 項)  +20 分
    → execution_status=success（成功）
    → workflow-state: act=completed（5c 新增步驟）
≈02:00 — 閉環完成（MTTD→MTTR 總計 ~1.5h）

次日 00:40 — run-system-audit-team.ps1 再次觸發 → 新週期

（任何步驟失敗 → check-health.ps1 每日監控 → ntfy 告警）
（self-heal 修復失敗 → retry_count 機制，最多 3 次重試跨多日執行）
（validation loop → 次日 system-insight 驗證修復效果）
```

**注意**：`run-system-audit-team.ps1` 屬核心腳本，修改前需建立 Git commit 備份。Phase 3 新增位置在第 614 行之後（Phase 2 成功分支的末尾）。
