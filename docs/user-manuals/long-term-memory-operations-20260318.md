# 長期記憶模組操作手冊

## 作用

長期記憶模組會將每日摘要轉成可檢索記憶，並在檢索時結合時間、任務型別與標籤收斂結果。

## 常用操作

### 1. 手動同步當前摘要

```powershell
python tools/digest_sync.py --base-url http://localhost:3000
```

成功後，`context/digest-memory.json` 會更新：
- `last_sync_at`
- `last_note_id`
- `sync_status`
- `queue_size`

### 2. 查詢最近摘要記憶

```powershell
python tools/digest_sync.py --query "AI 系統開發摘要" --task-type ai_sysdev --task-tags AI 系統開發 --start-date 2026-03-01 --end-date 2026-03-31 --memory-layer recent
```

### 3. 沖刷待同步佇列

```powershell
python tools/digest_sync.py --flush-queue --base-url http://localhost:3000
```

### 4. 壓縮舊上下文

```powershell
python tools/long_term_memory.py --apply
```

## 異常處理

- `sync_status = queued`
  - 表示知識庫 API 當下不可用，資料已保存在 `state/long_term_memory_sync_queue.json`
- 查不到預期記憶
  - 先確認查詢條件是否過窄，例如 `taskType`、`startDate/endDate`
- 需要回復到升級前狀態
  - 依 `docs/deployment/long-term-memory-upgrade-20260318.md` 執行 snapshot restore

## 監控指標

- 寫入成功率：觀察 `sync_status`
- 佇列大小：觀察 `queue_size`
- 檢索延遲：定期執行 `python scripts/long_term_memory_perf.py`
- 壓縮品質：檢查 `archived_summaries` 與 `compressed_history`
