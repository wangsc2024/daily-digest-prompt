# ============================================================
# Gun.js 孤島加密排程機器人 - 本地端自動化腳本（claude -p 方案）
# ============================================================
# 遵循 learn-claude-code s11: "Poll, claim, work, repeat"
# Worker 主動認領任務，支援多 Worker 安全並行。
#
# 使用 claude -p 執行任務，直接呼叫本機已設定的 Claude Code CLI。
# 前置需求：claude CLI 已安裝並完成認證（claude /login）。
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

# ── Skill-First 前言（所有任務都注入，讓 Agent 主動使用 Skill）──
$SkillFirstPreamble = @"
## Skill-First 指引（最高優先原則）

在執行任何任務前，請先讀取以下 Skill 索引，了解所有可用技能：
路徑：$ProjectRoot\skills\SKILL_INDEX.md

**強制規則**：
1. 能用 Skill 就用 Skill，禁止自行拼湊已有 Skill 覆蓋的邏輯
2. 每個步驟必須先讀取對應 SKILL.md 再動手
3. 積極串聯多個 Skill 實現更高價值（如：新聞 → 政策解讀 → 知識庫匯入 → 通知）
4. 可用工具（--allowedTools）：Read、Bash、Write
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

        # ── KB 深化預處理（研究任務：執行 kb-research-strategist + 注入系列上下文）──
        $kbBriefPath = Join-Path $ProjectRoot "context\kb-research-brief.json"
        if ($isResearch -and $researchKeywords.Count -gt 0) {
            $keywords = ($researchKeywords -join ", ")
            Write-Log "研究任務偵測到 KB 深化需求（關鍵詞：$keywords），執行 kb-research-strategist..."
            $krsPrompt = "讀取 skills/kb-research-strategist/SKILL.md，以「$keywords」為研究主題執行完整步驟（步驟 0-5），結果輸出至 context/kb-research-brief.json。"
            $savedClaudeCodeKRS = $env:CLAUDECODE
            Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue
            try {
                & claude -p $krsPrompt --allowedTools "Read,Bash,Write" --max-turns 15 2>&1 | Out-Null
            } finally {
                if ($null -ne $savedClaudeCodeKRS) { $env:CLAUDECODE = $savedClaudeCodeKRS }
            }
            Write-Log "kb-research-strategist 執行完畢"
        }

        $isCoding = Test-IsCodingTask -Content $optimizedContent

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
        $memorySection = if ($memoryContext) { $memoryContext + "`n" } else { "" }
        $effectiveContent = $SkillFirstPreamble + "`n`n" + $memorySection + $workDirPrefix + $optimizedContent + $kbSeriesContext + $qualityReqs

        Write-Log "--> Worker 使用 claude -p 處理任務 (研究型: $isResearch, 編碼型: $isCoding, 工作目錄: $(if($workDir){$workDir}else{'預設'}), 記憶注入: $(if($memoryContext){'是'}else{'否'}))..."
        Write-CompletionLog -Uid $uid -Filename $filename -Event "started"
        $ClaudeStartTime = Get-Date
        # 清除 CLAUDECODE 環境變數：Task Scheduler 繼承此變數會導致 claude -p 拒絕啟動（巢狀 session 保護）
        # 官方說明：「To bypass this check, unset the CLAUDECODE environment variable.」
        $savedClaudeCode = $env:CLAUDECODE
        Remove-Item Env:\CLAUDECODE -ErrorAction SilentlyContinue
        try {
            if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
                Push-Location $workDir
                try {
                    $output = & claude -p $effectiveContent --allowedTools "Read,Bash,Write" 2>&1
                } finally {
                    Pop-Location
                }
            } else {
                $output = & claude -p $effectiveContent --allowedTools "Read,Bash,Write" 2>&1
            }
        } finally {
            # 還原環境變數
            if ($null -ne $savedClaudeCode) { $env:CLAUDECODE = $savedClaudeCode }
        }
        $toolUsed = "Claude CLI"
        $claudeDurationSec = [int]((Get-Date) - $ClaudeStartTime).TotalSeconds
        $outputStr = if ($output -is [array]) { $output -join "`n" } else { [string]$output }
        Write-Log "任務執行完畢 (使用: $toolUsed，耗時: ${claudeDurationSec}s，輸出: $($outputStr.Length) 字元)"
        Write-CompletionLog -Uid $uid -Filename $filename -Event "completed" `
            -DurationSec $claudeDurationSec -OutputLen $outputStr.Length

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

        # 標記為 failed（讓系統知道此任務失敗，可觸發重試）
        try {
            $failBody = @{ state = "failed"; worker_id = $WorkerId } | ConvertTo-Json
            Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/state" -Method Patch -Body $failBody -Headers $JsonHeaders | Out-Null
            Write-Log "已將任務標記為 failed"
        } catch {
            Write-Log "標記 failed 失敗: $_"
        }
    } finally {
        if (Test-Path $localFilePath) {
            Remove-Item $localFilePath -Force
        }
    }
}
Write-Log "=========================================="
Write-Log "本次排程處理完畢"
