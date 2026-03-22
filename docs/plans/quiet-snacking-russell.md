# 系統能力擴展計畫 — 8 個改進項目（v3）

## Context

目標：提升 daily-digest-prompt 的路由精準度、執行可靠性、日誌可觀測性與 Skill 安全隔離能力。
原則：改配置不改 prompt，最小化 Python 修改範圍。

**現況基線（已驗證）**：
- `config/llm-router.yaml`：routing_rules mapping dict，12 個 task_type；Groq relay 回傳 `{result, model, cached}`，**無 confidence 欄位**
- `tools/llm_router.py` `route()` 函數結構：
  - L207：`rule = match_rule(config, task_type)`
  - L209：`if rule is None: return claude default`
  - L220：`if dry_run: return {...}`
  - L233：`if provider == "groq": ...`
  - L257：`except urllib.error.URLError` → fallback_skipped
  - L270：`except (TimeoutError, json.JSONDecodeError, ConnectionError, OSError)` → fallback_skipped（**#7 必須同時覆蓋兩個 except 塊**）
- `templates/shared/preamble.md` 126 行：
  - L36：`status: "success" 只能在確認實際輸出存在後才能寫入`（被 #2 absorb，不保留）
  - L55：`KB 失敗 → status 改為 "partial"`（合法場景，不觸動）
- `templates/sub-agent/research-task.md`：子 Agent 模板（`{placeholder}`），非 auto-task 的依賴
- `config/schemas/results-auto-task-schema.json` v1.1.0：`status` enum 含 `["success", "partial", "failed", "format_failed"]`；`done_cert` 已有 `quality_score`
- `prompts/team/todoist-query.md`：已確認存在；步驟 1 查詢 → 步驟 1.1 過濾 → 步驟 2 Tier 路由
- `config/llm-router.yaml` 中 `quick_extract` 標記「預留未用」，無對應 Groq prompt
- 測試：912 個（hooks 529 + skills 27 + tools 300）；無 `agent-roles.yaml`、無子目錄 CLAUDE.md、無 `intent-patterns.yaml`

---

## 批次執行順序

```
Batch A（並行，Week 1 Day 1-2）
  #1 Category-Based Model Routing  ← llm-router.yaml + llm_router.py（~20 行）
  #3 階層式 CLAUDE.md              ← 純 Markdown 新建 4 個檔案 + 精簡主 CLAUDE.md
  #4 命名 Agent 角色               ← 新建 agent-roles.yaml + preamble.md 8 行

Batch B（依賴 #1，Week 1 Day 3 ~ Week 2 Day 2）
  #7 多層 Fallback Chain           ← 依賴 #1（_apply_category_defaults 已存在）
  #2 Todo Enforcer                 ← preamble.md 插入 22 行，移除 L36 舊規則
  #8 Intent Gate                   ← 新建 intent-patterns.yaml + routing.yaml + todoist-query.md

Batch C（高影響，Week 3）
  #6 Skill 權限隔離                ← 5 個 SKILL.md + pre_write_guard.py（~48 行）
  #5 Ralph Loop 自我迭代           ← research-task.md + 7 個 auto-task prompt + schema 擴充
```

**preamble.md 三項累積修改總覽**（按批次順序，最終 ~162 行）：

```
完成後結構：
  1. 語言宣告（不變，2 行）
  2. [Batch A] Agent 角色聲明（#4，8 行）
  3. Skill-First 規則（不變，~20 行）
  4. [Batch C] Skill permissions 感知（#6，6 行）
  5. Workflow 自動引用規則（不變，~10 行）
  6. Shell 執行強制規則（Batch B 移除 L36 舊規則，其餘不變，~14 行）
  7. [Batch B] 完成度自檢協議（#2，22 行）← 取代原 L36 的 status 規則
  8. 知識庫寫入確認規則（不變，~8 行）— L55 的 partial 用法保留不動
  9. Context 保護規則（不變，~12 行）
  10. 自動任務連續記憶規則（不變，~15 行）
  11. Context 壓縮感知（不變，~8 行）
  12. nul 禁令（不變，~6 行）
```

---

## 項目 1：Category-Based Model Routing

**目標**：task_type 宣告所屬 category，自動繼承 model 與 token 上限，降成本、提品質。

### 修改 `config/llm-router.yaml`

在 `providers:` 段落前加入 `categories:` 段落：

```yaml
categories:
  quick_summary:
    description: "快速摘要/分類：低成本、低延遲"
    preferred_provider: groq
    max_tokens: 500
    model: llama-3.1-8b-instant
  deep_research:
    description: "深度研究/長文合成：需要完整上下文理解"
    preferred_provider: claude
    max_tokens: 4000
    model: claude-sonnet-4-6
  complex_analysis:
    description: "複雜分析/政策/安全：高精準需求"
    preferred_provider: claude
    max_tokens: 2000
    model: claude-sonnet-4-6
  translation:
    description: "翻譯類任務：保留術語原文"
    preferred_provider: groq
    max_tokens: 800
    model: llama-3.1-8b-instant
```

各 routing_rule 加 `category` 欄位（現有 12 個 rule）：

| task_type | category |
|-----------|---------|
| `news_summary`, `topic_classify`, `quick_extract`, `kb_content_score`, `todoist_query_simple` | `quick_summary` |
| `en_to_zh` | `translation` |
| `policy_analysis`, `code_review`, `kb_import`, `security_analysis`, `gmail_processing` | `complex_analysis` |
| `research_synthesis` | `deep_research` |

### 修改 `tools/llm_router.py`

**新增一個純函數**（約 18 行），放在 `match_rule()` 函數定義之後：

```python
def _apply_category_defaults(config: dict, rule: dict | None) -> dict | None:
    """
    合併 category 預設值（max_tokens / model）到 rule。
    rule 層級設定優先；rule 為 None 時直接回傳 None（保持呼叫方的 None 判斷有效）。
    """
    if rule is None:
        return None              # ← 必須回傳 None，不可回傳 {}，否則破壞下游 `if rule is None` 判斷
    cat_name = rule.get("category")
    if not cat_name:
        return rule
    cat = config.get("categories", {}).get(cat_name, {})
    result = dict(rule)
    if not result.get("max_tokens") and cat.get("max_tokens"):
        result["max_tokens"] = cat["max_tokens"]
    if not result.get("model") and cat.get("model"):
        result["model"] = cat["model"]
    return result
```

**插入點**：`route()` 函數的 L207 之後、L209 之前（這樣 `if rule is None` 判斷仍有效，且 `dry_run` 在 L220 會看到已合併的 rule）：

```python
rule = match_rule(config, task_type)
rule = _apply_category_defaults(config, rule)    # ← 插入此行

if rule is None:
    return {... claude default ...}
```

`dry_run` 回傳（L220-226）中加入 `"category": rule.get("category")` 欄位。

### 新增測試（4 個，`tests/tools/test_llm_router.py`）

```python
class TestCategoryBasedRouting:
    def test_none_rule_returns_none(self):
        """rule=None → 回傳 None，不破壞 route() 的 if rule is None 判斷"""
    def test_category_max_tokens_inherited(self):
        """rule 無 max_tokens → 繼承 category 設定（news_summary → 500）"""
    def test_rule_max_tokens_overrides_category(self):
        """rule 有 max_tokens → 不被 category 覆寫"""
    def test_unknown_category_no_crash(self):
        """category 不存在於 categories 段落時，rule 原樣回傳，不拋錯"""
```

### 驗證

```bash
uv run python tools/llm_router.py --task-type news_summary --dry-run
# 預期輸出含：category=quick_summary, max_tokens=500
uv run python tools/llm_router.py --task-type research_synthesis --dry-run
# 預期輸出含：category=deep_research, max_tokens=4000
uv run pytest tests/tools/test_llm_router.py -v
```

---

## 項目 2：Todo Enforcer

**目標**：preamble.md 加入結構化完成度自檢，取代現有 L36 的單行規則，減少靜默失敗。

**邊界說明**：
- `"partial"` 是 schema 合法值（`KB 失敗 → status="partial"` 保留在 L55）；**自檢協議不限制 status 值，只驗證欄位完整性**
- `"partial"` 的任務級禁令保留在各研究 prompt 中，不從 preamble 全域管控

### 修改 `templates/shared/preamble.md`

**Step 1**：移除 L36 的舊規則（被以下 checklist 取代）：
```
| `status: "success"` | 只能在確認實際輸出存在後才能寫入 |
```
→ 從表格中刪除此行（其餘表格行保留）。

**Step 2**：在「Shell 執行強制規則」章節的表格之後，加入「**完成度自檢協議**」章節（約 22 行）：

```markdown
## 完成度自檢協議（所有 todoist-auto-*.md 結束前必須執行）

> **任何 auto-task 在輸出結束訊息前，必須通過以下 4 項自檢。未通過禁止結束。**

| # | 檢查項 | 通過條件 | 失敗處置 |
|---|--------|---------|---------|
| 1 | 結果 JSON 已寫入 | `Bash ls results/todoist-auto-{task_key}.json` 有輸出 | 立即 Write，status="failed" |
| 2 | status 非空 | status 欄位為非空字串（任何合法值均可） | 補填 status，說明原因 |
| 3 | 必填欄位齊全 | task_key、status、agent（或 task_type）均非 null | 補填缺失欄位 |
| 4 | 寫入已確認 | `Bash grep "status" results/todoist-auto-{task_key}.json` 有輸出 | 重新 Write，直到 grep 有輸出 |

**補充說明**：
- 失敗路徑也必須寫入 JSON（status="failed"，summary 說明原因）
- 禁止「描述性結束」：執行日誌必須有 Bash tool 的 ls/grep 確認記錄
- 各研究任務 prompt 有額外的 status 限制（如禁止 "partial"）— 請以各 prompt 規則為準
```

### 驗證

執行任一 auto-task 後，確認：
- `results/todoist-auto-*.json` 存在且 status 非空
- 對話記錄中有 `ls results/todoist-auto-*.json` 的 Bash tool 呼叫

---

## 項目 3：階層式 CLAUDE.md

**目標**：各子目錄放局部規則，主 CLAUDE.md 縮減至 <215 行。

**載入機制**：Claude Code 啟動時遞迴掃描專案內所有子目錄的 CLAUDE.md（已確認行為），`claude -p` 從專案根目錄執行時自動載入。主 CLAUDE.md 加入 `@import` 引用行作為文件指引。

### 新建 `prompts/CLAUDE.md`（約 38 行）

```markdown
# prompts/ 目錄局部規則

## 自動任務命名（唯一真相：config/frequency-limits.yaml）
- task_key 使用底線，禁用連字號
- 自動任務 prompt：todoist-auto-{task_key}.md
- 結果 JSON 路徑：results/todoist-auto-{task_key}.json
- 結果 JSON agent 欄位："todoist-auto-{task_key}"
- 新增任務時以上四處必須一致；validate_config.py --check-auto-tasks 驗證

## 結果 JSON 格式（符合 config/schemas/results-auto-task-schema.json）
- 必填：task_key、status、agent（或 task_type）
- status 合法值：success / partial / failed / format_failed
- 研究任務額外規則：status 禁止 "partial"（見各任務 prompt 說明）

## 禁止事項
- 禁止在 prompt 中硬編碼端點 URL（改用 .env 或 config/）
- 禁止在 prompt 中定義 TTL（改 config/cache-policy.yaml）
- 禁止在 prompt 中定義標籤路由規則（改 config/routing.yaml）
```

### 新建 `skills/CLAUDE.md`（約 32 行）

```markdown
# skills/ 目錄局部規則

## SKILL.md frontmatter 必填欄位
name / version（X.Y.Z）/ description（含 "Use when:" 段落）/ allowed-tools / triggers（≥3 個）
validate_config.py 會驗證以上欄位，缺少時在 check-health.ps1 中告警。

## allowed-tools 最小權限原則
- 只列入實際需要的工具
- 唯讀 Skill（如 scheduler-state）：只含 Read，禁止 Write/Edit
- 研究類 Skill：必須含 WebSearch、WebFetch

## 版本更新規則
- 修改步驟/規則等實質內容 → minor 版本 +0.1.0
- 修改格式/備注/範例 → patch 版本 +0.0.1
```

### 新建 `hooks/CLAUDE.md`（約 28 行）

```markdown
# hooks/ 目錄局部規則

## 規則外部化原則
攔截規則定義在 config/hook-rules.yaml，不在 Python 中硬編碼。
FALLBACK_* 常數只是 YAML 不可用的最後防線，內容應與 YAML 同步。
新增攔截規則：只改 hook-rules.yaml（Python 零修改）。

## 測試規範
- 每個 hook 對應 tests/hooks/test_*.py
- 新規則至少加：正常路徑 + 攔截路徑 + warn_only 路徑 各一個測試
- uv run pytest tests/ 必須全部通過（912+ 個）

## 日誌
- 位置：logs/structured/YYYY-MM-DD.jsonl
- 攔截：level="blocked"；警告：level="warn"
- 統一用 hook_utils.log_blocked_event()
```

### 新建 `config/CLAUDE.md`（約 28 行）

```markdown
# config/ 目錄局部規則

## 單一定義原則（修改前先確認唯一真相來源）
- TTL → cache-policy.yaml
- task_key → frequency-limits.yaml（auto-task 命名的唯一真相）
- Todoist 標籤路由 → routing.yaml
- LLM 模型選擇 → llm-router.yaml
- 端點 URL → .env 或 dependencies.yaml（若存在）

## YAML 版本管理
- 每個 YAML 頂部必須有 version: 欄位
- 影響現有行為的修改 → 遞增版本號
- 純新增欄位（向後相容）→ 不需遞增

## 高影響配置修改後的必要驗證
- hook-rules.yaml → uv run pytest tests/hooks/
- frequency-limits.yaml → uv run python hooks/validate_config.py --check-auto-tasks
- routing.yaml → 觀察下次 todoist-query 執行的路由日誌
```

### 修改主 `CLAUDE.md`

移除下列段落，加入子目錄引用說明（各段落精確替換）：

| 被移除內容 | 行數 | 替換為 |
|-----------|------|--------|
| 「自動任務命名規範（嚴禁使用連字號）」完整表格 + 黃金規則 + 新增 checklist | ~28 行 | 2 行：`> 命名規範詳見 prompts/CLAUDE.md（Claude Code 自動載入）` |
| 「計畫檔存放」慣例一行 | 1 行 | 移至 config/CLAUDE.md 並在此刪除 |
| 「嚴禁產生 nul 檔案」8 行完整段落 | 8 行 | 2 行摘要：`> 禁止在 Bash 使用 > nul；改用 > /dev/null 2>&1。詳見 hooks/CLAUDE.md。` |

目標：主 CLAUDE.md 從 256 行縮減至 **<215 行**。

---

## 項目 4：命名 Agent 角色（agent-roles.yaml）

**目標**：標準化 4 個角色定義，透過 log_prefix 改善日誌追蹤。

**設計決策**：`post_tool_logger.py` 的 role tag 偵測列為「推薦實作」（非可選），因為 agent-roles.yaml 的 log_prefix 欄位只有在 logger 讀取時才能體現價值。

### 新建 `config/agent-roles.yaml`（約 55 行）

```yaml
version: 1
description: |
  標準 Agent 角色定義。Agent 在執行前聲明角色（透過 preamble.md 的規則）。
  post_tool_logger.py 偵測 log_prefix 並在結構化日誌中加入 agent-role 標籤。

roles:
  fetcher:
    description: "負責 API 呼叫與資料抓取"
    primary_tools: [Bash, Read]
    log_prefix: "[FETCH]"
    examples: [todoist-query.md（步驟1）, fetch-hackernews.md]

  analyst:
    description: "負責分析、評分、路由決策"
    primary_tools: [Read, Bash]
    log_prefix: "[ANLZ]"
    examples: [todoist-query.md（步驟2路由）, system-insight Skill]

  assembler:
    description: "負責整合多源資料並輸出最終結果"
    primary_tools: [Read, Write, Bash]
    log_prefix: "[ASMB]"
    examples: [assemble-digest.md, todoist-assemble.md]

  auditor:
    description: "負責系統審查與一致性檢查"
    primary_tools: [Read, Bash, Glob, Grep]
    log_prefix: "[AUDT]"
    examples: [fetch-audit-dim*.md, system-audit Skill]

multi_role_note: "一個 prompt 按階段切換角色時，宣告佔時最長的主要角色即可"
```

### 修改 `templates/shared/preamble.md`（Batch A）

在語言宣告（前 2 行）之後插入（約 8 行）：

```markdown
## Agent 角色聲明（改善日誌可讀性）

執行前，在輸出的第一行加入角色聲明：
```
[FETCH] 我的角色：fetcher（API 呼叫與資料抓取）
```
將 `[FETCH]` 替換為 `config/agent-roles.yaml` 中對應角色的 `log_prefix`（fetcher/analyst/assembler/auditor）。
若不確定角色或任務跨角色，略過此步驟，不影響執行。
```

### 推薦實作：修改 `hooks/post_tool_logger.py`（約 10 行）

在日誌條目建立時（`build_log_entry()` 或等效函數），加入 role tag 偵測：
- 從最近的 LLM 輸出（若可從 stdin JSON 取得 `assistant_output`）中偵測 `[FETCH]`/`[ANLZ]`/`[ASMB]`/`[AUDT]` 前綴
- 命中時加入 `tags: ["agent-role:fetcher"]` 等標籤至日誌條目

對應新增 3 個測試（`tests/hooks/test_post_tool_logger.py`）：
- `test_fetch_role_tag_detected`
- `test_no_role_prefix_no_tag`
- `test_role_tag_first_match_wins`（多個前綴取第一個）

---

## 項目 5：自我迭代（Ralph Loop）

**目標**：研究類任務完成初稿後自評品質，不足時補充搜尋。

**架構說明**：
- `templates/sub-agent/research-task.md`：子 Agent 模板（用戶觸發的研究任務），加入 Ralph Loop
- 7 個 `todoist-auto-*.md`：**自包含**，不依賴 research-task.md，需**獨立**加入 Ralph Loop
- 兩者的 Ralph Loop 內容相同，但位置不同（前者在模板末尾，後者在各 prompt 的 done_cert 寫入前）

**逾時意識**：
- `ai_deep_research` timeout=720s，加 2 次迭代可能超時 → **限制 max_iterations=1**
- `tech_research` timeout=2600s → max_iterations=2（正常）
- 其他佛學系列（shurangama 等）timeout=1200s → max_iterations=2

### 修改 `templates/sub-agent/research-task.md`

在「寫入知識庫」步驟之後、「品質自評」步驟之前插入「Ralph Loop 品質迭代」章節（約 38 行）：

**6 項品質評分標準**（1-5 分）：
1. 來源多樣性（≥5 個不同域名）
2. 主張有佐證（每個主要結論有 1+ 引用）
3. 知識差距識別（明確說明未查到的資訊）
4. 新穎性（與 KB 現有內容有明顯不同）
5. 結構完整性（含背景/發現/結論三段）
6. 可行性（對本專案有明確啟發或行動建議）

**迭代邏輯**：
```
quality_score = sum(六項分數) / 6（四捨五入至小數第一位）
max_iterations：依任務 timeout 決定（預設 2；timeout ≤ 900s 時限制為 1）

IF quality_score ≥ 4.0 → 進入 done_cert 寫入
IF quality_score < 4.0 AND iteration_count < max_iterations
  → 補充搜尋（針對分數最低的 1-2 項進行 WebSearch），修訂報告，重新自評
IF quality_score < 4.0 AND iteration_count ≥ max_iterations
  → 維持現有結果，在 summary 記錄「品質分 X.X，超出迭代上限」
```

**done_cert 新增欄位**（加入結果 JSON）：
```json
"done_cert": {
  "status": "DONE",
  "quality_score": 4.2,
  "iteration_count": 1,
  "quality_breakdown": {
    "source_diversity": 4, "claims_backed": 4, "gap_identified": 4,
    "novelty": 5, "structure": 4, "actionability": 4
  }
}
```

### 修改 7 個研究類 auto-task prompt

在各 prompt 的「品質自評」章節前加入 Ralph Loop 迭代條件（約 8 行）：

受影響的 prompt 清單（含現有 done_cert 欄位與 timeout 對照）：

| prompt | 現有 done_cert | timeout(s) | max_iterations |
|--------|--------------|------------|----------------|
| `todoist-auto-ai_github_research.md` | ✓ | 900 | 1 |
| `todoist-auto-tech_research.md` | 確認後補 | 2600 | 2 |
| `todoist-auto-ai_deep_research.md` | 確認後補 | 720 | 1 |
| `todoist-auto-shurangama.md` | 確認後補 | 1200 | 2 |
| `todoist-auto-jiaoguangzong.md` | 確認後補 | 1200 | 2 |
| `todoist-auto-fahua.md` | 確認後補 | 1200 | 2 |
| `todoist-auto-jingtu.md` | 確認後補 | 900 | 1 |

### 修改 `config/schemas/results-auto-task-schema.json`

在 `done_cert.properties` 加入兩個可選欄位（`additionalProperties: true`，不加入 `required`，向後相容）：

```json
"iteration_count": {
  "type": "integer", "minimum": 0, "maximum": 2,
  "description": "Ralph Loop 迭代次數（0=首次通過，1=一次補充，2=兩次補充）"
},
"quality_breakdown": {
  "type": "object",
  "description": "6 維度品質分數（Ralph Loop 自評）",
  "properties": {
    "source_diversity": {"type": "number", "minimum": 1, "maximum": 5},
    "claims_backed":    {"type": "number", "minimum": 1, "maximum": 5},
    "gap_identified":   {"type": "number", "minimum": 1, "maximum": 5},
    "novelty":          {"type": "number", "minimum": 1, "maximum": 5},
    "structure":        {"type": "number", "minimum": 1, "maximum": 5},
    "actionability":    {"type": "number", "minimum": 1, "maximum": 5}
  }
}
```

更新 `_metadata.version` 至 `1.2.0`，加入 changelog 條目。

### 驗證

```bash
cat results/todoist-auto-ai_github_research.json | uv run python -c "
import json,sys; d=json.load(sys.stdin)
dc = d.get('done_cert', {})
print('quality_score:', dc.get('quality_score'))
print('iteration_count:', dc.get('iteration_count'))
print('quality_breakdown:', dc.get('quality_breakdown'))
"
```

---

## 項目 6：Skill 權限隔離

**目標**：每個 Skill 宣告 writable-paths/forbidden-paths，Write Guard 感知並告警。

### 關鍵設計決策

**為何不用環境變數**：bash `export` 設定的變數不會傳遞給 hook 進程（獨立進程）。

**狀態檔案法**：Agent 執行 Skill 前寫入 `state/active-skill.txt`，Write Guard 讀取此檔案判斷當前 Skill。

**v1 Permission 模型範圍**（明確邊界）：
- **v1 強制**：`forbidden-paths` 命中 → warn_only 告警；`writable-paths = []`（空列表）→ warn_only 告警
- **v1 不強制**：`writable-paths` 正向檢查（不在列表就告警）← **v2 實作**
- 原因：正向檢查需要維護完整的白名單，v1 先積累 forbidden-paths 的觀察數據

**State file cleanup**：
- 任務正常結束：preamble.md 指示在最後一步清除
- 任務異常終止：warn_only 模式下影響可接受（最多誤告警一次，下次執行新 Skill 時覆蓋）

### 修改 `templates/shared/preamble.md`（Batch C 加入）

在「Skill-First 規則」章節加入（約 6 行）：

```markdown
**Skill permissions 感知（v6 啟用後）**：
執行宣告了 `permissions:` 段落的 Skill 時：
1. 執行前：`Bash echo "{skill_name}" > state/active-skill.txt`（聲明當前 Skill）
2. 執行中：Write Guard 自動偵測 forbidden-paths 違規並 warn_only 告警
3. 結束時（無論成功/失敗）：`Bash echo "" > state/active-skill.txt`（清除聲明）
```

### 修改 5 個示範 Skill 的 `SKILL.md` frontmatter

（其餘 51 個 Skill 在後續版本補充）

| Skill | writable-paths（文件意圖） | forbidden-paths（v1 強制） |
|-------|--------------------------|--------------------------|
| `skills/todoist/SKILL.md` | `results/, context/continuity/, cache/` | `.env, hooks/, bot/.env, state/scheduler-state.json` |
| `skills/ntfy-notify/SKILL.md` | `logs/` | `.env, state/scheduler-state.json, hooks/` |
| `skills/scheduler-state/SKILL.md` | `[]`（唯讀，強制告警任何寫入） | `state/scheduler-state.json` |
| `skills/knowledge-query/SKILL.md` | `cache/` | `.env, hooks/, state/scheduler-state.json` |
| `skills/system-audit/SKILL.md` | `docs/audit-reports/, results/, context/` | `.env, bot/.env, hooks/` |

frontmatter 格式範例：
```yaml
permissions:
  writable-paths: [results/, context/continuity/]   # 文件意圖（v1 不強制正向檢查）
  forbidden-paths: [.env, hooks/]                   # v1 強制：命中則 warn_only 告警
```

### 修改 `hooks/pre_write_guard.py`

在現有 `FALLBACK_WRITE_RULES` 列表後、函數定義前，新增兩個純函數（約 45 行）：

```python
def _load_active_skill_permissions(project_root: str) -> tuple[str | None, dict | None]:
    """
    讀取 state/active-skill.txt → 解析對應 SKILL.md 的 permissions 段落。
    任何錯誤（檔案不存在、YAML 解析失敗、Skill 目錄不存在）一律靜默回傳 (None, None)。
    設計為完全靜默失敗，確保 hook 主流程不受此功能影響。
    """
    try:
        active_file = os.path.join(project_root, "state", "active-skill.txt")
        if not os.path.isfile(active_file):
            return None, None
        skill_name = open(active_file, encoding="utf-8").read().strip()
        if not skill_name:
            return None, None
        skill_md = os.path.join(project_root, "skills", skill_name, "SKILL.md")
        if not os.path.isfile(skill_md):
            return None, None
        import yaml
        content = open(skill_md, encoding="utf-8").read()
        parts = content.split("---", 2)
        if len(parts) < 3:
            return skill_name, None
        fm = yaml.safe_load(parts[1])
        perms = fm.get("permissions") if isinstance(fm, dict) else None
        return skill_name, perms
    except Exception:
        return None, None   # 靜默失敗


def _check_skill_permissions(
    file_path: str, skill_name: str, permissions: dict
) -> tuple[bool, str | None]:
    """
    v1 範圍：僅檢查 forbidden-paths 與 writable-paths=[]。
    writable-paths 正向檢查（非空列表時的路徑限制）留待 v2 實作。
    回傳 (should_warn, reason_msg)。
    """
    norm = file_path.replace("\\", "/").lower()
    # v1.1：forbidden-paths 命中
    for fp in permissions.get("forbidden-paths", []):
        if fp.lower() in norm:
            return True, f"[SkillPerm:{skill_name}] 嘗試寫入 forbidden-path: {fp}"
    # v1.2：writable-paths=[]（唯讀 Skill）
    writable = permissions.get("writable-paths")
    if isinstance(writable, list) and len(writable) == 0:
        return True, f"[SkillPerm:{skill_name}] 此 Skill 為唯讀（writable-paths=[]），禁止任何寫入"
    # v2 預留：非空 writable-paths 的正向檢查（目前不實作）
    return False, None
```

在 `check_write_path()` 的規則迴圈**之前**插入（約 8 行）：

```python
# Skill permissions 感知（v1: warn_only 模式；state/active-skill.txt 不存在時跳過）
_skill_name, _skill_perms = _load_active_skill_permissions(project_root)
if _skill_name and _skill_perms:
    _perm_warn, _perm_reason = _check_skill_permissions(
        file_path, _skill_name, _skill_perms
    )
    if _perm_warn:
        log_blocked_event("skill-perm-guard", file_path, _perm_reason, warn_only=True)
        # warn_only=True：記錄告警，繼續執行（不 block）
```

### 新增測試（5 個，`tests/hooks/test_pre_write_guard.py`）

```python
class TestSkillPermissions:
    def test_forbidden_path_triggers_warn_not_block(self, tmp_path):
        """forbidden-paths 命中 → 記錄 warn 但不阻擋（warn_only=True）"""
    def test_empty_writable_paths_triggers_warn(self, tmp_path):
        """writable-paths=[] → 記錄 warn（唯讀 Skill）"""
    def test_no_active_skill_file_skips_check(self, tmp_path):
        """state/active-skill.txt 不存在 → 完全跳過 Skill 檢查"""
    def test_unknown_skill_name_silently_skips(self, tmp_path):
        """active-skill.txt 有內容但 SKILL.md 不存在 → 靜默跳過"""
    def test_no_permissions_field_skips(self, tmp_path):
        """SKILL.md frontmatter 無 permissions 欄位 → 跳過（向後相容）"""
```

**向後相容保證**：`state/active-skill.txt` 預設不存在 → `_load_active_skill_permissions` 直接回傳 `(None, None)` → 感知邏輯完全跳過 → 現有 49 個 pre_write_guard 測試行為完全不變。

### 驗證

```bash
# 建立測試場景
echo "scheduler-state" > state/active-skill.txt

# 模擬 pre_write_guard 檢查
uv run python -c "
import sys; sys.path.insert(0, 'hooks')
from pre_write_guard import _load_active_skill_permissions, _check_skill_permissions
sn, perms = _load_active_skill_permissions('.')
print('skill:', sn, '| perms:', perms)
if perms:
    warn, reason = _check_skill_permissions('state/scheduler-state.json', sn, perms)
    print('warn:', warn, '|', reason)
"
# 預期：warn: True | [SkillPerm:scheduler-state] 此 Skill 為唯讀...

# 清理
echo "" > state/active-skill.txt
```

---

## 項目 7：多層 Fallback Chain

**目標**：Groq 服務任何形式失敗時，逐層升級（groq → claude-haiku → claude-sonnet）。

**v1 範圍**：只實作失敗升級（URLError + TimeoutError + 其他連線錯誤）。
`quality_below_threshold` 觸發升級留待 v2（需 groq-relay.js 回傳 `confidence` 欄位）。

### 修改 `config/llm-router.yaml`

在現有 `fallback:` 段落後加入（約 22 行）：

```yaml
fallback_chain:
  enabled: true
  description: "v1：失敗觸發升級（URLError/Timeout/連線錯誤）。quality 升級為 v2（需 relay 回傳 confidence）。"
  tiers:
    tier1: { provider: groq, model: llama-3.1-8b-instant, description: "快速/低成本（預設）" }
    tier2:
      provider: claude_haiku
      model: claude-haiku-4-5-20251001
      trigger: [groq_unavailable, groq_timeout, groq_connection_error]
      description: "中等能力"
    tier3:
      provider: claude
      model: claude-sonnet-4-6
      trigger: [claude_haiku_failed]
      description: "完整能力（最後手段）"
  category_ceiling:
    quick_summary: tier2    # 防止 quick_summary/translation 升級至 claude-sonnet
    translation: tier2
    complex_analysis: tier3
    deep_research: tier3
  future_v2:
    quality_threshold: 0.7
    requires: "groq-relay.js 回傳 confidence 欄位"
```

### 修改 `tools/llm_router.py`

**新增 2 個函數**（共約 25 行，依賴 #1 的 `_apply_category_defaults` 已存在）：

```python
def _should_try_fallback_chain(config: dict, rule: dict | None) -> bool:
    """
    判斷是否應嘗試 fallback chain。
    條件：fallback_chain.enabled=true 且 category_ceiling 允許升到 tier2+。
    rule=None 時：category 為空，ceiling 預設 tier3 → 允許升級。
    """
    chain_cfg = config.get("fallback_chain", {})
    if not chain_cfg.get("enabled", False):
        return False
    cat = (rule or {}).get("category", "")
    ceiling = chain_cfg.get("category_ceiling", {}).get(cat, "tier3")
    return ceiling in ("tier2", "tier3")


def _build_tier2_fallback_response(mode: str, max_tokens: int) -> dict:
    """
    Tier 2 fallback 回傳結構。
    注意：不直接呼叫 claude-haiku API；回傳 use_claude=True + model_hint，
    讓 Agent（本身即 Claude）用 claude-haiku 的 token budget 內建推理。
    model_hint 僅供日誌與 dry_run 資訊顯示，不影響實際執行模型。
    """
    return {
        "provider": "claude_haiku",
        "use_claude": True,
        "model_hint": "claude-haiku-4-5-20251001",
        "fallback_tier": 2,
        "mode": mode,
        "max_tokens": max_tokens,
        "rationale": "Groq 不可用，升級至 tier2 claude-haiku"
    }
```

**插入點**：**同時修改兩個 except 塊**（L257 和 L270），在各自 `return {"provider": "fallback_skipped", ...}` 之前插入（約 6 行）：

```python
# Fallback Chain：Groq 任何失敗時嘗試升級至 tier2
rule_with_cat = _apply_category_defaults(config, rule)
if _should_try_fallback_chain(config, rule_with_cat):
    mode_for_fallback = rule.get("groq_mode") or rule.get("mode", "summarize") if rule else "summarize"
    tokens_for_fallback = (rule_with_cat or {}).get("max_tokens", 300)
    update_token_usage("claude")
    return _build_tier2_fallback_response(mode_for_fallback, tokens_for_fallback)
```

### 新增測試（5 個）

```python
class TestFallbackChain:
    def test_url_error_triggers_tier2_for_complex_analysis(self):
        """URLError → complex_analysis（ceiling=tier3）→ 升級至 claude_haiku"""
    def test_timeout_error_also_triggers_chain(self):
        """TimeoutError（第二個 except 塊）→ 同樣觸發 fallback chain"""
    def test_quick_summary_ceiling_stops_at_tier2(self):
        """quick_summary ceiling=tier2 → 不升級至 claude-sonnet"""
    def test_fallback_chain_disabled_returns_skip(self):
        """enabled=false → 維持原有 fallback_skipped 回傳"""
    def test_tier2_response_has_required_fields(self):
        """tier2 回傳含 provider=claude_haiku, fallback_tier=2, model_hint, use_claude=True"""
```

### 驗證

```bash
uv run pytest tests/tools/test_llm_router.py::TestFallbackChain -v

# 快速功能驗證（mock URLError）
uv run python -c "
from unittest.mock import patch
import urllib.error
# 注意：需要 llm_router.py 的 fallback_chain.enabled=true
# 驗證：complex_analysis task_type 的 URLError 回傳 provider=claude_haiku
print('run uv run pytest tests/tools/ -v for full validation')
"
```

---

## 項目 8：Intent Gate（純關鍵字匹配，無 Groq 依賴）

**目標**：todoist-query.md 在 Tier 2 路由前分析任務意圖，調整信心度。

**架構決策 — 純關鍵字匹配（不呼叫 Groq）**：

原計畫用 `quick_extract` 呼叫 Groq，但 `quick_extract` 在 `llm-router.yaml` 中標記「預留未用」（無對應 Groq prompt），且 `--input-file` flag 未在 `llm_router.py main()` 中實作。

**v1 採用純 LLM 關鍵字匹配**：Agent 讀取 `config/intent-patterns.yaml`，在工作記憶中對任務標題與描述做字串比對，調整信心度。無 Groq 呼叫、無檔案操作、無額外工具呼叫。v2 可接入 Groq 進行語義分類。

### 新建 `config/intent-patterns.yaml`（約 55 行）

```yaml
version: 1
description: |
  Todoist 任務意圖分類模式，供 todoist-query.md 的 Intent Gate 步驟使用。
  v1：純關鍵字匹配（LLM 在工作記憶中執行，無 Groq 呼叫）。
  v2 預留：接入 Groq quick_extract 進行語義分類（需定義對應 prompt）。

intents:
  research:
    description: "需要查詢、研究、蒐集資訊"
    keywords: [研究, 調查, 查詢, 了解, 最新, 技術趨勢, GitHub, HN, 深度分析]
    route_boost: 0.15     # Tier 2 信心度 +15%（80% → 95%）
    preferred_template: templates/sub-agent/research-task.md

  code:
    description: "程式碼開發、修復、重構"
    keywords: [開發, 修復, 重構, 程式碼, bug, deploy, 部署, 實作, 功能]
    route_boost: 0.15
    preferred_template: templates/sub-agent/code-task.md

  creative:
    description: "遊戲設計、創意內容"
    keywords: [遊戲, 創意, 設計, 美術, 關卡, 角色, game]
    route_boost: 0.10
    preferred_template: templates/sub-agent/game-task.md

  system:
    description: "系統維護、審查、配置"
    keywords: [系統, 審查, 排程, 自動化, 配置, 健康, 監控]
    route_boost: 0.10
    preferred_template: templates/sub-agent/skill-task.md

  chat:
    description: "對話/詢問（可能不適合自動處理）"
    keywords: [告訴我, 說明一下, 解釋, 這是什麼]
    route_boost: -0.20    # 80% → 60%，觸發 Tier 3 語義判斷
    preferred_template: null

gate_config:
  enabled: true
  only_for_tier: [2]        # 只在 Tier 2 候選任務前執行（Tier 1 已 100%，不需要）
  min_task_chars: 10         # 任務描述 < 10 字時跳過（太短無法判斷意圖）
  confidence_clamp: [0.40, 0.99]   # 調整後信心度上下限
  v2_groq:
    task_type: quick_extract
    note: "v2 啟用前需在 llm-router.yaml 定義 quick_extract 的 Groq prompt"
```

### 修改 `config/routing.yaml`

頂層加入 `intent_gate:` 配置參考（約 6 行）：

```yaml
intent_gate:
  enabled: true
  config_ref: config/intent-patterns.yaml
  note: "v1=純關鍵字匹配；Tier 1 路由不受影響；Groq 失敗時信心度維持原值"
```

### 修改 `prompts/team/todoist-query.md`

在「步驟 1.1 防止重複關閉+時間過濾」之後、步驟 2（Tier 路由）之前，新增「**步驟 1.5：Intent Gate**」（約 28 行）：

```markdown
## 步驟 1.5：Intent Gate（Tier 2 前置，純關鍵字匹配）

> 只對通過步驟 1.1 過濾後、**尚未被 Tier 1 確定路由**的任務執行。
> 若 `config/intent-patterns.yaml` 的 `gate_config.enabled = false`，跳過此步驟。

**一次性初始化（此步驟執行一次即可，不需對每個任務重複讀取）**：
讀取 `config/intent-patterns.yaml`，取得 `intents` 字典與 `gate_config`。

**對每個 Tier 2 候選任務執行**（任務描述字元 ≥ 10 字）：

1. 合併「任務標題 + 描述前 100 字」為分析文字
2. 與各 intent 的 `keywords` 逐一比對（不區分大小寫，部分比對）
3. 找到第一個命中的 intent（或未命中）：
   - **命中**：`adjusted_confidence = clamp(0.80 + route_boost, 0.40, 0.99)`
   - **未命中**：`adjusted_confidence = 0.80`（不變）
4. 將 `adjusted_confidence` 用於後續 Tier 2 路由的信心度計算

**重要邊界**：
- intent 分析只調整信心度，不改變路由目標（Skill 選擇仍由 routing.yaml 決定）
- `chat` intent 命中後信心度降至 ~60%，可能觸發 Tier 3 語義判斷
- 此步驟純在工作記憶中執行，不呼叫任何外部 API，不建立任何檔案
```

### 驗證

```bash
# 確認 YAML 格式正確，gate_config 存在
uv run python -c "
import yaml
d = yaml.safe_load(open('config/intent-patterns.yaml'))
print('intents:', list(d['intents'].keys()))
print('enabled:', d['gate_config']['enabled'])
print('v2_note:', d['gate_config']['v2_groq']['note'])
"
```

---

## 測試影響完整摘要

| 項目 | 新增測試 | 影響現有測試集 | 向後相容保證 |
|------|---------|--------------|------------|
| #1 | 4 | `tests/tools/test_llm_router.py` | `_apply_category_defaults(None)` 回傳 `None`，不破壞 `if rule is None` |
| #2 | 0 | 無 | partial 仍合法；只加 checklist，移除 L36 舊規則 |
| #3 | 0 | 無 | 子目錄 CLAUDE.md 是純增加，不刪現有規則 |
| #4 | 3（推薦） | `tests/hooks/test_post_tool_logger.py` | 角色聲明可選，不影響現有執行 |
| #5 | 0 | `results-auto-task-schema.json`（additionalProperties:true） | 只加欄位，不加入 required |
| #6 | 5 | `tests/hooks/test_pre_write_guard.py`（現有 49 個） | active-skill.txt 不存在時完全跳過 |
| #7 | 5 | `tests/tools/test_llm_router.py` | enabled=false 時兩個 except 塊行為不變 |
| #8 | 0 | 無 | 純 Markdown+YAML；on_groq_fail 不適用（v1 無 Groq） |
| **合計** | **17** | 54 個相關測試需回歸驗證 | |

**全部完成後總測試數**：912 + 17 = **929 個**。

---

## 關鍵檔案清單

| 檔案 | 改動類型 | 批次 |
|------|---------|------|
| `config/llm-router.yaml` | 加入 `categories:` + `fallback_chain:` 段落 | A → B |
| `tools/llm_router.py` | 新增 3 個函數（`_apply_category_defaults`, `_should_try_fallback_chain`, `_build_tier2_fallback_response`），修改兩個 except 塊 | A → B |
| `templates/shared/preamble.md` | Batch A 加 8 行，Batch B 移除 L36 + 加 22 行，Batch C 加 6 行（共 +36 -1 行） | A→B→C |
| `CLAUDE.md` | 精確移除 3 段，加引用說明，縮減至 <215 行 | A |
| `prompts/CLAUDE.md`（新建） | — | A |
| `skills/CLAUDE.md`（新建） | — | A |
| `hooks/CLAUDE.md`（新建） | — | A |
| `config/CLAUDE.md`（新建） | — | A |
| `config/agent-roles.yaml`（新建） | — | A |
| `config/intent-patterns.yaml`（新建） | — | B |
| `config/routing.yaml` | 加入 `intent_gate:` 6 行 | B |
| `prompts/team/todoist-query.md` | 在步驟 1.1 後插入步驟 1.5（約 28 行） | B |
| `templates/sub-agent/research-task.md` | 插入 Ralph Loop 章節（約 38 行） | C |
| 7 個 `todoist-auto-{研究類}.md` | 各加入 Ralph Loop 迭代條件（約 8 行/prompt） | C |
| `config/schemas/results-auto-task-schema.json` | `done_cert` 加 2 個可選欄位，版本升至 1.2.0 | C |
| 5 個 `skills/*/SKILL.md` | 加入 `permissions:` frontmatter 段落 | C |
| `hooks/pre_write_guard.py` | 新增 2 個純函數 + 8 行感知呼叫（共約 53 行） | C |
