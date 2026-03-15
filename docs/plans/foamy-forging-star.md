# 計畫：五者整合實作對齊與 Token 成本優化

> 計畫日期：2026-03-15（v4，四輪深度審查最終版）
> 前序文件：`docs/project-overview-workflows-models-skills.md`（五者關係已記錄）
> 前序計畫：`C:\Users\user\.cursor\plans\五者關係整合說明_277ae4d9.plan.md`（文件已落地）
> 相關專案：`D:\Source\RAG_Skill`（KB API, port 3000）、`D:\Source\my-gun-relay`（Gun Relay, port 8765）
> 相關計畫：`docs/plans/淨土教觀學苑podcast專輯.md`（750 集全輯規劃）

---

## Context

前序 Cursor 計畫已完成文件層。本計畫從文件走向**實作對齊 + Token 成本優化**。

歷經四輪深度審查，已修正 **7 個重大假設錯誤**：

| # | 舊假設（錯誤） | 實際狀況 |
|---|--------------|---------|
| F1 | Get-TaskBackend 只需補 switch case | foreach 清單完全遺漏 cursor_cli；`Start-CursorCliJob` 函式不存在 |
| F2 | cursor_cli 任務檔已存在 | `temp/cursor-cli-task-fahua.md`、`podcast_create.md` 均不存在 |
| F3 | llm_router.py 有 --input-file/--output | 只支援 `--input <inline>`；無檔案 I/O |
| F4 | behavior-patterns.json 被多 prompt 讀取 | 0 個 prompt 讀取（設計預留未啟用） |
| F5 | jiaoguang-podcast-next.json 已存在 | 不存在，执行鏈完全阻塞 |
| F6 | B1 可用 llm_router.py CLI 整合 | 應使用 curl POST localhost:3002/groq/chat（如 fetch-hackernews.md） |
| F7 | research-registry 只有幾個 prompt 讀取 | 13 個 prompt 讀取（含 Phase 1 路由的 todoist-query.md） |

---

## 三大外部依賴確認

| 服務 | 專案 | Port | 用途 | 計畫影響 |
|------|------|------|------|---------|
| **KB API** | `D:\Source\RAG_Skill` | 3000 | 知識庫 hybrid search、筆記匯入 | Batch C（去重防線）、Batch B（kb_score 模式） |
| **Gun Relay** | `D:\Source\my-gun-relay` | 8765 | 聊天室 + LINE 通知 | Batch G（健康檢查）、日常運作 |
| **Groq Relay** | `bot/groq-relay.js` | 3002 | Groq API 代理（summarize/translate/classify/extract/kb_score） | Batch B（主力） |

> **Groq Relay 支援的 mode 值（已確認）**：`summarize`、`translate`、`classify`、`extract`、`kb_score`

---

## 核心問題：6 個斷點

| 斷點 | 症狀 | 嚴重度 |
|------|------|-------|
| D1 | `Start-CursorCliJob` 不存在；foreach 遺漏 cursor_cli；任務檔缺失 | 🔴 P0 |
| D2 | `context/jiaoguang-podcast-next.json` 不存在，750 集執行鏈無法啟動 | 🔴 P0 |
| D3 | Groq 路由只在 2 個 prompt 手工整合，24 個自動任務全走 Claude | 🟠 P1 |
| D4 | `research-registry.json`（84K）被 13 個 prompt 完整讀取，只需 topic 去重 | 🟠 P1 |
| D5 | 三服務健康狀態（KB/Relay/Groq）無統一檢查；Groq relay 常離線時靜默失效 | 🟡 P2 |
| D6 | 自動任務 timeout 分散在 freq-limits + timeouts 兩處，新增需改兩處 | 🟡 P2 |

---

## 優先級矩陣

| 批次 | 主題 | 修改量 | 效益 | 風險 | 順序 |
|------|------|-------|------|------|------|
| **A** | cursor_cli 完整實作 | 2 新函式 + 2 新檔 | 模型路由修復 | 中 | 第 1 |
| **E** | Podcast 執行鏈初始化 | 1 新建 + 1 修改 + 驗證 | 750 集解鎖 + ~510K tokens 節省 | 低 | 第 1（與 A 並行） |
| **G** | 三服務健康預檢 | 1 修改（check-health.ps1） | 靜默失效轉為可觀測警告 | 低 | 第 1（與 A/E 並行） |
| **C** | registry 精簡 | 1 修改 + 13 prompt 去重步驟 | ~24K tokens/次底數 | 低 | 第 2 |
| **B** | Groq 路由擴展 | 6 prompt 修改 | ~9.6K tokens/日轉 Groq | 中 | 第 3 |
| **D** | 配置合併 | 2 修改 | 維護成本降低 | 低 | 第 4 |
| **F** | 結果檔命名統一 | 2 修改 | Phase 3 組裝可靠性 | 低 | 第 4（與 D 並行） |

---

## 實施計畫

---

### Batch A：cursor_cli 完整實作（從零建立）

> 需新增函式與任務檔，非僅補 switch case

#### A1：實作 `Start-CursorCliJob` 函式

**修改**：[run-todoist-agent-team.ps1](../../run-todoist-agent-team.ps1)

參考 `Start-CodexJob`（L700-755）的結構，在其後新增：

```powershell
function Start-CursorCliJob {
    param(
        [string]$TaskKey,
        [string]$TaskFile,
        [string]$AgentDir,
        [int]$TimeoutSeconds = 600,
        [string]$TraceId = ""
    )

    $resultFile = Join-Path $AgentDir "results\todoist-auto-$TaskKey.json"
    $stderrFile = Join-Path $AgentDir "logs\cursor-cli-$TaskKey-stderr.log"

    $job = Start-Job -WorkingDirectory $AgentDir -ScriptBlock {
        param($taskFile, $resultFile, $stderrFile, $traceId)
        $startTime = Get-Date
        $content = Get-Content $taskFile -Raw -Encoding UTF8
        $output = & agent -p $content 2>$stderrFile
        $elapsed = ((Get-Date) - $startTime).TotalSeconds

        # 統一為 Phase 3 相容的 JSON 格式
        $result = @{
            agent     = "todoist-auto-$using:TaskKey"
            backend   = "cursor_cli"
            status    = if ($LASTEXITCODE -eq 0) { "completed" } else { "failed" }
            summary   = ($output | Select-Object -Last 5) -join "`n"
            elapsed   = [math]::Round($elapsed, 1)
            trace_id  = $traceId
            generated_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        }
        $result | ConvertTo-Json -Depth 3 |
            Set-Content $resultFile -Encoding UTF8
    } -ArgumentList $TaskFile, $resultFile, $stderrFile, $TraceId

    return $job
}
```

#### A2：將 cursor_cli 加入 Phase 2 後端迴圈

**修改**：[run-todoist-agent-team.ps1](../../run-todoist-agent-team.ps1) L635 附近

```powershell
# 找到現有 foreach 清單，追加 "cursor_cli"：
# 原：@("claude_opus46","claude_sonnet45","claude_haiku","codex_exec",...,"openrouter_research")
# 改：末尾加入 "cursor_cli"

# Phase 2 型別判斷主迴圈中（L1461-1468 附近），在最後 else 之前插入：
} elseif ($backend.type -eq "cursor_cli") {
    $taskFile = Join-Path $AgentDir "temp\cursor-cli-task-$taskKey.md"
    if (-not (Test-Path $taskFile)) {
        Write-Warning "[$taskKey] cursor_cli 任務檔不存在: $taskFile，跳過"
        continue
    }
    $timeout = Get-TaskTimeout $taskKey
    $jobs[$taskKey] = Start-CursorCliJob -TaskKey $taskKey `
        -TaskFile $taskFile -AgentDir $AgentDir `
        -TimeoutSeconds $timeout -TraceId $TraceId
}
```

#### A3：建立缺失的 cursor_cli 任務檔

參考 `temp/cursor-cli-task-nebula-strike.md`（現有 13 行範例格式）：

**新建** `temp/cursor-cli-task-fahua.md`：
- 依 `frequency-limits.yaml` 的 `fahua` 任務 template（`templates/auto-tasks/buddhist-research.md` 或類似）生成
- 核心內容：法華經研究 + 知識庫匯入 + 結構化摘要格式

**新建** `temp/cursor-cli-task-podcast_create.md`：
- 依 `podcast_create` 任務定義生成
- 指向 `tools/article-to-podcast.ps1` 的執行步驟
- 包含「執行完畢後必須提供執行摘要」格式要求

**驗證 A**：
```powershell
# 執行後確認
cat state/run-fsm.json | Select-String "cursor_cli"
Test-Path results/todoist-auto-fahua.json
```

---

### Batch E：Podcast 執行鏈初始化（解鎖 750 集）

#### E1：建立 `jiaoguang-podcast-next.json`

**新建**：[context/jiaoguang-podcast-next.json](../../context/jiaoguang-podcast-next.json)

```json
{
  "schema_version": 1,
  "next_episode": 1,
  "last_produced": 0,
  "last_topic": "",
  "total_episodes": 750,
  "updated_at": "2026-03-15T00:00:00+08:00",
  "source_plan": "docs/plans/淨土教觀學苑podcast專輯.md",
  "note": "run-jiaoguang-podcast-next.ps1 依此檔取得下集集數；第N集在 source_plan Line (27+N)"
}
```

#### E2：驗證 article-to-podcast.ps1 參數相容性

已確認（審查結果）：`-Query`、`-Slug`、`-NoteId`、`-Model` 四個參數均存在。

驗證行號計算：`docs/plans/淨土教觀學苑podcast專輯.md` 第 1 集資料在 Line 29（索引 28 = 27 + 1），第 N 集在 `lines[27 + N]`，已確認正確。

#### E3：課程級 context 快取（Token 節省）

**修改**：[prompts/team/jiaoguang-podcast-one-episode.md](../../prompts/team/jiaoguang-podcast-one-episode.md)

同課程連續集次（如「佛法修學概要」35 講）每集重讀課程 context 造成重複 Token。

新增快取步驟：
1. 腳本生成前，讀 `temp/jiaoguang-course-cache-{課程名}.json`（存在且 < 7 天 → 直接讀取）
2. 首次生成時，將課程簡介寫入快取
3. 快取欄位：`{ course_name, description, created_at, ttl_days: 7 }`

**估計節省**：同課程 35 集省 34 次重讀 × ~150 課程批次 ≈ **510K tokens** for 全輯。

#### E4：確認 all_exhausted_fallback 觸發後的雙後端策略

已確認（審查結果）：
- Phase 2 在 L1346 和 L1513 兩處觸發 all_exhausted_fallback
- 執行 `tools/run-jiaoguang-podcast-next.ps1 -Backend {primary/fallback}`
- 結果寫入 `results/todoist-exhausted-fallback.json`
- primary 取自 `frequency-limits.yaml` 的 `all_exhausted_fallback_primary`（目前為 "claude"）

**計畫文件補充**：在 [config/frequency-limits.yaml](../../config/frequency-limits.yaml) 的 `all_exhausted_fallback_primary` 旁加注解，說明值為 "claude" 或 "cursor_cli"。

**驗證 E**：
```powershell
pwsh tools/run-jiaoguang-podcast-next.ps1
# ✓ context/jiaoguang-podcast-next.json 的 next_episode 從 1 → 2
# ✓ temp/jiaoguang-course-cache-*.json 存在
```

---

### Batch G：三服務健康預檢（新批次）

> 整合 RAG_Skill（localhost:3000）、my-gun-relay（localhost:8765）、Groq Relay（localhost:3002）的健康狀態檢查

**修改**：[check-health.ps1](../../check-health.ps1)

新增「[外部服務]」健康檢查區塊：

```powershell
# === [外部服務健康檢查] ===
Write-Host "`n[外部服務]" -ForegroundColor Cyan

# 1. RAG_Skill KB API (D:\Source\RAG_Skill, port 3000)
try {
    $kbResp = Invoke-RestMethod "http://localhost:3000/api/health" -TimeoutSec 3
    $kbNotes = (Invoke-RestMethod "http://localhost:3000/api/stats" -TimeoutSec 3).total_notes
    Write-Host "  ✅ KB API (localhost:3000) 正常，筆記總數: $kbNotes" -ForegroundColor Green
} catch {
    Write-Host "  ⚠️  KB API 離線 — 知識庫查詢/去重失效" -ForegroundColor Yellow
}

# 2. Gun Relay (D:\Source\my-gun-relay, port 8765)
try {
    $relayResp = Invoke-RestMethod "http://localhost:8765/api/health" -TimeoutSec 3
    Write-Host "  ✅ Gun Relay (localhost:8765) 正常，peers: $($relayResp.peers)" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Gun Relay 離線 — 聊天室/LINE 通知失效" -ForegroundColor Red
}

# 3. Groq Relay (bot/groq-relay.js, port 3002)
try {
    $groqResp = Invoke-RestMethod "http://localhost:3002/groq/health" -TimeoutSec 3
    $groqStatus = if ($groqResp.api_reachable) { "✅" } else { "⚠️ " }
    Write-Host "  $groqStatus Groq Relay (localhost:3002) — model: $($groqResp.model), latency: $($groqResp.api_latency_ms)ms" -ForegroundColor $(if ($groqResp.api_reachable) { "Green" } else { "Yellow" })
} catch {
    Write-Host "  ⚠️  Groq Relay 離線 — Groq 路由全部降級為 Claude" -ForegroundColor Yellow
}
```

**效益**：三服務健康狀態從「靜默失效」變為「可觀測警告」。

---

### Batch C：research-registry 精簡（降低 Token 底數）

> ⚠️ behavior-patterns.json 0 個 prompt 讀取，已從本批次移除

**問題**：`context/research-registry.json`（84K）被 13 個 prompt 完整讀取（含 Phase 1 的 todoist-query.md），但每個 prompt 只需確認「此 topic 是否近 7 天研究過」。

**受影響的 13 個 prompt**：
1. `todoist-auto-jingtu.md`
2. `todoist-auto-shurangama.md`
3. `todoist-auto-fahua.md`
4. `todoist-auto-jiaoguangzong.md`
5. `todoist-auto-unsloth_research.md`
6. `todoist-auto-tech_research.md`
7. `todoist-auto-creative_game_optimize.md`
8. `todoist-auto-ai_sysdev.md`
9. `todoist-auto-ai_smart_city.md`
10. `todoist-auto-ai_github_research.md`
11. `todoist-auto-ai_deep_research.md`
12. `todoist-auto-ai_workflow_github.md`
13. `prompts/team/todoist-query.md`（Phase 1 路由）

#### C1：為 research-registry.json 加入頂層 topics_index

**修改**：[context/research-registry.json](../../context/research-registry.json)

新增頂層欄位（由研究任務完成後的寫入邏輯同步維護）：

```json
{
  "version": 2,
  "topics_index": {
    "AI模型蒸餾": "2026-03-14",
    "vLLM推理優化": "2026-03-12",
    "楞嚴經修學法要": "2026-03-11"
  },
  "entries": [...]
}
```

`topics_index` 欄位：key = topic（精確）、value = 最後研究日期（`YYYY-MM-DD`）。

#### C2：修改 13 個 prompt 的去重步驟

各 prompt 的「去重步驟」從：
```
用 Read 讀取 context/research-registry.json，列出近 7 天 entries
```
改為：
```
用 Read 讀取 context/research-registry.json，只讀取頂層 topics_index{} 欄位
比對本次 topic 是否在 7 天冷卻期內（比較日期差）
```

**注意**：研究任務完成寫入 registry 時，需同步更新 `topics_index`（在寫入 entries 的同一步驟中加入）。

**估計節省**：~24K tokens/次底數 × 13 prompt × 每日平均執行次數 ≈ **每日節省 50-150K tokens**。

**驗證 C**：
```bash
python -c "import json; d=json.load(open('context/research-registry.json')); print('topics_index' in d)"
# 預期：True
```

---

### Batch B：Groq 路由擴展

> ⚠️ 修訂：使用 curl POST localhost:3002/groq/chat（如 fetch-hackernews.md），非 llm_router.py CLI

#### B1：6 個自動任務整合 Groq 前處理

參考 `prompts/team/fetch-hackernews.md` 的已驗證 Groq 整合模式：

```bash
# Step 1：健康檢查（快速失敗）
GROQ_OK=$(curl -s --max-time 3 http://localhost:3002/groq/health | \
  python -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)

if [ "$GROQ_OK" = "ok" ]; then
    # Step 2：建立 Groq 請求 JSON（用 Write 工具，確保 UTF-8）
    # 寫入 temp/groq-req-{task_key}.json: {"mode":"classify","content":"..."}

    # Step 3：POST 至 Groq Relay
    curl -s --max-time 20 -X POST http://localhost:3002/groq/chat \
        -H "Content-Type: application/json; charset=utf-8" \
        -d @temp/groq-req-${TASK_KEY}.json \
        > temp/groq-result-${TASK_KEY}.json

    # Step 4：Claude 主任務讀取前處理結果
    # Read temp/groq-result-{task_key}.json → 直接使用，不重讀原始文字
fi
# Groq 不可用時：Claude 自行完成（無 fallback 邏輯改變）
```

| task_key | mode | 前處理目標 |
|---------|------|-----------|
| `log_audit` | `classify` | 日誌分類標籤 |
| `skill_audit` | `extract` | Skill 違規清單 |
| `qa_optimize` | `extract` | QA 模式清單 |
| `github_scout` | `summarize` | trending 一句摘要 |
| `ai_workflow_github` | `extract` | Workflow 模式萃取 |
| `skill_forge` | `extract` | Skill 組成分析 |

**修改檔案**（6 個）：`prompts/team/todoist-auto-{log_audit,skill_audit,qa_optimize,github_scout,ai_workflow_github,skill_forge}.md`

#### B2：診斷並修復 groq_calls 計數器

`update_token_usage("groq")` 在 `llm_router.py` L215 有呼叫，但 `groq_calls` 始終為 0。

**診斷步驟**（執行前先做）：
```bash
curl http://localhost:3002/groq/health
uv run python hooks/query_logs.py --grep "groq" --days 3
```

若 relay 常離線（降級 skip），在降級路徑補充：
```python
# tools/llm_router.py 降級路徑
update_token_usage("groq_skipped")  # 記錄降級次數
```

---

### Batch D：配置合併

> ✅ 已確認：timeouts.yaml 整合完整（L44-61）；validate_config.py --check-auto-tasks 存在

**修改**：
- [config/frequency-limits.yaml](../../config/frequency-limits.yaml)：各任務加 `timeout_seconds` 欄位（與 timeouts.yaml 對齊，作為人類可讀的單一真相來源）
- [config/timeouts.yaml](../../config/timeouts.yaml)：`phase2_timeout_by_task` 段落加 `# source of truth: frequency-limits.yaml timeout_seconds` 注解（暫不刪，向下相容）

---

### Batch F：Phase 3 結果檔命名統一

**問題**：`results/` 混用 `{task_key}-report.md`、`{task_key}-note.md`，Phase 3 需感知多格式。

**修改**：
- [config/frequency-limits.yaml](../../config/frequency-limits.yaml)：各任務加 `result_suffix` 欄位（`report`/`note`/`json`）
- [prompts/team/todoist-assemble.md](../../prompts/team/todoist-assemble.md)：組裝時依 `result_suffix` 查找對應結果檔

---

## 關鍵檔案索引

| 角色 | 檔案 |
|------|------|
| 五者關係文件 | [docs/project-overview-workflows-models-skills.md](../project-overview-workflows-models-skills.md) |
| 執行入口（A1/A2 主修） | [run-todoist-agent-team.ps1](../../run-todoist-agent-team.ps1) |
| cursor_cli 任務檔（A3 新建） | `temp/cursor-cli-task-fahua.md`、`temp/cursor-cli-task-podcast_create.md` |
| cursor_cli 範例格式 | [temp/cursor-cli-task-nebula-strike.md](../../temp/cursor-cli-task-nebula-strike.md) |
| Podcast 狀態（E1 新建） | [context/jiaoguang-podcast-next.json](../../context/jiaoguang-podcast-next.json) |
| Podcast 腳本（E4 確認） | [tools/run-jiaoguang-podcast-next.ps1](../../tools/run-jiaoguang-podcast-next.ps1) |
| Podcast prompt（E3 修改） | [prompts/team/jiaoguang-podcast-one-episode.md](../../prompts/team/jiaoguang-podcast-one-episode.md) |
| 健康檢查（G 主修） | [check-health.ps1](../../check-health.ps1) |
| 研究去重 registry（C1 主修） | [context/research-registry.json](../../context/research-registry.json) |
| 研究任務 prompts（C2，13 個） | `prompts/team/todoist-auto-{jingtu,shurangama,fahua,jiaoguangzong,unsloth_research,tech_research,creative_game_optimize,ai_sysdev,ai_smart_city,ai_github_research,ai_deep_research,ai_workflow_github}.md` + `prompts/team/todoist-query.md` |
| Groq 整合參考（B1 模式） | [prompts/team/fetch-hackernews.md](../../prompts/team/fetch-hackernews.md) |
| Groq 路由規則 | [config/llm-router.yaml](../../config/llm-router.yaml) |
| LLM Router（B2 診斷） | [tools/llm_router.py](../../tools/llm_router.py) |
| 自動任務定義（D/F 修改） | [config/frequency-limits.yaml](../../config/frequency-limits.yaml) |
| 超時設定（D 加注解） | [config/timeouts.yaml](../../config/timeouts.yaml) |
| Phase 3 組裝（F 修改） | [prompts/team/todoist-assemble.md](../../prompts/team/todoist-assemble.md) |
| KB API 專案 | `D:\Source\RAG_Skill`（localhost:3000） |
| Gun Relay 專案 | `D:\Source\my-gun-relay`（localhost:8765） |
| Groq Relay 程式 | [bot/groq-relay.js](../../bot/groq-relay.js)（localhost:3002） |
| Podcast 全輯規劃 | [docs/plans/淨土教觀學苑podcast專輯.md](淨土教觀學苑podcast專輯.md) |

---

## 驗證步驟

```powershell
# Batch G：三服務健康狀態
curl http://localhost:3000/api/health   # RAG_Skill KB API
curl http://localhost:8765/api/health   # Gun Relay
curl http://localhost:3002/groq/health  # Groq Relay

# Batch A：cursor_cli 後端
pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1
# ✓ results/todoist-auto-fahua.json 存在且 backend: cursor_cli

# Batch E：Podcast 執行鏈
pwsh tools/run-jiaoguang-podcast-next.ps1
# ✓ context/jiaoguang-podcast-next.json next_episode 從 1 → 2
# ✓ temp/jiaoguang-course-cache-*.json 存在

# Batch C：registry 精簡
uv run python -c "import json; d=json.load(open('context/research-registry.json')); print('topics_index' in d)"
# ✓ True

# Batch B：Groq 路由驗證
curl -s --max-time 3 http://localhost:3002/groq/health | python -c "import sys,json; print(json.load(sys.stdin)['status'])"
# 執行任意含 Groq 的 prompt 後，確認 token-usage.json 的 groq_calls > 0

# Batch D：配置一致性
uv run python hooks/validate_config.py --check-auto-tasks
# ✓ 無 MISMATCH 警告

# 回歸測試
uv run pytest tests/ -x --timeout=120
# ✓ 856 個測試全部通過
```

---

## 執行順序

```
第 1 週（第 1 天）
  ├── Batch G：三服務健康預檢加入 check-health.ps1         ~1h
  ├── Batch E1/E2：建立 jiaoguang-podcast-next.json        ~30min
  └── Batch A1/A2：Start-CursorCliJob + Phase 2 迴圈       ~3h

第 1 週（第 2-3 天）
  ├── Batch A3：建立 cursor_cli 任務檔（fahua/podcast）    ~2h
  └── Batch E3：Podcast 課程快取（jiaoguang prompt 修改）  ~1h

第 2 週
  ├── Batch C1：registry topics_index 欄位                  ~1h
  └── Batch C2：13 個 prompt 去重步驟修改                  ~3h

第 3 週
  ├── Batch B1：6 個自動任務 Groq 前處理整合               ~4h
  ├── Batch B2：診斷 groq_calls 計數斷鏈                   ~1h
  ├── Batch D：配置合併（freq-limits timeout_seconds）     ~1h
  └── Batch F：結果檔命名統一                              ~1h
```

---

## Token 節省預估（全計畫）

| 批次 | 節省來源 | 估計節省 |
|------|---------|---------|
| C（registry 精簡） | ~24K tokens/次 × 13 prompt × 每日執行率 | ~50-150K tokens/日 |
| E（Podcast 課程快取） | 750 集 × 34/35 課程複用 | ~510K tokens（全輯） |
| B（Groq 路由） | ~2K tokens/任務 × 6 任務 × 0.8 執行率 | ~9.6K tokens/日 |
| A（cursor_cli 對齊） | fahua/podcast_create 從 Claude 轉 cursor_cli | 依任務複雜度 |

**7 日均值基準**：9.6M tokens/日；預計優化後可降至 **8M-8.5M tokens/日**（~12-17% 降幅）。
