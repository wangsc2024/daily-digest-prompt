# Phase 1: 審查維度 2+6

你是系統審查專家，全程使用正體中文。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 任務

對 `d:\Source\daily-digest-prompt` 專案進行審查，評估以下 2 個維度：
- **維度 2**：系統架構（6 個子項）
- **維度 6**：系統文件（5 個子項）

## 執行步驟

### 1. 讀取配置

讀取 `config/audit-scoring.yaml` 取得評分規則。

### 2. 評估維度 2：系統架構（權重 18%）

| 子項 | 檢查方法 |
|------|---------|
| 2.1 關注點分離 | 分析目錄結構（config/templates/skills/hooks/prompts），各層職責單一性 |
| 2.2 配置外部化 | 統計 config/ 覆蓋率，檢查 timeouts.yaml 是否被 PS1 使用 |
| 2.3 耦合度 | 分析模組間引用（Skills 是否零依賴，hooks 共用模組） |
| 2.4 可擴展性 | 檢查 task-manager Skill、標準化新增流程 |
| 2.5 容錯設計 | 檢查重試、降級、錯誤邊界、back-pressure |
| 2.6 DRY | Grep 搜尋 preamble.md 引用率，檢查 nul 禁令殘留 |

### 3. 評估維度 6：系統文件（權重 10%）

| 子項 | 檢查方法 |
|------|---------|
| 6.1 架構文件 | 檢查 CLAUDE.md、specs/system-docs/（SRD/SSD/ops-manual） |
| 6.2 操作手冊 | 檢查操作指南完整度（ops-manual 章節數） |
| 6.3 API 文件 | 檢查 SKILL.md 標準化 frontmatter（20/20）|
| 6.4 配置說明 | 檢查 config/README.md 覆蓋率，YAML 注釋率 |
| 6.5 變更記錄 | 檢查 CHANGELOG.md、git log 格式一致性 |

### 4. 輸出 JSON

寫入 `results/audit-dim2-6.json`：

```json
{
  "timestamp": "2026-02-17T00:41:00+08:00",
  "dimensions": {
    "2_system_architecture": {
      "weight": 18,
      "score": 84,
      "sub_items": {
        "2.1_separation_of_concerns": { "score": 90, "evidence": "...", "files_checked": [...] },
        "2.2_config_externalization": { "score": 78, "evidence": "...", "files_checked": [...] },
        "2.3_coupling": { "score": 85, "evidence": "...", "files_checked": [...] },
        "2.4_scalability": { "score": 88, "evidence": "...", "files_checked": [...] },
        "2.5_fault_tolerance": { "score": 82, "evidence": "...", "files_checked": [...] },
        "2.6_dry": { "score": 88, "evidence": "preamble.md 引用率 88.5% (46/52)，nul 禁令殘留 3 處", "files_checked": ["prompts/team/", "templates/"] }
      }
    },
    "6_system_documentation": {
      "weight": 10,
      "score": 88,
      "sub_items": {
        "6.1_architecture_docs": { "score": 92, "evidence": "...", "files_checked": [...] },
        "6.2_operation_manual": { "score": 90, "evidence": "...", "files_checked": [...] },
        "6.3_api_docs": { "score": 85, "evidence": "20/20 Skills 標準化 frontmatter", "files_checked": ["skills/*/SKILL.md"] },
        "6.4_config_docs": { "score": 78, "evidence": "config/README.md 覆蓋 13/15 配置檔", "files_checked": ["config/README.md"] },
        "6.5_changelog": { "score": 85, "evidence": "CHANGELOG.md 存在（51 行），67% 提交符合格式", "files_checked": ["CHANGELOG.md"] }
      }
    }
  },
  "agent_id": "fetch-audit-dim2-6"
}
```

## 校準標準

- 90-100：企業級（微服務架構 + API Gateway + 完整文檔）
- 70-89：良好（模組化清晰 + 配置外部化 + 結構化文檔）
- 50-69：基本（有分層 + 基本文檔，耦合度高）

每個子項必須附具體證據（檔案路徑、Grep 結果、統計數字）。
