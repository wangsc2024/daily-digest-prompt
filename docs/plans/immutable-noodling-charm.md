# 計畫：KB 驅動系統優化落實機制 + 26 項待辦執行

## Context

系統已累積大量 KB 研究報告（KB insight、system-insight 告警、GitHub Scout、insight briefing），但未落實原因：

1. **機制缺口**：`kb_system_optimize`（order 32）被飢餓問題壓制；且 Phase 1 只查詢 KB 近 2 天新鮮洞察，**完全忽略** `improvement-backlog.json` 26 個已評估的 pending 項目
2. **執行缺口**：26 個 pending 項目長期無人認領，缺乏：選項評分→狀態追蹤→重試上限→過期清理的完整生命週期
3. **未來計畫孤島**：`未來計畫/` 目錄（N9 五層自癒、GeminiCli 六大優化等）未納入 backlog，無法被自動排程

**目標**：建立可長期穩定運作的 KB 驅動優化閉環，讓 `kb_system_optimize` 成為每日可靠執行的落實引擎。

### 現狀核查（探索後確認）

| 項目 | 原計畫假設 | 實際狀態 | 影響 |
|------|---------|--------|------|
| `post_tool_logger.py` trace_id | 需新增 | **已整合** L697-723 | Batch D 簡化 |
| `post_tool_logger.py` context_compressor | 需新增 | **已整合** L853 | Batch E → 僅標記 done |
| `tools/time_slot_risk_scorer.py` | 需開發 | **已存在**（含 --write-report CLI）| Batch C → 僅執行 |
| `execution_order 15` | 可用 | **被 github_scout 佔用** | 改用空槽 27 |
| `execution_order 18-20` | 可用 | **全被佔用** | 確認 27 是空槽 |
| `jsonschema` 依賴 | 假設存在 | **不在 pyproject.toml** | D2 需 uv add 或 inline 驗證 |
| `tests/tools/test_time_slot_risk_scorer.py` | 需撰寫 | **已存在** | C 測試已覆蓋 |

---

## Part 1：強化 KB→落實機制（長期穩定運作核心）

### 1.1 `templates/auto-tasks/kb-system-optimize.md`

**修改**：在現有 Phase 1 之前插入 **Phase 0（backlog 優先掃描）**，Phase 7 新增 **7b（狀態生命週期）**。

**Phase 0 完整邏輯**（新增於「階段一：查詢 KB」之前）：

```
【Phase 0：Backlog 優先掃描】

Step 0-1：讀取 context/improvement-backlog.json
Step 0-2：過濾可執行項目（同時符合以下全部條件）：
  - status == "pending"
  - retry_count < 3（≥ 3 → 跳過，另行彙報至 ntfy）
  - effort != "high" 或 (effort == "high" 且選中項 <= 1 個)

Step 0-3：評分公式（滿分 42 分）
  score = priority_w[high=3, medium=2, low=1]
          × effort_w[low=3, medium=2, high=1]   ← 低 effort 優先
          × min(age_days, 14)                    ← 最多放大 14 倍（防飢餓）

Step 0-4：取 Top 2（保留 1 個 budget 給 KB 新鮮洞察）
  - 若 Top 2 全為 high effort → 降為 Top 1 + 1 個 fresh KB 洞察

Step 0-5：將選中項目寫回 backlog：
  status: "in_progress"
  started_at: <ISO 8601>
  執行者保留原 retry_count（落實後重置）

Step 0-6：永續健康檢查（每次執行都跑）
  a) 若 pending 項目數 > 40 → ntfy 告警「backlog 過載，請人工清理」
  b) 若任何項目 age_days > 30 且 retry_count == 0 → 標記 status: "stale"
  c) 若任何項目 retry_count >= 3 → 標記 status: "needs_human_review"
     + ntfy 告警（每週最多告警一次，dedup 防刷）
```

**Phase 7b 狀態歸檔**（新增於現有「階段七：成果記錄」之後）：

```
【Phase 7b：生命週期歸檔】

- 成功落實 → status: "done", completed_at: now, retry_count: 0
- 部分完成 → status: "partial", notes: 說明進度
- 驗收失敗/回滾 → status: "pending", retry_count: retry_count + 1
  （第 3 次後自動改為 "needs_human_review"）

寫回 context/improvement-backlog.json（Read → 修改對應項目 → Write）

若當日完成 >= 1 項 → 觸發 uv run python tools/time_slot_risk_scorer.py --write-report
（確保成功率改善即時反映到時段風險配置）
```

**不修改現有 Phase 1-7** 邏輯（向後相容）。

---

### 1.2 `config/frequency-limits.yaml`

**問題**：`kb_system_optimize` 在 `execution_order: 32`，完整 execution_order 清單確認 **27 為空槽**（歷史預留，未使用）。

**修改**：`execution_order: 32` → `execution_order: 27`

位置語義：在 `skill_forge`(24)、`ntfy_review`(25)、`future_plan_optimize`(26) 之後，`workflow_forge`(28) 之前。此位置確保 kb_system_optimize 在每輪 round-robin 中能被選到，同時不干擾 OODA 核心鏈（13-18）。

**驗證**：`uv run python hooks/validate_config.py --check-auto-tasks`

---

## Part 2：立即落實 Backlog 項目（分批）

### Batch A：狀態清理（6 項標記 done，0 風險）

以下項目工具已存在/指標已達標，只需更新 `context/improvement-backlog.json`：

| backlog_id | 已完成依據 | resolved_by |
|-----------|---------|------------|
| `backlog_kie_20260322_cache_optimizer_execution` | results/cache-optimizer-report.json（98.8%） | ADR-20260323-043 |
| `backlog_kie_20260322_failure_taxonomy` | config/failure-taxonomy.yaml + tools/classify_failure.py | ADR-20260323-042 |
| `backlog_si_20260323_cache_hit_ratio` | 98.8% >> 目標 40% | ADR-20260323-043 |
| `backlog_si_20260322_cache_hit_ratio` | 同上 | ADR-20260323-043 |
| `backlog_ib_20260321_context_compression` | post_tool_logger.py L853 已整合 context_compressor | ADR-036 |
| `backlog_kie_20260321_time_slot_risk` | tools/time_slot_risk_scorer.py 已完整實作 | 已驗證存在 |

每項新增：`"status": "done", "resolved_at": "2026-03-23", "resolved_by": "<上表>"，"actual_result": "..."`

---

### Batch B：ADR-044 Skill 候選評分修復（TDD 流程）

**問題**：現有三維評分模型偏好高頻簡單 Bash 命令（date/curl-health/rm），Top 10 全無業務邏輯價值。

**B1. 先寫測試（紅燈）— `tests/tools/test_score_skill_candidates.py`**

新增測試（依 test_classify_failure.py 的導入慣例）：
```python
def test_is_complexity_excluded_simple_date():
    p = {"tool": "Bash", "summary_sample": "date -u +%Y-%m-%dT%H:%M:%SZ"}
    assert _is_complexity_excluded(p) is True

def test_is_complexity_excluded_health_check():
    p = {"tool": "Bash", "summary_sample": "curl -s --max-time 5 http://localhost:3001/api/health"}
    assert _is_complexity_excluded(p) is True

def test_is_complexity_excluded_pwsh_multiline():
    p = {"tool": "Bash", "summary_sample": "pwsh -Command '\\n$t = if ($env:TODOIST)..."}
    assert _is_complexity_excluded(p) is False  # 應保留

def test_score_complexity_short_returns_zero():
    p = {"tool": "Bash", "summary_sample": "rm temp.json"}
    assert _score_complexity(p) == 0.0

def test_score_complexity_multiline_returns_high():
    p = {"tool": "Bash", "summary_sample": "pwsh -Command '\\nif ($x) { ... }"}
    assert _score_complexity(p) >= 2.0
```

**B2. 實作（綠燈）— `config/skill-candidate-scoring.yaml`**

version 1→2；四維度權重：freq 0.30 / conf 0.25 / reuse 0.20 / **complexity 0.25**；新增：
```yaml
complexity_exclusions:
  max_simple_command_length: 80   # <= 80 字元且無換行無管道 → 視為簡單命令

candidate_threshold:
  # ... 現有欄位不變 ...
  min_complexity_score: 1.0       # 新增：純簡單命令直接排除
```

**B3. 實作（綠燈）— `tools/score_skill_candidates.py`**

新增兩個純函數（內嵌常數，避免複雜 YAML 解析）：
```python
_SIMPLE_BASH_PREFIXES = ("date ", "rm ", "mkdir ", "cat ", "echo ", "cp ", "mv ", "ls ")
_HEALTH_CHECK_RE = re.compile(r"curl -s --max-time \d+ http://localhost:\d+/api/health")

def _is_complexity_excluded(pattern: dict) -> bool:
    if pattern.get("tool") != "Bash": return False
    s = str(pattern.get("summary_sample", ""))
    if any(s.startswith(p) for p in _SIMPLE_BASH_PREFIXES): return True
    if _HEALTH_CHECK_RE.search(s): return True
    if len(s) <= 80 and "|" not in s and "\\n" not in s and "\n" not in s: return True
    return False

def _score_complexity(pattern: dict) -> float:
    s = str(pattern.get("summary_sample", ""))
    pipes = s.count("|") + s.count("&&") + s.count(";")
    has_logic = any(k in s for k in ("if ", "for ", "while ", "pwsh", "\\n", "\n"))
    raw = pipes + (1 if has_logic else 0)
    if len(s) > 200 or raw >= 3: return 3.0
    if len(s) > 100 or raw >= 1: return 2.0
    if len(s) > 50: return 1.0
    return 0.0
```

修改 `score_pattern()`：在 exclude_tools 判斷後加入複雜度排除；更新加權公式：
`total = f*0.30*3 + c*0.25*3 + r*0.20*3 + cx*0.25*3`；scores 加 `"complexity"` 欄位。

修改 `_load_config()`：reusability 邊界從 `# Skill 候選門檻` 改為 `  complexity:`；加 `cfg["min_complexity_score"] = extract_val("min_complexity_score")`。

**B4. context/kb-research-brief.json**：completion_pct 0→30，steps[1].status → done，新增 auto_advance_condition。同步 **context/research-series.json** 對應系列 partial_completion。

**B5. context/arch-decision.json**：ADR-044 新增 next_retry_plan 記錄此修復。

執行驗證：
```bash
uv run pytest tests/tools/test_score_skill_candidates.py -v   # 先確認綠燈
uv run python tools/score_skill_candidates.py --top 10         # Top 10 無 date/curl/rm
```

---

### Batch C：時段風險落實（`tools/time_slot_risk_scorer.py` 已存在）

**核查發現**：`tools/time_slot_risk_scorer.py` 已完整實作（含 compute_hour_stats、score_time_slot、write_risk_report CLI），`tests/tools/test_time_slot_risk_scorer.py` 已存在。

**C1. 執行工具產生 config/time-slot-risk.json**：
```bash
uv run python tools/time_slot_risk_scorer.py --write-report --days 7
# 工具自動寫入 config/time-slot-risk.json（動態生成，非硬編碼）
```

**C2. 若 config/time-slot-risk.json 尚不存在**：確認 write_risk_report() 的輸出路徑正確。

**C3. 標記 backlog**：`backlog_kie_20260321_time_slot_risk` status → done（工具已存在）。

---

### Batch D：Trace ID 查詢支援（PS1 + query_logs --trace）

**核查確認**：`post_tool_logger.py` L697-723 已讀取 `DIGEST_TRACE_ID` 環境變數並寫入 JSONL。**只缺**：PS1 設定入口 + query_logs.py 的 --trace 查詢參數。

**D1. `run-todoist-agent-team.ps1` 和 `run-agent-team.ps1`**（兩個都加）：
```powershell
# 在 $AgentDir 設定後、Phase 0 開始前插入
$TraceId = [System.Guid]::NewGuid().ToString("N").Substring(0, 12)
$env:DIGEST_TRACE_ID = $TraceId
Write-Host "Trace: $TraceId"   # 不用 emoji（避免 UTF-8 BOM 問題）
```

**D2. `hooks/query_logs.py`**（先寫測試，再實作）：

先在 `tests/hooks/test_query_logs.py` 新增：
```python
def test_trace_filter_matches():
    entries = [{"trace_id": "abc123"}, {"trace_id": "xyz999"}, {"trace_id": ""}]
    result = [e for e in entries if e.get("trace_id","").startswith("abc")]
    assert len(result) == 1

def test_trace_filter_empty_matches_all():
    # --trace 未指定時不過濾
    ...
```

在 `argparse` 段落新增：`parser.add_argument("--trace", type=str, default="", help="Filter by trace_id prefix")`

在 `load_entries` 後加入過濾邏輯：
```python
if args.trace:
    entries = [e for e in entries if e.get("trace_id", "").startswith(args.trace)]
```

**D3. Config Schema 驗證（最小可行，不加 jsonschema 依賴）**

在 `hooks/validate_config.py` 的 `--check-auto-tasks` 邏輯中，**inline** 新增任務欄位驗證（不 import jsonschema）：
```python
# 在現有 auto-task 驗證迴圈中加入
required_fields = ["execution_order", "daily_limit", "timeout_seconds"]
for field in required_fields:
    if field not in task_config:
        errors.append(f"Task '{task_key}' missing required field: {field}")
    elif not isinstance(task_config[field], int) or task_config[field] < 0:
        errors.append(f"Task '{task_key}.{field}' must be non-negative int")
```

同步新建 `config/schemas/improvement-backlog-schema.json`（純文件用途，不需 Python 讀取）。

---

## Part 3：未來計畫納入 Backlog（長期 KB 驅動供料）

將以下 `未來計畫/` 項目正式寫入 `context/improvement-backlog.json`（source: "future_plan"，status: "pending"），完整 execution_plan 讓 kb_system_optimize 可自動評估並排程：

| id | 標題 | priority | effort | 來源 |
|----|------|---------|--------|------|
| `backlog_future_n9_self_heal_5tier` | 5-tier 分級自癒機制（Tier 0-4 遞進） | high | high | 待辦事項.md N9 |
| `backlog_future_n10_llm_agnostic` | LLM-Agnostic 統一環境變數（LLM_PROVIDER routing） | medium | medium | 待辦事項.md N10 |
| `backlog_future_n5_llm_judge` | LLM-as-Judge Agent 輸出品質評估（四維度框架） | medium | medium | 待辦事項.md N5 |
| `backlog_future_gemini_error_classifier` | 錯誤分類 + Circuit Breaker（GeminiCli items 2+4） | high | medium | GeminiCli借鏡方案.md Phase B |
| `backlog_future_gemini_security_engine` | 分層安全策略引擎 + 結構化測試（GeminiCli items 5+6） | medium | high | GeminiCli借鏡方案.md Phase C |
| `backlog_future_adaptive_ttl` | 自適應 TTL 演算法（d-TTL/f-TTL，arXiv 1704.04448） | high | medium | backlog_ib_20260323 |
| `backlog_future_arc_eviction` | ARC 快取驅逐策略（Redis 官方，比 LRU+12-18%） | medium | medium | backlog_ib_20260323 |
| `backlog_future_wrr_fairness` | 自動任務 WRR 公平輪轉（需 PS1 + 7 天觀測） | high | high | backlog_kb_insight_20260323 |

每項格式：
```json
{
  "id": "backlog_future_{{slug}}",
  "source": "future_plan",
  "title": "...",
  "priority": "high|medium",
  "effort": "medium|high",
  "status": "pending",
  "retry_count": 0,
  "evaluated_at": "2026-03-23",
  "execution_plan": {
    "steps": ["(具體步驟，參考 未來計畫/ 對應文件)"],
    "acceptance_criteria": ["(可量化驗收條件)"],
    "research_sources": ["未來計畫/GeminiCli借鏡方案.md", "..."]
  }
}
```

---

## Part 4：長期穩定運作設計說明

### 為何此設計可長期穩定運作

| 風險 | 設計因應 |
|------|---------|
| Backlog 無限膨脹 | Phase 0 Step 0-6a：pending > 40 項觸發 ntfy 告警 |
| 同一項目反覆失敗卡死 | retry_count >= 3 自動改為 "needs_human_review"，跳出輪轉 |
| 過期未處理項目積壓 | age_days > 30 + retry == 0 → status: "stale"，月底 ntfy 彙報 |
| kb_system_optimize 被飢餓 | order 32 → 27，在 round-robin 中提前 5 個位次 |
| effort=high 項目永遠排第一 | 評分公式 effort_w[high=1]（低優先），需搭配 medium/low 才能入選 |
| 已落實但 backlog 未更新 | Phase 7b 強制寫回 status + completed_at |
| 成功率改善未反映 | Phase 7b 完成後自動執行 time_slot_risk_scorer --write-report |
| 供料不足（KB 無新洞察） | Phase 0 先從 backlog 取 2 項，保留 1 個 budget 給新鮮 KB 查詢 |

### OODA 閉環完整性確認

```
Observe: system_insight (order 16) → context/system-insight.json
         kb_insight_evaluation (order 14) → improvement-backlog.json
         insight_briefing (order 13) → improvement-backlog.json

Orient:  system_audit (run-system-audit-team.ps1) → 周期性

Decide:  arch_evolution (order 17) → context/arch-decision.json

Act:     kb_system_optimize (order 27) ← 本計畫修復
         ↓ Phase 0 讀 backlog → 選 Top 2 → 實作
         ↓ Phase 7b 寫回 status → ntfy 通知
         ↓ time_slot_risk_scorer --write-report (驗收後)
         → 結果回寫 KB → 下輪 Observe 感測改善
```

---

## 關鍵文件速查

| 文件 | 操作 | 批次 |
|------|------|------|
| [templates/auto-tasks/kb-system-optimize.md](templates/auto-tasks/kb-system-optimize.md) | 插入 Phase 0 + Phase 7b | P1 |
| [config/frequency-limits.yaml](config/frequency-limits.yaml) | kb_system_optimize order 32→27 | P1 |
| [context/improvement-backlog.json](context/improvement-backlog.json) | 6 項 done；8 項 future_plan 新增 | A/P3 |
| [config/skill-candidate-scoring.yaml](config/skill-candidate-scoring.yaml) | version 2，四維度 + complexity | B |
| [tools/score_skill_candidates.py](tools/score_skill_candidates.py) | _is_complexity_excluded + _score_complexity | B |
| [tests/tools/test_score_skill_candidates.py](tests/tools/test_score_skill_candidates.py) | 新建，5 個測試（TDD 紅→綠） | B |
| [context/kb-research-brief.json](context/kb-research-brief.json) | completion_pct → 30，steps 更新 | B |
| [context/research-series.json](context/research-series.json) | 同步 partial_completion | B |
| [context/arch-decision.json](context/arch-decision.json) | ADR-044 next_retry_plan | B |
| [run-todoist-agent-team.ps1](run-todoist-agent-team.ps1) | 新增 DIGEST_TRACE_ID 設定 | D |
| [run-agent-team.ps1](run-agent-team.ps1) | 新增 DIGEST_TRACE_ID 設定 | D |
| [hooks/query_logs.py](hooks/query_logs.py) | 新增 --trace 參數 + 過濾邏輯 | D |
| [tests/hooks/test_query_logs.py](tests/hooks/test_query_logs.py) | 新增 --trace 過濾測試（TDD） | D |
| [hooks/validate_config.py](hooks/validate_config.py) | inline 欄位驗證（不加 jsonschema 依賴） | D |
| [config/schemas/improvement-backlog-schema.json](config/schemas/improvement-backlog-schema.json) | 新建（文件用途） | D |

---

## 執行順序

```
Part 1（機制修復：kb-system-optimize.md + frequency-limits.yaml）
  → Batch A（6 項 status → done）
  → Batch B（TDD: 測試→實作→驗證 score_skill_candidates）
  → Batch C（執行 time_slot_risk_scorer --write-report）
  → Batch D（PS1 TraceId + query_logs --trace + validate_config 欄位驗證）
  → Part 3（未來計畫 8 項新增至 backlog）
```

## 驗收

| 批次 | 驗收指令 | 預期結果 |
|------|---------|--------|
| P1 | `grep "execution_order" config/frequency-limits.yaml \| grep kb_system` | 顯示 27 |
| P1 | `uv run python hooks/validate_config.py --check-auto-tasks` | 無錯誤 |
| A | `context/improvement-backlog.json` 6 項 status=done | ✓ |
| B | `uv run pytest tests/tools/test_score_skill_candidates.py -v` | 全綠 |
| B | `uv run python tools/score_skill_candidates.py --top 10` | Top 10 無 date/curl/rm |
| C | `uv run python tools/time_slot_risk_scorer.py --write-report` | config/time-slot-risk.json 產出 |
| D | `uv run pytest tests/hooks/test_query_logs.py -v` | 全綠 |
| D | `uv run python hooks/query_logs.py --trace abc123` | 只顯示對應 trace 的日誌 |
| D | `uv run python hooks/validate_config.py --check-auto-tasks` | 欄位驗證通過 |
| P3 | `context/improvement-backlog.json` 含 8 個 source=future_plan 項目 | ✓ |
| 整體 | `uv run pytest tests/ -x` | 全套測試通過 |
