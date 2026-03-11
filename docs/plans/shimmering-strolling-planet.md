# AI 架構治理與系統自動優化更新建議方案

> 計畫編號：shimmering-strolling-planet
> 建立日期：2026-03-11（v5 更新：二輪審查修正 — C1/C2/A4/B1/B4 阻斷項、B2/B3/B5/C3-C5/D3/D4 補全）
> 狀態：草稿（待審議）

> **⚠️ 生產問題注意（2026-03-11）**：執行時出現「Phase 2 結果缺失（Missing result file）」。
> **根本原因已知（2026-02-24 已修復）**：prompt 檔命名不規範 + `$dedicatedPrompts` hardcode，已改為動態掃描。
> 若問題再次出現，排查步驟（按 `docs/troubleshooting.md §1.1`）：
> 1. 查看 run 日誌中是否有「Discovered N dedicated prompts」— 若 N 比預期少，代表有 prompt 檔未被掃描到
> 2. 查看 `logs/structured/*.jsonl` 中 Phase 2 任務的 `job_state` 欄位，確認是逾時（timeout）或失敗（error）
> 3. 對照 `config/timeouts.yaml` 的 `phase2_timeout_by_task`（各任務獨立 timeout），計算 Phase 2 總超時應為 `max(各任務 timeout) + 300s buffer`
> 4. 查看 `HEARTBEAT.md` 的「Phase 2 逾時預防」段落確認 watchdog 設定
> 5. 短期緩解：手動執行失敗的 Phase 2 任務後，重跑 Phase 3 組裝
> **P5-A（Agent Pool）是此問題的架構級預防，不是緊急修復**（緊急修復已於 2026-02-24 完成）。

---

## Context（背景與動機）

本計畫整合七個知識來源的洞察，針對 daily-digest-prompt 現有 OODA 閉環架構提出系統性強化方案：

| 來源 | 核心洞察 |
|------|---------|
| DeerFlow 2.0（KB: ddc422ab）| 11層中介軟體鏈、雙線程池子Agent編排、虛擬路徑沙箱隔離 |
| AI 架構治理閉環（KB: b9db3b71）| ADR自動化、Fitness Function量化、技術債優先級排序 |
| 2026 Agentic AI 工作流（KB: 3b45aced）| xRouter RL成本感知路由、ToolOrchestra小模型監督大模型 |
| LLM-as-Router—Gemini CLI（KB: 7f06170d）| 輕量LLM作請求分類器、ClassifierStrategy prompt設計 |
| Dify 蜂巢架構（KB: 52f6a3b0）| Plugin生態、工作流可視化、LLMOps多模型節點 |
| AFFiNE Local-First（KB: 15a379d8）| CRDT協作、Local-First多平台架構 |
| Vite 靜態知識庫管線（KB: 049c6822）| Build-Time Data、增量同步、Cloudflare邊緣部署 |
| AI模型蒸餾計畫（本地）| 量化/剪枝/LoRA減少token消耗、輕量模型路由 |
| 可觀測性成熟度路線圖（KB: 7f971400）| Level 1-5成熟度模型、根因分析整合 |
| **Hono Edge-First 框架（KB: 新）** | RegExpRouter O(1)路由、Web Standards跨Runtime、RPC端對端型別安全 |
| **Structured Generation（KB: 新）** | Constrained Decoding 100%合規、FSM token masking、Instructor/Pydantic AI |
| **Paperclip 零人力公司（KB: 新）** | BYOA架構、原子化預算治理、組織圖目標繼承鏈、不可變審計日誌 |

**現狀問題診斷**（基於 ADR Registry + OODA Workflow + llm-router.yaml 實際探索）：

1. `config/llm-router.yaml` 定義了完整的 providers + routing_rules，**但從未被動態讀取**
   — 現有 Groq 呼叫全部 hardcode 在 `skills/groq/SKILL.md` 的 curl 指令中
2. ADR 記錄全手動，無 Fitness Function 量化驗證，技術債排序無自動化
3. Hook Pipeline 扁平（5個串列），缺乏 DeerFlow 式中介軟體組合能力
4. OODA Decide 層（arch-evolution）剛啟用，決策品質機制待建立
5. 研究成果同步到 know-w.pages.dev 的管線為手動操作
6. 系統可觀測性停留在 Level 2（指標收集），未達 Level 4（根因分析）
7. **Phase 2 自動任務缺乏 pool 化治理**：單一慢速 I/O 可卡住整個 Phase；子步驟失敗後缺乏一致的取消與收尾機制（已知生產風險：「Phase 2 結果缺失」）

---

## 建議方案總覽

| 方案 | 優先級 | 影響範圍 | 預估工時 |
|------|--------|---------|---------|
| **P0-A**：ADR 自動化閉環 | P0 | adr-registry.json + arch-evolution Skill | 2-3天 |
| **P0-B**：Fitness Function 基線 | P0 | config/benchmark.yaml + check-health.ps1 | 1天 |
| **P1-A**：Hook 中介軟體鏈重構 | P1 | hooks/*.py + hook_utils.py | 2天 |
| **P1-B**：LLM Router 具體實作 ⭐ | P1 | tools/llm_router.py + tools/invoke-llm.ps1 | 2天 |
| **P2-A**：Vite 增量同步管線 | P2 | tools/kb-sync-incremental.ps1 | 2天 |
| **P2-B**：OODA Decide 層強化 | P2 | config/ooda-workflow.yaml + arch-evolution | 2天 |
| **P3-A**：LLM-as-Router 元分類器 | P3 | tools/llm_classifier.py | 3天 |
| **P3-B**：可觀測性成熟度 Level 4 | P3 | logs/ + check-health.ps1 | 2天 |
| **P3-C**：ToolOrchestra 編排模式 | P3 | run-todoist-agent-team.ps1 | 3天 |
| **P4-A**：Hono 重構 groq-relay + Workers | P4 | bot/groq-relay.js + workers/ | 2天 |
| **P5-A**：Agent Pool 架構 ⭐ | P5 | run-todoist-agent-team.ps1 + tools/agent_pool/ | 3天 |
| **P4-B**：Structured Generation 強型別輸出 | P4 | tools/llm_router.py + hooks/ | 2天 |
| **P4-C**：Paperclip 式預算治理 | P4 | state/token-usage.json + circuit-breaker | 1天 |
| **P4-D**：目標繼承鏈 + 不可變審計日誌 | P4 | context/improvement-backlog.json + logs/ | 2天 |

---

## P0-A：ADR 自動化閉環

### 問題
`context/adr-registry.json` 目前有11條ADR，更新完全手動。arch-evolution Skill 雖可產生新ADR，但無自動驗證格式、狀態一致性與實施情況的機制。

### 借鑑來源
**KB: b9db3b71**（AI架構治理閉環）提出三層閉環：
1. **ADR-Lint**：CI自動驗證ADR格式與狀態轉換合法性
2. **Fitness Function**：量化架構健康指標（可執行的架構測試）
3. **技術債優先級**：依複雜度×影響力×可行性自動排序

### 實施方案

**新建 `tools/validate_adr.py`**：
```python
"""
功能：
- 驗證 adr-registry.json schema（必填欄位：id, title, status, date, context, decision, consequences）
- 狀態轉換合法性：Proposed→Accepted/Rejected/Deferred，不得跳過
- 自動計算 tech_debt_score（0-10）基於 open_issues + age_days
- 輸出：JSON report（通過/失敗項目列表）
整合到 .git/hooks/pre-commit（已有 validate_config.py 範例可參照）
"""
```

**`context/adr-registry.json` 每條 ADR 新增欄位**：
```json
{
  "fitness_functions": ["test_case_1"],
  "tech_debt_score": 7.5,
  "auto_generated": false,
  "review_due": "2026-04-11"
}
```

**`prompts/team/todoist-auto-arch-evolution.md` 強化**（已存在）：
- 新增 Step：ADR 狀態機掃描，列出 90 天未複查項目
- 從 `context/improvement-backlog.json` 的 ≥P1 項目自動生成 ADR 草稿
- 輸出標記 `auto_generated: true`

**關鍵檔案**：
- `context/adr-registry.json`（修改 schema）
- `tools/validate_adr.py`（新建）
- `.git/hooks/pre-commit`（修改，加 ADR lint）
- `prompts/team/todoist-auto-arch-evolution.md`（修改）

---

## P0-B：Fitness Function 基線定義

### 問題
現有 `config/benchmark.yaml` 有效能基準但無架構健康的量化指標。

### 實施方案

在 `config/benchmark.yaml` 新增 `fitness_functions` 段落：

```yaml
fitness_functions:
  adr_coverage:        # ADR 覆蓋率
    target: ">= 90%"
    auto_check: true
  hook_precision:      # Hook 攔截精準率（False Positive < 5%）
    target: "false_positive_rate < 5%"
    measure: "uv run python hooks/query_logs.py --mode precision"
  ooda_completion:     # OODA 循環完成率
    target: ">= 80%"
    source: "logs/structured/ooda-transitions.jsonl"
  tech_debt_velocity:  # 每週解決 >= 新增
    target: "resolved >= new_per_week"
  config_entropy:      # 配置膨脹（已有 analyze-config.ps1）
    target: "< 0.65"
    measure: "analyze-config.ps1 -Mode score"
  groq_routing_ratio:  # Groq 路由佔比（P1-B 啟用後才有意義）
    target: ">= 30%"
    measure: "state/token-usage.json groq_calls / total_calls"
```

`check-health.ps1` 新增 `[Fitness Function 評分]` 區塊，6 維度加權輸出 0-100 分。

**關鍵檔案**：`config/benchmark.yaml`、`check-health.ps1`

---

## P1-A：Hook 中介軟體鏈重構

### 問題
5 個 Hook 各自獨立載入 `config/hook-rules.yaml`，無共用 pipeline 框架。

### 借鑑來源
**DeerFlow 2.0** 的中介軟體鏈：每層 `(context) → (modified_context | block)`，短路機制。

### 實施方案

**新建 `hooks/hook_pipeline.py`**：
```python
class HookPipeline:
    """借鑑 DeerFlow 11層設計；不改變 stdin/stdout JSON 接口"""
    def __init__(self, middlewares: list): ...
    def execute(self, context: dict) -> dict:
        for mw in self.middlewares:
            result = mw(context)
            if result.get("decision") == "block":
                return result          # 短路
            context = {**context, **result.get("modified", {})}
        return {"decision": "allow", "modified": context}
```

`hooks/hook_utils.py` 新增 `compose_middlewares()` 工廠函數（已有基礎 load_yaml_rules/log_blocked_event）。
`hooks/pre_bash_guard.py` 拆成 4 個中介軟體函數，通過 HookPipeline 組合。

**測試策略**：現有 556 個測試全數通過（不改變行為，只改組合方式）。

**關鍵檔案**：`hooks/hook_pipeline.py`（新建）、`hooks/hook_utils.py`、`hooks/pre_bash_guard.py`、`tests/hooks/test_hook_pipeline.py`（新建）

---

## P1-B：LLM Router 具體實作 ⭐

### 問題
`config/llm-router.yaml` 已有完整 providers + routing_rules 定義，但**從未被動態讀取**。現有呼叫模式：
- `skills/groq/SKILL.md` hardcode `curl localhost:3002/groq/chat`（4 種 mode）
- 兩者脫鉤：`llm-router.yaml` 的路由決策 ≠ 實際 Groq Skill 執行路徑

### 目標架構

```
任何 Prompt / PowerShell 腳本
         │
         ▼  --task-type news_summary
tools/invoke-llm.ps1
         │
         ▼  讀取 config/llm-router.yaml
tools/llm_router.py   ←── routing_rules 比對
         │
    ┌────┴────┐
    ▼         ▼
Groq Relay   Claude CLI
localhost:   claude -p
3002/groq/   (由呼叫方
chat         負責執行)
    │
    ▼
結果回傳 JSON
```

### 現有 llm-router.yaml 結構（已確認 — Mapping 格式）

> ⚠️ **重要**：實際 `config/llm-router.yaml` 的 `routing_rules` 是 **mapping（dict）格式**，key 為 task_type，value 為規則物件。計畫中所有程式碼必須基於此格式，使用 O(1) dict lookup，不得以 list 遍歷。

```yaml
providers:
  groq:
    endpoint: "http://localhost:3002"
    model: "llama-3.1-8b-instant"
    rate_limit: "5 req/min"
    cache_ttl: "5min"
  claude:
    fallback: true

routing_rules:
  # → Groq 路徑（key = task_type）
  news_summary:
    provider: groq
  en_to_zh:
    provider: groq
  topic_classify:
    provider: groq
  quick_extract:
    provider: groq
  kb_content_score:
    provider: groq
  # → Claude 路徑
  policy_analysis:
    provider: claude
  research_synthesis:
    provider: claude
  code_review:
    provider: claude
  security_analysis:
    provider: claude
  gmail_processing:
    provider: claude
```

> **需要補充**：每條 Groq 規則需加 `groq_mode` 與 `max_tokens` 子欄位。

### 實施方案

#### Step 1：擴充 `config/llm-router.yaml`（修改 — 保持 Mapping 格式）

在每條 Groq 規則下補充 `groq_mode` 和 `max_tokens`，Claude 規則補充 `rationale`：

```yaml
routing_rules:
  # → Groq 路徑（key = task_type，value = 規則物件）
  news_summary:
    provider: groq
    groq_mode: summarize        # ← 新增，對應 relay /groq/chat 的 mode 參數
    max_tokens: 200
    rationale: "30字摘要，結構固定"

  en_to_zh:
    provider: groq
    groq_mode: translate
    max_tokens: 500
    rationale: "英中翻譯，保留術語"

  topic_classify:
    provider: groq
    groq_mode: classify
    max_tokens: 100
    rationale: "主題標籤，JSON輸出"

  quick_extract:
    provider: groq
    groq_mode: extract
    max_tokens: 300
    rationale: "結構化萃取，JSON輸出"

  kb_content_score:
    provider: groq
    groq_mode: classify
    max_tokens: 150
    rationale: "KB內容分類評分"

  # → Claude 路徑
  policy_analysis:
    provider: claude
    rationale: "需要深度語境理解"

  research_synthesis:
    provider: claude
    rationale: "需要複雜推理+長上下文"

  code_review:
    provider: claude
    rationale: "需要程式語意理解"

  security_analysis:
    provider: claude
    rationale: "高精準度需求"

  gmail_processing:
    provider: claude
    rationale: "需要細膩情境判斷"
```

#### Step 2：新建 `tools/llm_router.py`（核心路由器）

```python
#!/usr/bin/env python3
"""
LLM Router — 動態讀取 llm-router.yaml，決定呼叫 Groq Relay 或回傳 Claude 指示

使用方式（命令列）：
  uv run python tools/llm_router.py --task-type news_summary --input "AI news..."
  uv run python tools/llm_router.py --task-type research_synthesis --dry-run

回傳 JSON：
  Groq 路徑：{"provider":"groq","result":"...","model":"llama-3.1-8b-instant","cached":false}
  Claude 路徑：{"provider":"claude","use_claude":true,"rationale":"..."}
  失敗降級：{"provider":"fallback_skipped","error":"...","action":"skip_and_log"}
"""
import yaml, json, sys, argparse, urllib.request, urllib.error
from pathlib import Path

# 路徑常數
REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "llm-router.yaml"
TOKEN_USAGE_PATH = REPO_ROOT / "state" / "token-usage.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def match_rule(config: dict, task_type: str) -> dict | None:
    """
    從 routing_rules（mapping 格式）查找任務規則。
    llm-router.yaml 的 routing_rules 是 dict，key=task_type，O(1) lookup。
    """
    rules = config.get("routing_rules", {})
    return rules.get(task_type)  # None 表示未命中，由呼叫方決定 fallback


def call_groq_relay(endpoint: str, mode: str, content: str, max_tokens: int) -> str:
    """
    POST 到 groq-relay（localhost:3002/groq/chat）
    Relay 接口：{"mode": "summarize|translate|classify|extract", "content": "..."}
    成功回傳：{"result": "...", "cached": bool, "model": "..."}
    """
    url = endpoint.rstrip("/") + "/groq/chat"
    payload = json.dumps({
        "mode": mode,
        "content": content,
        "max_tokens": max_tokens
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def update_token_usage(provider: str) -> None:
    """
    更新 state/token-usage.json 的 groq_calls / claude_calls 計數
    供 Fitness Function groq_routing_ratio 指標使用
    """
    try:
        usage = json.loads(TOKEN_USAGE_PATH.read_text(encoding="utf-8"))
        today = __import__("datetime").date.today().isoformat()
        day_record = usage.setdefault("daily", {}).setdefault(today, {})
        key = "groq_calls" if provider == "groq" else "claude_calls"
        day_record[key] = day_record.get(key, 0) + 1
        TOKEN_USAGE_PATH.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # Token usage 追蹤失敗不應中斷主流程


def route(task_type: str, content: str, dry_run: bool = False) -> dict:
    config = load_config()
    rule = match_rule(config, task_type)

    if rule is None:
        # 未知任務類型 → 預設 Claude
        return {"provider": "claude", "use_claude": True,
                "rationale": f"task_type '{task_type}' 未在 routing_rules 中定義，預設 Claude"}

    provider = rule.get("provider", "claude")

    if dry_run:
        # rule 已是 dict（mapping lookup 結果），直接用
        return {"provider": provider, "rule": {"task_type": task_type, **rule},
                "dry_run": True,
                "endpoint": config["providers"].get("groq", {}).get("endpoint")}

    if provider == "groq":
        provider_cfg = config["providers"]["groq"]
        endpoint = provider_cfg.get("endpoint", "http://localhost:3002")
        mode = rule.get("groq_mode", "summarize")
        max_tokens = rule.get("max_tokens", 300)

        try:
            relay_resp = call_groq_relay(endpoint, mode, content, max_tokens)
            update_token_usage("groq")
            return {
                "provider": "groq",
                "result": relay_resp.get("result", ""),
                "model": provider_cfg.get("model"),
                "cached": relay_resp.get("cached", False),
                "task_type": task_type
            }
        except urllib.error.URLError as e:
            # Relay 離線 → 依 fallback 配置處理
            fallback_action = config.get("fallback", {}).get("groq_unavailable", "skip_and_log")
            return {"provider": "fallback_skipped", "error": str(e),
                    "action": fallback_action, "task_type": task_type}
        except Exception as e:
            return {"provider": "fallback_skipped", "error": str(e),
                    "action": "skip_and_log", "task_type": task_type}

    # Claude 路徑：回傳路由決策，由 PowerShell 呼叫 claude -p
    update_token_usage("claude")
    return {"provider": "claude", "use_claude": True,
            "rationale": rule.get("rationale", ""), "task_type": task_type}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM Router")
    parser.add_argument("--task-type", required=True, help="對應 llm-router.yaml task_type")
    parser.add_argument("--input", default="", help="要處理的文字內容")
    parser.add_argument("--input-file", help="從檔案讀取輸入（優先於 --input）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示路由決策，不實際呼叫")
    args = parser.parse_args()

    content = args.input
    if args.input_file:
        content = Path(args.input_file).read_text(encoding="utf-8")

    result = route(args.task_type, content, args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
```

#### Step 3：新建 `tools/invoke-llm.ps1`（PowerShell 呼叫端）

```powershell
<#
.SYNOPSIS
  LLM 路由呼叫器 — 讀取 llm-router.yaml 後決定打 Groq 或 Claude

.PARAMETER TaskType
  對應 llm-router.yaml 的 task_type（如 news_summary, research_synthesis）

.PARAMETER InputText
  要處理的文字（與 -InputFile 二選一）

.PARAMETER InputFile
  從檔案讀取輸入

.PARAMETER ClaudePromptFile
  若路由到 Claude，傳入的 prompt 檔路徑（用於 claude -p）

.PARAMETER DryRun
  只顯示路由決策，不實際呼叫

.EXAMPLE
  # 新聞摘要 → 自動路由到 Groq
  .\tools\invoke-llm.ps1 -TaskType "news_summary" -InputText "ByteDance releases..."

  # 研究合成 → 自動路由到 Claude
  .\tools\invoke-llm.ps1 -TaskType "research_synthesis" -ClaudePromptFile "prompts/research.md"

  # 只查路由決策
  .\tools\invoke-llm.ps1 -TaskType "en_to_zh" -DryRun
#>
param(
    [Parameter(Mandatory)][string]$TaskType,
    [string]$InputText = "",
    [string]$InputFile = "",
    [string]$ClaudePromptFile = "",
    [switch]$DryRun
)

# Step 1：呼叫 Python Router 取得路由決策
$routerArgs = @("--task-type", $TaskType)
if ($InputFile)  { $routerArgs += "--input-file", $InputFile }
elseif ($InputText) { $routerArgs += "--input", $InputText }
if ($DryRun) { $routerArgs += "--dry-run" }

$routerOutput = uv run --project "$PSScriptRoot/.." python "$PSScriptRoot/llm_router.py" @routerArgs
$decision = $routerOutput | ConvertFrom-Json

# Step 2：依決策分派
switch ($decision.provider) {
    "groq" {
        Write-Host "[LLM-Router] ✓ Groq ($($decision.model)) task=$TaskType cached=$($decision.cached)"
        return $decision.result   # 直接回傳 Groq 結果字串
    }
    "claude" {
        Write-Host "[LLM-Router] → Claude task=$TaskType ($($decision.rationale))"
        if ($ClaudePromptFile -and (Test-Path $ClaudePromptFile)) {
            # 呼叫 claude -p，由呼叫方捕獲輸出
            return claude -p $ClaudePromptFile
        }
        # 若無 prompt 檔，回傳決策供呼叫方自行處理
        return $decision
    }
    "fallback_skipped" {
        Write-Warning "[LLM-Router] ⚠ Groq 不可用，動作=$($decision.action), 錯誤=$($decision.error)"
        return $null
    }
    default {
        Write-Warning "[LLM-Router] 未知 provider=$($decision.provider)"
        return $null
    }
}
```

#### Step 4：整合到現有 Prompts（示範）

現有 `prompts/team/fetch-hackernews.md` 已引用 llm-router.yaml。修改其 Groq 呼叫區段：

```markdown
<!-- 舊做法（hardcode curl）-->
curl -s -X POST localhost:3002/groq/chat -d @/tmp/groq_input.json

<!-- 新做法（透過 Router）-->
# Agent 內部直接呼叫：
uv run python tools/llm_router.py --task-type en_to_zh --input-file /tmp/article.txt
```

或 PowerShell 腳本中：
```powershell
$result = .\tools\invoke-llm.ps1 -TaskType "news_summary" -InputText $articleContent
```

#### Step 5：更新 `state/token-usage.json` schema（B5 修正 — 保持向後相容）

```json
{
  "schema_version": 2,
  "daily": {
    "2026-03-11": {
      "groq_calls": 0,
      "claude_calls": 0,
      "total_tokens": 0,
      "estimated_tokens": 0,
      "tool_calls": 0,
      "input_chars": 0,
      "output_chars": 0
    }
  }
}
```

> **向後相容策略**：v1 schema 的 `estimated_tokens/tool_calls/input_chars/output_chars` 欄位保留。
> `update_token_usage()` 採用 `dict.get(..., 0)` 讀取（缺失欄位回傳 0），不會因 schema 升級而崩潰。
> 建議用 `uv run python tools/migrate_token_schema.py` 一次性遷移現有 state/token-usage.json。

### 測試計畫

```bash
# 單元測試：路由決策
uv run python tools/llm_router.py --task-type news_summary --dry-run
# 期望：{"provider":"groq","rule":{...},"dry_run":true}

uv run python tools/llm_router.py --task-type research_synthesis --dry-run
# 期望：{"provider":"claude","rule":{...},"dry_run":true}

# 整合測試：實際呼叫 Groq（需 relay 運行中）
uv run python tools/llm_router.py --task-type en_to_zh --input "The quick brown fox"
# 期望：{"provider":"groq","result":"快速的棕色狐狸","model":"llama-3.1-8b-instant","cached":false}

# 降級測試：Groq 離線時
# 停止 relay → 重新路由
uv run python tools/llm_router.py --task-type news_summary --input "test"
# 期望：{"provider":"fallback_skipped","action":"skip_and_log",...}
```

**關鍵檔案**：
- `config/llm-router.yaml`（修改，補充 groq_mode + max_tokens）
- `tools/llm_router.py`（新建，核心路由器）
- `tools/invoke-llm.ps1`（新建，PowerShell 包裝層）
- `state/token-usage.json`（修改 schema，新增 groq_calls/claude_calls）
- `prompts/team/fetch-hackernews.md`（修改，示範整合）
- `tests/tools/test_llm_router.py`（新建，TDD 測試）

---

## P2-A：Vite 增量同步管線整合

### 問題
研究成果需手動同步到 know-w.pages.dev（靜態知識庫）。

### 借鑑來源
**KB: 049c6822** 四段式責任分離：Extract → Transform → Load → Deploy

### 實施方案

**新建 `tools/kb-sync-incremental.ps1`**：
```powershell
# 1. 讀取 state/records.json 的 last_sync_time
# 2. GET http://localhost:3000/api/notes?updated_after=$lastSync
# 3. 轉換為靜態 JSON（含全文索引）
# 4. 寫入 workers/podcast-index/data/kb-snapshot.json
# 5. 觸發 deploy-podcast-worker.ps1（已存在）
# 6. 更新 state/records.json 同步時間戳
```

整合到 `HEARTBEAT.md`：每日 03:00 排程（低峰期）。

**關鍵檔案**：`tools/kb-sync-incremental.ps1`、`state/records.json`、`HEARTBEAT.md`

---

## P2-B：OODA Decide 層強化

### 問題
arch-evolution Skill 剛啟用，決策輸出無品質保障機制。

### 借鑑來源
**DeerFlow** 雙線程池 + **KB: b9db3b71** 決策必須產生可驗證 Fitness Function

### 實施方案

**`config/ooda-workflow.yaml` Decide 步驟補充**：
```yaml
steps:
  decide:
    skill: arch-evolution
    timeout: 900
    quality_gates:
      - "至少1個新ADR或更新現有ADR"
      - "至少1個Fitness Function定義"
      - "improvement-backlog.json至少1項狀態更新"
    output_schema:
      required: [adr_changes, fitness_functions, backlog_updates]
    dual_mode:
      fast_track: "優先級P0且修改<3個檔案"
      deep_track: "架構重構或影響>5個模組"
```

`skills/arch-evolution/SKILL.md` 新增 Step 6（生成可執行 Fitness Function 腳本）、Step 7（更新 improvement-backlog.json 狀態）。

**關鍵檔案**：`config/ooda-workflow.yaml`、`skills/arch-evolution/SKILL.md`

---

## P3-A：LLM-as-Router 元分類器

### 問題
P1-B 的路由需呼叫方**已知 task_type**。現實中很多場景（如自由格式 Todoist 任務）難以預先標記類型。

### 借鑑來源
**KB: 7f06170d**（Gemini CLI）的 ClassifierStrategy：用輕量 LLM 作請求分類器
**KB: 3b45aced**（2026 Agentic AI）的 xRouter：RL 成本感知路由，多目標最佳化（速度/成本/準確度）

### 設計方案

**新建 `tools/llm_classifier.py`**：
```python
"""
LLM-as-Router：用 Groq Llama 8B 自動分類任務類型
輸入：自由格式文字（如 Todoist 任務描述）
輸出：task_type（對應 llm-router.yaml 的 routing_rules 之一）

流程：
1. 讀取 llm-router.yaml 取得所有 task_type 列表
2. 建構分類 prompt（System: 你是任務分類器，以下是可用的 task_type...）
3. 呼叫 Groq Relay（mode=classify）→ 回傳 task_type JSON
4. 將分類結果回傳給 llm_router.py 做路由決策
"""
```

**分類 prompt 設計**（ClassifierStrategy 模式）：
```
System: 你是任務路由分類器。給定以下任務描述，從候選列表選擇最合適的 task_type。
回傳純 JSON：{"task_type": "...", "confidence": 0.0-1.0}

候選 task_type（從 llm-router.yaml 動態載入）：
- news_summary: 新聞摘要、文章縮寫
- en_to_zh: 英文翻譯、中英互譯
- topic_classify: 主題分類、標籤分配
- research_synthesis: 研究合成、深度分析（→ Claude）
- policy_analysis: 政策解讀、政府公文（→ Claude）
...（自動從 routing_rules 讀取）

任務描述：{user_input}
```

**整合鏈**：
```
自由格式輸入
    │
    ▼
llm_classifier.py（Groq classify）→ task_type + confidence
    │
    ▼
llm_router.py（規則比對）→ provider 決策
    │
    ▼
Groq Relay / Claude CLI
```

**關鍵檔案**：`tools/llm_classifier.py`（新建）、`tools/llm_router.py`（修改，加 --auto-classify 選項）

---

## P3-B：可觀測性成熟度 Level 4

### 問題
依據 **KB: 7f971400**（可觀測性成熟度路線圖），系統目前在 Level 2（指標收集），尚未達到 Level 4（根因分析自動化）。

### 成熟度對照

| Level | 描述 | 現狀 |
|-------|------|------|
| 1 | 基本日誌 | ✅ JSONL Hooks 日誌 |
| 2 | 指標收集 | ✅ check-health.ps1 |
| 3 | 關聯分析（spans + traces） | ⚠️ 部分（traceId 存在但未串接） |
| 4 | 根因分析（自動異常關聯） | ❌ 缺失 |
| 5 | 預測性可觀測性 | ❌ 長期目標 |

### 實施方案

**補強 Level 3**（traceId 串接）：
- `run-todoist-agent-team.ps1` 的 `$traceId` 已存在，但 Phase 1/2/3 的日誌缺少統一追蹤
- 在每個 Phase 輸出的 JSONL 加入 `trace_id` 欄位

**達成 Level 4**（根因分析）：
- 新建 `tools/trace_analyzer.py`：掃描 `logs/structured/*.jsonl`，找出同一 traceId 下的錯誤鏈
- 輸出：`{"trace_id": "...", "root_cause": "...", "affected_phases": [...], "suggested_fix": "..."}`
- 整合到 `check-health.ps1` 的 `[根因分析]` 區塊

**關鍵檔案**：`tools/trace_analyzer.py`（新建）、`check-health.ps1`（修改）、`run-todoist-agent-team.ps1`（修改，加 trace_id 到 Phase 日誌）

---

## P3-C：ToolOrchestra 編排模式

### 問題
現有 Todoist 團隊模式（Phase 1/2/3）全程使用 Claude。KB: 3b45aced 的 ToolOrchestra 模式顯示：**小型編排模型監督大型模型的工具呼叫**可降低成本約 50%。

### 借鑑來源
**KB: 3b45aced**（2026 Agentic AI 工作流）：
- ToolOrchestra：Groq Llama 8B 作為編排者，決定何時呼叫 Claude
- 分工：簡單工具呼叫（Groq）→ 複雜推理（Claude）

### 設計方案

**Phase 1 拆分**（Todoist 查詢）：
```
Phase 1a（Groq）：查詢 Todoist API、格式化任務列表、初步過濾
Phase 1b（Claude，僅當需要）：複雜優先級判斷、任務依賴分析
```

**`run-todoist-agent-team.ps1` 修改**：
```powershell
# Phase 1 拆分示範
$simpleQueryResult = .\tools\invoke-llm.ps1 -TaskType "todoist_query_simple" -InputText $taskList
if ($simpleQueryResult.needs_deep_analysis) {
    # 只有需要深度分析時才呼叫 Claude
    $deepResult = claude -p prompts/team/todoist-deep-analyze.md
}
```

新增 `task_type: todoist_query_simple`（→ Groq）到 `llm-router.yaml`（D4 補充 groq_mode/max_tokens）：
```yaml
  todoist_query_simple:
    provider: groq
    groq_mode: extract          # 關鍵字提取 + 優先級初步判斷
    max_tokens: 500
    rationale: "Todoist 簡易查詢格式化，不需複雜語境推理"
```

**關鍵檔案**：`config/llm-router.yaml`（新增 task_type）、`run-todoist-agent-team.ps1`（修改 Phase 1 拆分）

---

## P4-A：Hono 重構 groq-relay + Cloudflare Workers

### 問題
`bot/groq-relay.js`（groq-relay）目前使用傳統 Node.js HTTP 模組或 Express，缺乏型別安全。
`workers/podcast-index/index.js` 是 Cloudflare Workers，但未利用 Edge-First 框架優勢。
兩者均缺乏 RPC 型別安全，API 契約靠文件維護而非程式碼保證。

### 借鑑來源
**Hono**（29.2K Stars）：
- **RegExpRouter**：啟動時將全部路由編譯成單一正則，O(1) 路由匹配，402,820 ops/sec on Cloudflare Workers（比 Express 快 10x+）
- **Web Standards**：基於 Request/Response/fetch API，跨 Runtime 無縫移植（Node.js → Cloudflare Workers）
- **RPC 型別安全**：TypeScript Template Literal Types 從路由定義萃取型別，無需 Code Generation

### 實施方案

#### 方案 A：groq-relay.js 遷移到 Hono（Node.js Runtime）

```typescript
// bot/groq-relay.ts（新版，替換現有 groq-relay.js）
import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'

// 請求 schema（取代現有無型別 body parsing）
const ChatSchema = z.object({
  mode: z.enum(['summarize', 'translate', 'classify', 'extract']),
  content: z.string().max(8000),
  max_tokens: z.number().int().min(50).max(2000).default(300)
})

const app = new Hono()

// /groq/health — 健康檢查（watchdog-groq-relay.ps1 依賴此端點）
app.get('/groq/health', (c) => c.json({ status: 'ok', timestamp: Date.now() }))

// /groq/chat — 主要推理端點（zValidator 確保 100% 合規請求）
app.post('/groq/chat', zValidator('json', ChatSchema), async (c) => {
  const { mode, content, max_tokens } = c.req.valid('json')
  // ... 呼叫 Groq API 邏輯（不變）
  return c.json({ result, cached, model: 'llama-3.1-8b-instant' })
})

export default app
// Node.js 啟動：serve(app, { port: 3002 })
```

**效益**：
- `zValidator` 自動驗證請求 schema，取代目前手動 JSON.parse + 檢查
- 錯誤回傳標準化（422 Unprocessable Entity + 欄位詳情）
- 為未來遷移到 Cloudflare Workers 預鋪路（Web Standards 相容）

#### 方案 B：podcast-index Worker 整合 Hono RPC

```typescript
// workers/podcast-index/index.ts（重構）
import { Hono } from 'hono'
import type { AppType } from './routes'  // RPC 型別匯出

const app = new Hono()
  .get('/api/episodes', ...) // 靜態 KB 資料服務
  .post('/api/sync', ...)    // 增量同步觸發（P2-A 的 kb-sync）

export type AppType = typeof app  // 供前端 hono/client 消費
export default app
```

**遷移策略**（最小侵入）：
1. 安裝 `hono`（< 12kB，零依賴）
2. 保留現有路由邏輯，只替換框架層
3. 現有 `watchdog-groq-relay.ps1` 監控的 `/groq/health` 端點保持不變

**關鍵檔案**：
- `bot/groq-relay.js` → `bot/groq-relay.ts`（Hono 重構）
- `workers/podcast-index/index.js` → `index.ts`（加 Hono）
- `package.json`（新增 `hono`, `@hono/zod-validator`, `zod`）

---

## P4-B：Structured Generation 強型別輸出保證

### 問題
`tools/llm_router.py` 的 Groq Relay 回傳（特別是 classify/extract mode）目前：
- 回傳純字串，**無格式保證**
- P3-A 的 `llm_classifier.py` 要求回傳 `{"task_type":"...", "confidence": 0.0-1.0}`，但 classify mode 可能輸出任意文字
- OODA Decide 層的 ADR 輸出格式靠 prompt 約束（80-95% 成功率），非結構化保證

### 借鑑來源
**Structured Generation 指南**（2026）的核心洞察：
- **Constrained Decoding**：在 logit 輸出與 sampling 之間插入 logit processor，token masking 確保只有合法 token 被採樣 → 100% schema 合規
- **Instructor**：高階 SDK，將 Pydantic 模型直接作為 `response_model`，適用 Claude API
- **Phase 4（2025-2026）**：O(1) 有效 token 查詢，預編譯 grammar

### 實施方案

#### Step 1：`tools/llm_router.py` 回傳 schema 強化

對 classify/extract 路徑，在 Python 端加入 JSON schema 驗證層：

```python
# tools/llm_router.py 新增

import jsonschema

# classify 回傳 schema
CLASSIFY_SCHEMA = {
    "type": "object",
    "required": ["labels"],
    "properties": {
        "labels": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    }
}

# extract 回傳 schema
EXTRACT_SCHEMA = {
    "type": "object",
    "required": ["extracted"],
    "properties": {
        "extracted": {"type": "object"}
    }
}

SCHEMA_MAP = {
    "classify": CLASSIFY_SCHEMA,
    "extract": EXTRACT_SCHEMA,
}

def validate_relay_response(mode: str, raw_result: str) -> dict:
    """
    驗證 Groq Relay 回傳格式。
    若 raw_result 是字串（非 JSON），嘗試包裝為合法結構。
    若驗證失敗，回傳 fallback 結構（不拋例外）。
    """
    schema = SCHEMA_MAP.get(mode)
    if schema is None:
        return {"result": raw_result}  # summarize/translate：純字串，不需驗證

    try:
        parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        jsonschema.validate(parsed, schema)
        return parsed
    except (json.JSONDecodeError, jsonschema.ValidationError):
        # Relay 輸出不合規 → 記錄並回傳降級結構
        return {"result": raw_result, "schema_violation": True, "mode": mode}
```

#### Step 2：`tools/llm_classifier.py` 加入 Constrained Decoding 模擬

由於 Groq Relay 不直接支援 Constrained Decoding，採用「JSON Schema 修復」策略（Instructor 模式）：

```python
# tools/llm_classifier.py 新增 schema 修復層

CLASSIFIER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["task_type", "confidence"],
    "properties": {
        "task_type": {"type": "string"},  # 從 routing_rules 動態建 enum
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    }
}

def classify_with_retry(content: str, valid_task_types: list[str], max_retries: int = 2) -> dict:
    """
    呼叫 Groq classify mode，確保輸出符合 classifier schema。
    若輸出不合規，最多重試 max_retries 次（每次加強 prompt）。
    參考 Instructor 的 retry-on-validation-failure 模式。
    """
    prompt = build_classifier_prompt(content, valid_task_types)
    for attempt in range(max_retries + 1):
        raw = call_groq_relay(..., mode="classify", content=prompt)
        try:
            result = json.loads(raw)
            jsonschema.validate(result, CLASSIFIER_OUTPUT_SCHEMA)
            # 確保 task_type 在合法列表中
            if result["task_type"] not in valid_task_types:
                raise ValueError(f"task_type '{result['task_type']}' 不在合法列表")
            return result
        except Exception as e:
            if attempt == max_retries:
                return {"task_type": "research_synthesis", "confidence": 0.0,
                        "fallback": True, "error": str(e)}
            # 加強 prompt：明確要求輸出純 JSON
            prompt = f"[重試 {attempt+1}] 必須只回傳純 JSON，不得有任何其他文字。\n" + prompt
```

#### Step 3：Claude 路徑 Instructor 整合（ADR 輸出）

針對 OODA Decide 層輸出，使用 `instructor` 套件確保 ADR 結構合規：

```python
# tools/structured_claude.py（新建）
"""
Instructor 整合層 — 讓 Claude API 輸出嚴格符合 Pydantic schema

使用場景：
- arch-evolution 的 ADR 輸出
- OODA Decide 層的 quality_gates 驗證
- improvement-backlog 更新的結構化回傳
"""
import instructor
import anthropic
from pydantic import BaseModel, Field
from typing import Literal

class ADROutput(BaseModel):
    adr_id: str = Field(pattern=r"ADR-\d{8}-\d{3}")
    title: str
    status: Literal["Proposed", "Accepted", "Rejected", "Deferred"]
    context: str = Field(min_length=50)
    decision: str = Field(min_length=30)
    consequences: list[str] = Field(min_length=1)
    fitness_functions: list[str]  # 可執行驗證項目
    tech_debt_score: float = Field(ge=0.0, le=10.0)

class OODADecideOutput(BaseModel):
    adr_changes: list[ADROutput]
    fitness_functions: list[str]
    backlog_updates: list[dict]
    fast_track: bool  # 是否走 fast_track 模式

# D3 修正：明確 ANTHROPIC_API_KEY 初始化（claude CLI 執行時環境變數已繼承，
# 但 structured_claude.py 作為獨立 Python 程序時需顯式讀取）
import os
_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    raise EnvironmentError("請設定 ANTHROPIC_API_KEY 環境變數（從 .env 或 Windows 環境變數）")
client = instructor.from_anthropic(anthropic.Anthropic(api_key=_api_key))

def generate_adr(context_text: str) -> ADROutput:
    """呼叫 Claude，保證回傳符合 ADROutput schema（100% 合規）"""
    return client.chat.completions.create(
        model="claude-sonnet-4-6",
        response_model=ADROutput,
        messages=[{"role": "user", "content": context_text}]
    )
```

**pyproject.toml 新增依賴**（完整 diff，H5 修正）：
```toml
# 在 [project.dependencies] 陣列中新增以下項目（uv add 或手動追加）：
# P4-B Structured Generation:
#   instructor = ">=1.0"        # Claude Instructor 整合，structured output
#   jsonschema = ">=4.0"        # Groq relay 回傳 schema 驗證
# P1-B LLM Router:
#   pyyaml = ">=6.0"            # 讀取 llm-router.yaml（已存在，確認版本）
# P4-C 預算治理:
#   （無新依賴，budget_guard.py 僅使用標準庫 + pyyaml）
# P4-D 審計日誌:
#   （無新依賴，hashlib + json 均為標準庫）

# 執行指令（uv 管理）：
# uv add "instructor>=1.0" "jsonschema>=4.0"
```

確認 `pyproject.toml` 現有 `pyyaml` 版本需 `>=6.0`（支援 `yaml.safe_load` mapping 格式）。

**關鍵檔案**：
- `tools/llm_router.py`（修改，加 validate_relay_response）
- `tools/llm_classifier.py`（修改，加 classify_with_retry）
- `tools/structured_claude.py`（新建，Instructor 整合）
- `pyproject.toml`（新增 instructor, jsonschema 依賴）
- `tests/tools/test_structured_generation.py`（新建）

---

## P4-C：Paperclip 式原子化預算治理

### 問題
`state/token-usage.json` 目前只做計數，無預算上限、無警告機制、無自動熔斷。
系統在高峰日（如 2026-03-09）消耗 30.47M tokens，無任何防護。

### 借鑑來源
**Paperclip**（7.7K Stars）的原子化預算治理：
- **月度預算上限**：全局限制，原子扣款
- **80% 警告**：達到上限 80% 時發送告警通知
- **100% 暫停**：達到上限時自動停止新的 Agent 呼叫
- **多維追蹤**：按 Agent 類型、任務類型分別計費

### 實施方案

#### Step 1：`config/budget.yaml`（新建）

```yaml
# LLM 用量預算配置（對應 Paperclip 的原子化預算治理）
version: 1

daily_budget:
  claude_tokens: 5_000_000       # 每日 Claude token 上限
  groq_calls: 100                # 每日 Groq API 呼叫上限
  warn_threshold: 0.80           # 80% 時發送 ntfy 告警
  suspend_threshold: 1.00        # 100% 時暫停新呼叫（circuit breaker）

monthly_budget:
  claude_tokens: 100_000_000     # 月度 Claude token 上限
  warn_threshold: 0.80

per_task_limits:                 # 各任務類型單次上限
  research_synthesis: 8_192
  arch_evolution: 4_096
  system_insight: 4_096
  default: 2_000

cost_tracking:                   # 成本估算（供財務監控）
  claude_sonnet_per_1m_input: 3.00   # USD
  claude_sonnet_per_1m_output: 15.00
  groq_llama_8b_per_1m: 0.05
```

#### Step 2：`tools/budget_guard.py`（新建）

```python
#!/usr/bin/env python3
"""
Paperclip 式預算守衛 — 原子化扣款 + 閾值熔斷

整合到 tools/llm_router.py 的 update_token_usage()：
每次 LLM 呼叫前先檢查預算，超限時回傳 {"decision": "budget_suspended"}
"""
import yaml, json
from pathlib import Path
from datetime import date

# H1 修正：使用絕對路徑，避免 CWD 依賴問題
REPO_ROOT = Path(__file__).parent.parent
BUDGET_CONFIG = REPO_ROOT / "config" / "budget.yaml"
TOKEN_USAGE = REPO_ROOT / "state" / "token-usage.json"

def check_budget(task_type: str, provider: str, estimated_tokens: int) -> dict:
    """
    呼叫前預算檢查（原子化，不實際扣款）
    回傳：{"allowed": bool, "reason": str, "utilization": float}
    """
    config = yaml.safe_load(BUDGET_CONFIG.read_text())
    usage = json.loads(TOKEN_USAGE.read_text())
    today = date.today().isoformat()
    day_data = usage.get("daily", {}).get(today, {})

    # 按 provider 選擇對應限制
    if provider == "claude":
        used = day_data.get("claude_tokens", 0)
        limit = config["daily_budget"]["claude_tokens"]
    else:  # groq
        used = day_data.get("groq_calls", 0)
        limit = config["daily_budget"]["groq_calls"]

    utilization = (used + estimated_tokens) / limit if limit > 0 else 0

    if utilization >= config["daily_budget"]["suspend_threshold"]:
        return {"allowed": False, "reason": "daily_budget_exhausted",
                "utilization": utilization, "used": used, "limit": limit}

    if utilization >= config["daily_budget"]["warn_threshold"]:
        # 觸發 ntfy 告警（非同步，不阻塞主流程）
        _send_budget_warning(provider, utilization)

    return {"allowed": True, "utilization": utilization}

def _send_budget_warning(provider: str, utilization: float) -> None:
    """80% 警告 → ntfy 通知（與現有 on_stop_alert.py 模式相同）"""
    import subprocess, json, tempfile, os
    payload = {
        "topic": "wangsc2025",
        "title": f"⚠️ LLM 預算警告 {utilization:.0%}",
        "message": f"{provider} 用量已達每日上限 {utilization:.1%}",
        "priority": 3
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False,
                                     encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
        tmp = f.name
    subprocess.run(["curl", "-s", "-H", "Content-Type: application/json; charset=utf-8",
                    "-d", f"@{tmp}", "https://ntfy.sh"], capture_output=True)
    os.unlink(tmp)
```

#### Step 3：整合到 `tools/llm_router.py`

在 `route()` 函數的呼叫前插入預算檢查：

```python
# tools/llm_router.py 修改
# C1 修正：相對 import 在命令列執行失敗，改用 sys.path 注入
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tools.budget_guard import check_budget  # noqa: E402

def route(task_type: str, content: str, dry_run: bool = False) -> dict:
    # ... 現有路由邏輯 ...

    if provider == "groq":
        # 預算預檢查（Paperclip 式原子化）
        budget_check = check_budget(task_type, "groq", estimated_tokens=50)
        if not budget_check["allowed"]:
            return {"provider": "budget_suspended", "reason": budget_check["reason"],
                    "utilization": budget_check["utilization"]}
        # ... 正常 Groq 呼叫 ...
```

**關鍵檔案**：
- `config/budget.yaml`（新建）
- `tools/budget_guard.py`（新建）
- `tools/llm_router.py`（修改，加預算預檢查）
- `check-health.ps1`（修改，新增 [預算使用率] 區塊）

---

## P4-D：目標繼承鏈 + 不可變審計日誌

### 問題
現有 `context/improvement-backlog.json` 是扁平任務列表，缺乏：
1. **目標層級**：無法表達「此任務對齊哪個高層目標」
2. **不可變審計**：Hooks JSONL 日誌可被覆寫，缺乏 Append-only 保證

### 借鑑來源
**Paperclip** 的兩大設計原則：
1. **目標繼承鏈**：`Task → Project → Goal → Company Mission`，確保每個 Agent 行動都可追溯到頂層目標
2. **不可變審計日誌**：Append-only 設計，完整追溯，無法刪改歷史記錄

### 實施方案

#### Step 1：`context/mission.yaml`（新建）—— 系統使命定義

```yaml
# 對應 Paperclip 的 Company Mission 層
version: 1
mission: "每日自動彙整資訊、學習與禪語，輔助個人成長與決策"

goals:
  - id: G01
    title: "降低 LLM 成本"
    metric: "groq_routing_ratio >= 30%"
    linked_fitness_function: "groq_routing_ratio"

  - id: G02
    title: "提升系統可靠性"
    metric: "ooda_completion >= 80%"
    linked_fitness_function: "ooda_completion"

  - id: G03
    title: "知識累積品質"
    metric: "kb_notes_per_week >= 5"
    linked_fitness_function: "adr_coverage"

  - id: G04
    title: "架構自治治理"
    metric: "tech_debt_velocity: resolved >= new_per_week"
    linked_fitness_function: "tech_debt_velocity"
```

#### Step 2：`context/improvement-backlog.json` schema 強化

每個 backlog 項目新增 `goal_id` 欄位，形成繼承鏈：

```json
{
  "items": [
    {
      "id": "BL-2026-001",
      "title": "啟用 LLM Router 動態路由",
      "priority": "P1",
      "goal_id": "G01",           // ← 新增：對齊「降低 LLM 成本」目標
      "project": "llm-router",
      "status": "in_progress",
      "adr_ref": "ADR-20260311-XXX"  // ← 新增：關聯 ADR
    }
  ]
}
```

#### Step 3：Append-only 日誌強化

在 `hooks/post_tool_logger.py` 加入日誌完整性驗證：

```python
# hooks/post_tool_logger.py 新增

import hashlib

def append_with_checksum(log_path: Path, entry: dict) -> None:
    """
    Append-only 寫入（Paperclip 不可變審計日誌模式）：
    1. 讀取上一筆記錄的 checksum
    2. 計算新記錄 hash（含前一筆 checksum，形成鏈式結構）
    3. 新增 '_prev_hash' 欄位後 append
    """
    prev_hash = ""
    if log_path.exists():
        # 讀取最後一行取得前一筆 hash
        last_line = log_path.read_text(encoding="utf-8").strip().split("\n")[-1]
        try:
            prev_hash = json.loads(last_line).get("_hash", "")
        except Exception:
            pass

    entry["_prev_hash"] = prev_hash
    # C2 修正：計算 hash 前先排除 _hash 欄位本身（避免循環依賴），
    # 確保 audit_verify.py 驗證端可用相同方法重算（排除 _hash 後計算）
    hash_payload = {k: v for k, v in entry.items() if k != "_hash"}
    entry["_hash"] = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

**C3 修正 — 日誌輪轉（50MB）斷鏈處理規格**：
- `post_tool_logger.py` 在檔案輪轉後，**第一筆記錄**必須寫入「輪轉標記行」：
  ```json
  {"_type":"rotation_marker","rotated_from":"hooks_20260310.jsonl","_prev_hash":"","_hash":"<本行hash>"}
  ```
- `audit_verify.py` 遇到 `_type=rotation_marker` 時，重置鏈式驗證起點（不視為斷鏈錯誤）

**新建 `tools/audit_verify.py`**：驗證 JSONL 日誌的鏈式完整性（偵測篡改）。
- 驗證邏輯：對每筆 entry，排除 `_hash` 欄位後重算 SHA256，比對 `entry["_hash"]`；同時確認 `entry["_prev_hash"]` 與上一筆 `entry["_hash"]` 一致。

**關鍵檔案**：
- `context/mission.yaml`（新建）
- `context/improvement-backlog.json`（修改 schema，加 goal_id + adr_ref）
- `hooks/post_tool_logger.py`（修改，加 append_with_checksum）
- `tools/audit_verify.py`（新建）
- `check-health.ps1`（修改，新增 [審計日誌完整性] 區塊）

---

## P5-A：Agent Pool 架構（自動任務 Agent 化落地）

### 問題
現有 `run-todoist-agent-team.ps1` 的 Phase 2 並行任務存在兩個已知生產風險：
1. **慢速 I/O 阻塞**：單一 Web 搜尋或 KB API 呼叫逾時，導致整個 Phase 2 卡住，後續 Phase 3 組裝找不到結果檔（「Missing result file」）
2. **失敗收尾不一致**：子步驟（如 Vite 同步、KB 匯入）失敗後，無統一取消機制，已完成步驟的結果孤立無法被後續任務使用

### 現有任務類型對照

| 任務分類 | 現有實作 | Pool 化後歸屬 |
|---------|---------|------------|
| Phase 選題、去重決策 | `run-todoist-agent-team.ps1` Phase 1 | **Coordination Pool** |
| KB 策略分析 | `templates/shared/kb-depth-check.md` | **Coordination Pool** |
| 完成條件判定 | Phase 3 組裝邏輯 | **Coordination Pool** |
| Web 搜尋（HN、屏東新聞） | claude subagent + Skill | **Worker Pool** |
| KB API 呼叫（localhost:3000） | `skills/knowledge-query/SKILL.md` | **Worker Pool** |
| 檔案同步（Vite 增量） | `tools/kb-sync-incremental.ps1`（P2-A）| **Worker Pool** |
| JSON 結果產生 | 各 auto-task prompt 輸出 | **Worker Pool** |
| ntfy 通知送出 | `skills/ntfy-notify/SKILL.md` | **Worker Pool** |

### 設計方案

#### 四層架構

```
┌─────────────────────────────────────────────────────┐
│  Coordination Pool（1個 Coordinator Agent）           │
│  Phase 選題 → 去重 → KB策略 → fan-out → done判定      │
└───────────────────┬────────────────────────────────┘
                    │ 透過 Bounded Queue 派發工作
┌───────────────────▼────────────────────────────────┐
│  Bounded Queue（config/agent-pool.yaml 控制 fan-out）│
│  web_search: max_concurrent=3                       │
│  kb_import: max_concurrent=5                        │
│  file_sync: max_concurrent=2                        │
└───────────────────┬────────────────────────────────┘
                    │ N 個並行 Worker（不超過上限）
┌───────────────────▼────────────────────────────────┐
│  Worker Pool（每 Worker 只做一件事）                  │
│  WebSearch Worker │ KBImport Worker │ Sync Worker   │
│  Notify Worker    │ JSONGen Worker               │
└───────────────────┬────────────────────────────────┘
                    │ 每個 Worker 輸出必須通過
┌───────────────────▼────────────────────────────────┐
│  Middleware Chain（hook_pipeline.py P1-A 延伸）      │
│  Cache → Trace → Timeout → Retry → SchemaValidate  │
│  → done_cert 生成（僅 schema 通過才簽發）            │
└────────────────────────────────────────────────────┘
```

#### Step 1：`config/agent-pool.yaml`（新建）

```yaml
# Agent Pool 配置 — 控制並行度、超時、重試與 done_cert 策略
version: 1

coordination_pool:
  max_coordinators: 1          # 同時只有一個 Coordinator 做決策（避免衝突）
  phase_selection_timeout: 60  # Phase 選題最長 60 秒

worker_pool:
  # B1 修正：timeout 繼承自 config/timeouts.yaml 的 phase2_timeout_by_task
  # 不在此處重複定義數值；coordinator.py 讀取 timeouts.yaml 後填入實際值
  # Phase 2 總超時公式（E2 補充）：max(各任務 timeout) + 300s buffer
  # 例：podcast_create=2400s 時，Phase 2 總超時 = 2400+300 = 2700s
  timeout_source: "config/timeouts.yaml"
  timeout_key: "phase2_timeout_by_task"

  web_search:
    max_concurrent: 3          # 同時最多 3 個 Web 搜尋
    retry: 1                   # 失敗重試 1 次（timeout 從 timeouts.yaml 讀取）
  kb_import:
    max_concurrent: 5
    retry: 2
  file_sync:
    max_concurrent: 2
    retry: 1
  notification:
    max_concurrent: 10         # ntfy 快速，不需嚴格限制
    timeout_override: 30       # 通知固定 30s（不依賴任務 timeout）
    retry: 3

done_cert:
  enabled: true
  schema_required: true        # 結果必須通過 JSON schema 驗證才能簽發
  cert_path: "state/done-certs/{task_id}.json"
  # done_cert 格式：
  # {"task_id":"...", "phase":2, "worker_type":"web_search",
  #  "result_file":"results/todoist-auto-xxx.json",
  #  "schema_valid":true, "issued_at":"..."}

cancel_policy:
  on_worker_failure: "cancel_siblings_of_same_type"  # 同類 Worker 均取消
  on_timeout: "cancel_and_log"
  min_success_ratio: 0.6       # ≥60% Worker 成功才允許 Phase 3 組裝
```

#### Step 2：`tools/agent_pool/coordinator.py`（新建）

```python
#!/usr/bin/env python3
"""
Coordination Pool — Phase 選題、去重決策、fan-out 分派、完成條件判定

與現有 run-todoist-agent-team.ps1 的關係：
- 不取代 PowerShell 腳本，作為 Phase 1 的 Python 決策輔助層
- PowerShell 呼叫 coordinator.py 取得「本次應執行哪些任務 + 各任務 Worker 類型」
- 結果寫入 state/coordination-plan.json，Phase 2 依此 fan-out 派發 Workers

主要職責：
1. 讀取 config/frequency-limits.yaml + context/research-registry.json → 去重決策
2. 讀取 config/agent-pool.yaml → 計算 bounded queue 限制
3. 輸出 coordination_plan（task_list + worker_assignments + done_cert_requirements）
"""
import yaml, json
from pathlib import Path
from datetime import date, datetime

REPO_ROOT = Path(__file__).parent.parent.parent
POOL_CONFIG = REPO_ROOT / "config" / "agent-pool.yaml"
FREQ_LIMITS = REPO_ROOT / "config" / "frequency-limits.yaml"
RESEARCH_REG = REPO_ROOT / "context" / "research-registry.json"
COORD_PLAN_OUT = REPO_ROOT / "state" / "coordination-plan.json"


def build_coordination_plan(available_tasks: list[dict]) -> dict:
    """
    輸入：Phase 1 篩選出的可執行任務列表
    輸出：coordination_plan，包含 worker_assignments 與 fan-out 限制
    """
    pool_cfg = yaml.safe_load(POOL_CONFIG.read_text(encoding="utf-8"))
    plan = {"generated_at": datetime.now().isoformat(), "tasks": []}

    for task in available_tasks:
        worker_type = _infer_worker_type(task)
        limit = pool_cfg["worker_pool"].get(worker_type, {}).get("max_concurrent", 5)
        plan_key = task.get("plan_key", task["id"])
        plan["tasks"].append({
            "task_id": task["id"],
            "plan_key": plan_key,
            "worker_type": worker_type,
            "max_concurrent": limit,
            "done_cert_required": pool_cfg["done_cert"]["enabled"],
            # C2 修正：prompt_file 明確納入 coordination-plan schema
            "prompt_file": f"prompts/team/todoist-auto-{plan_key}.md",
            "result_file": f"results/todoist-auto-{plan_key}.json"
        })

    COORD_PLAN_OUT.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return plan


# C1 修正：明確 plan_key → worker_type 映射表（優先於標籤推斷）
PLAN_KEY_WORKER_MAP: dict[str, str] = {
    # Web 搜尋型（需要呼叫外部 API/搜尋引擎）
    "ai_research": "web_search",     "tech_research": "web_search",
    "ai_deep_research": "web_search", "hackernews": "web_search",
    "self_heal": "web_search",       "github_scout": "web_search",
    # KB 匯入型（產出 JSON → 呼叫 localhost:3000）
    "kb_content_score": "kb_import", "shurangama": "kb_import",
    "jingtu": "kb_import",
    # 系統維護型（讀寫本地 state/logs）
    "system_insight": "file_sync",   "skill_audit": "file_sync",
    "log_audit": "file_sync",
    # 通知/媒體型
    "podcast_jiaoguangzong": "notification", "podcast_create": "notification",
}

def _infer_worker_type(task: dict) -> str:
    """
    優先查 PLAN_KEY_WORKER_MAP 精確映射（C1 修正）；
    未命中時回退到 label 推斷（向後相容）。
    """
    plan_key = task.get("plan_key", "")
    if plan_key in PLAN_KEY_WORKER_MAP:
        return PLAN_KEY_WORKER_MAP[plan_key]
    labels = set(task.get("labels", []))
    if "研究" in labels: return "web_search"
    if "知識庫" in labels: return "kb_import"
    if "通知" in labels: return "notification"
    return "web_search"  # 預設
```

#### Step 3：`tools/agent_pool/done_cert.py`（新建）

```python
#!/usr/bin/env python3
"""
done_cert（完成憑證）生成與驗證

設計：只有通過 JSON schema 驗證的 Worker 結果，才能被 Coordinator 消費。
Phase 3 組裝前先呼叫 verify_done_cert()，確保結果完整後才組裝。

解決「Phase 2 結果缺失」根本問題：
- 舊模式：Phase 3 直接讀結果檔，若缺失才報錯（為時已晚）
- 新模式：Worker 完成後即簽發 done_cert；Phase 3 只讀有憑證的結果
"""
import json, hashlib
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent.parent
CERT_DIR = REPO_ROOT / "state" / "done-certs"


def issue_cert(task_id: str, phase: int, worker_type: str,
               result_file: Path, schema_valid: bool) -> dict:
    """Worker 完成後由 middleware chain 呼叫，簽發完成憑證"""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert = {
        "task_id": task_id,
        "phase": phase,
        "worker_type": worker_type,
        "result_file": str(result_file),
        "schema_valid": schema_valid,
        "issued_at": datetime.now().isoformat(),
        "result_hash": _file_hash(result_file) if result_file.exists() else None
    }
    cert_path = CERT_DIR / f"{task_id}.json"
    cert_path.write_text(json.dumps(cert, ensure_ascii=False, indent=2), encoding="utf-8")
    return cert


def verify_done_cert(task_id: str) -> tuple[bool, str]:
    """
    Phase 3 組裝前呼叫：驗證 done_cert 存在且 result_file 未被篡改
    回傳：(ok: bool, reason: str)
    """
    cert_path = CERT_DIR / f"{task_id}.json"
    if not cert_path.exists():
        return False, f"done_cert 不存在：{task_id}"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    if not cert.get("schema_valid"):
        return False, f"schema 驗證未通過：{task_id}"
    result_file = Path(cert["result_file"])
    if not result_file.exists():
        return False, f"結果檔案已消失：{result_file}"
    if cert.get("result_hash") and _file_hash(result_file) != cert["result_hash"]:
        return False, f"結果檔案 hash 不符（可能被篡改）：{task_id}"
    return True, "ok"


def _file_hash(path: Path) -> str:
    """A4 修正：串流讀取防 OOM（>5MB 檔案仍可安全計算 hash）"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):  # 64KB 塊
            h.update(chunk)
    return h.hexdigest()[:16]
```

#### Step 4：Middleware Chain 整合（P1-A 延伸）

`hooks/hook_pipeline.py`（P1-A 已定義 `HookPipeline`）新增 Worker 專用中介軟體：

```python
# 在 HookPipeline 基礎上組裝 Worker 用的 pipeline
def build_worker_pipeline(worker_type: str, pool_config: dict) -> HookPipeline:
    """
    為指定 worker_type 組裝中介軟體鏈
    順序：Cache → Trace → Timeout → Retry → SchemaValidate → DoneCert
    """
    cfg = pool_config["worker_pool"].get(worker_type, {})
    return HookPipeline([
        cache_middleware(ttl=cfg.get("cache_ttl", 300)),
        trace_middleware(),                            # 注入 trace_id（P3-B）
        timeout_middleware(seconds=cfg.get("timeout", 120)),
        retry_middleware(max_retries=cfg.get("retry", 1)),
        schema_validate_middleware(worker_type),       # 驗證結果 schema
        done_cert_middleware(),                        # 簽發完成憑證
    ])
```

#### Step 5：`run-todoist-agent-team.ps1` Phase 2 修改（最小侵入）

```powershell
# Phase 2 修改：fan-out 前先讀 coordination-plan.json
$coordPlan = Get-Content "state/coordination-plan.json" | ConvertFrom-Json

# 依 done_cert 模式啟動 Workers（而非直接並行執行所有 claude -p）
$jobs = @()
foreach ($task in $coordPlan.tasks) {
    if ($jobs.Count -ge $task.max_concurrent) {
        # 等待最早的 Job 完成後再繼續（Bounded Queue 效果）
        $jobs | Wait-Job -Any | Out-Null
        $jobs = $jobs | Where-Object { $_.State -eq 'Running' }
    }
    $jobs += Start-Job -ScriptBlock {
        param($taskId, $promptFile, $certEnabled)
        # 執行 Worker
        $result = claude -p $promptFile
        # 簽發 done_cert（middleware chain 自動處理）
        if ($certEnabled) {
            uv run python tools/agent_pool/done_cert.py --issue --task-id $taskId
        }
    } -ArgumentList $task.task_id, $task.prompt_file, $task.done_cert_required
}
$jobs | Wait-Job | Out-Null  # 等所有 Worker 完成

# Phase 3 組裝前：驗證 done_cert
$allCertsValid = uv run python tools/agent_pool/done_cert.py --verify-all
if (-not $allCertsValid) {
    Write-Warning "[Phase 3] 部分 done_cert 未通過，跳過無效結果，繼續組裝有效部分"
}
```

### 關鍵設計決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| Coordination Pool 大小 | 1（單 Coordinator） | 避免多個 Coordinator 同時做去重決策衝突 |
| Worker 取消策略 | `cancel_siblings_of_same_type` | 同類 Worker 失敗表示整批相同 API 可能不可用，無需繼續 |
| done_cert 簽發時機 | schema 驗證通過後立即簽發 | 確保 Phase 3 只消費有效結果，避免「缺失才報錯」的亡羊補牢 |
| 最低成功率 | 60%（`min_success_ratio`） | C4 決策：低於 60% → 重試一次（`--retry-failed`）→ 若仍低於 60% → 告警但繼續組裝有效部分（不完全取消）|
| Bounded Queue 實作 | PowerShell `Wait-Job -Any` | 不引入 Python asyncio，利用現有 PS 原語；避免 PowerShell 巢狀 Job 問題（每個 Worker 為頂層 Job）|
| done-certs 清理責任 | B2/C3：由 self-heal 自動任務負責 | `templates/auto-tasks/self-heal.md` Step 4 新增：掃描 `state/done-certs/` 中 mtime > 24h 的檔案並刪除 |
| P5-A 分階段依賴 | B3 澄清：`done_cert.py` 核心驗證邏輯不依賴 P1-A | P1-A 完成前可先實作 done_cert issue/verify；`build_worker_pipeline()` 整合需待 P1-A |

### 關鍵檔案

- `config/agent-pool.yaml`（新建，fan-out 上限 + done_cert 策略；timeout 繼承 timeouts.yaml）
- `tools/agent_pool/__init__.py`（新建，空檔，啟用 Python package）
- `tools/agent_pool/coordinator.py`（新建，Phase 1 決策輔助 + PLAN_KEY_WORKER_MAP 映射表）
- `tools/agent_pool/done_cert.py`（新建，完成憑證系統；串流 hash 防 OOM）
- `hooks/hook_pipeline.py`（P1-A 修改，延伸 `build_worker_pipeline()`；P5-A 第二階段依賴此）
- `run-todoist-agent-team.ps1`（Phase 2 修改：Bounded Queue + done_cert 驗證；Phase 2 總超時 = max(task timeout)+300）
- `templates/auto-tasks/self-heal.md`（修改 Step 4：新增 done-certs 清理邏輯，清除 >24h 的舊憑證）
- `state/done-certs/`（新建目錄，由 self-heal 定期清理）
- `tests/tools/__init__.py`（新建，啟用 pytest 發現）
- `tests/tools/test_done_cert.py`（新建，15 個測試：issue/verify/篡改偵測/min_success_ratio 行為）

---

## 實施順序與依賴關係

```
P0-A (ADR自動化) ──┐
                   ├──→ P2-B (OODA Decide強化)
P0-B (Fitness Fn) ─┘

P1-A (Hook中介軟體) ─────────────────────────── 獨立，可並行
                   └──→ P5-A (Agent Pool，延伸 HookPipeline)
P1-B (LLM Router) ──────────────────────────── 獨立，可並行（⭐ 最高 ROI）

P2-A (Vite同步) ─────────────── 依賴 state/records.json（已存在）

P3-A (LLM-as-Router) ────────── 依賴 P1-B 完成
P3-B (可觀測性 L4) ──────────── 依賴 P0-B 的 traceId 強化
P3-C (ToolOrchestra) ────────── 依賴 P1-B 完成

P4-A (Hono groq-relay) ──────── 獨立，可並行（不影響現有邏輯）
P4-B (Structured Generation) ─── 依賴 P1-B（llm_router.py 已存在）
P4-C (預算治理) ─────────────── 依賴 P1-B（route() 函數插入點）
P4-D (目標繼承鏈) ───────────── 依賴 P0-A（ADR schema 先確立）

P5-A (Agent Pool) ───────────── 依賴 P1-A（HookPipeline 延伸）；
                                 done_cert 機制獨立可先實作
```

**建議實施批次**：
- **Batch 1**（本週）— 注意 Batch 內部有序依賴：
  - **Batch 1-a**（並行）：P0-A + P0-B（ADR 閉環 + Fitness Function 基線，互相獨立）
  - **Batch 1-b**（P0-A/B 完成後）：P1-B（LLM Router — `tools/llm_router.py` 核心，後續多項依賴此）
  - **Batch 1-c**（P1-B 完成後）：P4-C（預算治理 — 插入 `route()` 函數，必須 P1-B 先完成）
- **Batch 2**（下週）：P1-A + P2-A + P2-B + P4-A（Hook重構 + 同步 + OODA + Hono，可並行）
  - **Batch 2-b**（P1-A 完成後）：P5-A `done_cert.py` + `coordinator.py`（架構預防，非緊急修復 — 根本修復已於 2026-02-24 完成）
- **Batch 3**（第三週）：P3-A + P3-B + P3-C + P4-B（進階優化 + Structured Generation）
  - **Batch 3-b**（P5-A 完成後）：P5-A middleware chain 整合（`build_worker_pipeline()`）
- **Batch 4**（第四週）：P4-D（目標繼承鏈，依賴前三批確立 schema）

---

## 驗證方式

### P1-B LLM Router（最關鍵）
```bash
# 路由決策測試（mapping 格式 — O(1) dict lookup）
uv run python tools/llm_router.py --task-type news_summary --dry-run
# 期望：{"provider":"groq","rule":{"task_type":"news_summary","groq_mode":"summarize",...},"dry_run":true}

uv run python tools/llm_router.py --task-type research_synthesis --dry-run
# 期望：{"provider":"claude","use_claude":true,"task_type":"research_synthesis",...}

# 未知 task_type 應降級到 Claude（不報錯）
uv run python tools/llm_router.py --task-type unknown_type --dry-run
# 期望：{"provider":"claude","use_claude":true,"rationale":"task_type 'unknown_type' 未在 routing_rules 中定義..."}

# 實際 Groq 呼叫（需 relay 運行）
uv run python tools/llm_router.py --task-type en_to_zh --input "The quick brown fox"
# 期望：{"provider":"groq","result":"快速的棕色狐狸",...}

# Groq 離線降級
uv run python tools/llm_router.py --task-type news_summary --input "test"
# 期望：{"provider":"fallback_skipped","action":"skip_and_log",...}

# PowerShell 整合
.\tools\invoke-llm.ps1 -TaskType "news_summary" -InputText "ByteDance releases DeerFlow 2.0" -DryRun
```

### P0-A ADR Lint
```bash
uv run python tools/validate_adr.py --check context/adr-registry.json
# 期望：0 errors
```

### P0-B Fitness Function
```bash
pwsh -File check-health.ps1
# 期望：出現 [Fitness Function 評分] 區塊
```

### P1-A Hook Pipeline
```bash
uv run pytest tests/hooks/ -v
# 期望：556+ 個測試全數通過
```

### P3-A LLM-as-Router
```bash
uv run python tools/llm_classifier.py --input "幫我把這篇英文文章翻譯成中文"
# 期望：{"task_type":"en_to_zh","confidence":0.95}
```

### P4-A Hono groq-relay
```bash
# 啟動 Hono 版 relay（替換原 Node.js relay）
node bot/groq-relay.ts  # 或 tsx bot/groq-relay.ts

# 健康檢查（watchdog 端點不變）
curl http://localhost:3002/groq/health
# 期望：{"status":"ok","timestamp":...}

# 型別安全測試：送錯誤 mode 應得 422
curl -X POST http://localhost:3002/groq/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"invalid_mode","content":"test"}'
# 期望：422 Unprocessable Entity + 欄位錯誤說明
```

### P4-B Structured Generation
```bash
# 驗證 classify 回傳 schema
uv run python -c "
from tools.llm_router import validate_relay_response
result = validate_relay_response('classify', '{\"labels\":[\"AI\"],\"confidence\":0.9}')
print(result)  # 期望：{'labels': ['AI'], 'confidence': 0.9}
"

# Instructor 整合測試
uv run python tools/structured_claude.py --test-adr
# 期望：輸出符合 ADROutput schema 的 JSON
```

### P4-C 預算治理
```bash
# 預算狀態查詢
uv run python tools/budget_guard.py --status
# 期望：{"claude_tokens":{"used":X,"limit":5000000,"utilization":X%},...}

# 模擬超限
uv run python tools/budget_guard.py --simulate-exhaustion --provider groq
# 期望：{"allowed":false,"reason":"daily_budget_exhausted",...}
```

### P4-D 目標繼承鏈 + 審計完整性
```bash
# 驗證審計日誌鏈式完整性
uv run python tools/audit_verify.py --log logs/structured/hooks.jsonl
# 期望：VALID - 所有記錄鏈式 hash 驗證通過

# 查詢 backlog 目標對齊狀況
uv run python tools/audit_verify.py --mission-alignment
# 期望：G01(降低成本) 3/5 items, G02(可靠性) 2/3 items...
```

### P5-A Agent Pool
```bash
# 驗證 Coordination Plan 產生
uv run python tools/agent_pool/coordinator.py --tasks-file /tmp/test_tasks.json
# 期望：state/coordination-plan.json 產生，含 worker_type 分配

# done_cert 簽發 + 驗證（Phase 3 前置確認）
uv run python tools/agent_pool/done_cert.py --issue \
  --task-id "test-task-001" --worker-type web_search \
  --result-file results/todoist-auto-ai-research.json
# 期望：state/done-certs/test-task-001.json 產生

uv run python tools/agent_pool/done_cert.py --verify --task-id "test-task-001"
# 期望：{"ok": true, "reason": "ok"}

# 模擬 Phase 2 結果缺失：result_file 被刪除後 verify 應失敗
uv run python tools/agent_pool/done_cert.py --verify --task-id "test-task-001"
# 期望：{"ok": false, "reason": "結果檔案已消失: ..."}

# Bounded Queue 壓力測試（fan-out 10 個 web_search，應限制到 max_concurrent=3）
uv run python tools/agent_pool/coordinator.py --stress-test --worker-type web_search --count 10
# 期望：任何時刻並行數不超過 3

# 整合測試：執行一次 run-todoist-agent-team.ps1 後確認 done-certs/ 目錄有憑證
pwsh -File run-todoist-agent-team.ps1 -DryRun
ls state/done-certs/
# 期望：每個 Phase 2 任務都有對應的 .json 憑證檔
```

---

## 測試矩陣（M2 補充）

> 每個方案需達到的最低測試覆蓋要求，與現有 556 個測試保持相容。

| 方案 | 測試檔案 | 最低測試數 | 覆蓋重點 |
|------|---------|-----------|---------|
| P0-A ADR Lint | `tests/tools/test_validate_adr.py` | 15 | schema 驗證、狀態轉換合法性 |
| P0-B Fitness Fn | `check-health.ps1` 輸出格式驗證 | — | 手動驗證 6 維度均出現 |
| P1-A Hook Pipeline | `tests/hooks/test_hook_pipeline.py` | 20 | 短路機制、中介軟體組合 |
| P1-B LLM Router | `tests/tools/test_llm_router.py` | 25 | mapping lookup、Groq/Claude 分流、降級 |
| P4-B Structured Gen | `tests/tools/test_structured_generation.py` | 15 | schema 驗證、classify_with_retry 重試邏輯 |
| P4-C 預算治理 | `tests/tools/test_budget_guard.py` | 12 | 80%/100% 閾值、多 provider 計算 |
| P4-D 審計日誌 | `tests/tools/test_audit_verify.py` | 10 | hash chaining、輪轉標記、篡改偵測 |
| P5-A Agent Pool | `tests/tools/test_done_cert.py` | 15 | issue/verify/篡改偵測/Bounded Queue 上限 |

**目錄結構說明（C5）**：
- 新工具測試放在 `tests/tools/`（需先建立此目錄，現有 `pyproject.toml` 的 `testpaths = ["tests"]` 已覆蓋此路徑）
- 現有測試位於 `tests/hooks/`（556 個）；新增 `tests/tools/` 為平行目錄
- 第一個測試檔 `tests/tools/__init__.py`（空檔）需建立以啟用 pytest 發現

**與現有測試相容性保證**：
- P1-A Hook 重構必須確保現有 `uv run pytest tests/hooks/ -v` 全數通過（556 個測試）
- 新增測試採 TDD：先寫失敗測試 → 最小實作 → 通過

---

## Skills 整合評估（M7 補充）

> 評估新工具與現有 Skills 體系的整合方式，避免重複造輪。

| 新工具 | 現有相關 Skill | 整合策略 |
|--------|--------------|---------|
| `tools/llm_router.py` | `skills/groq/SKILL.md` | Groq Skill 的 curl 呼叫改為透過 `invoke-llm.ps1` 路由（漸進替換，不破壞現有呼叫） |
| `tools/llm_classifier.py` | `skills/groq/SKILL.md`（classify mode） | 共用 groq-relay classify endpoint，不重複實作 |
| `tools/budget_guard.py` | `skills/system-insight/SKILL.md` | budget 狀態納入 system-insight 的健康報告輸出 |
| `tools/structured_claude.py` | `skills/arch-evolution/SKILL.md` | arch-evolution Step 7 改呼叫 `generate_adr()` 確保輸出 schema 合規 |
| `tools/audit_verify.py` | `skills/system-audit/SKILL.md` | 審計完整性驗證納入 system-audit 的 7 維度之一 |
| `tools/agent_pool/done_cert.py` | `skills/self-heal/SKILL.md` | done-certs 清理邏輯整合到 self-heal Step 4（每日 >24h 清理） |
| `tools/agent_pool/coordinator.py` | `run-todoist-agent-team.ps1` | Coordinator 作為 Phase 1 Python 輔助，PS 腳本讀取 coordination-plan.json 派發 Phase 2 |

**關鍵原則**：新工具作為底層工具（tool layer），Skills 作為 LLM 可呼叫的高層業務邏輯（skill layer）。兩者分工明確，Skills 在需要時透過 `uv run python tools/...` 呼叫工具，不直接複製工具邏輯。

---

## 關鍵參考資料

| 參考 | 位置 |
|------|------|
| AI架構治理閉環 | KB: b9db3b71 |
| DeerFlow 2.0 | KB: ddc422ab |
| 2026 Agentic AI 工作流（xRouter/ToolOrchestra） | KB: 3b45aced |
| LLM-as-Router—Gemini CLI ClassifierStrategy | KB: 7f06170d |
| Dify LLMOps設計 | KB: 52f6a3b0 |
| AFFiNE架構 | KB: 15a379d8 |
| Vite同步管線 | KB: 049c6822 |
| 可觀測性成熟度路線圖 | KB: 7f971400 |
| AI模型蒸餾計畫 | docs/plans/2026-03-11-ai-model-distillation-miniaturization.md |
| 現有 Groq Skill | skills/groq/SKILL.md |
| 現有 LLM 路由配置 | config/llm-router.yaml |
| Groq Relay 監控哨兵 | bot/watchdog-groq-relay.ps1 |
| 現有 OODA 工作流 | config/ooda-workflow.yaml |
| 現有 ADR 索引 | context/adr-registry.json |
| **Hono Edge-First 框架（29.2K Stars）** | KB: 新（搜尋 "Hono Edge-First"）|
| **Structured Generation 完整指南（2026）** | KB: 新（搜尋 "Constrained Decoding Outlines"）|
| **Paperclip 零人力公司（7.7K Stars）** | KB: 新（搜尋 "Paperclip Heartbeat BYOA"）|
