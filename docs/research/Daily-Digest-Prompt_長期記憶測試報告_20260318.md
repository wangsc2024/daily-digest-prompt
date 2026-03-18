# Daily-Digest-Prompt 長期記憶測試報告

日期：2026-03-18

## 測試範圍

- 每日摘要寫入長期記憶
- 30 天內摘要檢索
- research-registry / continuity 壓縮
- daily / weekly / monthly scheduler 判定
- 100 筆摘要高負載寫入與檢索延遲
- 1,000,000 筆合成索引檢索延遲

## 測試案例

| 編號 | 案例 | 驗證內容 | 結果 |
|---|---|---|---|
| T1 | 摘要 note 建構 | `taskType`、`retrievalHints`、`memoryLayer`、`digestDate` 正確生成 | 通過 |
| T2 | 同日摘要去重更新 | `sync_note()` 命中既有 `digestDate` 時更新原 note id | 通過 |
| T3 | 同步狀態回寫 | `context/digest-memory.json.long_term_memory` 正確更新 | 通過 |
| T4 | 30 天檢索參數 | `taskType`、`taskTags`、`startDate/endDate`、`recencyHalfLifeDays` 正確傳入 | 通過 |
| T5 | 舊研究壓縮 | `research-registry.json` 舊條目轉 `archived_summaries` | 通過 |
| T6 | continuity 自壓縮 | 超過 `max_runs` 的歷史轉 `compressed_history` | 通過 |
| T7 | 三層記憶摘要 | `daily` 摘要可生成結構化 summary，支援多階段檢索 | 通過 |
| T8 | 過期淘汰 | daily 過期刪除、monthly 保留 | 通過 |
| T9 | scheduler 觸發 | 依時間窗與訊息量雙條件判定 | 通過 |
| T10 | 100 筆高負載 | 100 筆摘要寫入與檢索 p95 延遲 < 200ms | 通過 |
| T11 | metadata filter | `topic/taskType/tag/date` 過濾後只返回符合結果 | 通過 |
| T12 | 1M 合成索引檢索 | 1,000,000 筆資料候選收斂後 p95 < 200ms | 通過 |

## 執行命令

```powershell
python -m pytest tests/tools/test_digest_sync.py tests/tools/test_long_term_memory.py tests/test_memory_long_term_optimization.py tests/test_digest_scheduler.py tests/test_long_term_memory_perf.py --cov=tools.digest_sync --cov=tools.long_term_memory --cov=memory.long_term_memory --cov=digest_scheduler --cov-report=term-missing
python scripts/long_term_memory_perf.py
```

## 執行結果

### 單元與整合測試

- 測試結果：`23 passed`
- 重新驗證時間：`2026-03-18`
- 關鍵路徑 coverage：
  - `tools.digest_sync.py`：99%
  - `tools.long_term_memory.py`：84%
  - `memory.long_term_memory.py`：95%
  - `digest_scheduler.py`：88%
  - 合計：93%

### 高負載測試

```json
{
  "write_search_smoke": {
    "summary_count": 100,
    "write_avg_ms": 0.089,
    "write_p95_ms": 0.132,
    "search_avg_ms": 3.045,
    "search_p95_ms": 3.396,
    "within_200ms": true
  },
  "million_scale_retrieval": {
    "record_count": 1000000,
    "hot_bucket_size": 256,
    "search_avg_ms": 0.031,
    "search_p95_ms": 0.164,
    "candidate_count": 257,
    "within_200ms": true
  }
}
```

## 失敗與限制

- `knowledge-base-search` 的 Vitest 尚未執行，原因是目前工作區未安裝 `knowledge-base-search/node_modules`，`vitest` 不存在。
- 外部原始頁面 `know-w.pages.dev` 仍無法直接連線；本次依本機知識庫已匯入副本進行比對與實作。
- 依 `cursor-cli` 工作流建立任務檔後，實際執行 `agent -p` 仍回傳 `Error: [internal]`；因此本次保留 CLI fallback 紀錄，改以本機知識庫與既有研究文件完成驗證。
- 1M 驗證目前為「合成索引 benchmark」，尚未覆蓋完整 knowledge-base-search 端到端部署拓撲。

## 結論

- 驗收中的每日摘要寫入、30 天檢索、高負載延遲與關鍵路徑 coverage 已達標。
- Node 端 API 測試檔已同步更新，但需待安裝依賴後再執行 Vitest 完成最終補驗。
