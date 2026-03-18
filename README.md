# Daily Digest Prompt

Daily Digest Prompt 是一套以排程驅動的摘要系統，整合待辦、新聞、研究與知識庫查詢，並透過長期記憶維持跨次上下文。

## Long-Term Memory

- 工作記憶：`context/digest-memory.json`、`state/*.json`
- 長期記憶：`knowledge-base-search` 的 `/api/import`、`/api/search/*`
- 壓縮維護：`tools/long_term_memory.py --apply`

### 每日摘要寫回流程

1. `prompts/team/assemble-digest.md` 在摘要完成後建立 `temp/digest-memory-import.json`
2. 透過 `POST /api/search/hybrid` 去重
3. 透過 `POST /api/import` 寫入 `Daily Digest Memory - YYYY-MM-DD`
4. 若知識庫 API 暫時失效，摘要先寫入 `state/long_term_memory_sync_queue.json`
5. `context/digest-memory.json` 更新 `long_term_memory.*` 同步狀態
5. 檢索時可加上 `taskType`、`taskTags`、`startDate/endDate`、`recencyHalfLifeDays`，讓 30 天內同任務類型摘要優先返回

### 記憶壓縮維護

- `research-registry.json`：超過 7 天的研究條目壓縮為 `archived_summaries`
- `context/continuity/auto-task-*.json`：超過 `max_runs` 的歷史壓縮為 `compressed_history`

```powershell
python tools/long_term_memory.py --apply
```

建議將此命令加入每日摘要後處理或夜間維護排程，避免 registry 與 continuity 檔案持續膨脹。

### 失敗重送與回退

```powershell
python tools/digest_sync.py --flush-queue
python tools/long_term_memory_rollback.py snapshot --label pre-upgrade
python tools/long_term_memory_rollback.py restore --snapshot backups/long_term_memory_snapshots/<snapshot-name>
```

### 檢索範例

```powershell
python tools/digest_sync.py --query "過去 30 天 AI 系統開發關鍵資訊" `
  --task-type ai_sysdev `
  --task-tags AI 系統開發 `
  --memory-layer recent `
  --start-date 2026-02-17 `
  --end-date 2026-03-18 `
  --recency-half-life-days 60
```

### 壓測

```powershell
python scripts/long_term_memory_perf.py
```

此腳本會模擬 100 筆摘要寫入與 30 天檢索，輸出平均值與 p95 延遲。
