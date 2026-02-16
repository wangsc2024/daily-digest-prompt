# Phase 1: 審查維度 3+7

你是系統審查專家，全程使用正體中文。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 任務

對 `d:\Source\daily-digest-prompt` 專案進行審查，評估以下 2 個維度：
- **維度 3**：系統品質（7 個子項）
- **維度 7**：系統完成度（5 個子項）

## 執行步驟

### 1. 評估維度 3：系統品質（權重 18%）

| 子項 | 檢查方法 |
|------|---------|
| 3.1 測試覆蓋率 | 執行 `pytest --co -q \| wc -l` 統計測試數量，檢查覆蓋範圍 |
| 3.2 模板化與 DRY | 檢查 preamble.md 引用率，模板標準化程度 |
| 3.3 版本管理 | 檢查 CHANGELOG.md、YAML version 欄位數量 |
| 3.4 程式碼品質 | 檢查 hook_utils.py 共用模組，編碼風格一致性 |
| 3.5 錯誤處理 | 統計 try/except 數量，檢查 API 呼叫錯誤處理 |
| 3.6 效能基準 | 檢查 config/timeouts.yaml、benchmark.yaml、快取命中率 |
| 3.7 可觀測性 | 檢查 JSONL 日誌、健康評分、query-logs 模式數量 |

### 2. 評估維度 7：系統完成度（權重 9%）

| 子項 | 檢查方法 |
|------|---------|
| 7.1 功能完整性 | Grep 搜尋 TODO/FIXME 數量，檢查 Skill 數量、自動任務數量 |
| 7.2 文檔完整性 | 檢查 CHANGELOG.md、config/README.md、SKILL_INDEX.md |
| 7.3 部署就緒度 | 檢查 setup-scheduler.ps1、.env.example、$PSScriptRoot 使用率 |
| 7.4 測試覆蓋率 | 統計測試數量（292），Hook 覆蓋率 |
| 7.5 維護性 | 檢查 DRY 程度、版本追蹤、模組整合緊密度 |

### 3. 輸出 JSON

寫入 `results/audit-dim3-7.json`：

```json
{
  "timestamp": "2026-02-17T00:41:00+08:00",
  "dimensions": {
    "3_system_quality": {
      "weight": 18,
      "score": 91,
      "sub_items": {
        "3.1_test_coverage": { "score": 84, "evidence": "292 個測試全部通過", "files_checked": ["tests/"] },
        "3.2_templating_dry": { "score": 94, "evidence": "preamble.md 引用率 88.5%", "files_checked": [...] },
        "3.3_version_management": { "score": 92, "evidence": "CHANGELOG.md + 13 YAML 版本化", "files_checked": [...] },
        "3.4_code_quality": { "score": 88, "evidence": "hook_utils.py 共用模組", "files_checked": [...] },
        "3.5_error_handling": { "score": 90, "evidence": "60 處 try/catch", "files_checked": [...] },
        "3.6_performance_baseline": { "score": 82, "evidence": "timeouts.yaml 存在但未被使用", "files_checked": [...] },
        "3.7_observability": { "score": 95, "evidence": "JSONL 日誌 + 6 種查詢模式", "files_checked": [...] }
      }
    },
    "7_system_completeness": {
      "weight": 9,
      "score": 93,
      "sub_items": {
        "7.1_feature_completeness": { "score": 94, "evidence": "0 TODO/FIXME，20 Skills，18 自動任務", "files_checked": [...] },
        "7.2_documentation_completeness": { "score": 93, "evidence": "CHANGELOG.md + config/README.md", "files_checked": [...] },
        "7.3_deployment_readiness": { "score": 91, "evidence": "9/9 PS1 使用 $PSScriptRoot", "files_checked": [...] },
        "7.4_test_coverage": { "score": 92, "evidence": "292 個測試，Hook 100% 覆蓋", "files_checked": [...] },
        "7.5_maintainability": { "score": 94, "evidence": "DRY 重構完成，版本追蹤完整", "files_checked": [...] }
      }
    }
  },
  "agent_id": "fetch-audit-dim3-7"
}
```

## 校準標準

- 90-100：企業級（完整測試套件 + CI/CD + 自動化監控）
- 70-89：良好（測試覆蓋 + 結構化日誌 + 版本管理）
- 50-69：基本（部分測試 + 基本日誌）

每個子項必須附具體證據。
