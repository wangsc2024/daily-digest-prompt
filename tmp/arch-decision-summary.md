# 架構決策資料準備報告

**生成時間**: 2026-03-23
**資料來源**: improvement-backlog.json + adr-registry.json

## 📊 統計摘要

| 指標 | 數量 |
|------|------|
| Backlog 項目總數 | 42 |
| 有 pattern 的項目 | 17 |
| 已有對應 ADR 的項目 | 10 |
| 需要建立新 ADR 的項目 | 7 |
| ADR 記錄總數 | 41 |
| 無 pattern 項目（需人工評估） | 25 |

## 🆕 需要建立 ADR 的項目（7 項）

### 🔴 高優先級（2 項）

1. **cache_hit_ratio_optimization** - 工作量 medium
   - 描述：依據最佳實踐（Cachefly、Redis Blog、Medium），將快取命中率從 22.7% 提升至 40%+。採用 TTL 分層策略（高頻端點 4-8h、中頻 2-4h）、新增 stale-while-revalidate 機制、進行 per-endpoint 分析並形成閉環監控。

2. **time_based_failure_diagnosis** - 工作量 medium
   - 描述：針對 7 點、13 點高失敗時段（成功率 87.5%）進行根因分析。依據 Dynatrace、JAMS、GeeksforGeeks 的最佳實踐，採用集中化日誌、趨勢分析、三層監控（alerts + logging + metrics）識別外部 API 不穩定、資源競爭等根因，並建立預防機制。

### 🟡 中優先級（1 項）

3. **task_scheduling_fairness** - 工作量 high
   - 描述：針對自動任務飢餓問題（18 個零執行任務、fairness_stddev=1.371），依據 Wikipedia、GeeksforGeeks、Grokipedia 的排程理論，從純 round-robin 升級為 Weighted Round-robin + Aging 機制，消除任務飢餓並將 fairness_stddev 降至 <0.5。

### ⚪ 其他優先級（4 項）

4. **TODO/FIXME 持續清理** - P1, 工作量 low
   - 369 處 TODO/FIXME 分佈 76 檔案（Markdown 佔 30 檔）。建議定期清理規劃性 TODO 或轉入 tech-debt-backlog。

5. **測試覆蓋率門檻提升** - P2, 工作量 high
   - 覆蓋率門檻 44% 偏低（1086 測試），建議逐步提升至 60%。hook_utils 復用率 63.6% 可提升至 80%+。

6. **YAML 注釋密度持續提升** - P2, 工作量 low
   - YAML 注釋密度 10.6%-13.2%，低於 20% 目標。關鍵配置檔案需補充說明注釋。

7. **Context Budget Guard 強制化** - P0, 工作量 medium
   - avg_io_per_call 達 24875 chars，遠高於 benchmark 的 5000。建議把 Context 保護從提示規則提升為可量測、可拒絕、可降級的執行守門機制。

## ✅ 已有對應 ADR 的項目（10 項）

所有已匹配的項目皆為 **Accepted** 狀態，實施狀態為 **done**：

1. ADR-20260318-025: 跨平台路徑硬編碼清理
2. ADR-20260318-026: 輸入驗證強化
3. ADR-20260318-027: 自動任務公平輪轉修復
4. ADR-20260318-028: Phase 2 快照恢復與故障續跑
5. ADR-20260319-029: 快取命中率調優與自適應 TTL 治理
6. ADR-20260319-030: 統一 execution trace schema 與因果追蹤
7. ADR-20260319-031: 宣告式 hook registry 與 stage 化 guard 鏈
8. ADR-20260320-032: 每日成功率根因分類與 SLO/Error Budget 治理
9. ADR-20260320-033: Machine-readable Skill Registry 與 Schema 驗證
10. ADR-20260320-034: Prompt/模板版本追蹤與結果對映

## 📋 ADR 現況分析

### 狀態分佈
- **Accepted**: 39 項
- **Deferred**: 1 項
- **Wontfix**: 1 項

### 實施狀態分佈
- **done**: 40 項
- **declined**: 1 項

## 🎯 建議行動

### 立即處理（高優先級）
1. 為 `cache_hit_ratio_optimization` 建立 ADR（快取命中率優化）
2. 為 `time_based_failure_diagnosis` 建立 ADR（時段性失敗診斷）

### 短期規劃（中優先級）
3. 為 `task_scheduling_fairness` 建立 ADR（任務排程公平性）

### 長期改善
4. 評估 25 個無 pattern 的 backlog 項目，決定是否需要建立 pattern 並納入 ADR 追蹤
5. 持續清理技術債務（TODO/FIXME）
6. 提升測試覆蓋率與配置文件注釋密度

## 📁 完整資料位置

- **詳細匹配資料**: `D:\Source\daily-digest-prompt\tmp\arch-decision-data.json`
- **本摘要報告**: `D:\Source\daily-digest-prompt\tmp\arch-decision-summary.md`
