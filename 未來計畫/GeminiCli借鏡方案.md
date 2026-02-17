Context
透過深入分析 google-gemini/gemini-cli（94.6k stars，TypeScript monorepo），識別出 8 個可移植到本專案的架構模式。Gemini CLI 採用分層架構（core/cli/sdk）、TOML 政策引擎、4 類錯誤分類、3 階段上下文壓縮、迴圈偵測服務、裝飾器管線、11 個生命週期 Hook 事件等成熟設計。
本專案目前的不足：

錯誤處理盲區：所有 PowerShell 腳本只有 $LASTEXITCODE + 固定延遲重試，無錯誤分類
無分散式追蹤：Team 模式 5 個並行 Agent 寫入同一 JSONL，無法關聯同一次執行的所有日誌
配置驗證不完整：validate_config.py 只覆蓋 7/13 個 YAML 檔，無 Schema 驗證
無迴圈偵測：Agent 可能重複呼叫相同 API 或陷入無限循環，無法偵測
安全規則扁平化：hook-rules.yaml 所有規則同等權重，無法區分開發 vs 生產環境

選擇標準：影響力 × 可行性 × 與現有架構的契合度。所有方案都基於現有 Python hooks + PowerShell 腳本 + YAML 配置的技術棧，不引入新的 runtime 依賴。

優化項目總覽（按優先級排序）
#優化項目影響工作量來源模式1分散式追蹤（Trace ID）高低Gemini CLI telemetry 系統2錯誤分類 + API 可用性追蹤極高中errorClassification.ts + modelAvailabilityService.ts3配置 Schema 驗證 + 遷移系統高中storageMigration.ts + Zod 驗證4迴圈偵測服務高中loopDetectionService.ts5分層安全策略引擎中中policy-engine.ts + TOML presets6結構化測試 + 錄製/重播中高RecordingContentGenerator + co-located tests

項目 1：分散式追蹤（Trace ID + Phase 標記）
為何選擇此項目
這是最低成本、最高可見性的改善。目前 Team 模式同時啟動 5 個 Agent，各自寫入相同的 JSONL 日誌，靠 sid（session ID 前 12 字元）區分。但無法回答「08:00 的摘要為什麼缺少新聞？」——必須手動比對時間戳。Gemini CLI 的 telemetry 系統為每個操作附加 trace/span ID，實現端到端追蹤。
實作方案
A. PowerShell 腳本產生 Trace ID
修改 run-agent-team.ps1（第 97-99 行區域）：
powershell$TraceId = [guid]::NewGuid().ToString("N").Substring(0, 12)
$env:DIGEST_TRACE_ID = $TraceId
Write-Log "TraceId: $TraceId"
在 Phase 1 每個 Start-Job 前設定 phase 環境變數（第 133 行區域）：
powershell$env:DIGEST_PHASE = "phase1-$agentName"
Phase 2 組裝前：
powershell$env:DIGEST_PHASE = "phase2-assemble"
B. Hook 傳播 Trace 到 JSONL
修改 hooks/post_tool_logger.py（第 217-226 行），在 entry 中加入：
pythontrace_id = os.environ.get("DIGEST_TRACE_ID", "")
phase = os.environ.get("DIGEST_PHASE", "")
if trace_id:
    entry["trace_id"] = trace_id
if phase:
    entry["phase"] = phase
C. on_stop_alert.py 寫入 Trace 摘要
在 write_session_summary() 中（第 302 行）加入 trace_id 和 phase 欄位。
D. 查詢工具支援 Trace 過濾
修改 hooks/query_logs.py 新增 --trace <trace_id> 參數。
修改檔案
檔案動作run-agent-team.ps1修改：產生 + 傳播 trace_id、phaserun-todoist-agent-team.ps1修改：同上run-system-audit-team.ps1修改：同上hooks/post_tool_logger.py修改：讀取環境變數寫入 JSONL（~5 行）hooks/on_stop_alert.py修改：summary 加入 trace_id 欄位hooks/query_logs.py修改：新增 --trace 過濾選項

項目 2：錯誤分類 + API 可用性追蹤
為何選擇此項目
這是影響最大的改善。目前所有重試邏輯都是「檢查 $LASTEXITCODE → 固定等 60s → 重試一次」。不區分 429（應等 Retry-After 秒數再試）、500（應立即重試）、401（應停止）、timeout（應延長超時重試）。Gemini CLI 的 4 類錯誤分類 + 模型可用性服務提供了精確的重試決策，且跨 session 記住 API 健康狀態。
本專案每小時執行一次，若上一輪 Todoist API 全面故障，下一輪仍盲目重試。加入 circuit breaker 可跳過已知故障 API，直接使用快取。
實作方案
A. 錯誤分類器 — 新建 hooks/error_classifier.py
pythonclass ErrorCategory(Enum):
    TERMINAL = "terminal"      # 401, 403 → 停止
    TRANSIENT = "transient"    # 429, 500, 502, 503, timeout → 重試
    NOT_FOUND = "not_found"    # 404 → 跳過此步驟
    UNKNOWN = "unknown"        # 未知 → 重試一次

class RetryIntent(Enum):
    STOP = "stop"
    RETRY_ALWAYS = "retry_always"
    RETRY_ONCE = "retry_once"
    RETRY_LATER = "retry_later"  # 429 + Retry-After
    SKIP = "skip"

def classify(tool_output: str, exit_code: int = 0) -> tuple[ErrorCategory, RetryIntent]:
    """從工具輸出提取 HTTP 狀態碼 + 錯誤訊息，回傳分類結果。"""
B. 錯誤模式配置 — 新建 config/error-patterns.yaml
yamlversion: 1
http_status_map:
  401: { category: terminal, intent: stop }
  403: { category: terminal, intent: stop }
  404: { category: not_found, intent: skip }
  429: { category: transient, intent: retry_later }
  500: { category: transient, intent: retry_always }
  502: { category: transient, intent: retry_always }
  503: { category: transient, intent: retry_always }
backoff:
  base_seconds: 30
  max_seconds: 300
  multiplier: 2
  jitter_max: 15
C. API 可用性追蹤 — 新建 hooks/api_availability.py
Circuit breaker 狀態檔 state/api-health.json：
json{
  "todoist": {
    "last_success": "2026-02-16T08:00:00",
    "consecutive_failures": 0,
    "circuit_state": "closed",
    "cooldown_until": null
  }
}
三種狀態：closed（正常）→ 3 次連續失敗 → open（跳過，用快取）→ cooldown 到期 → half_open（試一次）→ 成功則 closed。
D. 整合 post_tool_logger.py
在錯誤偵測區段（第 207-214 行）加入分類：
pythonif has_error:
    from error_classifier import classify
    category, intent = classify(tool_output)
    entry["error_category"] = category.value
    entry["retry_intent"] = intent.value
E. 整合 on_stop_alert.py
Session 結束時呼叫 api_availability.update_health() 更新 circuit breaker 狀態。
F. 整合 PowerShell 腳本
run-agent-team.ps1 Phase 1 前讀取 state/api-health.json，跳過 open 狀態的 API 對應 Agent：
powershell# Read API health, skip agents with open circuits
$apiHealth = Get-Content "state/api-health.json" | ConvertFrom-Json
foreach ($agent in $fetchAgents) {
    $source = $agent.Name
    if ($apiHealth.$source.circuit_state -eq "open") {
        Write-Log "[Phase1] Skipping $source (circuit open until $($apiHealth.$source.cooldown_until))"
        $sections[$source] = "circuit_open"
        continue
    }
    # ... launch job as usual
}
修改檔案
檔案動作hooks/error_classifier.py新建：錯誤分類邏輯hooks/api_availability.py新建：circuit breaker + 健康追蹤config/error-patterns.yaml新建：HTTP 狀態碼 → 分類對映hooks/post_tool_logger.py修改：加入錯誤分類欄位hooks/on_stop_alert.py修改：session 結束更新 API 健康run-agent-team.ps1修改：Phase 1 前讀取健康狀態、跳過故障 APIrun-todoist-agent-team.ps1修改：同上config/cache-policy.yaml修改：加入 circuit_breaker 區段（cooldown_minutes）tests/hooks/test_error_classifier.py新建tests/hooks/test_api_availability.py新建

項目 3：配置 Schema 驗證 + 遷移系統
為何選擇此項目
專案有 13 個 YAML 配置檔（~59KB），但 validate_config.py 只覆蓋 7 個且驗證極淺（只查頂層 key 存在性）。例如 timeouts.yaml、audit-scoring.yaml、benchmark.yaml、health-scoring.yaml、topic-rotation.yaml、hook-rules.yaml(read_rules) 完全無驗證。frequency-limits.yaml 已從 v2 演進到 v3，但無自動遷移——手動改壞格式會在排程執行時才發現。
Gemini CLI 使用 storageMigration.ts 為配置升級提供版本化遷移路徑，用 Zod schema 驗證所有配置結構。
實作方案
A. JSON Schema 定義 — 新建 config/schemas/ 目錄
為每個 YAML 建立對應的 JSON Schema 檔案（13 個）。範例 timeouts.schema.json：
json{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version"],
  "properties": {
    "version": { "type": "integer", "minimum": 1 },
    "daily_digest_team": {
      "type": "object",
      "properties": {
        "phase1_timeout": { "type": "integer", "minimum": 60, "maximum": 600 },
        "phase2_timeout": { "type": "integer", "minimum": 60, "maximum": 900 }
      }
    }
  }
}
B. 強化 hooks/validate_config.py

優先使用 jsonschema 套件驗證（pip install jsonschema）
若未安裝則回退到現有的手寫 SCHEMAS
新增跨檔一致性檢查：

frequency-limits.yaml 的 task keys 必須對應 run-todoist-agent-team.ps1 的 $dedicatedPrompts
cache-policy.yaml 的 source names 必須涵蓋 post_tool_logger.py 的 API_SOURCE_PATTERNS
notification.yaml 的 tag_mappings 必須覆蓋所有 agent 類型



C. 遷移系統 — 新建 hooks/config_migration.py
pythonMIGRATIONS = {
    "frequency-limits.yaml": {
        2: migrate_freq_v2_to_v3,  # 加入 execution_order 欄位
    },
    "hook-rules.yaml": {
        1: migrate_hooks_v1_to_v2,  # 加入 priority 欄位（項目 5）
    },
}

def migrate(config_dir, dry_run=True):
    """檢查並執行所有待進行的遷移。"""
CLI：python hooks/config_migration.py --check（乾跑）或 --apply（執行）
修改檔案
檔案動作config/schemas/*.schema.json新建：13 個 JSON Schemahooks/validate_config.py修改：整合 JSON Schema + 跨檔檢查hooks/config_migration.py新建：版本遷移引擎tests/hooks/test_validate_config.py修改：測試新 schematests/hooks/test_config_migration.py新建

項目 4：迴圈偵測服務
為何選擇此項目
Agent 可能陷入迴圈（重複呼叫同一 curl 指令、反覆讀取同一 SKILL.md、產生重複輸出），浪費 API 配額和 context window。現有的 research-registry.json 只做跨 session 的研究主題去重，無法偵測 session 內的工具呼叫迴圈。
Gemini CLI 的 loopDetectionService.ts 提供三層偵測：工具呼叫 hash（SHA-256, 閾值 5）、內容重複（50 字元窗口, 閾值 10）、LLM 分析（30+ turns 後）。本專案採用前兩層即足夠。
實作方案
A. 迴圈偵測模組 — 新建 hooks/loop_detector.py
pythondef check_tool_call_loop(session_entries: list, new_entry: dict) -> dict | None:
    """Tier 1: 相同 tool+input 組合重複 >= threshold 次。"""
    # SHA-256(tool_name + tool_input_json)
    # 視窗：最近 20 筆同 session 條目
    # 閾值：5 次相同呼叫

def check_content_repetition(session_entries: list) -> dict | None:
    """Tier 2: 輸出內容重複迴圈偵測。"""
    # 滑動視窗：最近 10 筆工具輸出
    # 比對 50 字元前綴 hash
    # 閾值：3 次近似輸出

def check_excessive_turns(session_entries: list, agent_type: str) -> dict | None:
    """Tier 3: 工具呼叫次數超標。"""
    # 閾值從 config/timeouts.yaml 讀取
    # 80% 時 warning，100% 時 block
B. 整合 post_tool_logger.py
在日誌寫入後（第 246 行之後）呼叫偵測：
python# Loop detection (after logging)
try:
    from loop_detector import check_tool_call_loop
    loop_result = check_tool_call_loop(session_entries_cache, entry)
    if loop_result:
        # Write loop detection event
        loop_entry = {**entry, "event": "loop_detected", "loop_type": loop_result["type"]}
        # Write signal file for PowerShell to check
        with open("results/.loop_detected", "w") as f:
            json.dump(loop_result, f)
except ImportError:
    pass
C. 配置擴展 — 修改 config/timeouts.yaml
yamlloop_detection:
  tool_hash_threshold: 5
  tool_hash_window: 20
  content_threshold: 3
  content_window: 10
  max_turns:
    digest: 80
    todoist: 150
    research: 100
    audit: 120
修改檔案
檔案動作hooks/loop_detector.py新建：三層迴圈偵測hooks/post_tool_logger.py修改：日誌後呼叫偵測器config/timeouts.yaml修改：加入 loop_detection 區段tests/hooks/test_loop_detector.py新建

項目 5：分層安全策略引擎
為何選擇此項目
目前 config/hook-rules.yaml 是扁平規則列表，所有規則同等權重。專案在兩種截然不同的模式下運行：排程自動化（應嚴格）和互動開發（應寬鬆）。無法為不同場景啟用/停用規則。
Gemini CLI 使用 TOML 策略檔 + 3 層優先級（Admin > User > Default）+ 審批模式（DEFAULT/AUTO_EDIT/YOLO），可針對不同場景套用不同安全等級。
實作方案
A. 規則加入優先級和預設集 — 修改 config/hook-rules.yaml
yamlversion: 2

presets:
  strict:
    description: "排程執行（預設）— 全部規則啟用"
    disabled_rules: []
  standard:
    description: "互動開發 — 放寬非關鍵規則"
    disabled_rules: ["sensitive-env"]
  permissive:
    description: "除錯模式 — 僅保留 critical 規則"
    disabled_rules: ["sensitive-env", "force-push"]

bash_rules:
  - id: nul-redirect
    priority: critical    # 新欄位
    # ... 現有欄位不變 ...
  - id: exfiltration
    priority: critical    # 不可被任何 preset 停用
  - id: sensitive-env
    priority: medium      # 可被 standard/permissive 停用
B. 策略解析器 — 修改 hooks/hook_utils.py
pythondef resolve_active_rules(section_key, fallback_rules):
    """載入規則，依活動 preset 過濾，依優先級排序。"""
    rules = load_yaml_rules(section_key, fallback_rules)
    preset_name = os.environ.get("DIGEST_SECURITY_LEVEL", "strict")
    # 載入 preset 定義
    # 過濾 disabled_rules（critical 規則永遠不可停用）
    # 依優先級排序：critical > high > medium > low
    return filtered_rules
C. PowerShell 腳本設定安全等級
排程腳本（run-agent-team.ps1 等）：
powershell$env:DIGEST_SECURITY_LEVEL = "strict"  # 排程執行
```

互動時可手動設為 `standard` 或 `permissive`。

### 修改檔案
| 檔案 | 動作 |
|------|------|
| `config/hook-rules.yaml` | 修改：加入 presets + priority 欄位（v1→v2 遷移） |
| `hooks/hook_utils.py` | 修改：新增 `resolve_active_rules()` |
| `hooks/pre_bash_guard.py` | 修改：使用 `resolve_active_rules()` |
| `hooks/pre_write_guard.py` | 修改：同上 |
| `hooks/pre_read_guard.py` | 修改：同上 |
| `run-agent-team.ps1` | 修改：設定 `$env:DIGEST_SECURITY_LEVEL` |
| `run-todoist-agent-team.ps1` | 修改：同上 |
| `tests/hooks/test_policy_engine.py` | 新建 |

---

## 項目 6：結構化測試 + 錄製/重播

### 為何選擇此項目
目前只有 10 個測試檔（~636 行），覆蓋 hooks 和基本 API 格式。無整合測試（Phase 1→2 管線）、無 golden 測試（配置輸出穩定性）、無 API 回應錄製/重播。專案 24/7 自動運行，對配置修改的信心不足。

Gemini CLI 使用 `RecordingContentGenerator` 錄製真實 API 回應 → `FakeContentGenerator` 確定性重播，加上 co-located tests 和 golden tests。

### 實作方案

**A. API 回應 fixtures** — 新建 `tests/fixtures/`
```
tests/fixtures/
  api_responses/
    todoist_tasks.json          # 去敏的真實 Todoist 回應
    pingtung_news.json
    hackernews_top.json
  cache_states/
    fresh_cache.json            # TTL 內的快取
    expired_cache.json          # TTL 外但降級窗口內
B. 整合測試 — 新建 tests/integration/
python# tests/integration/test_error_pipeline.py
def test_transient_error_classified_correctly():
    """429 回應應分類為 transient + retry_later。"""

def test_circuit_breaker_opens_after_3_failures():
    """連續 3 次失敗後 circuit 應開啟。"""

# tests/integration/test_loop_detection.py
def test_identical_curl_detected_at_threshold():
    """同一 curl 指令重複 5 次應觸發迴圈偵測。"""
C. Golden 測試 — 新建 tests/golden/
python# tests/golden/test_config_stability.py
def test_frequency_limits_total_45():
    """所有任務 daily_limit 總和應為 45。"""

def test_routing_templates_exist():
    """所有路由對映的模板檔案應存在。"""

def test_hook_rules_ids_unique():
    """所有規則 id 必須唯一。"""
```

**D. 配置跨引用測試** — 新建 `tests/golden/test_cross_references.py`

驗證各配置檔之間的參照一致性。

### 修改檔案
| 檔案 | 動作 |
|------|------|
| `tests/fixtures/api_responses/*.json` | 新建：去敏 API 回應 |
| `tests/fixtures/cache_states/*.json` | 新建：快取狀態 fixtures |
| `tests/integration/test_error_pipeline.py` | 新建 |
| `tests/integration/test_loop_detection.py` | 新建 |
| `tests/golden/test_config_stability.py` | 新建 |
| `tests/golden/test_cross_references.py` | 新建 |

---

## 實作順序（依賴關係）
```
Phase A（基礎層）：
  項目 1: 分散式追蹤    ← 無依賴，立即提供可見性
  項目 3: 配置 Schema   ← 無依賴，保護後續配置變更

Phase B（核心改善）：
  項目 2: 錯誤分類      ← 依賴項目 1 的 trace_id 做錯誤關聯
  項目 4: 迴圈偵測      ← 依賴項目 1 的 session 追蹤

Phase C（強化層）：
  項目 5: 策略引擎      ← 依賴項目 3 的 schema 驗證 preset 格式
  項目 6: 測試框架      ← 依賴項目 2/4 才有東西可測
新建 / 修改檔案完整清單
新建檔案（14 個）
檔案用途hooks/error_classifier.py4 類錯誤分類引擎hooks/api_availability.pyCircuit breaker + API 健康追蹤hooks/loop_detector.py三層迴圈偵測hooks/config_migration.py配置版本遷移引擎config/error-patterns.yamlHTTP 狀態碼 → 錯誤分類對映config/schemas/*.schema.json13 個 JSON Schema（作為一組）tests/hooks/test_error_classifier.py錯誤分類測試tests/hooks/test_api_availability.pyCircuit breaker 測試tests/hooks/test_loop_detector.py迴圈偵測測試tests/hooks/test_policy_engine.py策略引擎測試tests/hooks/test_config_migration.py遷移測試tests/integration/test_error_pipeline.py錯誤管線整合測試tests/integration/test_loop_detection.py迴圈偵測整合測試tests/golden/test_config_stability.py配置穩定性 golden 測試
修改檔案（11 個）
檔案變更內容hooks/post_tool_logger.py+trace_id/phase 傳播、+錯誤分類、+迴圈偵測呼叫hooks/on_stop_alert.py+trace_id 到 summary、+API 健康更新hooks/hook_utils.py+resolve_active_rules() 策略解析hooks/pre_bash_guard.py使用 resolve_active_rules()hooks/pre_write_guard.py使用 resolve_active_rules()hooks/pre_read_guard.py使用 resolve_active_rules()hooks/validate_config.py+JSON Schema 驗證、+跨檔一致性hooks/query_logs.py+--trace 過濾選項run-agent-team.ps1+trace_id 產生、+API 健康前檢、+security levelrun-todoist-agent-team.ps1同上config/hook-rules.yaml+presets、+priority 欄位（v1→v2）config/cache-policy.yaml+circuit_breaker 區段config/timeouts.yaml+loop_detection 區段
驗證方式

項目 1 驗證：手動執行 run-agent-team.ps1，檢查 JSONL 日誌是否包含 trace_id 和 phase 欄位；用 python hooks/query_logs.py --trace <id> 確認可過濾
項目 2 驗證：執行 python -m pytest tests/hooks/test_error_classifier.py tests/hooks/test_api_availability.py；模擬 API 失敗確認 circuit breaker 開啟
項目 3 驗證：執行 python hooks/validate_config.py --json 確認全部 13 個檔通過；python hooks/config_migration.py --check 確認無待遷移
項目 4 驗證：執行 python -m pytest tests/hooks/test_loop_detector.py；人工製造重複呼叫確認偵測觸發
項目 5 驗證：設定 DIGEST_SECURITY_LEVEL=permissive，確認 medium 規則被跳過但 critical 規則仍生效
項目 6 驗證：執行 python -m pytest tests/ 全部測試通過