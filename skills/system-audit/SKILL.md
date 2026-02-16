---
name: system-audit
version: "1.0.0"
description: |
  通用系統審查評分工具 — 以 7 個維度（資訊安全、系統架構、系統品質、
  系統工作流、技術棧、系統文件、系統完成度）對目標系統進行全面評估，
  產出量化報告與改善建議。加權總分 0-100，含校準規則防止虛假高分。
  Use when: 系統審查、品質評估、安全評分、架構評審、完成度檢查。
  Note: 互動式工具 Skill，由使用者手動觸發，不透過 Todoist 自動路由。
allowed-tools: Read, Bash, Glob, Grep, Write, WebSearch
cache-ttl: N/A
triggers:
  - "系統審查"
  - "系統評分"
  - "品質評估"
  - "system audit"
  - "system review"
  - "安全評分"
  - "架構評審"
  - "完成度檢查"
  - "系統健檢"
  - "system score"
---

# System Audit — 通用系統審查評分

以 7 個維度、38 個子項對目標系統進行全面量化評估，產出結構化報告。

## 快速使用

向 Agent 說出以下任一觸發語句即可啟動：
- 「對這個專案做系統審查」
- 「幫我評估這個系統的品質」
- 「系統健檢」
- 「system audit」

## 評分概要

| 維度 | 權重（balanced） | 子項數 |
|------|-----------------|--------|
| 資訊安全 | 20% | 6 |
| 系統架構 | 18% | 6 |
| 系統品質 | 18% | 6 |
| 系統工作流 | 15% | 5 |
| 技術棧 | 10% | 5 |
| 系統文件 | 10% | 5 |
| 系統完成度 | 9% | 5 |
| **合計** | **100%** | **38** |

## 等級定義

| 等級 | 分數範圍 | 說明 |
|------|---------|------|
| S 卓越 | 90-100 | 業界標竿，極少數系統能達到 |
| A 優秀 | 80-89 | 超越多數同類系統 |
| B 良好 | 70-79 | 具備專業水準 |
| C 及格 | 55-69 | 基本可用，有明顯改善空間 |
| D 待改善 | 40-54 | 多項缺陷需優先處理 |
| F 不及格 | 0-39 | 嚴重不足，需全面檢討 |

> **校準提醒**：一般中小型系統典型得分 50-70。80+ 需要企業級實踐。100 分理論存在，現實幾乎不可能。

---

## 使用方式

本 Skill 支援兩種執行模式：互動式手動審查與排程自動審查。

### 方式 1：互動式手動審查（推薦用於深度分析）

**觸發方式**：
直接對 Agent 說出觸發語句（如「系統審查」），Agent 會依照本檔案的「操作步驟」（Phase 0-8）進行完整審查。

**特點**：
- ✅ 完整互動：可隨時提問、調整範圍、討論改善方案
- ✅ 深度分析：Agent 會詳細解釋每個維度的問題與建議
- ✅ 客製化：可指定權重模型（balanced / security_first / startup）
- ✅ 即時產出：產出報告到 `reports/audit-{system}-{date}.md`

**適用情境**：
- 新專案啟動前的基準評估
- 重大變更後的完整性驗證
- 技術債務盤點
- 交付前的品質閘門

---

### 方式 2：自動排程 - 團隊並行模式（推薦用於定期追蹤）

**架構設計**：
採用 Agent Team 並行架構，將 7 個維度拆分為 4 個並行 Agent，再由 1 個組裝 Agent 整合結果。相較於單一 Agent 串行執行（15-30 分鐘），團隊模式可縮短至 **15-20 分鐘**。

```
Phase 1: 並行審查（4 個 Agent，各 600s timeout）
  ├─ Agent 1: 維度 1（資訊安全）+ 維度 5（技術棧）→ results/audit-dim1-5.json
  ├─ Agent 2: 維度 2（系統架構）+ 維度 6（系統文件）→ results/audit-dim2-6.json
  ├─ Agent 3: 維度 3（系統品質）+ 維度 7（系統完成度）→ results/audit-dim3-7.json
  └─ Agent 4: 維度 4（系統工作流）→ results/audit-dim4.json

Phase 2: 組裝與修正（1 個 Agent，1200s timeout）
  1. 讀取 Phase 1 的 4 個 JSON 結果
  2. 計算加權總分（依 config/audit-scoring.yaml 權重模型）
  3. 識別問題項目（分數 <70 或較上次退步 >5 分）
  4. 自動修正（最多 5 項，優先處理簡單問題）
  5. 重新審查修正項目（驗證改善效果）
  6. 生成結構化報告（依 templates/audit-report.md 模板）
  7. 寫入知識庫（POST localhost:3000/api/notes）
  8. 更新執行狀態（state/scheduler-state.json）
  9. 清理中間檔案（results/*.json）
```

**實作步驟**：

#### Step 1: 建立 Team Mode Prompts（5 個檔案）

在專案根目錄建立 `prompts/team/` 目錄，並建立以下 5 個 prompt 檔案：

**1. `fetch-audit-dim1-5.md`**（Phase 1 Agent 1）
```markdown
# Phase 1: 審查維度 1+5

## 角色
你是系統審查 Phase 1 的 Agent 1，負責評估 2 個維度。

## 任務
評估以下 2 個維度：
- **維度 1**：資訊安全（6 個子項）
- **維度 5**：技術棧（5 個子項）

## 操作步驟
1. Read skills/system-audit/SKILL.md（取得評分規則）
2. Read config/audit-scoring.yaml（取得權重與校準規則）
3. 依照 SKILL.md 的 Phase 1（維度 1）和 Phase 5（維度 5）逐項評估
4. 每個子項產出：分數（0-100）、證據、給分理由
5. Write results/audit-dim1-5.json（JSON 格式）

## 輸出格式
```json
{
  "dimension_1": {
    "name": "資訊安全",
    "weight": 20,
    "sub_items": [
      {"id": "1.1", "name": "機密管理", "score": 75, "evidence": "...", "reason": "..."},
      {"id": "1.2", "name": "輸入驗證", "score": 60, "evidence": "...", "reason": "..."}
      // ... 共 6 項
    ],
    "avg_score": 68.3
  },
  "dimension_5": {
    "name": "技術棧",
    "weight": 10,
    "sub_items": [
      // ... 共 5 項
    ],
    "avg_score": 72.0
  },
  "agent_id": "dim1-5",
  "timestamp": "2026-02-16T00:45:00+08:00"
}
```

## 重要規則
- 每個子項必須有具體證據（檔案路徑、Grep 結果、Bash 輸出）
- 禁止模糊語言（「看起來不錯」「應該有」）
- 遵守校準規則（如：無測試 → 品質上限 50）
```

**2. `fetch-audit-dim2-6.md`**（Phase 1 Agent 2，結構同上，負責維度 2+6）

**3. `fetch-audit-dim3-7.md`**（Phase 1 Agent 3，結構同上，負責維度 3+7）

**4. `fetch-audit-dim4.md`**（Phase 1 Agent 4，結構同上，負責維度 4）

**5. `assemble-audit.md`**（Phase 2 組裝 Agent）
```markdown
# Phase 2: 組裝審查報告

## 角色
你是系統審查 Phase 2 的組裝 Agent，負責整合 Phase 1 的結果並產出最終報告。

## 任務
整合 Phase 1 的 4 個 JSON 結果，計算加權總分，自動修正問題，產出報告。

## 操作步驟

### Step 1: 讀取 Phase 1 結果
1. Read results/audit-dim1-5.json
2. Read results/audit-dim2-6.json
3. Read results/audit-dim3-7.json
4. Read results/audit-dim4.json

### Step 2: 計算加權總分
1. Read config/audit-scoring.yaml（取得權重模型，預設 balanced）
2. 計算各維度平均分
3. 依權重計算加權總分：
   ```
   總分 = Σ(維度平均分 × 維度權重)
   ```
4. 判定等級（S/A/B/C/D/F）

### Step 3: 識別問題項目
標記以下項目為待修正：
- 分數 < 70（C 級以下）
- 較上次審查退步 > 5 分（需讀取上次報告比對）
- 觸發校準上限的子項（如：無測試 → 品質上限 50）

### Step 4: 自動修正（最多 5 項）
依以下原則選擇修正項目：
1. **優先修正簡單問題**（預估 <5 分鐘可完成）：
   - 新增缺失的配置檔（如 .gitignore）
   - 補充文件注釋
   - 更新過時的文件
2. **跳過複雜問題**（需人工介入）：
   - 重構架構
   - 新增測試
   - 修正程式碼邏輯

修正後立即重新審查該子項，確認改善效果。

### Step 5: 生成報告
1. Read templates/audit-report.md（取得報告模板）
2. 填入各維度分數、證據、建議
3. 計算 TOP 5 改善建議（依影響度排序）
4. Write reports/audit-{專案名稱}-{日期}.md

### Step 6: 寫入知識庫
將報告摘要寫入知識庫：
```bash
curl -s -X POST http://localhost:3000/api/notes \
  -H "Content-Type: application/json" \
  -d @note.json
```
其中 note.json：
```json
{
  "title": "系統審查 - {專案名稱} - {日期}",
  "content": "{報告摘要（Markdown 格式）}",
  "tags": ["系統審查", "品質評估", "{專案名稱}"],
  "source": "import"
}
```

### Step 7: 更新執行狀態
**注意**：`state/scheduler-state.json` 由 PowerShell 腳本獨佔寫入，Agent 只讀。
僅在記憶體中記錄本次審查結果，供腳本稍後寫入。

### Step 8: 清理中間檔案
```bash
rm -f results/audit-dim*.json
```

## 輸出
- reports/audit-{專案名稱}-{日期}.md（完整報告）
- 知識庫新增一筆系統審查記錄
- 清理 results/ 目錄
```

#### Step 2: 建立 PowerShell 執行腳本

建立 `run-system-audit-team.ps1`：

```powershell
#Requires -Version 7.0
# 系統審查 - 團隊並行模式執行腳本

param(
    [int]$Phase1Timeout = 600,  # Phase 1 各 Agent timeout（秒）
    [int]$Phase2Timeout = 1200, # Phase 2 組裝 Agent timeout（秒）
    [int]$MaxRetries = 1
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $AgentDir "logs"
$ResultsDir = Join-Path $AgentDir "results"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "system-audit-team_$Timestamp.log"

# 確保目錄存在
@($LogDir, $ResultsDir, "$LogDir\structured") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $Time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Time] [$Level] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage -Encoding UTF8
}

Write-Log "===== 系統審查 - 團隊並行模式開始 ====="

# Phase 1: 並行審查（4 個 Agent）
$phase1Prompts = @(
    @{ Name = "dim1-5"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim1-5.md" },
    @{ Name = "dim2-6"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim2-6.md" },
    @{ Name = "dim3-7"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim3-7.md" },
    @{ Name = "dim4"; Prompt = "$AgentDir\prompts\team\fetch-audit-dim4.md" }
)

$phase1Jobs = @()
foreach ($p in $phase1Prompts) {
    Write-Log "啟動 Phase 1 Agent: $($p.Name)"
    $job = Start-Job -ScriptBlock {
        param($AgentDir, $PromptFile, $Timeout)
        $OutputEncoding = [System.Text.UTF8Encoding]::new()
        Set-Location $AgentDir
        claude -p (Get-Content $PromptFile -Raw -Encoding UTF8) --allowedTools "Read,Bash,Glob,Grep,Write"
    } -ArgumentList $AgentDir, $p.Prompt, $Phase1Timeout -WorkingDirectory $AgentDir
    $phase1Jobs += @{ Job = $job; Name = $p.Name }
}

Write-Log "等待 Phase 1 完成（timeout ${Phase1Timeout}s）..."
$phase1Jobs | ForEach-Object {
    $job = $_.Job
    $name = $_.Name
    $completed = Wait-Job -Job $job -Timeout $Phase1Timeout
    if ($completed) {
        $output = Receive-Job -Job $job
        Write-Log "Phase 1 Agent [$name] 完成"
    } else {
        Write-Log "Phase 1 Agent [$name] 超時，強制停止" "WARN"
        Stop-Job -Job $job
    }
    Remove-Job -Job $job -Force
}

# 檢查 Phase 1 結果
$phase1Results = @()
foreach ($p in $phase1Prompts) {
    $resultFile = Join-Path $ResultsDir "audit-$($p.Name).json"
    if (Test-Path $resultFile) {
        Write-Log "Phase 1 結果已產出: $resultFile"
        $phase1Results += $resultFile
    } else {
        Write-Log "Phase 1 結果缺失: $resultFile" "ERROR"
    }
}

if ($phase1Results.Count -ne 4) {
    Write-Log "Phase 1 失敗，結果不完整（$($phase1Results.Count)/4）" "ERROR"
    exit 1
}

# Phase 2: 組裝報告
Write-Log "啟動 Phase 2: 組裝 Agent"
$phase2Prompt = Join-Path $AgentDir "prompts\team\assemble-audit.md"

$phase2Job = Start-Job -ScriptBlock {
    param($AgentDir, $PromptFile)
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
    Set-Location $AgentDir
    claude -p (Get-Content $PromptFile -Raw -Encoding UTF8) --allowedTools "Read,Bash,Write"
} -ArgumentList $AgentDir, $phase2Prompt -WorkingDirectory $AgentDir

$phase2Completed = Wait-Job -Job $phase2Job -Timeout $Phase2Timeout
if ($phase2Completed) {
    $output = Receive-Job -Job $phase2Job
    Write-Log "Phase 2 組裝完成"
    Remove-Job -Job $phase2Job -Force
} else {
    Write-Log "Phase 2 超時，嘗試重試一次..." "WARN"
    Stop-Job -Job $phase2Job
    Remove-Job -Job $phase2Job -Force

    # 重試一次
    Start-Sleep -Seconds 60
    $phase2Job = Start-Job -ScriptBlock {
        param($AgentDir, $PromptFile)
        $OutputEncoding = [System.Text.UTF8Encoding]::new()
        Set-Location $AgentDir
        claude -p (Get-Content $PromptFile -Raw -Encoding UTF8) --allowedTools "Read,Bash,Write"
    } -ArgumentList $AgentDir, $phase2Prompt -WorkingDirectory $AgentDir

    $phase2Completed = Wait-Job -Job $phase2Job -Timeout $Phase2Timeout
    if ($phase2Completed) {
        Write-Log "Phase 2 重試成功"
        Receive-Job -Job $phase2Job | Out-Null
    } else {
        Write-Log "Phase 2 重試失敗" "ERROR"
        Stop-Job -Job $phase2Job
    }
    Remove-Job -Job $phase2Job -Force
}

Write-Log "===== 系統審查 - 團隊並行模式結束 ====="
```

#### Step 3: 設定 Windows Task Scheduler

使用專案的 `setup-scheduler.ps1` 工具：

```powershell
# 方式 1：從 HEARTBEAT.md 批次建立（推薦）
.\setup-scheduler.ps1 -FromHeartbeat

# 方式 2：手動建立單一排程
.\setup-scheduler.ps1 -Time "00:40" -Script "run-system-audit-team.ps1"
```

或在 `HEARTBEAT.md` 中定義：

```yaml
system-audit:
  cron: "40 0 * * *"
  script: run-system-audit-team.ps1
  timeout: 1800
  retry: 1
  description: "每日系統審查 - 團隊模式（00:40）"
```

**特點**：
- ⚡ 快速：15-20 分鐘完成（相較單一模式的 30 分鐘）
- 🔄 自動化：排程執行，無需人工介入
- 🛠️ 自動修正：自動修正簡單問題（最多 5 項）
- 📊 趨勢追蹤：可比對歷史報告，追蹤進步情況
- 📚 知識庫整合：自動將報告寫入知識庫（localhost:3000）

**適用情境**：
- 定期品質檢查（建議每日或每週一次）
- 持續追蹤改善進度
- CI/CD 整合（Pull Request 前自動審查）

---

### 兩種方式的比較

| 項目 | 互動式手動審查 | 自動排程 - 團隊模式 |
|------|---------------|-------------------|
| **執行時間** | 15-30 分鐘 | 15-20 分鐘 |
| **互動性** | 高（可隨時提問） | 無（全自動） |
| **深度** | 深（可詳細討論） | 標準（依規則評分） |
| **自動修正** | 需手動 | 自動修正簡單問題（最多 5 項） |
| **報告輸出** | reports/*.md | reports/*.md + 知識庫 |
| **適用情境** | 深度分析、技術債盤點 | 定期追蹤、CI/CD |

---

## 操作步驟

### Phase 0：準備

1. **讀取評分規則**
   ```
   Read config/audit-scoring.yaml
   ```

2. **確認目標系統**
   - 預設：當前專案根目錄
   - 使用者可指定其他系統路徑

3. **選擇權重模型**
   - `balanced`（預設）：均衡考量
   - `security_first`：金融/醫療/政府系統
   - `startup`：新創/MVP/原型系統

4. **讀取報告模板**
   ```
   Read templates/audit-report.md
   ```

5. **初始化計分表**
   準備 7 個維度的空分數陣列，後續逐項填入。

---

### Phase 1：資訊安全審查（權重 20%）

逐項檢查 6 個子項，每項 0-100 分。

#### 1.1 機密管理

**檢查步驟**：
1. Grep 掃描程式碼中的硬編碼機密：
   ```
   Grep pattern="(password|secret|api_key|token)\s*[=:]\s*['\"][^'\"]+['\"]"
   排除：*.md, *.yaml 中的說明文字
   ```
2. 確認 `.gitignore` 包含 `.env`、`credentials*`、`token*`
3. 確認環境變數使用方式（`$ENV_VAR` 或 `os.environ`）

**給分標準**：
- 90-100：Secret Manager + 環境變數 + .gitignore 完整 + 定期輪換
- 70-89：環境變數 + .gitignore 完整，無硬編碼
- 50-69：.gitignore 有但不完整，部分硬編碼
- 30-49：有硬編碼機密但不在 git 中
- 0-29：硬編碼機密已 commit 到 git

#### 1.2 輸入驗證

**檢查步驟**：
1. Grep 搜尋外部輸入接收點（API 端點、表單、CLI 參數）
2. 檢查附近是否有驗證邏輯（validate、sanitize、check、assert）
3. 特別關注 SQL/命令注入風險

**給分標準**：
- 90-100：所有輸入有白名單驗證 + 型別檢查 + 長度限制
- 70-89：主要輸入有驗證，次要輸入有基本檢查
- 50-69：部分輸入有驗證，部分無
- 30-49：僅少數輸入有基本驗證
- 0-29：完全無輸入驗證

#### 1.3 存取控制

**檢查步驟**：
1. 檢查是否有 Hook/Guard/Middleware 攔截機制
2. 檢查 allowedTools 或權限限縮配置
3. 檢查敏感檔案保護規則（write guard、路徑遍歷防護）

**給分標準**：
- 90-100：多層存取控制（Hook + RBAC + 最小權限 + 路徑遍歷防護）
- 70-89：有 Hook/Guard + 權限限縮
- 50-69：有基本權限設定但不完整
- 30-49：權限設定過於寬鬆
- 0-29：無任何存取控制

#### 1.4 依賴安全

**檢查步驟**：
1. 檢查依賴管理檔案（requirements.txt / package.json / Cargo.toml）
2. 檢查是否有 lock 檔案
3. 嘗試執行 `pip audit` 或 `npm audit`（若工具可用）

**給分標準**：
- 90-100：依賴鎖定 + 無已知漏洞 + 定期更新策略
- 70-89：依賴鎖定 + 無高危漏洞
- 50-69：有依賴檔案但未鎖定版本
- 30-49：依賴檔案不完整
- 0-29：無依賴管理

#### 1.5 傳輸安全

**檢查步驟**：
1. Grep 搜尋 `http://`（排除 localhost / 127.0.0.1 / 0.0.0.0）
2. 確認所有外部 API 呼叫使用 HTTPS

**給分標準**：
- 90-100：全部 HTTPS + 憑證驗證 + HSTS
- 70-89：全部 HTTPS，無明文例外
- 50-69：多數 HTTPS，少數 HTTP 用於非敏感資料
- 30-49：混用 HTTP/HTTPS
- 0-29：多數使用 HTTP 明文傳輸

#### 1.6 日誌安全

**檢查步驟**：
1. 抽樣檢查 logs/ 目錄最新 3 個日誌檔案
2. Grep 搜尋日誌中的敏感關鍵字（token、password、secret、Bearer）
3. 確認是否有結構化日誌系統

**給分標準**：
- 90-100：結構化日誌 + 自動脫敏 + 日誌輪轉 + 存取控制
- 70-89：結構化日誌 + 無敏感資訊洩露
- 50-69：有日誌但非結構化，無明顯洩露
- 30-49：日誌中有部分敏感資訊
- 0-29：日誌中有明文密碼/Token

**Phase 1 完成後**：計算 6 個子項平均分 → 檢查校準規則（硬編碼密碼→上限 30，無安全掃描→上限 60）。

---

### Phase 2：系統架構審查（權重 18%）

#### 2.1 關注點分離

**檢查步驟**：
1. 用 `ls` 或 Glob 分析頂層目錄結構
2. 判斷是否有清晰分層：config / templates / code / tests / docs / scripts
3. 檢查各層是否職責單一（config 不含邏輯、template 不含數據）

**給分標準**：
- 90-100：5+ 層清晰分離，各層職責完全單一
- 70-89：4+ 層分離，個別交叉可接受
- 50-69：有基本分離但邊界模糊
- 30-49：僅 2-3 個目錄，職責混合
- 0-29：所有檔案在同一目錄

#### 2.2 配置外部化

**檢查步驟**：
1. 統計 config/ 目錄中的配置檔數量和覆蓋範圍
2. Grep 搜尋程式碼中的硬編碼常數（magic number）
3. 確認修改配置是否需要動程式碼

**給分標準**：
- 90-100：所有可變參數外部化，改配置不改程式碼
- 70-89：主要參數外部化，少數硬編碼有注釋
- 50-69：部分配置外部化，部分硬編碼
- 30-49：多數參數硬編碼
- 0-29：所有參數硬編碼

#### 2.3 耦合度

**檢查步驟**：
1. 分析模組間的依賴關係（import/Read/引用）
2. 檢查是否有循環依賴或隱性耦合
3. 評估修改一個模組是否需要連動其他模組

**給分標準**：
- 90-100：模組間完全透過介面溝通，零循環依賴
- 70-89：低耦合，偶有直接引用但合理
- 50-69：中等耦合，部分模組關係緊密
- 30-49：高耦合，改一處常需連動多處
- 0-29：義大利麵架構，改任何地方都影響全局

#### 2.4 可擴展性

**檢查步驟**：
1. 確認新增功能是否有標準化流程/工具（如 task-manager）
2. 檢查擴展點是否文件化
3. 評估新增一個功能需觸碰幾個檔案

**給分標準**：
- 90-100：標準化新增工具 + 文件化流程 + 插件機制
- 70-89：有標準化流程，新增觸碰 ≤ 5 個檔案
- 50-69：有約定但無工具，新增觸碰 6-10 個檔案
- 30-49：無標準流程，新增觸碰 > 10 個檔案
- 0-29：新增功能需重寫核心

#### 2.5 容錯設計

**檢查步驟**：
1. Grep 搜尋 retry / retry_count / 重試 / fallback / 降級
2. 檢查 API 呼叫的失敗處理路徑（快取降級、back-pressure）
3. 確認是否有 timeout 保護

**給分標準**：
- 90-100：多層容錯（重試 + 降級 + 斷路器 + timeout + back-pressure）
- 70-89：重試 + 快取降級 + timeout
- 50-69：有 timeout 和基本重試
- 30-49：僅有 timeout，無降級
- 0-29：無容錯機制

#### 2.6 單一定義處（DRY）

**檢查步驟**：
1. Grep 搜尋重複的配置片段或常數定義
2. 檢查是否有共用模組（如 preamble.md、hook_utils.py）
3. 確認共用邏輯是否集中管理

**給分標準**：
- 90-100：完全 DRY，共用邏輯集中管理，無重複
- 70-89：主要邏輯不重複，偶有合理冗餘
- 50-69：有些重複但不影響維護
- 30-49：明顯重複，維護時容易遺漏
- 0-29：大量複製貼上

---

### Phase 3：系統品質審查（權重 18%）

#### 3.1 測試覆蓋率

**檢查步驟**：
1. Glob 搜尋 `tests/**/*.py` 或 `**/*.test.*` 統計測試檔案數
2. 嘗試 `pytest --co -q` 統計測試案例數
3. 嘗試 `pytest --cov` 取覆蓋率（若可用）

**給分標準**：
- 90-100：覆蓋率 ≥ 80%，含邊界測試和整合測試
- 70-89：覆蓋率 60-79%，核心邏輯有測試
- 50-69：覆蓋率 40-59%，有基本測試
- 30-49：覆蓋率 < 40%，測試零散
- 0-29：無自動化測試（觸發校準上限 50）

#### 3.2 程式碼品質

**檢查步驟**：
1. 嘗試執行 linter（pylint / flake8 / eslint）
2. 檢查命名規範一致性（snake_case / camelCase）
3. 抽樣檢查程式碼格式整潔度

**給分標準**：
- 90-100：零 lint 錯誤 + 一致風格 + 有 formatter
- 70-89：少量 lint 警告（< 10），風格基本一致
- 50-69：有 lint 錯誤但不嚴重，風格不太一致
- 30-49：多處 lint 錯誤，風格混亂
- 0-29：程式碼品質極差

#### 3.3 錯誤處理

**檢查步驟**：
1. Grep 搜尋外部呼叫附近的 try/catch/except/error handling
2. 檢查錯誤是否有分級（warning vs error vs critical）
3. 確認錯誤是否被記錄而非靜默忽略

**給分標準**：
- 90-100：所有外部呼叫有錯誤處理 + 分級 + 上報
- 70-89：主要呼叫有錯誤處理和記錄
- 50-69：部分呼叫有錯誤處理
- 30-49：錯誤處理不完整，有靜默忽略
- 0-29：無錯誤處理

#### 3.4 品質驗證機制

**檢查步驟**：
1. 檢查是否有品質閘門（quality gate）機制
2. 檢查是否有完成認證（DONE_CERT 或等效機制）
3. 確認是否有迭代精修流程

**給分標準**：
- 90-100：品質閘門 + 完成認證 + 迭代精修 + 外部驗證
- 70-89：有品質閘門和認證機制
- 50-69：有基本的品質檢查
- 30-49：僅靠人工 review
- 0-29：無品質驗證

#### 3.5 監控與可觀測性

**檢查步驟**：
1. 檢查是否有結構化日誌系統（JSONL / JSON 日誌）
2. 檢查是否有健康檢查腳本
3. 檢查是否有異常告警機制（ntfy / email / Slack）

**給分標準**：
- 90-100：結構化日誌 + 健康檢查 + 自動告警 + 儀表板
- 70-89：結構化日誌 + 健康檢查 + 告警
- 50-69：有日誌和基本監控
- 30-49：僅有文字日誌，無監控
- 0-29：無日誌無監控

#### 3.6 效能基準

**檢查步驟**：
1. 檢查是否有 timeout 設定
2. 檢查是否追蹤平均耗時
3. 檢查快取命中率統計

**給分標準**：
- 90-100：效能指標追蹤 + 基準測試 + 快取統計 + SLA
- 70-89：有 timeout + 耗時追蹤 + 快取統計
- 50-69：有 timeout，耗時偶爾記錄
- 30-49：僅有 timeout
- 0-29：無效能監控

---

### Phase 4：系統工作流審查（權重 15%）

#### 4.1 自動化程度
1. 檢查排程配置（cron / Task Scheduler / HEARTBEAT.md）
2. 統計自動化流程數量 vs 手動流程數量
3. 確認端到端流程是否全自動（排程→執行→通知）

#### 4.2 並行效率
1. 檢查是否有並行執行機制（Start-Job / Task 工具 / 多 Agent）
2. 統計可並行的獨立任務是否真的並行
3. 比較串行 vs 並行模式的提供情況

#### 4.3 失敗恢復
1. Grep 搜尋 retry / 重試 / fallback / back-pressure
2. 檢查失敗後是否自動重試、降級、延期
3. 確認失敗任務的後續處理流程

#### 4.4 狀態追蹤
1. 檢查是否有持久化狀態檔案（state/*.json / context/*.json）
2. 確認執行歷史是否可查詢
3. 檢查跨次記憶機制

#### 4.5 排程管理
1. 檢查排程是否集中定義（單一配置檔 vs 散佈各處）
2. 確認是否有批次管理工具（setup-scheduler 或等效）
3. 評估新增排程的便利性

> Phase 4 各子項的給分標準參照 Phase 1-3 的 5 級標準模式。

---

### Phase 5：技術棧審查（權重 10%）

#### 5.1 技術成熟度
1. 列出核心依賴清單
2. 查詢各依賴的穩定性（LTS / GA / Beta / Alpha）
3. 確認技術社群活躍度

#### 5.2 版本管理
1. 檢查 lock 檔案存在性（requirements.txt / package-lock.json / poetry.lock）
2. 確認版本固定方式（== / >= / ^）
3. 檢查是否有更新策略文件

#### 5.3 工具鏈完整性
1. 列舉已有工具覆蓋的階段：
   - 開發（editor config / formatter）
   - 測試（pytest / jest / 覆蓋率）
   - 品質（linter / type checker）
   - 部署（setup script / CI/CD）
   - 監控（health check / 告警）
2. 統計覆蓋率

#### 5.4 跨平台相容性
1. 檢查文件中的平台支援聲明
2. Grep 搜尋平台條件處理（os.name / platform / runtime）
3. 確認路徑處理是否跨平台（/ vs \）

#### 5.5 技術債務
1. Grep 搜尋 deprecated / workaround / HACK / 臨時
2. 檢查是否有過時 API 使用
3. 統計技術債務項目數量

---

### Phase 6：系統文件審查（權重 10%）

#### 6.1 架構文件
1. 檢查 README.md / CLAUDE.md / specs/ 中的架構說明
2. 確認目錄結構是否文件化
3. 評估架構說明是否與實際一致

#### 6.2 操作手冊
1. 檢查 ops-manual 或等效文件
2. 確認安裝/設定/執行/疑難排解是否完整
3. 評估新手能否依手冊獨立操作

#### 6.3 API / 介面文件
1. 統計 API/SKILL 的文件覆蓋率
2. 確認參數、回傳值、錯誤碼是否說明
3. 檢查是否有使用範例

#### 6.4 配置說明
1. 抽樣 3-5 個配置檔案
2. 統計注釋行佔比
3. 確認參數用途是否可理解

#### 6.5 變更記錄
1. 檢查 git log 最近 20 筆 commit message 的格式一致性
2. 確認是否有 CHANGELOG.md
3. 評估版本可追溯性

---

### Phase 7：系統完成度審查（權重 9%）

#### 7.1 功能完成度
1. Grep 搜尋 `TODO|FIXME|HACK|XXX` 並統計數量
2. 列舉所有待完成項目
3. 評估規劃功能的實作比例

#### 7.2 邊界處理
1. 抽樣檢查 3-5 個核心函式
2. 確認空值/null check、timeout 處理、長度限制
3. 評估異常輸入的處理方式

#### 7.3 部署就緒
1. 確認一鍵部署/設定腳本是否存在且完整
2. 檢查是否有未自動化的手動步驟
3. 評估從零到運行的步驟數

#### 7.4 整合完整性
1. 確認各模組間的整合是否有驗證
2. 檢查端到端流程是否可通
3. 評估整合測試的覆蓋範圍

#### 7.5 生產穩定性
1. 檢查最近 7 天執行記錄（scheduler-state 或等效）
2. 計算成功率（成功次數 / 總執行次數）
3. 統計平均耗時和異常次數

---

### Phase 8：彙總與報告

1. **計算各維度分數**
   - 維度分數 = 該維度所有子項的平均分（排除 N/A 後重算）
   - 檢查校準規則，若觸發則套用硬性上限

2. **計算加權總分**
   ```
   加權總分 = Σ (維度分數 × 維度權重 / 100)
   ```
   - 使用選定的 weight_profile 中的權重

3. **判定等級**
   - 依 grade_thresholds 對應等級（S/A/B/C/D/F）

4. **產出 TOP 5 改善建議**
   - 從所有子項中選出分數最低的 5 項
   - 計算改善後的預期分數提升
   - 評估實作難度（低/中/高）

5. **填寫報告模板**
   ```
   Read templates/audit-report.md
   ```
   將所有分數、證據、建議填入模板。

6. **輸出報告**
   - 用 Write 工具將報告寫入 `reports/audit-{system}-{date}.md`
   - 在終端輸出總覽表和 TOP 5 建議

---

## 校準規則（防止虛假高分）

以下規則在 Phase 8 彙總時自動檢查：

| 條件 | 受影響維度 | 硬性上限 |
|------|-----------|---------|
| 無自動化測試 | 系統品質 | 50 |
| 無安全掃描且無 Hook/Guard | 資訊安全 | 60 |
| 無架構文件 | 系統文件 | 40 |
| TODO/FIXME > 20 處 | 系統完成度 | 50 |
| 無重試/降級機制 | 系統工作流 | 55 |
| 硬編碼密碼/Token 存在 | 資訊安全 | 30 |

## 證據要求

- 每個子項必須記錄至少 1 項具體證據
- 可接受的證據類型：檔案路徑、Grep 結果、指令輸出、程式碼片段
- 不可接受的證據：「看起來不錯」「應該有」「大致符合」
- 缺乏證據的子項不得高於 40 分

## 權重模型切換

```
使用者：「用安全優先模式審查這個系統」
→ 讀取 config/audit-scoring.yaml 的 weight_profiles.security_first
```

可用模型：
- `balanced`：均衡（預設）
- `security_first`：安全優先（金融/醫療/政府）
- `startup`：快速迭代（新創/MVP）

## 注意事項

- 此 Skill 為通用工具，可審查任何系統（不限本專案）
- 評分結果僅為參考，實際品質需結合專案背景判斷
- 建議定期執行（每月一次或重大變更後）以追蹤趨勢
- 報告保存於 `reports/` 目錄，可用 git 追蹤歷史
