# 長期記憶升級部署說明

## 需求原文

以 https://know-w.pages.dev/article/ai-agent-context-management-%E8%88%87--8fb70bab#%E4%B8%83-daily-digest-prompt-%E5%B0%88%E6%A1%88%E7%9A%84%E6%87%89%E7%94%A8%E5%A0%B4%E6%99%AF 中的 Daily‑Digest‑Prompt 專案建議，優化系統長期記憶功能

## 環境相容性

- 作業系統：Windows
- Python：`>=3.9`
- Node.js：`>=18`
- Python 套件：`requests==2.32.5`、`pyyaml==6.0.3`
- 知識庫服務：`http://localhost:3000`

## 升級步驟

1. 建立回退快照：

```powershell
python tools/long_term_memory_rollback.py snapshot --label pre-upgrade
```

2. 確認知識庫 API 健康：

```powershell
Invoke-RestMethod -Uri http://localhost:3000/api/health
```

3. 執行測試：

```powershell
python -m pytest tests\test_memory_long_term_optimization.py tests\test_long_term_memory_perf.py tests\tools\test_digest_sync.py tests\tools\test_long_term_memory.py tests\tools\test_long_term_memory_rollback.py tests\test_digest_scheduler.py
python scripts\long_term_memory_perf.py
```

4. 若要將當前摘要同步至知識庫：

```powershell
python tools/digest_sync.py --base-url http://localhost:3000
```

5. 若要整理既有長期上下文：

```powershell
python tools/long_term_memory.py --apply
```

## 資料遷移與回填

- `context/digest-memory.json`：新增 `long_term_memory.last_sync_at`、`last_note_id`、`sync_status`、`queue_size`
- `context/research-registry.json`：舊條目可壓縮到 `archived_summaries`
- `context/continuity/auto-task-*.json`：超過 `max_runs` 的舊執行記錄會進入 `compressed_history`

## 回退指令

1. 找出快照路徑，例如 `backups/long_term_memory_snapshots/20260318T010000Z-pre-upgrade`
2. 還原：

```powershell
python tools/long_term_memory_rollback.py restore --snapshot backups/long_term_memory_snapshots/<snapshot-name>
```

3. 若只需重送佇列，不必回退：

```powershell
python tools/digest_sync.py --flush-queue --base-url http://localhost:3000
```

## 驗證清單

- `context/digest-memory.json` 的 `long_term_memory.sync_status` 為 `success` 或 `queued`
- `state/long_term_memory_sync_queue.json` 大小符合 `config/long_term_memory.yaml` 上限
- `python scripts/long_term_memory_perf.py` 顯示 100 筆 smoke 與 1M 合成檢索都在 200ms 內
