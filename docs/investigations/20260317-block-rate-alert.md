# 調查報告：2026/3/17 系統洞察 block_rate 警報

**時間**：2026-03-17 14:41（Priority 5 警報）  
**現象**：block_rate 從 0.06% 暴增至 6.35%（+100 倍），avg_io_per_call 從 8998 反彈至 10673（+18.6%）。

## 結論摘要

- **block_rate 暴增為誤報**：實際 7 天 JSONL 統計為 **blocked=13～14、total≈21k、block_rate≈0.06%**，與「前次」趨勢一致；報告中的 1085 / 17096（6.35%）為**錯誤數據**。
- **根因**：系統洞察由 **LLM 手動從 JSONL 解讀並填寫** `blocked_count` / `total_tool_calls`，易受日誌內容干擾。日誌中多處出現數字 **「1085」**（如 summary 的 `(1085 chars)`、時間戳小數如 `.321085`），高度懷疑被誤當成 `blocked_count` 或混入計算，導致 1085 被寫入報告。
- **avg_io_per_call 反彈**：屬正常波動或不同取樣（例如 7 天平均 vs 前次基準），非本次調查重點；若需可再單獨比對 behavior-patterns / 輸出長度分佈。

## 證據

### 1. 當前 7 天 JSONL 真實統計（與 query_logs 一致）

| 來源 | total | blocked | block_rate |
|------|-------|---------|------------|
| `uv run python hooks/query_logs.py --blocked --days 7` | 13 筆為 blocked | 13 | - |
| 本機 Python 遍歷 7 天 `logs/structured/*.jsonl`（event=blocked 或 tags 含 blocked） | 21,103 | 13 | **0.0006** |
| 以 collect_system_data 日期範圍（END_DATE=2026-03-16）重算 | 20,806 | 14 | **0.0007** |

### 2. 報告中的錯誤數字

- `context/system-insight.json`（generated_at: 2026-03-17T14:18）：
  - `statistics.total_tool_calls`: **17,096**
  - `statistics.blocked_count`: **1,085**
  - `metrics.block_rate`: **0.0635**（6.35%）

與上面真實統計明顯不符：blocked 應為十餘筆，不可能是 1085。

### 3. 日誌中「1085」的出現

- 多筆 JSONL 的 **summary** 含 `(1085 chars)`（例如 Write 寫入檔案的輸出長度摘要）。
- 多筆 **ts** 時間戳小數部分含子字串 `1085`（如 `...T03:34:42.321085+08:00`）。
- 若 LLM 在閱讀原始日誌時，把某處的「1085」誤當成 blocked 相關計數並寫入 `blocked_count`，即可解釋 1085 與 6.35% 的誤報。

### 4. 攔截事件實際內容（正常防護）

近 7 天 13 筆 blocked 事件分佈合理，多為既有 Hook 防護：

- **exfiltration-guard**：禁止用 `$()` 外洩 .env（如 Todoist token）
- **traversal-guard**：寫入專案外路徑（如 `D:\tmp\...`、`temp_krs_query.json` 路徑解析問題）
- **state-guard**：禁止 Agent 寫入 `scheduler-state.json`
- **env-guard**：禁止讀取敏感環境變數
- **secret-guard**：禁止寫入 `.env`

無證據顯示「Hook 規則誤攔截」或系統行為異常；block_rate 暴增來自**指標計算錯誤**，非真實攔截率上升。

## 建議措施

1. **改由腳本產出 block_rate / blocked_count（建議立即做）**
   - 在 `tools/collect_system_data.py` 的 JSONL 統計中，明確產出：
     - `blocked_count`：`event == "blocked"` 或 `"blocked" in tags` 的筆數
     - `block_rate`：`blocked_count / total_calls`（total_calls 僅計算同一批 JSONL 的總行數）
   - 系統洞察 Agent 改為**優先讀取該腳本產出的 JSON**，並將上述欄位寫入 `context/system-insight.json`，**禁止從原始 JSONL 自行推斷** blocked_count。
2. **修正當前報告（可選）**
   - 若需即時消除誤報：手動或腳本將 `context/system-insight.json` 的 `blocked_count` / `total_tool_calls` / `block_rate` 改為上表真實值，並調整對應 `alerts`、`trends`、`summary`。
3. **avg_io_per_call**
   - 維持由 behavior-patterns / 既有邏輯計算；若日後要避免類似波動，可改為由同一腳本一併產出並寫入報告。

## 相關檔案

- `context/system-insight.json` — 當次錯誤報告
- `skills/system-insight/SKILL.md` — block_rate 定義（blocked 標籤 / 總呼叫數，≤2%）
- `hooks/query_logs.py` — `--blocked` 可查真實攔截明細
- `tools/collect_system_data.py` — 建議在此產出 blocked_count / block_rate
