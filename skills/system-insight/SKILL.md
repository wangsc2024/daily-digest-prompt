---
name: system-insight
version: "1.2.0"
description: |
  系統自省引擎。分析 Agent 執行品質、Skill 使用頻率、失敗模式，產出結構化洞察報告。
  Use when: 系統分析、執行報告、效能分析、Skill 使用統計、健康檢查、洞察趨勢。
allowed-tools: Read, Write, Bash, Glob, Grep
cache-ttl: N/A
triggers:
  - "系統分析"
  - "執行報告"
  - "效能分析"
  - "Skill 使用統計"
  - "健康檢查"
  - "system-insight"
  - "自省"
  - "洞察"
  - "趨勢分析"
  - "統計報告"
  - "執行品質"
depends-on:
  - "ntfy-notify"
---

# System Insight Skill（系統自省引擎）

分析 Agent 執行品質，產出結構化洞察報告至 `context/system-insight.json`。

## 執行步驟

### 步驟 1：收集原始資料
用 Read/Bash 讀取以下資料源：

1. **JSONL 日誌**（`logs/structured/YYYY-MM-DD.jsonl`）
   - 統計各工具呼叫次數
   - 統計 tags 分佈（api-call, cache-read, skill-read, error, blocked 等）
   - 計算 session 平均耗時

2. **scheduler-state.json**（`state/scheduler-state.json`）
   - 近 7 天成功/失敗比率
   - 高失敗率時段識別（哪些小時失敗最多）

3. **auto-tasks-today.json**（`context/auto-tasks-today.json`）
   - 各自動任務完成率
   - 計算各任務平均每日消耗 slots

4. **research-registry.json**（`context/research-registry.json`）
   - 主題多樣性指數（unique topics / total entries）
   - 近 7 天新增主題分佈

### 步驟 2：計算洞察指標

| 指標 | 計算方式 | 健康門檻 |
|------|---------|---------|
| daily_success_rate | 成功 runs / 總 runs（近 7 天） | >= 90% |
| skill_usage_coverage | 被使用的 Skill 數 / 總 Skill 數 | >= 70% |
| cache_hit_ratio | cache-read / (cache-read + api-call) | >= 40% |
| error_rate | error 標籤 / 總呼叫數 | <= 5% |
| block_rate | blocked 標籤 / 總呼叫數 | <= 2% |
| topic_diversity | unique topics / total research entries | >= 0.5 |
| auto_task_fairness | stddev(task_counts) / mean(task_counts) | <= 0.5 |

### 步驟 3：產出報告
用 Write 建立 `context/system-insight.json`：

```json
{
  "version": 1,
  "generated_at": "ISO timestamp",
  "period_days": 7,
  "metrics": {
    "daily_success_rate": 0.95,
    "skill_usage_coverage": 0.80,
    "cache_hit_ratio": 0.55,
    "error_rate": 0.02,
    "block_rate": 0.01,
    "topic_diversity": 0.65,
    "auto_task_fairness": 0.3
  },
  "alerts": [
    {"level": "warning", "metric": "cache_hit_ratio", "value": 0.35, "threshold": 0.40}
  ],
  "recommendations": [
    "快取命中率偏低，建議檢查 TTL 設定"
  ],
  "skill_heatmap": {
    "todoist": 45,
    "api-cache": 38,
    "knowledge-query": 12
  },
  "high_failure_hours": [3, 4]
}
```

### 步驟 4：異常時通知
若有 critical 等級的 alert → 透過 ntfy 發送系統洞察警告。

## 錯誤處理
- 若 JSONL 日誌不存在或為空 → 跳過該資料源，metrics 中標記 `"data_source": "partial"`
- 若 scheduler-state.json 不存在 → daily_success_rate 設為 null，加入 alert
- 若 auto-tasks-today.json 或 research-registry.json 不存在 → 對應指標設為 null
- 所有 JSON 解析失敗 → 記錄錯誤、跳過該來源，不中斷整體分析

## 注意事項
- 僅讀取日誌和狀態檔案，不修改任何配置
- scheduler-state.json 為唯讀（由 PowerShell 腳本維護）
- 報告每日最多產生 1 次，避免重複分析
