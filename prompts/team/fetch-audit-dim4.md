# Phase 1: 審查維度 4

你是系統審查專家，全程使用正體中文。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## 任務

對 `d:\Source\daily-digest-prompt` 專案進行審查，評估維度 4：系統工作流（5 個子項）。

## 執行步驟

### 1. 評估維度 4：系統工作流（權重 15%）

| 子項 | 檢查方法 |
|------|---------|
| 4.1 CI/CD | 檢查 HEARTBEAT.md、setup-scheduler.ps1、$PSScriptRoot 使用率 |
| 4.2 環境隔離 | 檢查虛擬環境、requirements.lock、配置管理 |
| 4.3 失敗恢復 | 檢查重試邏輯、指數退避、快取降級、config/timeouts.yaml |
| 4.4 日誌追蹤 | 檢查 scheduler-state.json、digest-memory.json、JSONL 日誌 |
| 4.5 團隊模式 | 檢查並行腳本數量、動態 timeout、team prompts 數量 |

### 2. 輸出 JSON

寫入 `results/audit-dim4.json`：

```json
{
  "timestamp": "2026-02-17T00:41:00+08:00",
  "dimensions": {
    "4_system_workflow": {
      "weight": 15,
      "score": 96,
      "sub_items": {
        "4.1_cicd": {
          "score": 88,
          "evidence": "HEARTBEAT.md 批次建立 + $PSScriptRoot",
          "files_checked": ["HEARTBEAT.md", "setup-scheduler.ps1"]
        },
        "4.2_environment_isolation": {
          "score": 95,
          "evidence": "requirements.lock + 15 YAML 配置外部化",
          "files_checked": ["requirements.lock", "config/"]
        },
        "4.3_failure_recovery": {
          "score": 98,
          "evidence": "retry + 指數退避 + jitter + 快取降級（24h）+ config/timeouts.yaml",
          "files_checked": ["run-*.ps1", "config/timeouts.yaml"]
        },
        "4.4_logging_tracking": {
          "score": 96,
          "evidence": "scheduler-state.json（200 筆滾動）+ JSONL 日誌 + Session 隔離",
          "files_checked": ["state/scheduler-state.json", "logs/structured/"]
        },
        "4.5_team_mode": {
          "score": 98,
          "evidence": "3 個團隊腳本 + 26 team prompts + 動態 timeout（按任務類型）",
          "files_checked": ["run-*-team.ps1", "prompts/team/"]
        }
      }
    }
  },
  "agent_id": "fetch-audit-dim4"
}
```

## 校準標準

- 90-100：企業級（完整 CI/CD + 多環境 + 自動化部署 + 監控告警）
- 70-89：良好（排程自動化 + 失敗恢復 + 日誌追蹤）
- 50-69：基本（手動部署 + 簡單日誌）

每個子項必須附具體證據（檔案路徑、Grep 結果、統計數字）。
