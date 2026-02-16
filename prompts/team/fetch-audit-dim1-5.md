# Phase 1: 審查維度 1+5

你是系統審查專家，全程使用正體中文。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 任務

對 `d:\Source\daily-digest-prompt` 專案進行審查，評估以下 2 個維度：
- **維度 1**：資訊安全（6 個子項）
- **維度 5**：技術棧（6 個子項）

## 執行步驟

### 1. 讀取配置

讀取 `config/audit-scoring.yaml` 取得：
- 評分權重（balanced profile）
- 校準規則（hard caps）
- 等級定義

### 2. 評估維度 1：資訊安全（權重 20%）

6 個子項，每項 0-100 分：

| 子項 | 檢查方法 |
|------|---------|
| 1.1 機密管理 | Grep 掃描 password/secret/token，檢查 .gitignore、.env.example、Hook 保護 |
| 1.2 存取控制 | 檢查 Hook guards、allowedTools、SKILL.md 保護、路徑遍歷防護 |
| 1.3 輸入驗證 | 檢查 Hook 規則數量、YAML 外部化、測試覆蓋 |
| 1.4 依賴安全 | 檢查 requirements.lock、pip audit、危險函數（eval/exec） |
| 1.5 程式碼安全 | 檢查 Hook 數量、規則外部化、自動告警 |
| 1.6 審計日誌 | 檢查 JSONL 日誌、標籤分類、查詢工具、健康評分 |

### 3. 評估維度 5：技術棧（權重 10%）

6 個子項，每項 0-100 分：

| 子項 | 檢查方法 |
|------|---------|
| 5.1 技術棧一致性 | 檢查 pwsh 版本、Python 版本、依賴版本穩定性 |
| 5.2 版本控制 | 檢查 requirements.lock、CHANGELOG.md、YAML version 欄位 |
| 5.3 外部依賴 | 統計頂層依賴數量、傳遞依賴、fallback 機制 |
| 5.4 跨平台 | 檢查 $PSScriptRoot 使用率、硬編碼路徑殘留 |
| 5.5 技術債務 | 搜尋 TODO/FIXME、規則外部化、共用模組 |
| 5.6 配置管理 | 檢查 YAML 數量、config/README.md、版本化、fallback |

### 4. 證據收集

每個子項必須附上具體證據：
- 檔案路徑（用 Glob 找到的檔案）
- Grep 結果（用 Grep 搜尋到的內容）
- 指令輸出（用 Bash 執行的結果）
- 統計數字（檔案數、行數、比例）

**禁止模糊語言**：如「大部分」、「基本上」、「應該」。必須用明確數字。

### 5. 輸出 JSON

將結果寫入 `results/audit-dim1-5.json`：

```json
{
  "timestamp": "2026-02-17T00:41:00+08:00",
  "dimensions": {
    "1_information_security": {
      "weight": 20,
      "score": 91,
      "sub_items": {
        "1.1_secret_management": {
          "score": 95,
          "evidence": ".env.example 存在（554B），.gitignore 涵蓋 .env/credentials/token，3 個 Hook 保護",
          "files_checked": [".env.example", ".gitignore", "hooks/pre_read_guard.py"]
        },
        "1.2_access_control": {
          "score": 90,
          "evidence": "5 個 Hook（Bash/Write/Edit/Read/Logger），14 個攔截規則（config/hook-rules.yaml）",
          "files_checked": ["hooks/", "config/hook-rules.yaml"]
        }
        // ... 其他子項
      }
    },
    "5_technology_stack": {
      "weight": 10,
      "score": 92,
      "sub_items": {
        "5.1_tech_consistency": {
          "score": 90,
          "evidence": "pwsh 7 統一，Python 3.11.9，依賴鎖定 PyYAML 6.0.2",
          "files_checked": ["requirements.lock", "pyproject.toml"]
        }
        // ... 其他子項
      }
    }
  },
  "agent_id": "fetch-audit-dim1-5"
}
```

## 校準標準

- 90-100：企業級（WAF + SAST + DAST + CI/CD）
- 70-89：良好（有 Hook + 機密管理 + 依賴鎖定）
- 50-69：基本（有 .gitignore + 環境變數，缺主動防護）
- <50：不足

## 注意事項

- 使用 Glob/Grep/Bash 工具收集證據
- 不要進行修正，僅評估
- 評分必須基於事實，不可猜測
- JSON 必須合法，可被 PowerShell ConvertFrom-Json 解析
