# 結果檔案格式驗證清單

> **版本**: 1.0.0
> **建立日期**: 2026-03-19
> **產出者**: workflow-forge
> **用途**: 確保所有 `results/todoist-auto-*.json` 符合統一 Schema，避免格式漂移導致失敗

---

## 背景

雖然專案已有 `config/schemas/results-auto-task-schema.json` 定義標準格式，以及 `tools/validate_results.py` 驗證工具，但這些工具**未整合至任何自動化流程**。導致：

- **格式漂移風險**：30 個自動任務的結果 JSON 依賴 Agent 自律，無機器強制驗證
- **失敗率偏高**：system-insight 顯示 daily_success_rate=83.5%（低於 95% 目標）
- **除錯成本高**：Phase 3 組裝失敗時，需人工排查格式錯誤

此驗證清單提供標準化流程，確保結果檔案品質。

---

## 1. 前提條件

執行驗證前，確認以下環境狀態：

| 項目 | 檢查方式 | 通過標準 |
|------|---------|---------|
| **Python 環境** | `uv run python --version` | 回傳版本號（≥ 3.11） |
| **Schema 檔案存在** | `ls config/schemas/results-auto-task-schema.json` | 檔案存在 |
| **驗證工具可用** | `uv run python tools/validate_results.py --help` | 顯示使用說明 |
| **results/ 目錄權限** | `ls -la results/` | 可讀寫權限 |

---

## 2. 驗證項目

### 2.1 Schema 可讀性

**檢查目標**：`config/schemas/results-auto-task-schema.json` 存在且可解析為有效 JSON Schema

**檢查方式**：
```bash
python -c "import json; json.load(open('config/schemas/results-auto-task-schema.json'))"
```

**通過標準**：exit code = 0，無錯誤輸出

**失敗處理**：
1. 檢查 schema 檔案是否損壞（JSON 格式錯誤）
2. 用 JSON validator 修正格式
3. 重新執行驗證

---

### 2.2 結果檔案格式驗證

**檢查目標**：所有 `results/todoist-auto-*.json` 符合 `results-auto-task-schema.json`

**檢查方式**：
```bash
uv run python tools/validate_results.py
```

**通過標準**：exit code = 0，無錯誤訊息

**失敗處理**：
1. 查看錯誤輸出，定位哪個檔案的哪個欄位不符合
2. 找到對應 prompt 檔案（`prompts/team/todoist-auto-{task_key}.md`）
3. 修正 prompt 中的輸出 JSON 範例
4. 重新執行該任務（或等待下次排程）
5. 再次執行 `validate_results.py` 確認修正成功

---

### 2.3 必填欄位完整性

**檢查目標**：所有結果檔案含必填欄位 `task_key`, `status`, `agent`（或 `task_type`）

**檢查方式**：`uv run python tools/validate_results.py`（內建檢查）

**通過標準**：無 `missing required field` 錯誤

**失敗處理**：
1. 記錄缺失欄位名稱
2. 補充至對應 prompt 的輸出 JSON 範例
3. 確保 prompt 明確要求 Agent 填寫這些欄位
4. 重新執行任務

---

### 2.4 agent 欄位命名一致性

**檢查目標**：`agent` 欄位值 = `todoist-auto-{task_key}`（底線命名，與 `task_key` 保持同步）

**檢查方式**：
```bash
for f in results/todoist-auto-*.json; do
  task_key=$(basename "$f" .json | sed 's/todoist-auto-//')
  agent=$(jq -r '.agent' "$f" 2>/dev/null)
  expected="todoist-auto-$task_key"
  if [ "$agent" != "$expected" ]; then
    echo "❌ $f: agent='$agent' (expected '$expected')"
  fi
done
```

**通過標準**：無輸出 = 全部一致

**失敗處理**：
1. 定位不一致的檔案
2. 修正對應 prompt 中的 `agent` 欄位硬編碼
3. 確保 prompt 使用變數而非硬編碼值（如：`"agent": "todoist-auto-{{task_key}}"`）
4. 重新執行任務

---

### 2.5 status 取值規範

**檢查目標**：`status` 欄位僅限以下值：`success`, `partial`, `failed`, `format_failed`

**檢查方式**：`uv run python tools/validate_results.py`（內建 enum 驗證）

**通過標準**：無 `invalid enum value` 錯誤

**失敗處理**：
1. 找出使用非標準值的檔案（如 `completed`, `error` 等）
2. 修正 prompt 中的 status 值定義
3. 參照 schema 中的 enum 定義更新 prompt
4. 重新執行任務

---

## 3. 整合點

### 3.1 Phase 3 assemble 後驗證

**觸發時機**：`run-todoist-agent-team.ps1` Phase 3 完成、寫入最終結果前

**實作方式**：
在 `prompts/team/todoist-assemble.md` 步驟 6（寫入結果前）加入驗證步驟：

```markdown
## 步驟 6：格式驗證（新增）

用 Bash 執行：
```bash
uv run python tools/validate_results.py results/todoist-auto-{task_key}.json
```

若驗證失敗（exit code ≠ 0）：
1. 將 status 改為 `format_failed`
2. 將驗證錯誤訊息寫入 error.message 欄位
3. 繼續步驟 7 寫入結果（含錯誤資訊）
```

**降級處理**：驗證失敗不中斷流程，但標記為 `format_failed` 供後續分析

---

### 3.2 check-health.ps1 每日檢查

**觸發時機**：每日健康檢查執行時

**實作方式**：
在 `check-health.ps1` 新增 `[結果格式驗證]` 區塊：

```powershell
# [結果格式驗證]
Write-Host "[結果格式驗證]" -ForegroundColor Cyan
$validationResult = uv run python tools/validate_results.py 2>&1
if ($LASTEXITCODE -eq 0) {
    $validFiles = (Get-ChildItem results/todoist-auto-*.json).Count
    Write-Host "  ✅ 全部 $validFiles 個結果檔案格式正確" -ForegroundColor Green
} else {
    Write-Host "  ⚠️ 格式驗證失敗：" -ForegroundColor Yellow
    Write-Host "     $validationResult" -ForegroundColor Yellow
    Write-Host "     請執行 'uv run python tools/validate_results.py' 查看詳細錯誤" -ForegroundColor Yellow
}
```

**降級處理**：驗證失敗輸出警告訊息，但不中斷健康檢查

---

### 3.3 手動驗證指令

**觸發時機**：開發/除錯時

**使用方式**：
```bash
# 驗證所有結果檔案
uv run python tools/validate_results.py

# 驗證單一檔案
uv run python tools/validate_results.py results/todoist-auto-workflow_forge.json

# 驗證指定目錄
uv run python tools/validate_results.py --dir results/
```

**文件位置**：於 `docs/OPERATIONS.md` 新增「結果格式驗證」段落，提供快速驗證指令

---

## 4. 失敗處理流程

當驗證失敗時，遵循以下標準流程：

1. **記錄錯誤**
   將 `validate_results.py` 輸出寫入 `logs/validation-errors-{date}.log`
   ```bash
   uv run python tools/validate_results.py > logs/validation-errors-$(date +%Y%m%d).log 2>&1
   ```

2. **定位來源**
   找到產生該結果檔案的 prompt 檔案
   ```bash
   # 範例：results/todoist-auto-workflow_forge.json
   # 對應 prompt：prompts/team/todoist-auto-workflow_forge.md
   ```

3. **修正 prompt**
   更新 prompt 中的輸出 JSON 範例，確保符合 schema
   - 檢查必填欄位是否存在
   - 檢查 `agent` 欄位命名是否正確
   - 檢查 `status` 取值是否在 enum 範圍內

4. **重新執行**
   - 手動觸發：`pwsh -File run-todoist-agent-team.ps1`（指定 task_key）
   - 等待排程：下次 round-robin 輪到該任務時自動執行

5. **再次驗證**
   ```bash
   uv run python tools/validate_results.py results/todoist-auto-{task_key}.json
   ```
   確認 exit code = 0

---

## 5. 維護規則

### 5.1 新增自動任務時

**必做步驟**：
1. 在 prompt 中參照 `config/schemas/results-auto-task-schema.json`
2. 確保輸出 JSON 包含所有必填欄位
3. 在本清單「2. 驗證項目」中新增對應檢查項（若有特殊欄位）
4. 執行 `validate_results.py` 驗證首次執行結果

### 5.2 修改 schema 時

**必做步驟**：
1. 更新 `config/schemas/results-auto-task-schema.json`
2. 遞增 schema 的 `_metadata.version`
3. 更新本清單的驗證項目（若新增/修改必填欄位）
4. 重新驗證所有現有結果檔案：
   ```bash
   uv run python tools/validate_results.py
   ```
5. 修正不符合新 schema 的 prompt 檔案

### 5.3 驗證失敗率監控

**觸發條件**：驗證失敗率 > 10%（即 30 個任務中有 3 個以上格式錯誤）

**處理流程**：
1. 在 `context/improvement-backlog.json` 新增項目
2. 分析失敗原因（schema 定義不清？prompt 範例過時？）
3. 檢討 schema 與 prompt 的同步機制
4. 考慮強化自動化驗證（如 pre-commit hook）

---

## 6. 參考檔案

| 檔案 | 用途 |
|------|------|
| `config/schemas/results-auto-task-schema.json` | 驗證標準（JSON Schema v1.1.0） |
| `tools/validate_results.py` | 驗證工具（支援單檔/批次/目錄驗證） |
| `prompts/team/todoist-auto-*.md` | 結果產出來源（30 個自動任務 prompt） |
| `config/frequency-limits.yaml` | 任務定義（29 個任務，含 task_key 與 template） |
| `docs/OPERATIONS.md` | 操作指南（應包含驗證指令） |

---

## 7. 版本歷史

| 版本 | 日期 | 變更內容 |
|------|------|---------|
| 1.0.0 | 2026-03-19 | 初版，定義 5 個核心驗證項目 + 3 個整合點 + 失敗處理流程 |

---

**建立者**: todoist-auto-workflow_forge (workflow-forge Skill)
**最後更新**: 2026-03-19T05:45:00+08:00
