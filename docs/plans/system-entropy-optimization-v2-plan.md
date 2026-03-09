# Daily-Digest-Prompt 系統穩定性與執行效率優化細部方案

> **版本**: 2.0
> **日期**: 2026-03-08
> **基於**: [系統熵增與複雜度治理優化建議（2026-03-01）](https://know-w.pages.dev/article/daily-digest-prompt-%E7%B3%BB%E7%B5%B1%E7%86%B5%E5%A2%9E%E8%88%87%E8%A4%87%E9%9B%9C%E5%BA%A6%E6%B2%BB%E7%90%86-1150955a)
> **目標**: 系統穩定性提升（錯誤率 ↓50%）+ 執行效率提升（Token 消耗 ↓30%、Phase 耗時 ↓25%）

---

## 一、背景與目標說明

### 1.1 報告來源

原始報告（noteId: 1150955a）於 2026-03-01 從「系統熵增」角度分析了專案複雜度的三個維度：

| 維度 | 報告時數值 | 風險等級 | 原文段落 |
|------|-----------|---------|---------|
| 配置膨脹（Config Entropy） | CLAUDE.md 586行、YAML 2,224行 | 🔴 高 | §1.1 |
| 認知負荷（Cognitive Load） | 每次啟動 ~9,200 tokens | 🟡 中 | §1.2 |
| 研究註冊表膨脹（Registry Bloat） | 120 條、65.2KB | 🟡 中 | §1.3 |

### 1.2 報告五項建議與已實施狀態

| # | 建議 | 優先級 | 已實施？ | 當前狀態 | 原文段落 |
|---|------|-------|---------|---------|---------|
| 1 | CLAUDE.md 分層瘦身 | P0 | ✅ 完成 | 586→214 行（-63%） | §建議1 |
| 2 | 快取命中率修復 | P0 | ⚠️ 部分 | 0%→~10%（目標 ≥40%） | §建議5 |
| 3 | 研究註冊表壓縮視圖 | P1 | ✅ 完成 | 120→66 條、summary 欄位已加 | §建議2 |
| 4 | 自動任務流程標準化 | P1 | ✅ 完成 | validate_config + new-auto-task.ps1 | §建議3 |
| 5 | run-fsm.json 生命週期 | P2 | ✅ 完成 | max_entries=20、殭屍偵測已加 | §建議4 |

### 1.3 新發現的問題（報告未涵蓋）

基於 2026-03-08 現場數據，識別出報告未覆蓋的 4 個新瓶頸：

| # | 新問題 | 當前數值 | 警戒閾值 | 風險等級 |
|---|-------|---------|---------|---------|
| N1 | Config YAML 總行數膨脹 | 3,588 行 | 3,000 行 | 🔴 高 |
| N2 | Token 消耗暴衝 | 3/7 達 16.3M tokens | 1.5M/日 | 🔴 高 |
| N3 | 持續 timeout 失敗 | 7 次/近 7 天 | 0 | 🟡 中 |
| N4 | Phase failure 持續 | 5 次/近 7 天（3/8 仍 2 次） | 0 | 🟡 中 |

### 1.4 優化目標（可量化）

| 目標 | 基線值（3/8） | 目標值 | 提升幅度 |
|------|-------------|-------|---------|
| 每日執行成功率 | ~85% | ≥95% | +10pp |
| 快取命中率 | ~10% | ≥40% | +30pp |
| 平均每日 Token 消耗 | ~6M tokens | ≤3M tokens | -50% |
| Phase 1 平均耗時 | ~114s | ≤60s | -47% |
| Config YAML 總行數 | 3,588 行 | ≤2,500 行 | -30% |
| Timeout 失敗次數 | 1/日 | 0/日 | -100% |

---

## 二、評估指標與測量方法

### 2.1 穩定性指標（4 項）

| 指標 ID | 名稱 | 定義 | 測量方法 | 基準值 | 目標值 |
|---------|------|------|---------|-------|-------|
| S1 | 每日執行成功率 | (成功次數 / 總執行次數) × 100% | `state/failure-stats.json` daily 統計 | ~85% | ≥95% |
| S2 | MTTR（平均故障恢復時間） | 從 failure 到下一次 success 的平均間隔 | `logs/structured/*.jsonl` 時間差計算 | ~60 min | ≤30 min |
| S3 | Phase Failure 率 | phase_failure / 總執行次數 | `state/failure-stats.json` | ~5% | ≤1% |
| S4 | Circuit Breaker 觸發頻率 | circuit_open 次數 / 日 | `state/failure-stats.json` + `cache/api-health.json` | 0/日 | 維持 0 |

### 2.2 效率指標（5 項）

| 指標 ID | 名稱 | 定義 | 測量方法 | 基準值 | 目標值 |
|---------|------|------|---------|-------|-------|
| E1 | 平均每日 Token 消耗 | 7 天滾動平均 estimated_tokens | `state/token-usage.json` daily | ~6M | ≤3M |
| E2 | 快取命中率 | cache_hits / (cache_hits + api_calls) × 100% | `context/digest-memory.json` skill_usage | ~10% | ≥40% |
| E3 | Phase 1 平均耗時 | 從 Phase 1 開始到結束的秒數 | `logs/structured/session-summary.jsonl` | ~114s | ≤60s |
| E4 | 每次工具呼叫平均 I/O | input_chars + output_chars / tool_calls | `state/token-usage.json` | ~5,000 chars | ≤3,500 chars |
| E5 | Config 載入 Token 開銷 | CLAUDE.md + SKILL_INDEX + 必讀 YAML 的估算 tokens | `wc -l` × 估算因子 | ~5,500 tokens | ≤3,500 tokens |

### 2.3 指標自動化追蹤

所有指標已有對應數據源（`state/`, `context/`, `logs/`），建議在 `check-health.ps1` 新增「KPI 儀表板」區塊統一呈現。

---

## 三、優化措施詳述

### 措施 M1：快取命中率根本修復（P0 — 穩定性 + 效率）

**對應報告段落**: §建議5（快取命中率歸零的根本修復）
**對應指標**: E2（快取命中率）、E3（Phase 1 耗時）、S1（成功率）

#### 問題根因

1. **進程隔離**：每個 `claude -p` 是獨立進程，Phase 1 的 5 個 Agent 各自打 API，互不共享
2. **Phase 0 預取不完整**：`cache/status.json` 只做有效性判斷，未在過期時主動重新取得
3. **寫回機制缺失**：Agent 呼叫 API 後結果僅寫入 `results/*.json`，未同步更新 `cache/*.json`

#### 技術方案

**方案 A：Phase 0 完整預取（推薦）**

```
實施步驟：
1. 修改 run-agent-team.ps1 Phase 0 區段
2. 新增 Invoke-CacheRefresh 函數：
   - 讀取 cache-policy.yaml 的 sources
   - 對每個 source 檢查 cache/*.json 的 cached_at + ttl
   - 過期時執行 API 呼叫（curl）並更新 cache/*.json
   - 寫入 cache/status.json 標記 valid=true
3. Phase 1 Agent prompt 改為「優先讀 cache/*.json，僅在 valid=false 時呼叫 API」
4. Agent 呼叫 API 後，在寫 results/*.json 的同時寫 cache/*.json
```

**所需資源**: 修改 2 個 PS 腳本 + 4 個 fetch prompt
**預估效益**:
- 快取命中率：10% → 50-60%（Phase 1 的 3/5 Agent 可直接讀快取）
- Phase 1 耗時：114s → 60-70s（快取命中的 Agent 省去 API 延遲）
- API 呼叫次數：每次 5 → 每次 2-3

**方案 B：共享記憶體快取（Redis-like）**

```
使用 PowerShell 背景作業作為快取代理：
- 啟動時載入所有 cache/*.json 到記憶體
- Agent 透過 named pipe 或臨時檔案請求/更新快取
- 快取代理負責 TTL 管理和持久化
```

**優缺點比較**:

| 面向 | 方案 A（Phase 0 預取） | 方案 B（共享記憶體快取） |
|------|---------------------|---------------------|
| 實施複雜度 | 低（修改既有腳本） | 高（新建快取代理服務） |
| 預期命中率 | 50-60% | 70-80% |
| 維護成本 | 低 | 中（多一個常駐服務） |
| 失敗風險 | 極低 | 中（代理當機影響全局） |
| 建議 | ✅ 優先實施 | 🔜 Phase 0 不足時再考慮 |

---

### 措施 M2：Token 消耗控制機制（P0 — 效率）

**對應指標**: E1（Token 消耗）、E4（I/O 大小）
**新發現問題**: N2（3/7 Token 16.3M，為 daily_limit_warn 的 10 倍）

#### 問題根因

1. **無 Token 預算機制**：Agent 可無限讀取大檔案、產出長文本
2. **研究任務產出過長**：ai_deep_research 單次可能生成 10K+ 字研究報告
3. **重複讀取**：同一 session 可能重複讀取相同配置文件

#### 技術方案

```
三層 Token 預算控制：

Layer 1 — 模型選擇路由（已部分實施）
  - 佛學研究 → claude-haiku-4-5（低 Token 消耗）
  - 系統維護 → claude-sonnet-4-5（中等）
  - 複雜分析 → claude-opus-4-6（僅必要時）
  → 在 frequency-limits.yaml 已有 model 欄位，擴大覆蓋

Layer 2 — 單次 Session Token 上限
  - 在 config/timeouts.yaml 新增 max_tokens_per_session
  - run-*-team.ps1 傳入 --max-tokens 參數給 claude -p
  - 預設: single_mode=200K, team_phase2=150K/agent

Layer 3 — 輸出長度限制
  - 在 auto-task 模板新增「輸出限制」指令：
    「研究報告不超過 800 字、摘要不超過 200 字」
  - 在 preamble.md 加入通用節約指令
```

**所需資源**: 修改 config/timeouts.yaml + preamble.md + 21 個 auto-task 模板
**預估效益**:
- 平均每日 Token：6M → 2.5-3M（-50%~-58%）
- 單日峰值：16.3M → ≤5M（-69%）
- 月度 API 成本：相應降低 50%

---

### 措施 M3：Config YAML 精簡與模組化（P1 — 效率 + 維護性）

**對應指標**: E5（Config 載入 Token）
**新發現問題**: N1（YAML 3,588 行超過 3,000 閾值）

#### 問題根因

1. **frequency-limits.yaml 佔 419 行**：19 個任務定義含大量重複結構
2. **domain-research 模板參數內嵌 YAML**：ai_smart_city、ai_sysdev 的 template_params 各佔 40+ 行
3. **停用任務仍佔空間**：daily_limit=0 的 5 個任務定義仍佔 ~80 行

#### 技術方案

```
1. template_params 外部化（-300 行）
   - 將 ai_smart_city、ai_sysdev 等的 template_params 移至對應模板的 frontmatter
   - frequency-limits.yaml 僅保留 key + 引用路徑

2. 停用任務歸檔（-80 行）
   - daily_limit=0 的任務移至 config/tasks-archived.yaml
   - validate_config 修改為同時掃描 active + archived

3. 共用欄位預設值（-100 行）
   - 新增 task_defaults 段落（template_version: 1, model: "", skills: []）
   - 各任務僅覆寫差異欄位（DRY 原則）

預計行數變化：
  frequency-limits.yaml: 419 → ~250 行
  其他 YAML 無影響
  總計: 3,588 → ~3,100 行（-13%）
```

**所需資源**: 修改 frequency-limits.yaml + validate_config.py
**預估效益**:
- YAML 總行數：3,588 → ~3,100（低於警戒線）
- 新增任務所需修改行數：~25 行 → ~8 行
- 維護認知負荷降低

---

### 措施 M4：Timeout 失敗消除（P1 — 穩定性）

**對應指標**: S1（成功率）、S3（Phase Failure 率）
**新發現問題**: N3（7 次 timeout）、N4（5 次 phase failure）

#### 問題根因

1. **固定 timeout 不適應任務複雜度**：所有任務共用同一 timeout 值
2. **研究任務天生耗時長**：ai_deep_research 4 階段可能超過 timeout
3. **無漸進式降級**：timeout 後直接失敗，無 graceful degradation

#### 技術方案

```
1. 動態 Timeout 分級
   修改 config/timeouts.yaml：
   tier_1_fast: 120s    # 佛學、git_push、chatroom
   tier_2_normal: 300s  # tech_research、ai_sysdev、log_audit
   tier_3_heavy: 600s   # ai_deep_research、system_insight、podcast

   在 frequency-limits.yaml 各任務新增 timeout_tier 欄位
   run-todoist-agent-team.ps1 讀取 tier 決定 timeout

2. Timeout 前的 Graceful Degradation
   在 auto-task 模板新增「時間感知」指令：
   「若已執行 >3 分鐘，立即產出目前成果（即使不完整），
     不要繼續深入研究。部分成果優於 timeout 失敗。」

3. 失敗自動重試優化
   目前 scheduler-state 已有重試機制，但僅重試 1 次
   修改為：timeout 類型重試時自動降級到 tier_2 timeout
```

**所需資源**: 修改 config/timeouts.yaml + frequency-limits.yaml + 3 個 PS 腳本
**預估效益**:
- Timeout 頻率：1/日 → ≤0.2/日
- Phase Failure：~5%→ ≤1%
- 整體成功率：~85% → ≥95%

---

### 措施 M5：研究註冊表進一步優化（P2 — 效率）

**對應報告段落**: §建議2
**對應指標**: E1（Token）、E4（I/O）

#### 現狀

summary 欄位已實施，但 66 條 entries 仍全量存在。todoist_research 佔 23 條（35%），分佈不均。

#### 技術方案

```
1. 自動淘汰機制
   - retention_days 從 7 天改為 5 天（實際使用模式顯示 3 天冷卻就足夠）
   - 新增 max_entries_per_type: 5（每種類型最多保留 5 條）
   - todoist_research 23 條 → 5 條

2. 壓縮存儲
   - entries 中移除 tags[]（已在 summary.by_type 有統計）
   - 保留: date, task_type, topic, kb_note_title, kb_imported
   - 移除: tags[], 重複的 metadata

預計效果：
  entries: 66 → ~35 條
  檔案大小: ~35KB → ~15KB
  Token 消耗: ~2,500 → ~1,000
```

---

### 措施 M6：KPI 自動化儀表板（P2 — 可觀測性）

**對應指標**: 所有指標的自動化追蹤

#### 技術方案

```
在 check-health.ps1 新增 [KPI 儀表板] 區塊：

[KPI 儀表板 — 2026-03-08]
穩定性
  S1 每日成功率:     92% (目標 ≥95%) ⚠️
  S2 MTTR:           45 min (目標 ≤30 min) ⚠️
  S3 Phase Failure:  2.3% (目標 ≤1%) ⚠️
  S4 Circuit Break:  0/日 (目標 0) ✅

效率
  E1 每日 Token:     6.2M (目標 ≤3M) ❌
  E2 快取命中率:     10% (目標 ≥40%) ❌
  E3 Phase 1 耗時:   98s (目標 ≤60s) ⚠️
  E4 I/O 大小:       4,800 (目標 ≤3,500) ⚠️
  E5 Config Token:   5,200 (目標 ≤3,500) ⚠️

資料來源: failure-stats.json, token-usage.json, digest-memory.json
```

**所需資源**: 修改 check-health.ps1
**預估效益**: 即時可視化所有 KPI，加速問題定位

---

## 四、優先級與實施路線圖

| 優先級 | 措施 | 對應指標 | 預期提升 | 複雜度 | 建議時程 |
|--------|------|---------|---------|--------|---------|
| **P0** | M1 快取命中率修復 | E2, E3, S1 | 命中率 +40pp, 耗時 -40% | 中 | 第 1 週 |
| **P0** | M2 Token 消耗控制 | E1, E4 | Token -50% | 低-中 | 第 1 週 |
| **P1** | M4 Timeout 消除 | S1, S3 | 成功率 +10pp | 中 | 第 1-2 週 |
| **P1** | M3 Config YAML 精簡 | E5 | YAML -13%, 維護 ↓ | 低 | 第 2 週 |
| **P2** | M5 研究註冊表優化 | E1, E4 | entries -47%, Token ↓ | 低 | 第 2 週 |
| **P2** | M6 KPI 儀表板 | 全部 | 可觀測性 | 低 | 第 1 週 |

### 依賴關係

```
M6（KPI 儀表板）── 無依賴，可立即開始
M1（快取修復）── 無依賴，可立即開始
M2（Token 控制）── 無依賴，可立即開始
M4（Timeout）── 部分依賴 M2（Token 降低可間接減少 timeout）
M3（YAML 精簡）── 無依賴
M5（註冊表）── 無依賴
```

**建議並行策略**：M1 + M2 + M6 同時啟動（Week 1），M3 + M4 + M5 第二週啟動。

---

## 五、風險評估

| 風險 | 可能性 | 影響 | 緩解措施 |
|------|--------|------|---------|
| M1 Phase 0 預取拉長啟動時間 | 中 | 低 | 設 15s timeout，超時跳過用舊快取 |
| M2 Token 限制導致任務截斷 | 中 | 中 | 先在 tier_3 任務試行，觀察 2 週再推廣 |
| M3 YAML 重構引入命名不一致 | 低 | 高 | validate_config.py 自動檢查 + Git pre-commit |
| M4 動態 timeout 設定過鬆 | 低 | 低 | 基於歷史數據的 P95 設定初始值 |
| M5 entries 過度淘汰導致去重失效 | 低 | 中 | summary.by_type 仍保留完整統計 |

### 安全性考量

- **M1 快取**：cache/*.json 不含敏感資料（Todoist token 在環境變數），無資料洩漏風險
- **M2 Token 限制**：不影響 Hook 安全層（Hooks 在 Agent 外部執行）
- **M3 YAML**：validate_config.py 確保一致性，不會引入靜默失效

---

## 六、迭代審查紀錄

### 第一輪審查（系統架構師視角）— 2026-03-08

**審查重點**: 架構一致性、ADR 對齊、技術可行性

| # | 審查項目 | 評估 | 意見 |
|---|---------|------|------|
| 1 | M1 是否符合 ADR-004（團隊並行） | ✅ 通過 | Phase 0 預取不破壞並行模式 |
| 2 | M2 Token 控制是否與 ADR-002（文件驅動）衝突 | ⚠️ 注意 | max_tokens 應寫入 config 而非 hardcode |
| 3 | M3 YAML 拆分是否增加散彈式修改 | ✅ 通過 | 反而減少（DRY + 預設值） |
| 4 | M4 timeout_tier 是否與現有 timeouts.yaml 整合 | ⚠️ 注意 | 需合併到 timeouts.yaml 而非新建文件 |
| 5 | M5 max_entries_per_type 是否影響去重品質 | ✅ 通過 | summary 仍有完整統計作為安全網 |
| 6 | M6 KPI 是否重複 benchmark.yaml | ⚠️ 注意 | KPI 儀表板應讀取 benchmark.yaml 的 target 值 |

**修正決議**:
- M2：max_tokens_per_session 加入 config/timeouts.yaml（不 hardcode）
- M4：timeout_tier 合併至 config/timeouts.yaml 現有結構
- M6：KPI 儀表板從 benchmark.yaml 讀取目標值（單一定義處原則）

### 第一輪修正摘要

1. **M2 修正**：`config/timeouts.yaml` 新增 `token_budgets` 段落：
   ```yaml
   token_budgets:
     single_mode: 200000
     team_phase2_per_agent: 150000
     tier_override:
       ai_deep_research: 250000
       podcast_create: 250000
   ```

2. **M4 修正**：`config/timeouts.yaml` 新增 `timeout_tiers` 段落（合併而非新建）：
   ```yaml
   timeout_tiers:
     fast: 120
     normal: 300
     heavy: 600
   task_tier_mapping:
     shurangama: fast
     jiaoguangzong: fast
     fahua: fast
     jingtu: fast
     git_push: fast
     chatroom_optimize: fast
     tech_research: normal
     ai_sysdev: normal
     log_audit: normal
     skill_audit: normal
     ai_deep_research: heavy
     system_insight: heavy
     podcast_create: heavy
     self_heal: normal
     ai_github_research: normal
     ai_workflow_github: normal
   ```

3. **M6 修正**：KPI 目標值從 `benchmark.yaml` 動態讀取，不在 check-health.ps1 中 hardcode。

---

### 第二輪審查（DevOps / 運維視角）— 2026-03-08

**審查重點**: 可操作性、監控告警、回滾計畫、部署安全

| # | 審查項目 | 評估 | 意見 |
|---|---------|------|------|
| 1 | M1 Phase 0 預取失敗的降級策略 | ⚠️ 需補充 | 需明確定義：預取 timeout/失敗時用舊快取還是直接打 API |
| 2 | M2 Token 超限時的行為定義 | ⚠️ 需補充 | claude -p 的 --max-tokens 超限行為需測試確認 |
| 3 | M4 timeout_tier 的回滾方式 | ✅ 通過 | 修改 YAML 即可回滾，無程式碼變更 |
| 4 | M6 KPI 告警整合 ntfy | ⚠️ 建議 | KPI 紅燈時應自動推播 ntfy 告警 |
| 5 | 部署順序與依賴 | ⚠️ 需補充 | M1 需要同時部署 PS 腳本 + prompt，原子性？ |
| 6 | 監控盲區：研究品質下降 | ⚠️ 注意 | Token 限制可能導致研究品質下降，需品質指標 |

**修正決議**:
- M1：新增降級矩陣（預取 timeout→用舊快取；舊快取也過期→直接打 API）
- M2：新增「品質守衛」— 研究報告字數 < 200 字時標記為 low_quality
- M6：KPI 紅燈（≥2 個指標未達標）時透過 ntfy 告警

### 第二輪修正摘要

1. **M1 降級矩陣**：

   | Phase 0 預取結果 | cache/*.json 狀態 | Agent 行為 |
   |-----------------|------------------|-----------|
   | 成功 | valid=true | 讀快取（最佳路徑） |
   | 超時（>15s） | 舊快取 <24h | 讀舊快取 + 標記 degraded |
   | 超時（>15s） | 舊快取 >24h 或不存在 | 直接打 API |
   | API 錯誤 | 舊快取 <24h | 讀舊快取 + 標記 degraded |
   | API 錯誤 | 舊快取 >24h 或不存在 | 跳過該資料源 + 記錄 |

2. **M2 品質守衛**：
   ```yaml
   # config/benchmark.yaml 新增
   quality_guards:
     research_min_words: 200
     research_min_sources: 2
     digest_min_sections: 3
   ```

3. **M6 ntfy 整合**：
   ```powershell
   # check-health.ps1 KPI 區塊尾部
   $redCount = ($kpis | Where-Object { $_.status -eq 'red' }).Count
   if ($redCount -ge 2) {
     # 觸發 ntfy 告警
     Send-NtfyAlert -Topic "wangsc2025" -Title "KPI 警告" `
       -Message "$redCount 個指標未達標" -Priority 4
   }
   ```

---

## 七、預期效益總結

### 實施前後對比（預估）

| 指標 | 實施前（3/8） | 實施後（預估） | 提升幅度 | 對應措施 |
|------|-------------|--------------|---------|---------|
| S1 每日成功率 | ~85% | ≥95% | +10pp | M1, M4 |
| S2 MTTR | ~60 min | ≤30 min | -50% | M4 |
| S3 Phase Failure | ~5% | ≤1% | -4pp | M4, M1 |
| S4 Circuit Break | 0/日 | 0/日 | 維持 | — |
| E1 每日 Token | ~6M | ≤3M | -50% | M2 |
| E2 快取命中率 | ~10% | ≥40% | +30pp | M1 |
| E3 Phase 1 耗時 | ~114s | ≤60s | -47% | M1 |
| E4 I/O 大小 | ~5,000 | ≤3,500 | -30% | M2 |
| E5 Config Token | ~5,500 | ≤3,500 | -36% | M3 |

### 綜合提升預估

- **穩定性綜合提升**: ~25%（加權：S1×40% + S2×25% + S3×25% + S4×10%）
- **效率綜合提升**: ~40%（加權：E1×30% + E2×25% + E3×20% + E4×15% + E5×10%）
- **迭代後殘餘提升空間**: <5%（已達止損點條件）

---

## 八、實施計畫時程

```
Week 1（3/9 - 3/15）
├─ Day 1-2: M6 KPI 儀表板（基礎建設，後續措施效果可即時觀測）
├─ Day 1-3: M1 Phase 0 預取機制（最高 ROI）
├─ Day 2-4: M2 Token 控制（Layer 1 模型路由 + Layer 3 輸出限制）
└─ Day 5:   驗證 M1+M2 效果，調整參數

Week 2（3/16 - 3/22）
├─ Day 1-2: M4 Timeout 分級
├─ Day 2-3: M3 Config YAML 精簡
├─ Day 3-4: M5 研究註冊表優化
├─ Day 4-5: M2 Layer 2（max_tokens_per_session）
└─ Day 5:   全面驗證 + KPI 報告

Week 3（3/23 - 3/29）— 觀察期
├─ 每日監控 KPI 儀表板
├─ 收集 7 天完整數據
├─ 微調參數（timeout tier、TTL、Token budget）
└─ 撰寫最終驗證報告
```

---

## 九、與既有 ADR 的關聯

| 措施 | 關聯 ADR | 一致性 |
|------|---------|--------|
| M1 快取修復 | ADR-004 團隊並行優先 | ✅ Phase 0 預取增強並行效能 |
| M2 Token 控制 | ADR-002 文件驅動架構 | ✅ 預算值寫入 YAML 配置 |
| M3 YAML 精簡 | ADR-002 文件驅動架構 | ✅ DRY 原則減少散彈式修改 |
| M4 Timeout | ADR-006 PS 獨佔寫入 | ✅ timeout 由 PS 腳本控制 |
| M5 註冊表 | ADR-007 研究去重 | ✅ 壓縮不影響去重邏輯 |
| M6 KPI | ADR-008 OODA 閉環 | ✅ Observe 階段的量化增強 |

---

## 十、版本歷史

| 版本 | 日期 | 修改摘要 |
|------|------|---------|
| 1.0 | 2026-03-08 | 初版：6 項措施、9 項指標、實施路線圖 |
| 1.1 | 2026-03-08 | 第一輪審查修正：M2/M4/M6 配置整合 |
| 2.0 | 2026-03-08 | 第二輪審查修正：M1 降級矩陣、M2 品質守衛、M6 ntfy 整合 |

---

> **引用聲明**: 本文件基於知識庫文章「Daily-Digest-Prompt 系統熵增與複雜度治理優化建議」（noteId: 1150955a-8cd2-4453-96f8-038e3c3e4bf4，2026-03-01）進行深化分析。原文段落編號以 § 標註。
