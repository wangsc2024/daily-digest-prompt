# ADR-035/036/037 實作計畫

## Context

system-insight 分析（2026-03-22）發現三個可量化的系統缺口：
1. **ADR-035**：per-phase token 消耗不透明，無法預防 token 超支；results/*.json 缺成本歸因。
2. **ADR-036**：Session Context Window 使用率無追蹤，avg_io_per_call=25454 字元（超基準 2.1x），Agent 在長工作流中可能被截斷而無感知。
3. **ADR-037**：5、7、13 時失敗率顯著偏高（phase_failure 54 次），無 Phase 0 風險閘門，每次高風險時段都全速執行。

三個 ADR 均已在 `context/adr-registry.json` 登記為 Proposed/pending（P1 優先級）。

---

## 實作順序

```
ADR-037 → ADR-035 → ADR-036
```
原因：037 純新增無依賴；035 需升級 token-usage schema；036 依賴 035 的 per-phase 累計資料。

---

## ADR-037：高失敗時段根因分析與時段風險評估

### 新建檔案

**`config/external-sla.yaml`**
```yaml
version: 1
services:
  todoist:
    base_url: "https://api.todoist.com"
    known_unstable_hours: []
    sla_availability_target: 0.995
    blast_radius: "all_tasks"
  pingtung_news:
    base_url: "https://ptnews-mcp.pages.dev"
    sla_availability_target: 0.98
    blast_radius: "single_task"
  hackernews:
    base_url: "https://hacker-news.firebaseio.com"
    sla_availability_target: 0.99
    blast_radius: "single_task"
  knowledge_base:
    base_url: "http://localhost:3000"
    sla_availability_target: 0.98
    blast_radius: "dependent_tasks"

risk_model:
  weights:
    historical_failure_rate: 0.40
    external_sla_risk: 0.25
    resource_contention: 0.20
    task_complexity: 0.15
  thresholds:
    low: 0.30
    medium: 0.55
    high: 0.75

degradation:
  medium:
    action: "extend_timeout"
    timeout_multiplier: 1.30
  high:
    action: "skip_non_critical"
    skip_task_types: ["research", "creative"]
  critical:
    action: "skip_phase2"
    notify: true
```

**`tools/time_slot_risk_scorer.py`**
- `compute_hour_stats(days=14) -> dict[int, HourStats]`：掃描 `logs/structured/*.jsonl`，依 `has_error` 欄位統計各小時失敗率
- `score_time_slot(hour, hour_stats) -> RiskScore`：套用多因子加權公式（四個因子，讀 external-sla.yaml 的 weights）
- `get_current_risk() -> RiskScore`：一站式呼叫，供 PS1 使用
- `write_risk_report(output_path) -> None`：寫入 `state/time-slot-risk.json`
- CLI：`uv run python tools/time_slot_risk_scorer.py --format json`

輸出格式（`state/time-slot-risk.json`）：
```json
{
  "generated_at": "ISO8601",
  "current_hour": 13,
  "risk": {
    "risk_score": 0.72,
    "risk_level": "high",
    "recommended_action": "skip_non_critical",
    "skip_task_types": ["research", "creative"],
    "contributing_factors": { "historical_failure_rate": 0.38, ... }
  }
}
```

**`tests/tools/test_time_slot_risk_scorer.py`**（TDD，先紅後綠）
- `compute_hour_stats()` 空 log → 全 0 統計
- `score_time_slot(hour=5)` 高失敗率時段 → level="high"
- `score_time_slot(hour=10)` 低失敗率 → level="low"
- `write_risk_report()` 輸出格式驗證

### 修改現有檔案

**`tools/trace_analyzer.py`**：新增 `analyze_by_hour(entries) -> dict[int, dict]`
- 依 entry["ts"] 的 hour 分組，統計 total/errors/failure_rate/top_modes
- 整合到 `run_analysis()` 回傳：`"hour_breakdown": analyze_by_hour(entries)`

**`run-todoist-agent-team.ps1`**：在 Phase 0d 之後、Phase 1a 之前插入 Phase 0e

```powershell
# Phase 0e: ADR-037 時段風險評估閘門
$script:ADR037_SkipTaskTypes = @()
$script:ADR037_TimeoutMultiplier = 1.0
try {
    $riskJson = uv run --project $AgentDir python tools/time_slot_risk_scorer.py --format json 2>/dev/null
    if ($riskJson) {
        $risk = ConvertFrom-Json $riskJson
        $action = $risk.risk.recommended_action
        switch ($action) {
            "extend_timeout" { $script:ADR037_TimeoutMultiplier = 1.30 }
            "skip_non_critical" {
                $script:ADR037_SkipTaskTypes = @($risk.risk.skip_task_types)
                $script:ADR037_TimeoutMultiplier = 1.30
            }
            "skip_phase2" { $script:ADR037_CriticalRisk = $true }
        }
        $riskJson | Set-Content "$AgentDir\state\time-slot-risk.json" -Encoding UTF8
        Write-Log "[Phase0e] ADR-037 risk=$($risk.risk.risk_level) action=$action"
    }
} catch {
    Write-Log "[Phase0e] 風險評估失敗（略過）: $_"
}
```

在 Phase 2 自動任務分配迴圈處，讀取 `$script:ADR037_SkipTaskTypes` 過濾任務型態。

---

## ADR-035：實時預算監控與 per-trace 成本歸因

### 修改現有檔案

**`config/budget.yaml`**（追加兩個段落）
```yaml
phase_budget:
  phase1: 500_000
  phase2: 2_000_000
  phase3: 200_000
  phase2_auto: 800_000

trace_budget:
  warn_threshold: 3_000_000
  suspend_threshold: 8_000_000
```

**`hooks/post_tool_logger.py`** — 在 `_update_token_usage()` 現有每日累計邏輯之後，**追加**（不替換）per-phase/per-trace 累計，所有新增程式碼包在 `try/except Exception: pass` 內：

```python
# 追加 per-phase 累計（ADR-035，silent fail）
try:
    phase_key = os.environ.get("AGENT_PHASE", "")
    if phase_key:
        phases = day_data.setdefault("phases", {})
        phases.setdefault(phase_key, {"estimated_tokens": 0, "tool_calls": 0})
        phases[phase_key]["estimated_tokens"] += estimated
        phases[phase_key]["tool_calls"] += 1
    trace_id = os.environ.get("DIGEST_TRACE_ID", "")
    if trace_id:
        traces = day_data.setdefault("traces", {})
        tk = trace_id[:12]
        traces.setdefault(tk, {"start_time": ..., "total_tokens": 0, "phase_breakdown": {}})
        traces[tk]["total_tokens"] += estimated
        if phase_key:
            traces[tk]["phase_breakdown"][phase_key] = traces[tk]["phase_breakdown"].get(phase_key, 0) + estimated
        if len(traces) > 50:  # 防膨脹
            oldest = sorted(traces, key=lambda k: traces[k].get("start_time", ""))[0]
            del traces[oldest]
except Exception:
    pass
```

升級 schema_version → 3，向後相容（budget_guard.py 用 `.get()` 讀新欄位）。

### 新建檔案

**`tools/phase_budget_reporter.py`**
- `check_phase_budget(phase, trace_id) -> dict`：讀 token-usage.json，比對 budget.yaml 的 phase_budget/trace_budget，回傳 `{warn_phase, warn_trace, suspend_trace, ...}`
- `format_phase_summary(trace_id) -> str`：格式化整個 trace 的 token 消耗摘要
- 超限時呼叫 ntfy 告警（tempfile JSON + curl，複用 budget_guard 模式）
- CLI：`uv run python tools/phase_budget_reporter.py --phase phase1 --trace-id abc --format json`

**`tests/tools/test_phase_budget_reporter.py`**（TDD）
- 未超限 → warn=False
- 超 phase_limit → warn_phase=True
- 超 warn_threshold → warn_trace=True
- 超 suspend_threshold → suspend_trace=True
- token-usage.json 不存在時 graceful fallback

**`tests/hooks/test_post_tool_logger.py`** 新增測試
- mock AGENT_PHASE env → phases 欄位正確更新
- mock DIGEST_TRACE_ID env → traces 欄位正確更新
- 無 env var 時 schema_version=2 資料不受影響（向後相容）

### `run-todoist-agent-team.ps1` — 各 Phase 結束後插入 budget check

```powershell
# Phase 1 結束後（緊接 Set-FsmState "phase1" "completed" 之後）
try {
    $bc = uv run --project $AgentDir python tools/phase_budget_reporter.py `
        --phase phase1 --trace-id $traceId --format json 2>/dev/null | ConvertFrom-Json
    if ($bc.warn_phase) { Write-Log "[ADR-035] Phase 1 token 警告: $($bc.phase_tokens)" }
    if ($bc.suspend_trace) { Write-Log "[ADR-035] Trace 超限，跳過後續 Phase 2 自動任務" }
} catch { }
```

---

## ADR-036：Context Compression 閾值觸發機制

### 新建檔案

**`tools/context_compressor.py`**

狀態機（ContextState）：
- `NORMAL` (< 65%)：無動作
- `WARNING` (65-80%)：注入 BufferWindow 提示（保留最近 5 次工具呼叫關鍵結果）
- `CRITICAL` (> 80%)：注入 Summary 提示（強制壓縮為任務摘要格式）

```python
MAX_CONTEXT_TOKENS = 200_000  # Claude Sonnet 4.6
WARN_THRESHOLD = 0.65
CRITICAL_THRESHOLD = 0.80

def update_session(session_id, input_chars, output_chars, phase) -> SessionUsage
def check_threshold(session) -> dict:
    # 回傳 {"state", "utilization", "action", "prompt_injection"}
def cleanup_stale_sessions(max_age_hours=4) -> int
```

狀態持久化：`state/context-usage.json`（schema_version=1）
壓縮提示寫入：`state/context-compression-hint-{sid8}.txt`（TTL=30 分鐘）

**`tests/tools/test_context_compressor.py`**（TDD，9 個測試案例）
- < 65% → action="none"
- 65-80% → action="inject_buffer_window", prompt_injection 非空
- > 80% → action="inject_summary"
- cleanup：4 小時以上 session 被移除，新鮮 session 保留
- context-usage.json 不存在時 graceful 初始化

### 修改現有檔案

**`hooks/post_tool_logger.py`** — `main()` 末尾追加（dynamic import，silent fail）：

```python
try:
    import importlib.util as _ilu
    _cc_path = os.path.join(project_root, "tools", "context_compressor.py")
    if os.path.exists(_cc_path):
        _spec = _ilu.spec_from_file_location("context_compressor", _cc_path)
        _cc = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_cc)
        _sid = (session_id or "")[:8]
        if _sid:
            _sess = _cc.update_session(_sid, input_len, output_len, os.environ.get("AGENT_PHASE",""))
            _res = _cc.check_threshold(_sess)
            if _res.get("prompt_injection"):
                hint_path = os.path.join(project_root, "state", f"context-compression-hint-{_sid}.txt")
                open(hint_path, "w", encoding="utf-8").write(_res["prompt_injection"])
                tags.append(f"context-{_res['state']}")
except Exception:
    pass
```

**`templates/shared/preamble.md`** — 結尾新增：
```markdown
## Context 壓縮感知
在每個主要步驟開始前，若 `state/context-compression-hint-{SESSION_ID[:8]}.txt` 存在：
讀取並按指示壓縮工作記憶，然後刪除此檔案繼續執行。此機制由 Hook 自動觸發。
```

**`config/budget.yaml`** — 新增段落：
```yaml
context_compression:
  enabled: true
  max_context_tokens: 200_000
  warn_threshold: 0.65
  critical_threshold: 0.80
  hint_file_ttl_minutes: 30
  cleanup_session_age_hours: 4
```

**`run-todoist-agent-team.ps1`** — Loop-State 清理段落附近新增：
```powershell
# context-compression hint 清理（30 分鐘 TTL）
Get-ChildItem "$AgentDir\state\context-compression-hint-*.txt" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddMinutes(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
```

---

## 修改檔案總覽

| 操作 | 檔案 | ADR |
|------|------|-----|
| 新建 | `config/external-sla.yaml` | 037 |
| 新建 | `tools/time_slot_risk_scorer.py` | 037 |
| 新建 | `tests/tools/test_time_slot_risk_scorer.py` | 037 |
| 修改 | `tools/trace_analyzer.py`（新增 `analyze_by_hour()`） | 037 |
| 修改 | `run-todoist-agent-team.ps1`（Phase 0e + budget check + hint 清理） | 037/035/036 |
| 修改 | `config/budget.yaml`（新增 phase_budget / trace_budget / context_compression） | 035/036 |
| 修改 | `hooks/post_tool_logger.py`（`_update_token_usage()` 追加 + dynamic import） | 035/036 |
| 新建 | `tools/phase_budget_reporter.py` | 035 |
| 新建 | `tests/tools/test_phase_budget_reporter.py` | 035 |
| 修改 | `tests/hooks/test_post_tool_logger.py`（新增 per-phase/trace 測試） | 035 |
| 新建 | `tools/context_compressor.py` | 036 |
| 新建 | `tests/tools/test_context_compressor.py` | 036 |
| 修改 | `templates/shared/preamble.md`（新增 Context 壓縮感知章節） | 036 |

---

## 安全原則（重要）

- **`post_tool_logger.py` 是 Hook 機器強制層**：所有新增程式碼必須用 `try/except Exception: pass` 包住，任何例外只能 silent fail，不可中斷工具呼叫流程
- **ADR-036 的 `context_compressor` 使用 dynamic import**：`tools/context_compressor.py` 不存在時 hook 不會 crash
- **ADR-035 的 schema 升級向後相容**：token-usage.json schema_version 2→3，讀取方用 `.get()` 取新欄位
- **ADR-037 Phase 0e 包在 `try/catch`**：評估失敗不影響主流程，`$ADR037_SkipTaskTypes` 預設為空陣列
- **不使用 `> nul`**：PS1 靜默輸出用 `2>/dev/null`（bash/pwsh 7）或 `| Out-Null`

---

## 驗證方式

### ADR-037
```bash
# 執行測試（紅→綠）
uv run pytest tests/tools/test_time_slot_risk_scorer.py -v
# 手動執行
uv run python tools/time_slot_risk_scorer.py --format json
# 確認輸出 state/time-slot-risk.json 存在且 risk_level 合理
```

### ADR-035
```bash
uv run pytest tests/tools/test_phase_budget_reporter.py tests/hooks/test_post_tool_logger.py -v
# 設置 env var 後執行 post_tool_logger，確認 phases 欄位出現在 token-usage.json
AGENT_PHASE=phase1 DIGEST_TRACE_ID=testTrace123 uv run python hooks/post_tool_logger.py ...
```

### ADR-036
```bash
uv run pytest tests/tools/test_context_compressor.py -v
# 確認 state/context-compression-hint-*.txt 在 > 65% 時被建立
# 確認 preamble.md 讀取指引已加入
```

### 整合驗證
```bash
# 全套測試（基線 856 個，新增後應 ≥ 880 個）
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
# 執行一次完整的 todoist-agent-team
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1
# 確認日誌中出現 [Phase0e] 和 [ADR-035] 訊息
```
