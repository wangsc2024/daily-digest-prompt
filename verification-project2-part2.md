# 項目 2 Part 2 驗證報告：Circuit Breaker 整合

## 完成時間
2026-02-17 19:54（Week 2 Day 1-2 完成）

## 實施內容

### 1. 修改 3 個 Assembly Prompts

#### 1.1 assemble-digest.md
- **位置**：步驟 1 與步驟 2 之間插入「步驟 1.5：更新 API 健康狀態」
- **功能**：
  - 讀取今日結構化日誌（logs/structured/YYYY-MM-DD.jsonl）
  - 建立 Python 腳本 update_circuit_breaker.py
  - 統計各 API（todoist, pingtung-news, hackernews, gmail）的呼叫結果
  - 呼叫 agent_guardian.CircuitBreaker 更新狀態
  - 清理暫存檔
- **程式碼行數**：+58 行

#### 1.2 todoist-assemble.md
- **位置**：步驟 1.5 之後插入「步驟 1.6：更新 API 健康狀態」
- **功能**：使用內嵌 Python one-liner 更新 todoist API 狀態
- **程式碼行數**：+20 行

#### 1.3 assemble-audit.md
- **位置**：Step 1 與 Step 2 之間插入「Step 1.5：更新 API 健康狀態」
- **功能**：架構一致性保留（系統審查不呼叫外部 API，實際跳過）
- **程式碼行數**：+8 行

### 2. 修正 Python 指令

**問題**：Windows Store 的 `python3` 是空殼（exit code 49）
**修正**：所有 assembly prompts 改用 `python`（非 `python3`）
**依據**：MEMORY.md 記錄「Hooks 必須用 `python`（非 `python3`）」

### 3. 建立驗證測試

#### 3.1 test_circuit_breaker.py（基礎功能測試）
- **測試場景**：
  1. 初始化（所有 API 為 closed）
  2. 連續 3 次失敗 → 轉為 open
  3. cooldown 檢查（未過期保持 open）
  4. cooldown 過期 → 轉為 half_open
  5. 試探成功 → 轉為 closed
  6. 失敗計數重置驗證
  7. 多個 API 來源測試
- **結果**：✅ 所有測試通過

#### 3.2 assembly 腳本整合測試
- **測試資料**：logs/structured/test-circuit-breaker.jsonl
  - todoist: 2 次呼叫（1 成功 + 1 network_error 失敗）
  - pingtung-news: 1 次呼叫（server_error 失敗）
  - hackernews: 1 次呼叫（成功）
- **執行結果**：
  ```
  Updated todoist: 2 calls, last=False
  Updated pingtung-news: 1 calls, last=False
  Updated hackernews: 1 calls, last=True
  ```
- **狀態檔案驗證**：
  - todoist: state=closed, failures=1（未達 3 次閾值）
  - pingtung-news: state=closed, failures=1
  - hackernews: state=closed, failures=0
  - gmail: state=closed, failures=0（初始化）
- **結果**：✅ Circuit Breaker 狀態正確更新

## 驗收標準檢查

### 檢查點 3（Week 2 Day 1-2）

| 檢查項 | 狀態 | 備註 |
|--------|------|------|
| Phase 2 assembly agent 讀取 api-health.json，open 狀態跳過 API | ⏸️ 待實施 | 簡化方案：Phase 2 只更新狀態，不事先跳過 |
| 摘要含降級標記「⚠️ XXX API 暫時故障，使用快取資料」 | ⏸️ 待實施 | 需在 assembly prompt 加入判斷邏輯 |
| ntfy 收到 401 告警（含 trace_id + error details） | ⏸️ 待測試 | 需端到端測試 |
| half_open 狀態試探成功後轉 closed | ✅ 通過 | test_circuit_breaker.py 驗證 |
| Circuit Breaker 狀態正確更新 | ✅ 通過 | assembly 腳本整合測試驗證 |

## 實施決策變更

### 簡化方案採用

**原計畫**：
1. PowerShell 在 Phase 1 開始前檢查 api-health.json → 跳過 open 狀態的 agent
2. Phase 2 assembly agent 更新 api-health.json

**實際實施**（簡化方案）：
1. Phase 1：正常執行（可能失敗），post_tool_logger.py 記錄錯誤到 JSONL
2. Phase 2：
   - 讀取 JSONL 並更新 api-health.json
   - 根據 result files 的 status 和 source 欄位判斷是否加降級標記
3. 未來改進（可選）：在 PowerShell 層面加入 circuit breaker 預檢查

**理由**：
1. 降低實施複雜度（不需修改 PowerShell 腳本）
2. Circuit Breaker 狀態在「這次執行」更新，「下次執行」生效
3. 現有的 result file 降級標記機制已足夠（cache_degraded, failed）

## 修改統計

| 類型 | 數量 | 詳情 |
|------|------|------|
| 修改檔案 | 3 | assemble-digest.md (+58), todoist-assemble.md (+20), assemble-audit.md (+8) |
| 新建檔案 | 2 | test_circuit_breaker.py (145 行), verification-project2-part2.md |
| 測試日誌 | 1 | logs/structured/test-circuit-breaker.jsonl (4 筆模擬記錄) |
| 總程式碼 | +86 行 | assembly prompts 新增邏輯 |

## 後續工作（Week 2 Day 3-5）

### 待完成項目
1. **降級標記邏輯**：在 assembly prompts 加入判斷，根據 api-health.json 狀態加註「⚠️ API 暫時故障」
2. **端到端測試**：
   - 模擬 Todoist 401 錯誤 → 驗證 ntfy 告警
   - 模擬連續 3 次失敗 → 驗證 circuit breaker 轉 open
   - 驗證 half_open 試探機制
3. **項目 3 實施**：建立 15 個 JSON Schema 檔案

## 驗證結論

✅ **項目 2 Part 2 核心功能完成**
- Circuit Breaker 狀態管理正常運作
- Assembly prompts 成功整合更新邏輯
- Python 指令修正為 Windows 相容版本

⏸️ **待優化功能**
- PowerShell 預檢查（Phase 1 跳過 open API）
- 降級標記自動加註
- 告警機制端到端測試

**總評**：核心架構已完成，可進行項目 3 的 JSON Schema 驗證實施。
