# 項目 3 驗證報告：配置 Schema 驗證

## 完成時間
2026-02-17 20:18（Week 2 Day 1-2 完成）

## 實施內容

### 1. 建立 3 個 JSON Schema 檔案

#### 1.1 cache-policy.schema.json（78 行）
- **位置**：`config/schemas/cache-policy.schema.json`
- **用途**：驗證 `config/cache-policy.yaml` 的結構
- **功能**：
  - 驗證 version、cache_dir、degradation_max_age_hours 必填欄位
  - 驗證 sources 物件結構（file, ttl_minutes, degraded_ttl_minutes）
  - TTL 範圍驗證（1-10080 分鐘，即 1 週上限）
  - 檔案路徑格式驗證（必須 .json 結尾）

#### 1.2 routing.schema.json（185 行）
- **位置**：`config/schemas/routing.schema.json`
- **用途**：驗證 `config/routing.yaml` 的三層路由規則
- **功能**：
  - 驗證 pre_filter、label_routing 結構
  - 驗證 task_type_labels（任務類型覆寫規則）
  - 驗證 template_resolution（模板優先級順序）
  - 驗證 modifier_labels（修飾標籤行為）
  - 驗證 mappings（^標籤 → skills/tools/template 映射）
  - **特殊處理**：priority_order 使用 additionalProperties（支援 YAML 數字 key）

#### 1.3 frequency-limits.schema.json（154 行）
- **位置**：`config/schemas/frequency-limits.schema.json`
- **用途**：驗證 `config/frequency-limits.yaml` 的自動任務頻率配置
- **功能**：
  - 驗證 trigger_modes、selection_strategy、tasks 結構
  - 驗證 autoTask 必填欄位（name, daily_limit, counter_field, template, history_type, execution_order）
  - 驗證可選欄位（skill, skills, description, stages, template_params）
  - daily_limit 範圍驗證（1-20）
  - execution_order 範圍驗證（1-50）
  - **特殊處理**：stages 使用 additionalProperties（支援 YAML 數字 key）

### 2. 擴展 validate_config.py

#### 2.1 新增函式
- `_load_json_schema(schema_path)`: 載入並解析 JSON Schema 檔案
- `_validate_with_json_schema(data, config_name, config_dir)`: 使用 jsonschema 模組驗證配置

#### 2.2 修改現有函式
- `validate_config()`:
  - 回傳值改為 `(errors, warnings, stats)` 三元組
  - 對每個配置檔先嘗試 JSON Schema 驗證，失敗則 fallback 到簡單驗證
  - 統計使用 JSON Schema vs 簡單驗證的數量
- `main()`: 顯示驗證統計資訊

#### 2.3 優雅降級機制
- 若 jsonschema 模組未安裝，自動 fallback 到簡單驗證（不中斷執行）
- 若 schema 檔案不存在，自動 fallback 到簡單驗證
- 若 schema 檔案格式錯誤，記錄警告後 fallback

### 3. 錯誤修正歷程

#### 3.1 錯誤 1：routing.schema.json - priority_order 數字 key 問題
- **現象**：`TypeError: expected string or bytes-like object, got 'int'`
- **根因**：routing.yaml 中 `priority_order` 使用數字 key（1, 2, 3, 4, 5），YAML 解析器將其轉為 Python int，但 JSON Schema 的 `patternProperties` 只接受字串 key 的 regex 匹配
- **修正**：將 `patternProperties` 改為 `additionalProperties`
  ```json
  // 修正前
  "patternProperties": {
    "^[1-9]$": { "type": "string", "pattern": "^templates/.+\\.md$" }
  }

  // 修正後
  "additionalProperties": {
    "type": "string",
    "pattern": "^templates/.+\\.md$"
  }
  ```

#### 3.2 錯誤 2：frequency-limits.schema.json - 缺少 skills/description/stages 欄位
- **現象**：`Additional properties are not allowed ('description', 'skills' were unexpected)`
- **根因**：實際 YAML 檔案中許多任務包含 skills（陣列）、description（說明）、stages（階段定義）等欄位，但 schema 未定義
- **修正**：在 autoTask 定義中新增可選欄位：
  - `skills`: 字串陣列（複數形式）
  - `description`: 字串（任務詳細說明）
  - `stages`: 物件（多階段任務定義）

#### 3.3 錯誤 3：frequency-limits.schema.json - stages 數字 key 問題
- **現象**：與錯誤 1 相同的 `TypeError`
- **根因**：ai_deep_research 的 stages 使用數字 key（1, 2, 3, 4），YAML 解析為 int
- **修正**：將 stages 的 `patternProperties` 改為 `additionalProperties`

## 驗收標準檢查

### 檢查點（Week 2 Day 1-2）

| 檢查項 | 狀態 | 備註 |
|--------|------|------|
| 建立 cache-policy.schema.json | ✅ 完成 | 78 行，Draft-07 標準 |
| 建立 routing.schema.json | ✅ 完成 | 185 行，含 labelMapping 定義 |
| 建立 frequency-limits.schema.json | ✅ 完成 | 154 行，含 autoTask 定義 |
| validate_config.py 支援 JSON Schema 載入 | ✅ 完成 | 新增 _load_json_schema() |
| validate_config.py 支援優雅降級 | ✅ 完成 | jsonschema 缺失時自動 fallback |
| 所有配置檔驗證通過 | ✅ 完成 | 13/13 檢查通過 |
| 統計資訊正確顯示 | ✅ 完成 | 3 個 JSON Schema，10 個簡單驗證 |

## 技術決策

### 1. YAML 數字 key 處理策略
**問題**：YAML 允許數字作為 key，解析後成為 Python int，但 JSON Schema 的 patternProperties 只支援字串 regex 匹配。

**方案 A**（未採用）：在 YAML 中強制使用字串 key（如 "1", "2", "3"）
- 優點：完全符合 JSON Schema 語義
- 缺點：需修改既有配置檔，破壞可讀性

**方案 B**（採用）：schema 使用 additionalProperties 取代 patternProperties
- 優點：相容現有配置檔，無需修改 YAML
- 缺點：無法用 regex 驗證 key 格式（但可驗證 value）
- 權衡：key 格式由人工審查，value 格式由 schema 強制

### 2. 可選欄位的驗證策略
**方案 A**（未採用）：`additionalProperties: true`（允許任意額外欄位）
- 優點：最靈活，向後相容
- 缺點：無法捕捉拼字錯誤

**方案 B**（採用）：明確定義所有可選欄位，`additionalProperties: false`
- 優點：捕捉拼字錯誤，強制一致性
- 缺點：新增欄位需同步更新 schema
- 權衡：嚴格驗證優於靈活性

## 修改統計

| 類型 | 數量 | 詳情 |
|------|------|------|
| 新建 Schema | 3 | cache-policy (78 行) + routing (185 行) + frequency-limits (154 行) = 417 行 |
| 修改檔案 | 1 | validate_config.py (+~120 行) |
| 總新增代碼 | ~537 行 | Schema JSON + Python 邏輯 |
| 修正次數 | 3 | routing priority_order + frequency-limits 欄位缺失 + frequency-limits stages |
| 測試執行 | 4 | 初次測試 + 3 次修正後測試 |

## 後續工作（Week 2 Day 3-5）

### 待完成項目

#### 1. 端到端測試（優先，用戶要求）
- **目標**：驗證 Circuit Breaker 在生產環境的實際效果
- **測試場景**：
  1. 模擬 Todoist API 401 錯誤 → 驗證 Circuit Breaker 記錄失敗
  2. 模擬連續 3 次失敗 → 驗證狀態轉為 open
  3. 等待 5 分鐘 cooldown → 驗證狀態轉為 half_open
  4. 模擬試探成功 → 驗證狀態轉為 closed
  5. 驗證 ntfy 告警（含 trace_id + error details）
  6. 驗證 assembly agent 根據 api-health.json 狀態加降級標記
- **預估時間**：2-3 小時

#### 2. 建立剩餘 12 個 JSON Schema（可選）
完整的 15 個配置檔 schema（目前已完成 3/15）：
- ✅ cache-policy.schema.json
- ✅ routing.schema.json
- ✅ frequency-limits.schema.json
- ⏸️ scoring.schema.json（TaskSense 計分規則）
- ⏸️ notification.schema.json（ntfy 通知配置）
- ⏸️ dedup-policy.schema.json（研究去重策略）
- ⏸️ audit-scoring.schema.json（系統審查計分）
- ⏸️ benchmark.schema.json（系統效能基準）
- ⏸️ health-scoring.schema.json（健康評分權重）
- ⏸️ hook-rules.schema.json（Hooks 規則）
- ⏸️ timeouts.schema.json（超時配置）
- ⏸️ topic-rotation.schema.json（主題輪替）
- ⏸️ pipeline.schema.json（每日摘要管線）
- ⏸️ digest-format.schema.json（摘要排版模板，需特殊處理）
- ⏸️ config.schema.json（.claude/settings.json，Hooks 配置）

#### 3. 降級標記自動加註（可選，~1 小時）
在 assembly prompts 加入判斷邏輯：
- 讀取 api-health.json 檢查各 API 狀態
- 若 state=open 或 half_open，在摘要中加註「⚠️ XXX API 暫時故障，使用快取資料」

#### 4. PowerShell 預檢查（可選，~2 小時）
在 Phase 1 開始前檢查 api-health.json：
- 若 API 為 open 狀態，跳過該 API 的 agent 執行
- 直接使用降級快取，節省執行時間

## 驗證結論

✅ **項目 3 核心功能完成**
- 3 個關鍵配置的 JSON Schema 建立完成
- validate_config.py 成功整合 JSON Schema 驗證
- 優雅降級機制確保向後相容
- 所有配置檔（13/13）驗證通過

🔍 **關鍵技術突破**
- YAML 數字 key 與 JSON Schema 相容性問題的解決方案（additionalProperties）
- 漸進式驗證策略（JSON Schema 優先，簡單驗證 fallback）
- 嚴格欄位定義捕捉拼字錯誤

⏭️ **下一步建議**
1. **優先**：端到端測試 Circuit Breaker（用戶明確要求）
2. **次要**：完成剩餘 12 個 JSON Schema（可依需求逐步實施）
3. **改進**：降級標記自動加註 + PowerShell 預檢查（提升用戶體驗）

**總評**：核心架構已完成，配置驗證機制上線，可進行生產環境測試。
