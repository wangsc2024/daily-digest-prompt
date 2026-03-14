# ============================================================
# Gun.js 孤島加密排程機器人 - 本地端自動化腳本
# ============================================================
# 遵循 learn-claude-code s11: "Poll, claim, work, repeat"
# Worker 主動認領任務，支援多 Worker 安全並行。
#
# 一般任務：使用 Cursor CLI (agent -p) + cursor-composer-1-5 執行；用法依 skills/cursor-cli/SKILL.md。
# 研究型任務：使用 Codex (codex exec --full-auto -m gpt-5.4) 以研究工作流執行；前置 kb-research-strategist 與主任務皆由 Codex 執行；完成後 research-series 更新仍用 claude -p。
# 前置需求：agent（Cursor CLI）、codex（研究型）、claude CLI（研究後置）已安裝並完成認證。
#
# 流程：poll → claim → work → complete
#
# 安全修正：
# - API 回應結構驗證
# - claim_generation 追蹤，防止逾時後重複完成
# - 錯誤時標記為 failed，不靜默忽略
# ============================================================
$ApiBaseUrl = "http://127.0.0.1:3001"
$TempDir = $PWD
$WorkerId = "$env:COMPUTERNAME-$PID"

# ── 知識庫根目錄（集中定義，避免在 workflows.json 硬編碼路徑）
# workflows.json 使用 {KB_DIR} 佔位符，task content 在執行前自動展開
$KbDir = "$PSScriptRoot\..\knowledge_base"
$KbDir = [System.IO.Path]::GetFullPath($KbDir)  # 展開為絕對路徑

# 編碼任務關鍵字（符合其中一個即視為編碼任務）
$CodingKeywords = @(
    '程式', '程式碼', '寫程式', '修程式', '實作', '重構', '除錯', 'debug',
    'code', 'coding', 'script', 'function', 'class', 'implement', 'refactor',
    'python', 'javascript', 'typescript', 'powershell', 'bash', 'nodejs', 'node',
    'npm', 'pip', 'git', 'api', 'sql', 'html', 'css', 'react', 'vue', 'angular',
    '單元測試', 'unit test', 'test', 'pytest', 'jest', 'vitest',
    '爬蟲', 'scraper', 'automation', '自動化'
)

function Test-IsCodingTask {
    param([string]$Content)
    $lower = $Content.ToLower()
    foreach ($kw in $CodingKeywords) {
        if ($lower.Contains($kw.ToLower())) { return $true }
    }
    return $false
}

# A4: 日誌設定
$LogDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir ("task_log_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$WorkerId] $Message"
    Write-Host $logEntry
    Add-Content -Path $LogFile -Value $logEntry -Encoding UTF8
}

$CompletionLogFile = Join-Path $LogDir "completion_log.jsonl"
$ProjectRoot = "D:\Source\daily-digest-prompt"

# ── Skill-First + Cursor CLI 前言（一般任務由 agent -p 執行，依 skills/cursor-cli/SKILL.md）──
$SkillFirstPreamble = @"
## Cursor CLI 與 Skill-First 指引

本任務由 **Cursor CLI (agent -p)** 執行，請依 **skills/cursor-cli/SKILL.md** 之規則：
- 先讀 **skills/SKILL_INDEX.md**，積極採用與任務相關的 Skill（knowledge-query、ntfy-notify、api-cache 等）。
- 外部功能與 Skill 調用**必須先在 CLI 內實際執行**，僅當執行失敗時才在輸出中註明 fallback 與手動做法。

在執行任何步驟前，請先讀取對應 SKILL.md；禁止自行拼湊已有 Skill 覆蓋的邏輯。專案規則（CLAUDE.md、.cursor/rules/）會由 Cursor CLI 自動載入。
"@

# ── 查詢近期任務記憶（提供上下文，避免重複執行）──
function Get-BotMemoryContext {
    try {
        $memResp = Invoke-RestMethod -Uri "$ApiBaseUrl/api/memory/recent?limit=3" `
            -Method Get -Headers $DlHeaders -TimeoutSec 5
        if ($memResp.recent_tasks -and $memResp.recent_tasks.Count -gt 0) {
            $lines = @("## 近期完成任務（供參考，避免重複執行相同工作）")
            foreach ($t in $memResp.recent_tasks) {
                $date = $t.ts.Substring(0, 10)
                $lines += "- [$date] $($t.task_preview)"
            }
            return ($lines -join "`n") + "`n"
        }
    } catch {}
    return ""
}

# ── 品質要求後綴（依任務類型，強制結構化輸出）──
function Get-QualityRequirements {
    param([string]$TaskContent, [bool]$IsCoding, [bool]$IsResearch)
    $lower = $TaskContent.ToLower()
    $isPlan     = $lower -match '規劃|計畫|方案|策略|架構|設計'
    $isOptimize = $lower -match '優化|改善|提升|重構|改進'
    $common = "`n`n---`n## 輸出品質要求（必須遵守）`n執行完畢後，**必須**以下列格式提供結構化摘要：`n`n✅ **執行摘要**：（2-3 句話說明完成了什麼）"
    if ($IsResearch) {
        return $common + "`n📚 **主要發現**：（列出 3-5 個關鍵洞察）`n💾 **知識庫**：（是否已存入知識庫，使用何關鍵字）`n🔗 **延伸方向**：（建議後續研究方向）"
    } elseif ($IsCoding) {
        return $common + "`n📁 **已修改/建立的檔案**：（列出所有異動檔案）`n🧪 **測試結果**：（測試通過情況）`n⚠️ **注意事項**：（使用限制或後續動作）"
    } elseif ($isPlan) {
        return $common + "`n📋 **具體行動步驟**：（有序列出 3-7 個步驟）`n✔️ **可驗收標準**：（如何確認計畫成功執行）"
    } elseif ($isOptimize) {
        return $common + "`n📊 **改善成果**：（量化說明改善幅度）`n🎯 **可驗證成果**：（已完成的具體成果）`n🔄 **後續建議**：（維持或進一步優化的方向）"
    } else {
        return $common + "`n📌 **重要結論**：（最重要的 2-3 個結論）`n🚀 **後續行動**：（建議的後續步驟）"
    }
}

function Write-CompletionLog {
    param(
        [string]$Uid,
        [string]$Filename,
        [string]$Event,          # started | completed | failed
        [int]$DurationSec = -1,
        [int]$OutputLen = -1,
        [string]$ErrorMsg = ""
    )
    $entry = [ordered]@{
        ts           = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
        uid          = $Uid
        worker_id    = $WorkerId
        event        = $Event
        filename     = $Filename
    }
    if ($DurationSec -ge 0) { $entry["duration_sec"] = $DurationSec }
    if ($OutputLen -ge 0)   { $entry["output_len"]   = $OutputLen }
    if ($ErrorMsg)           { $entry["error"]        = $ErrorMsg }
    $json = $entry | ConvertTo-Json -Compress
    Add-Content -Path $CompletionLogFile -Value $json -Encoding UTF8
}

# 嘗試從 .env 讀取設定 (本地部署便利性)
$DotEnvPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $DotEnvPath) {
    Get-Content $DotEnvPath | ForEach-Object {
        if ($_ -match "^\s*API_SECRET_KEY\s*=\s*(.*)") {
            $val = $matches[1].Trim()
            if (-not [string]::IsNullOrWhiteSpace($val)) {
                $env:API_SECRET_KEY = $val
            }
        }
    }
}

# API 認證標頭
$ApiSecretKey = $env:API_SECRET_KEY
$JsonHeaders = @{ "Content-Type" = "application/json; charset=utf-8" }
if (-not [string]::IsNullOrWhiteSpace($ApiSecretKey)) {
    $JsonHeaders["Authorization"] = "Bearer $ApiSecretKey"
}

# 下載用標頭（不含 Content-Type）
$DlHeaders = @{}
if (-not [string]::IsNullOrWhiteSpace($ApiSecretKey)) {
    $DlHeaders["Authorization"] = "Bearer $ApiSecretKey"
}

Write-Log "Worker 啟動，開始尋找未處理的任務..."

# ---- Step 1: Poll — 查詢 pending 狀態的任務 ----
try {
    $response = Invoke-RestMethod -Uri "$ApiBaseUrl/api/records?state=pending" -Method Get -Headers $DlHeaders
} catch {
    Write-Log "無法連接到 API 伺服器: $_"
    exit
}

# 驗證回應結構
if ($null -eq $response -or $null -eq $response.records) {
    Write-Log "API 回應格式異常，中止執行"
    exit
}

$records = $response.records

# ---- SLA Check: 告警卡住的任務 ----
try {
    $allResp = Invoke-RestMethod -Uri "$ApiBaseUrl/api/records" -Method Get -Headers $DlHeaders -TimeoutSec 5
    $now = Get-Date
    $ic = [System.Globalization.CultureInfo]::InvariantCulture
    $slaWarns = @()
    foreach ($t in $allResp.records) {
        $shortId = if ($t.uid.Length -ge 8) { $t.uid.Substring(0,8) } else { $t.uid }
        if ($t.state -eq "pending") {
            try {
                $age = [int]($now - [datetime]::Parse($t.time, $ic)).TotalMinutes
                if ($age -gt 10) { $slaWarns += "⏳pending[$shortId] ${age}m" }
            } catch {}
        } elseif ($t.state -in @("claimed","processing")) {
            try {
                $refStr = if ($t.claimed_at) { $t.claimed_at } else { $t.time }
                $age = [int]($now - [datetime]::Parse($refStr, $ic)).TotalMinutes
                if ($age -gt 35) { $slaWarns += "⚠️$($t.state)[$shortId] ${age}m" }
            } catch {}
        }
    }
    if ($slaWarns.Count -gt 0) {
        Write-Log "[SLA 告警] $($slaWarns -join ' | ')"
    }
} catch { Write-Log "[SLA] 無法查詢: $_" }

if ($records.Count -eq 0) {
    Write-Log "目前沒有新任務需要處理。"
    exit
}

# 每次只處理 1 筆：讓 scheduler 的 timeout 是 per-task 而非 per-batch，
# 避免研究型任務（11-17 min）累計超時導致整批被殺。
$record = $records[0]
Write-Log "找到 $($records.Count) 個待處理任務，本輪處理第 1 筆"

foreach ($record in @($record)) {
    $uid = $record.uid
    $filename = $record.filename
    $isResearch = $record.is_research
    $taskType = $record.task_type   # general | code | podcast | detail；舊記錄可能為空

    if ([string]::IsNullOrWhiteSpace($filename)) { continue }

    Write-Log "=========================================="
    Write-Log "正在處理任務 UID [$uid]，檔名: $filename"

    # ---- Step 2: Claim — 原子性認領任務 ----
    $claimGeneration = $null
    try {
        $claimBody = @{ worker_id = $WorkerId } | ConvertTo-Json
        $claimResp = Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/claim" -Method Patch -Body $claimBody -Headers $JsonHeaders
        $claimGeneration = $claimResp.claim_generation
        Write-Log "已認領任務 (worker: $WorkerId, generation: $claimGeneration)"
        $TaskStartTime = Get-Date
    } catch {
        $statusCode = $null
        try { $statusCode = $_.Exception.Response.StatusCode.value__ } catch {}
        if ($statusCode -eq 409) {
            Write-Log "任務已被其他 Worker 認領，跳過"
        } else {
            Write-Log "認領失敗 (HTTP $statusCode): $_"
        }
        continue
    }

    # ---- Step 3: Work — 轉換為 processing 並執行 ----
    try {
        $stateBody = @{ state = "processing"; worker_id = $WorkerId } | ConvertTo-Json
        Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/state" -Method Patch -Body $stateBody -Headers $JsonHeaders | Out-Null
    } catch {
        Write-Log "狀態轉換為 processing 失敗: $_"
    }

    $localFilePath = Join-Path $TempDir $filename

    try {
        # 下載 MD 檔案
        Invoke-WebRequest -Uri "$ApiBaseUrl/api/files/$filename" -OutFile $localFilePath -Headers $DlHeaders
        Write-Log "檔案下載成功。"

        # 讀取任務內容，判斷是否為編碼任務
        $taskContent = [string](Get-Content $localFilePath -Raw -Encoding UTF8)

        # ── 任務強化：保留原始意圖，補充技術細節，絕不簡化或刪減需求 ──
        $optimizedContent = $taskContent
        try {
            $optimizePayload = @{ task_content = $taskContent } | ConvertTo-Json -Depth 3 -Compress
            $optimizeResp = Invoke-RestMethod -Uri "$ApiBaseUrl/api/tasks/optimize" `
                -Method Post -Body $optimizePayload -Headers $JsonHeaders -TimeoutSec 60
            if ($optimizeResp.success -and -not [string]::IsNullOrWhiteSpace($optimizeResp.optimized)) {
                $optimizedContent = $optimizeResp.optimized
                Write-Log "任務強化完成（原始 $($taskContent.Length) 字 → 強化後 $($optimizedContent.Length) 字）"
            } else {
                Write-Log "任務強化回傳異常，使用原始任務內容"
            }
        } catch {
            Write-Log "任務強化呼叫失敗（將使用原始任務）: $_"
        }

        # ── 擷取 optimize 回應的研究關鍵詞，更新 is_research 判定 ──
        $researchKeywords = @()
        if ($optimizeResp -and $optimizeResp.research_keywords) {
            $researchKeywords = @($optimizeResp.research_keywords)
        }
        if ($optimizeResp -and $optimizeResp.is_research -eq $true) {
            $isResearch = $true
        }

        # ── 研究型一律採研究工作流：KB 深化預處理 + 系列上下文；完成後結果存知識庫（由 bot routes 完成時觸發）──
        $CodexAvailable = Get-Command codex -ErrorAction SilentlyContinue
        $kbBriefPath = Join-Path $ProjectRoot "context\kb-research-brief.json"
        if ($isResearch -and $researchKeywords.Count -gt 0) {
            $keywords = ($researchKeywords -join ", ")
            Write-Log "研究型任務：KB 深化需求（關鍵詞：$keywords），以 Codex 執行 kb-research-strategist..."
            $krsPrompt = "請以正體中文輸出。讀取 skills/kb-research-strategist/SKILL.md，以「$keywords」為研究主題執行完整步驟（步驟 0-5），結果輸出至 context/kb-research-brief.json。"
            if ($CodexAvailable) {
                $krsPrompt | & codex exec --full-auto -m gpt-5.4 2>&1 | Out-Null
                Write-Log "kb-research-strategist（Codex）執行完畢"
            } else {
                $savedClaudeCodeKRS = $env:CLAUDECODE
                Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue
                try {
                    & claude -p $krsPrompt --allowedTools "Read,Bash,Write" --max-turns 15 2>&1 | Out-Null
                } finally {
                    if ($null -ne $savedClaudeCodeKRS) { $env:CLAUDECODE = $savedClaudeCodeKRS }
                }
                Write-Log "kb-research-strategist（claude -p fallback）執行完畢"
            }
        }

        $isCoding = Test-IsCodingTask -Content $optimizedContent

        # ── 展開 {KB_DIR} 佔位符（避免 workflows.json 硬編碼絕對路徑）──
        $taskContent = $taskContent -replace '\{KB_DIR\}', $KbDir
        $optimizedContent = $optimizedContent -replace '\{KB_DIR\}', $KbDir

        # ── 偵測 [WORKDIR: path] 標記或訊息中的 Windows 路徑（優先從原始內容偵測，確保意圖不失真）──
        $workDir = $null
        if ($taskContent -match '\[WORKDIR:\s*([A-Za-z]:[^\]]+)\]') {
            $workDir = $matches[1].Trim()
            Write-Log "偵測到 WORKDIR 標記: $workDir"
        } elseif ($taskContent -match '(?:儲存|建立|實作|放在|位於|目錄|dir|directory)[^\n]*?([A-Za-z]:\\[^\s\n,，。、\]]+)') {
            $workDir = $matches[1].Trim().TrimEnd('\', '/', '.', ',', '，')
            Write-Log "從任務內容偵測到目標路徑: $workDir"
        }

        # 若有目標目錄，確保其存在
        if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
            if (-not (Test-Path $workDir)) {
                New-Item -ItemType Directory -Path $workDir -Force | Out-Null
                Write-Log "已建立目標目錄: $workDir"
            }
        }

        # ── 取得記憶上下文（查詢最近 3 筆完成任務）──
        $memoryContext = Get-BotMemoryContext

        # ── 品質要求（依任務類型）──
        $qualityReqs = Get-QualityRequirements -TaskContent $taskContent -IsCoding $isCoding -IsResearch ([bool]$isResearch)

        # ── 注入 KB 系列研究上下文（若有 kb-research-brief.json）──
        $kbSeriesContext = ""
        if ($isResearch -and (Test-Path $kbBriefPath)) {
            try {
                $brief = Get-Content $kbBriefPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($brief.recommendation -eq "deepen" -or $brief.recommendation -eq "series_continue") {
                    $seriesId = if ($brief.series -and $brief.series.series_id) { $brief.series.series_id } else { "（新系列）" }
                    $currentStage = if ($brief.series -and $brief.series.current_stage) { $brief.series.current_stage } else { "" }
                    $synthesis = if ($brief.kb_foundation -and $brief.kb_foundation.synthesis) { $brief.kb_foundation.synthesis } else { "" }
                    $primaryQ = if ($brief.research_plan -and $brief.research_plan.primary_question) { $brief.research_plan.primary_question } else { "" }
                    $kbSeriesContext = "`n`n## [KB 研究策略簡報]`n系列：$seriesId（當前階段：$currentStage）`n現有知識：$synthesis`n本次研究問題：$primaryQ`n"
                    Write-Log "已注入 KB 系列上下文（$seriesId/$currentStage）"
                }
            } catch {
                Write-Log "讀取 kb-research-brief.json 失敗，略過系列上下文注入: $_"
            }
        }

        # ── 組合最終任務內容：Skill-First + 記憶 + 工作目錄 + 任務本文 + KB上下文 + 品質要求 ──
        $workDirPrefix = ""
        if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
            $workDirPrefix = "請在目錄 $workDir 中執行以下任務。若目錄不存在請先建立。所有產出的檔案必須儲存在 $workDir 目錄中。`n`n"
        }
        # ── 從知識庫中回答型（kb_answer）：注入 RAG 流程，先依 knowledge-query Skill 蒐集資料再由 LLM 回答 ──
        if ($taskType -eq 'kb_answer') {
            $kbSkillPath = Join-Path $ProjectRoot "skills\knowledge-query\SKILL.md"
            $ragPreamble = @"
## 任務類型：從知識庫中回答（RAG）

請依下列步驟執行：
1. 讀取 Skill：$kbSkillPath
2. 依 Skill 的查詢步驟，以**使用者問題**為 query 呼叫知識庫混合搜尋（POST /api/search/hybrid），取得相關筆記。
3. **僅根據檢索到的筆記內容**回答下列問題；若知識庫無相關筆記或服務未啟動，請如實說明。

使用者問題：
"@
            $optimizedContent = $ragPreamble + "`n`n" + $optimizedContent
            Write-Log "從知識庫回答型：已注入 RAG 前置（knowledge-query → 檢索 → LLM 回答）"
        }

        $memorySection = if ($memoryContext) { $memoryContext + "`n" } else { "" }
        $researchWorkflowPreamble = ""
        if ($isResearch) {
            $researchWorkflowPreamble = "`n`n## 研究工作流（本任務依研究工作流執行）`n請善用 WebSearch/WebFetch、知識庫查詢與匯入（skills/knowledge-query、skills/web-research），產出結構化報告或寫入 context/；必要時將研究成果匯入知識庫。`n"
        }
        $codeTaskPreamble = ""
        if ($isCoding) {
            $codeTaskPreamble = "`n`n## 編碼型任務（依 cursor-cli skill 執行）`n本任務為 CODE 型任務，請依 **skills/cursor-cli/SKILL.md** 執行：先讀 skills/SKILL_INDEX.md、積極採用與程式/重構/除錯相關的 Skill，所有修改與產出須在指定工作目錄內完成。`n"
        }
        $effectiveContent = $SkillFirstPreamble + "`n`n" + $memorySection + $workDirPrefix + $optimizedContent + $researchWorkflowPreamble + $codeTaskPreamble + $kbSeriesContext + $qualityReqs

        # ── Podcast 型一律採 podcast 工作流（article-to-podcast.ps1 → TTS→MP3→上傳 R2）──
        $podcastHandled = $false
        $podcastQuery = ""
        $podcastCount = 1
        if ($taskType -eq 'podcast') {
            $podcastHandled = $true
            # 若內容未匹配下方 regex，以任務本文前段作為查詢主題；完全無內容時用預設
            $fallbackQuery = ($taskContent -split "`n")[0].Trim()
            if ([string]::IsNullOrWhiteSpace($fallbackQuery)) { $fallbackQuery = $taskContent.Trim() }
            if ($fallbackQuery.Length -gt 200) { $fallbackQuery = $fallbackQuery.Substring(0, 200) }
            if ([string]::IsNullOrWhiteSpace($fallbackQuery)) { $fallbackQuery = "未指定主題" }
            $podcastQuery = $fallbackQuery
        }
        # 匹配格式：「製作N則X podcast/播客」或「X podcast/播客」（不分大小寫）
        if ($taskContent -match '製作\s*(\d+)\s*則?\s*(.+?)\s*[Pp]odcast|製作\s*(\d+)\s*則?\s*(.+?)\s*播客') {
            $podcastCount = [int]$(if ($matches[1]) { $matches[1] } else { $matches[3] })
            $podcastQuery = $(if ($matches[2]) { $matches[2] } else { $matches[4] }).Trim()
            $podcastHandled = $true
        } elseif ($taskContent -match '製作\s*(.+?)\s*[Pp]odcast|製作\s*(.+?)\s*播客') {
            $podcastQuery = $(if ($matches[1]) { $matches[1] } else { $matches[2] }).Trim()
            $podcastHandled = $true
        }

        if ($podcastHandled -and -not [string]::IsNullOrWhiteSpace($podcastQuery)) {
            Write-Log "🎙️ 偵測到 Podcast 製作任務（主題：$podcastQuery，集數：$podcastCount）"
            Write-Log "直接呼叫 article-to-podcast.ps1（略過 claude -p 自由詮釋）"
            Write-CompletionLog -Uid $uid -Filename $filename -Event "started"
            $ClaudeStartTime = Get-Date
            $podcastOutputParts = @()
            $podcastScript = Join-Path $ProjectRoot "tools\article-to-podcast.ps1"

            $savedClaudeCode = $env:CLAUDECODE
            Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue
            try {
                for ($epIdx = 1; $epIdx -le $podcastCount; $epIdx++) {
                    Write-Log "--- 第 ${epIdx}/${podcastCount} 集：Query=$podcastQuery ---"
                    $epOutput = pwsh -ExecutionPolicy Bypass -File $podcastScript -Query $podcastQuery 2>&1
                    $podcastOutputParts += "=== 第 ${epIdx}/${podcastCount} 集（$podcastQuery）==="
                    $podcastOutputParts += ($epOutput -join "`n")
                }
            } finally {
                if ($null -ne $savedClaudeCode) { $env:CLAUDECODE = $savedClaudeCode }
                else { Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue }
            }
            $output = $podcastOutputParts -join "`n`n"
        } else {

        Write-CompletionLog -Uid $uid -Filename $filename -Event "started"
        $AgentStartTime = Get-Date
        $toolUsed = "Cursor CLI (cursor-composer-1-5)"
        if ($isResearch -and $CodexAvailable) {
            # 研究型任務：以 Codex 研究工作流執行（codex exec --full-auto -m gpt-5.4，依 config/frequency-limits codex_exec）
            Write-Log "--> Worker 使用 Codex 研究工作流 (codex exec --full-auto -m gpt-5.4) 處理研究型任務 (關鍵詞: $($researchKeywords -join ', '), 工作目錄: $(if($workDir){$workDir}else{'預設'}), 記憶注入: $(if($memoryContext){'是'}else{'否'}))..."
            try {
                $codexPrompt = "請以正體中文輸出。`n`n" + $effectiveContent
                $codexPromptFile = Join-Path $LogDir "codex-prompt-$uid-$(Get-Date -Format 'yyyyMMddHHmmss').txt"
                Set-Content -Path $codexPromptFile -Value $codexPrompt -Encoding UTF8 -NoNewline
                try {
                    if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
                        Push-Location $workDir
                        try {
                            $output = Get-Content -Path $codexPromptFile -Raw -Encoding UTF8 | & codex exec --full-auto -m gpt-5.4 2>&1
                        } finally {
                            Pop-Location
                        }
                    } else {
                        $output = Get-Content -Path $codexPromptFile -Raw -Encoding UTF8 | & codex exec --full-auto -m gpt-5.4 2>&1
                    }
                } finally {
                    Remove-Item $codexPromptFile -Force -ErrorAction SilentlyContinue
                }
                $toolUsed = "Codex (gpt-5.4, 研究工作流)"
            } catch {
                Write-Log "[WARN] Codex 執行失敗，fallback 至 Cursor CLI: $_"
                $toolUsed = "Cursor CLI (cursor-composer-1-5, Codex fallback)"
                if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
                    Push-Location $workDir
                    try {
                        $output = & agent -p $effectiveContent --workspace $ProjectRoot --model cursor-composer-1-5 --trust 2>&1
                    } finally {
                        Pop-Location
                    }
                } else {
                    $output = & agent -p $effectiveContent --workspace $ProjectRoot --model cursor-composer-1-5 --trust 2>&1
                }
            }
        } else {
            # CODE 型任務或一般任務：皆依 skills/cursor-cli/SKILL.md，排程內 agent -p 須 --workspace 與 --trust
            if ($isCoding) {
                Write-Log "--> Worker 使用 Cursor CLI (cursor-cli skill, agent -p, cursor-composer-1-5) 處理 CODE 型任務 (工作目錄: $(if($workDir){$workDir}else{'預設'}), 記憶注入: $(if($memoryContext){'是'}else{'否'}))..."
            } else {
                Write-Log "--> Worker 使用 Cursor CLI (agent -p, cursor-composer-1-5) 處理一般任務 (從知識庫回答: $(if($taskType -eq 'kb_answer'){'是'}else{'否'}), 工作目錄: $(if($workDir){$workDir}else{'預設'}), 記憶注入: $(if($memoryContext){'是'}else{'否'}))..."
            }
            try {
                if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
                    Push-Location $workDir
                    try {
                        $output = & agent -p $effectiveContent --workspace $ProjectRoot --model cursor-composer-1-5 --trust 2>&1
                    } finally {
                        Pop-Location
                    }
                } else {
                    $output = & agent -p $effectiveContent --workspace $ProjectRoot --model cursor-composer-1-5 --trust 2>&1
                }
                if ($isCoding) { $toolUsed = "Cursor CLI (cursor-cli skill, cursor-composer-1-5)" }
            } catch {
                throw
            }
        }

        } # end podcast else
        $agentDurationSec = [int]((Get-Date) - $AgentStartTime).TotalSeconds
        $outputStr = if ($output -is [array]) { $output -join "`n" } else { [string]$output }
        Write-Log "任務執行完畢 (使用: $toolUsed，耗時: ${agentDurationSec}s，輸出: $($outputStr.Length) 字元)"
        Write-CompletionLog -Uid $uid -Filename $filename -Event "completed" `
            -DurationSec $agentDurationSec -OutputLen $outputStr.Length

        # ---- Step 4: Complete — 標記為已完成（帶 claim_generation、result 供工作流下游使用）----
        # 注意：結果回傳至聊天室由 bot server 的 /processed 端點透過穩定 Gun 連線負責，
        # 避免 Worker 自行呼叫 /api/send 時因 Gun relay 閒置斷線導致訊息遺失。
        $completeBody = @{ claim_generation = $claimGeneration; result = $outputStr } | ConvertTo-Json -Depth 3
        Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/processed" -Method Patch -Body $completeBody -ContentType "application/json; charset=utf-8" -Headers $JsonHeaders | Out-Null
        Write-Log "狀態已更新為 completed (generation: $claimGeneration)。已請 bot server 透過 Gun 回傳結果至聊天室。"

        # ── 更新 research-series.json（研究任務完成後）──
        if ($isResearch -and (Test-Path $kbBriefPath)) {
            try {
                $brief = Get-Content $kbBriefPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($brief.series_update -and $brief.series_update.series_id) {
                    $su = $brief.series_update
                    # 委派給 kb-depth-check.md Phase C Python 腳本（涵蓋 completion_pct + current_stage 推進邏輯）
                    $updatePrompt = "讀取 templates/shared/kb-depth-check.md，執行其中 Phase C（研究完成後更新系列狀態）的 Bash 指令（Python 腳本）。若 context/research-series.json 不存在，先用 Write 建立空結構 ``{""version"":1,""updated_at"":""$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')"",""series"":{}}``。"
                    $savedClaudeCodeSU = $env:CLAUDECODE
                    Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue
                    try {
                        & claude -p $updatePrompt --allowedTools "Read,Bash,Write" --max-turns 5 2>&1 | Out-Null
                    } finally {
                        if ($null -ne $savedClaudeCodeSU) { $env:CLAUDECODE = $savedClaudeCodeSU }
                    }
                    Write-Log "research-series.json 已更新（$($su.series_id)/$($su.stage_to_update) → $($su.new_status)）"
                }
            } catch {
                Write-Log "更新 research-series.json 失敗: $_"
            }
            Remove-Item $kbBriefPath -ErrorAction SilentlyContinue
            Write-Log "kb-research-brief.json 已清理"
        }

    } catch {
        $errMsg = "$_"
        Write-Log "處理發生錯誤: $errMsg"
        $failDurationSec = if ($null -ne $TaskStartTime) { [int]((Get-Date) - $TaskStartTime).TotalSeconds } else { -1 }
        Write-CompletionLog -Uid $uid -Filename $filename -Event "failed" `
            -DurationSec $failDurationSec -ErrorMsg $errMsg

        # 呼叫 /fail 端點（含自動重試 / Dead Letter Queue 邏輯）
        try {
            $failBody = @{ worker_id = $WorkerId; error = $errMsg.Substring(0, [Math]::Min($errMsg.Length, 300)) } | ConvertTo-Json
            $failResp = Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/fail" -Method Post -Body $failBody -Headers $JsonHeaders
            if ($failResp.status -eq "dead_letter") {
                Write-Log "任務已移入 Dead Letter Queue（重試 $($failResp.retry_count) 次後放棄）"
            } else {
                Write-Log "任務已重回佇列（第 $($failResp.retry_count) 次重試）"
            }
        } catch {
            Write-Log "呼叫 /fail 失敗，改用舊方式: $_"
            try {
                $oldFailBody = @{ state = "failed"; worker_id = $WorkerId } | ConvertTo-Json
                Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/state" -Method Patch -Body $oldFailBody -Headers $JsonHeaders | Out-Null
            } catch {}
        }
    } finally {
        if (Test-Path $localFilePath) {
            Remove-Item $localFilePath -Force
        }
    }
}
Write-Log "=========================================="
Write-Log "本次排程處理完畢"
