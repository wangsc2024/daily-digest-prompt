# Daily-Digest-Prompt 長期記憶優化報告

日期：2026-03-17  
專案：`D:\Source\daily-digest-prompt`

## 1. 原始資料取得狀態

- 目標網址：`https://know-w.pages.dev/article/ai-agent-context-management-%E8%88%87--8fb70bab#七-daily-digest-prompt-專案的應用場景`
- 已實際嘗試：
  - `WebSearch / Open`：無法取得內容
  - `Invoke-WebRequest`：失敗，錯誤為「嘗試存取通訊端被拒絕，因為存取權限不足」
  - `curl.exe -L`：失敗，錯誤為 `Could not connect to server`
  - `agent -p`：依 `temp/cursor-cli-task-long-term-memory.md` 執行，回傳 `Error: [internal]`
- 結論：**本次未取得外部網路來源全文**，因此無法保存原文快照。以下整理採用：
  - 專案內既有 prompt / Skill / 測試 / README
  - repo 內先前同題報告
  - 已實作程式碼的實際能力

## 2. 文章建議對應整理（以 repo 內既有建議與實作語意還原）

由 `prompts/team/assemble-digest.md`、`skills/digest-memory/SKILL.md`、`knowledge-base-search/README.md`
可還原本專案對長期記憶的核心要求如下：

| 建議 | 核心概念 | 預期效益 |
|---|---|---|
| 每日摘要自動寫回長期記憶 | 將 `digest-memory.json` 摘要同步到可檢索知識庫 | 避免每日摘要只停留在單次執行狀態 |
| 分層記憶 | 區分近期記憶與遠期記憶 | 降低檢索成本，保留近期高相關內容 |
| 檢索需帶主題/時間/關鍵字 | 不只做向量比對，還要可精準過濾 | 提升取回正確性與可控性 |
| 長期記憶需要生命週期欄位 | 加入 `topic`、`importance`、`expiresAt`、`accessCount` | 支援淘汰、排序與後續治理 |
| 舊上下文要壓縮，不是直接丟棄 | `research-registry` / continuity 舊資料摘要化 | 控制 context 膨脹，保留歷史趨勢 |
| 寫入需有錯誤處理與重試 | 健康檢查、去重、重試、指數退避 | 提高長期運行穩定性 |

### 與短期記憶 / 即時摘要的差異

- 短期記憶：`context/digest-memory.json`、`state/*.json`，偏執行狀態與 streak。
- 長期記憶：`knowledge-base-search` 的 `data/long_term_memory.json` 與 `/api/search/*`，偏可檢索摘要與知識。
- 即時摘要：`prompts/team/assemble-digest.md` 的組裝結果，現在可透過同步工具落地到長期記憶層。

## 3. 現況評估

### 3.1 既有實作

- `tools/long_term_memory.py`
  - 已能壓縮 `context/research-registry.json` 與 `context/continuity/auto-task-*.json`
- `knowledge-base-search/src/server.ts`
  - 已提供 `/api/import`、`/api/search/semantic`、`/api/search/keyword`、`/api/search/hybrid`、`/api/search/retrieve`
- `knowledge-base-search/src/vector-store.ts`
  - 已有 JSON 持久化、混合搜尋、過期淘汰

### 3.2 缺口

| 檢查項目 | 儲存格式 / 結構 | 更新 / 刪除 | 檢索 | 效能 | 安全 / 隱私 |
|---|---|---|---|---|---|
| 修改前狀態 | JSON 持久化已有，但缺 `topic` / `memoryLayer` | 有 `expiresAt`，但無每日摘要同步腳本 | 只有一般搜尋，缺主題/時間/分層過濾 | 有 10k 筆 < 200ms 測試，但僅針對混合搜尋 | 無加密；僅本機檔存與 API 存取 |
| 風險 | 摘要難按主題回溯 | 長期記憶寫入靠 prompt，不夠穩 | 舊資料與近期資料混查 | 隨資料成長可能帶入無效舊記憶 | 若部署到多人環境，需補 ACL / 加密 |

## 4. 本次優化方案與實作

### 4.1 技術選型

- 保留現有 `knowledge-base-search` JSON 持久化架構，不引入外部向量資料庫
- 在現有向量庫上增加：
  - `topic`
  - `memoryLayer`（`recent` / `archive`）
  - 主題 / 時間 / 分層篩選
- 新增 Python 同步工具 `tools/digest_sync.py`
  - 讀取 `context/digest-memory.json`
  - 對 `knowledge-base-search` 做健康檢查、去重查詢、匯入與重試

### 4.2 程式碼變更點

- `knowledge-base-search/src/types.ts`
  - 新增 `topic`、`memoryLayer`
- `knowledge-base-search/src/vector-store.ts`
  - 新增 `SearchFilters`
  - 支援主題 / 標籤 / 時間 / 記憶層篩選
  - 自動正規化近期 / 遠期記憶層
  - `stats()` 回傳 `layerCounts`
- `knowledge-base-search/src/server.ts`
  - `/api/notes` 與 `/api/search/*` 接受 `topic`、`memoryLayer`、`startDate`、`endDate` 等參數
- `tools/digest_sync.py`
  - 新增每日摘要同步工具與重試機制
- `tests/tools/test_digest_sync.py`
  - 補齊同步與重試測試
- `knowledge-base-search/tests/*.test.ts`
  - 補齊分層與篩選測試

### 4.3 資料遷移策略

- 現有 `data/long_term_memory.json` 不需一次性搬遷
- 舊資料在讀取與查詢時會依 `digestDate` / `updatedAt` 自動推導 `memoryLayer`
- 新寫入的摘要則直接帶 `topic` 與 `memoryLayer`

### 4.4 測試計畫

- 單元測試
  - `build_digest_note()` 產生正確欄位
  - `sync_note()` 驗證去重、更新同日 note、重試成功
  - `vector-store` 驗證 topic / time / layer 過濾
- 效能測試
  - 保留既有 10,000 筆資料混合搜尋 < 200ms 測試
- 回歸測試
  - 壓縮舊 registry / continuity 歷史
  - `/api/import` 與 `/api/search/*` 基本契約維持不變

## 5. 驗證結果

### 已完成

- `python -m pytest tests/tools/test_long_term_memory.py tests/tools/test_digest_sync.py`
  - 結果：**5 passed**

### 未完成 / 受環境限制

- `npm test`（`knowledge-base-search/`）
  - 失敗原因：`vitest` 不存在，代表本機未安裝 Node 依賴
- lint / CI / 30 天長期模擬
  - 本次未執行；目前只有靜態程式與 Python 測試驗證

## 6. 仍待後續處理

1. 安裝 `knowledge-base-search` 的 Node 依賴後重跑 `npm test`
2. 將 `tools/digest_sync.py` 真正掛入每日摘要排程
3. 若部署到多人或雲端環境，補上：
   - API 驗證
   - 資料加密
   - 權限控管
4. 建立 30 天 / 10,000 筆摘要的端到端壓力測試，驗證讀寫延遲與容量增長
