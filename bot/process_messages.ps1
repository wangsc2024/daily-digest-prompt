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

Write-Log "找到 $($records.Count) 個待處理任務"

foreach ($record in $records) {
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

        # 若有目標目錄，在強化後內容前加入 cd 指令以確保 Codex 在正確目錄執行
        $effectiveContent = $optimizedContent
        if ($workDir -and -not [string]::IsNullOrWhiteSpace($workDir)) {
            $effectiveContent = "請在目錄 $workDir 中執行以下任務。若目錄不存在請先建立。所有產出的檔案必須儲存在 $workDir 目錄中。`n`n" + $optimizedContent
        }

        Write-Log "--> Worker 使用 claude -p 處理任務 (研究型: $isResearch, 編碼型: $isCoding, 工作目錄: $(if($workDir){$workDir}else{'預設'}))..."
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
        $toolUsed = "Claude CLI"

        Write-Log "任務執行完畢 (使用: $toolUsed)"

        # ---- Step 4: Complete — 標記為已完成（帶 claim_generation、result 供工作流下游使用）----
        # 注意：結果回傳至聊天室由 bot server 的 /processed 端點透過穩定 Gun 連線負責，
        # 避免 Worker 自行呼叫 /api/send 時因 Gun relay 閒置斷線導致訊息遺失。
        $outputStr = if ($output -is [array]) { $output -join "`n" } else { [string]$output }
        $completeBody = @{ claim_generation = $claimGeneration; result = $outputStr } | ConvertTo-Json -Depth 3
        Invoke-RestMethod -Uri "$ApiBaseUrl/api/records/$uid/processed" -Method Patch -Body $completeBody -ContentType "application/json; charset=utf-8" -Headers $JsonHeaders | Out-Null
        Write-Log "狀態已更新為 completed (generation: $claimGeneration)。已請 bot server 透過 Gun 回傳結果至聊天室。"

    } catch {
        Write-Log "處理發生錯誤: $_"

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
