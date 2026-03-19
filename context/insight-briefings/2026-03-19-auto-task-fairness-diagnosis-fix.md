# 自動任務公平性診斷與修復方案

**日期**: 2026-03-19
**類型**: 深度研究洞察簡報
**系列**: auto-task-fairness (mechanism 階段)

---

## 摘要

本簡報針對系統自動任務公平性退化問題（Gini 係數從 0.517 惡化至 1.993, +285%）進行根因診斷,並提出修復方案。透過內部程式碼分析(run-todoist-agent-team.ps1、todoist-query.md)與業界最佳實踐研究(Weighted Round-Robin、Aging、SWRR),發現當前 round-robin 演算法本身正確,但缺少**飢餓保護機制**與**可觀測性設計**。23 個任務完全未執行,可能因 daily_limit=0 停用或持續被跳過。建議引入 **starvation score**、**weighted round-robin** 與**選任務理由記錄**,並建立 7 天公平性驗證機制。本簡報承接 skill-forge 生成的 task-fairness-analyzer 概念,進入 mechanism 階段:從問題認知深入到根因分析與解決方案設計。

---

## 關鍵洞見

### 1. Round-Robin 演算法本身正確,但缺少飢餓保護

**發現**:
- `todoist-query.md` 步驟 2.5(第 260-274 行)實作的 round-robin 演算法符合標準定義:以 `next_execution_order` 為起點循環掃描,取前 N 個符合條件的任務
- 但**無 aging 機制**:等待時間長的任務不會自動提升優先級
- 無權重系統:所有任務平等對待,無法補償長期未執行任務

**證據要點**:
- 演算法流程:`next_execution_order` → 循環掃描 → 取前 min(max_auto_per_run, 可用數量) 個
- git_push 特殊處理:移到批次末位(避免並行衝突)
- 計算下次起點:`next_execution_order_after = max(selected原始orders) % N + 1`

**業界對比**: [Weighted Round-Robin](https://en.wikipedia.org/wiki/Weighted_round_robin) 是 starvation-free 演算法,任務權重決定 CPU 時間分配比例。[Starvation and Aging in Operating Systems](https://www.geeksforgeeks.org/operating-systems/starvation-and-aging-in-operating-systems/) 指出:作業系統使用 aging 技術逐漸提升等待中任務的優先級,確保公平執行。

---

### 2. 23 個未執行任務可能因 daily_limit=0 被停用

**發現**:
- `config/frequency-limits.yaml` 中 `daily_limit: 0` 的任務視同**停用**(todoist-query.md 第 255 行明確規定)
- `auto-tasks-today.json` 顯示 29 個任務,今日僅 15 個執行過
- system-insight.json 報告:29 個任務中僅 6 個有執行記錄,23 個完全未執行

**證據要點**:
```yaml
# config/frequency-limits.yaml 結構
tasks:
  task_key:
    daily_limit: 2  # > 0 啟用
    daily_limit: 0  # = 0 停用,round-robin 跳過
```

**診斷行動**:需盤點 frequency-limits.yaml 完整清單,確認停用任務數量與重新啟用評估。

---

### 3. 缺少可觀測性,無法診斷跳過原因

**發現**:
- 選任務邏輯無 `skip_reason` 記錄(todoist-query.md 未見相關欄位)
- 無法追蹤:為何某任務連續多次被跳過
- improvement-backlog.json ADR-006 已建議:記錄 selected/skipped/skip_reason/starvation_score

**證據要點**:
- 當前輸出:僅 `selected_tasks` 陣列,無跳過任務列表
- 缺失資訊:跳過原因(達上限 vs. 超時風險 vs. 其他條件)、連續跳過次數、最近執行時間

**業界對比**: [Priority-Based Scheduling](https://www.sciencedirect.com/topics/computer-science/priority-based-scheduling) 強調可觀測性與診斷能力,確保排程決策可追溯。

**改進方向**:
```json
{
  "selected_tasks": [...],
  "skipped_tasks": [
    {"key": "task_a", "reason": "daily_limit_reached", "count": 3, "limit": 3},
    {"key": "task_b", "reason": "timeout_risk", "consecutive_skips": 5}
  ],
  "starvation_warnings": ["task_c (7 天未執行)", "task_d (連續 10 次跳過)"]
}
```

---

### 4. Weighted Round-Robin (WRR) 是業界成熟解法

**發現**:
- **Weighted Round-Robin (WRR)**: 任務權重決定分配比例,防飢餓特性([Wikipedia](https://en.wikipedia.org/wiki/Weighted_round_robin))
- **Smooth Weighted Round-Robin (SWRR)**: 改進版,避免高權重任務壟斷處理器([SuperTinyKernel RTOS](https://en.wikipedia.org/wiki/Weighted_round_robin))
- **DWRR (分散式 WRR)**: 實現本地與全域公平性([Efficient and Scalable Multiprocessor Fair Scheduling](https://www.cs.rice.edu/~vs3/PDF/ppopp.09/p65-li.pdf))

**實作建議**:
```pseudo
# 步驟 1: 計算 starvation score
days_since_last_run = (today - last_executed_date).days
consecutive_skips = count_from_state(failed_auto_tasks.json)
starvation_score = days_since_last_run × (1 + consecutive_skips × 0.2)

# 步驟 2: 計算權重
base_weight = 1.0
weight = base_weight × (1 + starvation_score)

# 步驟 3: Weighted Round-Robin 選取
sorted_by_weight = sort_desc(tasks, by=weight)
selected = sorted_by_weight[0:max_auto_per_run]
```

**關鍵參數**:
- `starvation_score` 閾值:≥ 3.0 觸發警告
- `consecutive_skips` 權重:每次 +0.2 (5 次跳過 = +1.0 權重)
- 最大權重倍率:5x (防止過度補償)

---

### 5. Failed Task Recovery 機制已存在但不完整

**發現**:
- todoist-query.md 第 230-247 行有**失敗任務補跑邏輯**(Failed Task Recovery)
- 觸發條件:`consecutive_count ≥ 1` + `last_failed_at ≤ 24h` + 今日執行資格
- 但僅補跑 1 個任務,且需手動記錄到 `state/failed-auto-tasks.json`

**證據要點**:
```markdown
# todoist-query.md 第 234-243 行
觸發行為（符合條件的 entry，最多取 1 個插入本次任務）：
- 將失敗任務的 task_key **插入 selected_tasks 最前方**
- 優先選 `consecutive_count` 最高者（最嚴重優先）
```

**改進方向**:
- **自動偵測飢餓**:連續 7 天未執行 → 自動加入 failed-auto-tasks.json
- **擴大補跑名額**:1 個 → min(2, max_auto_per_run // 2)
- **結合 starvation score**:飢餓任務自動進入 recovery 佇列

---

## 建議行動

### 即刻執行（P0）

1. **盤點停用任務**
   - 讀取 `config/frequency-limits.yaml` 完整清單
   - 統計 `daily_limit: 0` 的任務數量
   - 評估:哪些需重新啟用,哪些永久停用

2. **建立飢餓偵測腳本**
   ```bash
   # tools/detect-starvation.ps1
   # 輸出:連續 7 天未執行的任務清單
   # 自動寫入 state/failed-auto-tasks.json
   ```

### 短期修復（P1, 1-2 天）

3. **引入 Starvation Score 計算**
   - 在 Phase 1 (todoist-query.md 步驟 2.5) 加入 starvation_score 計算
   - 公式:`days_since_last_run × (1 + consecutive_skips × 0.2)`
   - 記錄到 plan.json:每個任務附帶 starvation_score

4. **加權輪轉修復**
   - 選任務時依 `weight = 1.0 + starvation_score` 排序
   - 保留 round-robin 起點(`next_execution_order`),但優先補償飢餓任務
   - git_push 末位規則維持不變

5. **可觀測性增強**
   - 在 plan.json 加入 `skipped_tasks` 陣列
   - 每個 skipped 記錄:`key`、`reason`、`count`、`limit`、`consecutive_skips`
   - 新增 `starvation_warnings` 陣列(starvation_score ≥ 3.0 的任務)

### 中期完善（P2, 1 週）

6. **7 天公平性驗證腳本**
   ```powershell
   # tools/verify-fairness.ps1
   # 檢查項目:
   # - Gini 係數 ≤ 0.5
   # - idle 任務數 ≤ 5
   # - 每個啟用任務至少執行 1 次
   # 輸出:HTML 報告 + ntfy 告警
   ```

7. **自動化飢餓保護**
   - 每日檢查:`days_since_last_run ≥ 7` → 自動加入 failed-auto-tasks.json
   - Failed Task Recovery 名額:1 → 2
   - 連續記憶整合:步驟 0 的 `recently_failed[]` 自動更新 state

---

## 後續研究方向

1. **進入 application 階段**:實作加權輪轉 PS 程式碼
2. **進入 optimization 階段**:benchmark 公平性演算法效能
3. **進入 synthesis 階段**:與 scheduler-state 整合,建立全域公平性監控

---

## 參考來源

### 內部程式碼
- [run-todoist-agent-team.ps1](D:/Source/daily-digest-prompt/run-todoist-agent-team.ps1) — 第 1-200 行:配置與輔助函數
- [todoist-query.md](D:/Source/daily-digest-prompt/prompts/team/todoist-query.md) — 步驟 2.5(第 249-276 行):round-robin 演算法
- [auto-tasks-today.json](D:/Source/daily-digest-prompt/context/auto-tasks-today.json) — 今日執行狀態:29 任務,15 執行過
- [system-insight.json](D:/Source/daily-digest-prompt/context/system-insight.json) — Gini 係數 1.993, 23 任務 0 次執行
- [improvement-backlog.json](D:/Source/daily-digest-prompt/context/improvement-backlog.json) — ADR-006:可觀測性增強建議

### 業界最佳實踐
- [Weighted round robin - Wikipedia](https://en.wikipedia.org/wiki/Weighted_round_robin) — WRR 基本原理與防飢餓特性
- [Starvation and Aging in Operating Systems - GeeksforGeeks](https://www.geeksforgeeks.org/operating-systems/starvation-and-aging-in-operating-systems/) — Aging 技術與公平性保證
- [Efﬁcient and Scalable Multiprocessor Fair Scheduling](https://www.cs.rice.edu/~vs3/PDF/ppopp.09/p65-li.pdf) — DWRR 分散式公平排程
- [Round Robin Distribution for Fair Task Assignment in Java | Medium](https://medium.com/@puspas99/round-robin-distribution-for-fair-task-assignment-in-java-7ce5fb16bbf1) — Java 實作範例
- [Priority-Based Scheduling - ScienceDirect](https://www.sciencedirect.com/topics/computer-science/priority-based-scheduling) — 優先級排程與可觀測性

### 知識庫參考
- [skill-forge 生成報告：task-fairness-analyzer（2026-03-14）](D:/Source/skills/task-fairness-analyzer/SKILL.md) — 前置研究:Gini 係數監控

---

**生成方式**: insight-briefing Skill (mechanism 階段)
**研究策略**: 系統內部分析 + 業界最佳實踐 WebSearch
**下一階段**: application — 實作加權輪轉與可觀測性增強
