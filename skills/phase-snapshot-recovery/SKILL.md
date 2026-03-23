---
name: phase-snapshot-recovery
version: "1.0.0"
description: |
  Phase 間快照恢復工具。在 run-todoist-agent-team.ps1 的 Phase 1→2→3 轉換前自動建立快照，
  Phase 失敗或 timeout 時從最近快照恢復續跑，避免整個管線重跑。
  借鑑 LangGraph checkpointing 與 Temporal durable execution 設計。
  Use when: Phase 2 timeout 後恢復、Phase 失敗後續跑、管線中斷恢復、快照建立與清理、排程恢復策略。
allowed-tools: [Read, Write, Bash, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "phase-snapshot-recovery"
  - "Phase 恢復"
  - "Phase 快照"
  - "管線中斷恢復"
  - "快照續跑"
  - "snapshot recovery"
  - "Phase timeout 恢復"
depends-on:
  - scheduler-state
  - self-heal
  - "config/dependencies.yaml"
---

# Phase Snapshot Recovery — Phase 間快照恢復工具

## 設計哲學

本 Skill 解決 `run-todoist-agent-team.ps1` 三階段管線（Phase 1 查詢 → Phase 2 並行執行 → Phase 3 組裝）的**中斷恢復**問題。

當前系統的失敗模式：Phase 2 單一 Agent timeout 或 Phase 3 組裝失敗時，整個管線必須從 Phase 1 重跑，浪費已完成的 Phase 1 查詢結果和 Phase 2 部分成功的任務執行結果。

**借鑑來源**（KB 研究）：
- LangGraph checkpointing：Phase 轉換前自動建立 checkpoint，失敗時回到最近 checkpoint
- Temporal durable execution：Activity 自動重試，崩潰後從中斷處繼續
- Kubernetes controller reconciliation：desired state vs actual state 比對，收斂至目標狀態

**核心能力**：
```
建立快照（Phase 轉換前）→ 偵測中斷（Phase 失敗/timeout）
→ 載入快照（跳過已完成 Phase）→ 續跑（從中斷 Phase 繼續）
→ 清理過期快照（TTL 管理）
```

---

## 快照 Schema

快照儲存於 `state/snapshots/` 目錄，檔名格式：`snapshot-{trace_id}-phase{N}.json`

```json
{
  "schema_version": 1,
  "trace_id": "20260323_160000_abc",
  "created_at": "2026-03-23T16:00:00+08:00",
  "phase_completed": 1,
  "next_phase": 2,
  "task_key": "todoist_team",
  "pipeline": "run-todoist-agent-team",
  "phase_results": {
    "phase1": {
      "status": "success",
      "query_result_path": "results/todoist-query.json",
      "tasks_found": 3,
      "plan_keys": ["tech_research", "code_task", "kb_curator"],
      "completed_at": "2026-03-23T15:58:00+08:00"
    }
  },
  "phase2_partial": {
    "completed_tasks": ["tech_research"],
    "pending_tasks": ["code_task", "kb_curator"],
    "failed_tasks": [],
    "result_files": {
      "tech_research": "results/todoist-auto-tech_research.json"
    }
  },
  "retry_count": 0,
  "max_retries": 2,
  "expires_at": "2026-03-23T22:00:00+08:00"
}
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立現有 Skill 認知地圖）

---

## 步驟 1：建立快照（Phase 轉換前呼叫）

在 Phase N 成功完成、Phase N+1 開始前，建立快照。

**觸發條件**：由 `run-todoist-agent-team.ps1` 的 Phase 轉換邏輯呼叫（或由 Agent prompt 手動觸發）。

**操作**：

```bash
# 確保目錄存在
mkdir -p state/snapshots
```

用 Write 工具建立 `state/snapshots/snapshot-{trace_id}-phase{N}.json`，內容依上方 Schema 填入：

| 欄位 | 來源 |
|------|------|
| `trace_id` | 環境變數 `$DIGEST_TRACE_ID` 或從 `state/run-fsm.json` 讀取 |
| `phase_completed` | 當前完成的 Phase 編號（1 或 2） |
| `phase_results.phase{N}` | 讀取對應的結果檔案路徑與狀態 |
| `phase2_partial` | Phase 2 進行中時，掃描 `results/todoist-auto-*.json` 已存在的檔案 |
| `expires_at` | `created_at` + 6 小時（避免過期快照佔用空間） |

**驗證**：

```bash
uv run python -X utf8 -c "
import json, os
snap_dir = 'state/snapshots'
files = [f for f in os.listdir(snap_dir) if f.startswith('snapshot-') and f.endswith('.json')]
for f in files:
    d = json.load(open(os.path.join(snap_dir, f), encoding='utf-8'))
    required = ['schema_version','trace_id','phase_completed','next_phase','pipeline']
    missing = [k for k in required if k not in d]
    status = 'VALID' if not missing else f'INVALID(missing:{missing})'
    print(f'{f}: {status}')
"
```

---

## 步驟 2：偵測中斷（Phase 失敗時呼叫）

當 Phase 失敗或 timeout 被偵測到時，檢查是否有可用快照。

**偵測邏輯**：

```bash
uv run python -X utf8 -c "
import json, os, glob
from datetime import datetime, timezone, timedelta

snap_dir = 'state/snapshots'
if not os.path.isdir(snap_dir):
    print('NO_SNAPSHOTS_DIR')
    exit(0)

now = datetime.now(timezone(timedelta(hours=8)))
snapshots = []
for f in sorted(glob.glob(os.path.join(snap_dir, 'snapshot-*.json')), reverse=True):
    try:
        d = json.load(open(f, encoding='utf-8'))
        expires = datetime.fromisoformat(d.get('expires_at', '2000-01-01T00:00:00+08:00'))
        if expires > now and d.get('retry_count', 0) < d.get('max_retries', 2):
            snapshots.append({
                'file': os.path.basename(f),
                'phase_completed': d['phase_completed'],
                'trace_id': d['trace_id'],
                'retry_count': d.get('retry_count', 0)
            })
    except (json.JSONDecodeError, KeyError):
        continue

if snapshots:
    print(f'RECOVERABLE: {len(snapshots)} snapshot(s) available')
    best = snapshots[0]
    print(f'BEST: {best[\"file\"]} (phase {best[\"phase_completed\"]} completed, retry #{best[\"retry_count\"]})')
else:
    print('NO_RECOVERABLE_SNAPSHOT')
"
```

**結果判斷**：

| 輸出 | 動作 |
|------|------|
| `RECOVERABLE: N snapshot(s)` | 繼續步驟 3（載入快照） |
| `NO_RECOVERABLE_SNAPSHOT` | 無法恢復，通知 self-heal Skill 執行 Tier 1 重試 |
| `NO_SNAPSHOTS_DIR` | 首次執行，無快照可用 |

---

## 步驟 3：載入快照並恢復

讀取最近可用快照，準備從中斷 Phase 繼續。

**操作**：

1. 用 Read 讀取步驟 2 識別的最佳快照
2. 根據 `phase_completed` 決定恢復策略：

| `phase_completed` | 恢復動作 |
|-------------------|---------|
| 1 | 跳過 Phase 1（查詢已完成），直接進入 Phase 2。讀取 `phase_results.phase1.query_result_path` 作為 Phase 2 輸入 |
| 2（partial） | 跳過 Phase 1 與已完成的 Phase 2 任務。讀取 `phase2_partial.completed_tasks`，只對 `pending_tasks` + `failed_tasks` 執行 Phase 2 |
| 2（complete） | 跳過 Phase 1 和 Phase 2，直接進入 Phase 3 組裝 |

3. 更新快照的 `retry_count` + 1：

```bash
uv run python -X utf8 -c "
import json
snap_file = 'state/snapshots/{snapshot_filename}'
d = json.load(open(snap_file, encoding='utf-8'))
d['retry_count'] = d.get('retry_count', 0) + 1
with open(snap_file, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print(f'RETRY_COUNT: {d[\"retry_count\"]}/{d.get(\"max_retries\", 2)}')
"
```

4. 將恢復計畫輸出為 JSON，供 `run-todoist-agent-team.ps1` 讀取：

用 Write 工具建立 `state/recovery-plan.json`：
```json
{
  "source_snapshot": "snapshot-{trace_id}-phase{N}.json",
  "skip_phases": [1],
  "resume_phase": 2,
  "resume_tasks": ["code_task", "kb_curator"],
  "skip_tasks": ["tech_research"],
  "phase1_result_path": "results/todoist-query.json",
  "retry_number": 1
}
```

---

## 步驟 4：恢復後驗證

Phase 恢復執行完成後，驗證結果完整性。

```bash
uv run python -X utf8 -c "
import json, os

# 讀取恢復計畫
if not os.path.exists('state/recovery-plan.json'):
    print('NO_RECOVERY_PLAN')
    exit(0)

plan = json.load(open('state/recovery-plan.json', encoding='utf-8'))
all_tasks = plan.get('skip_tasks', []) + plan.get('resume_tasks', [])
missing = []
for task in all_tasks:
    result_file = f'results/todoist-auto-{task}.json'
    if not os.path.exists(result_file):
        missing.append(task)

if missing:
    print(f'INCOMPLETE: missing results for {missing}')
else:
    print(f'RECOVERY_COMPLETE: all {len(all_tasks)} task results present')
"
```

| 結果 | 動作 |
|------|------|
| `RECOVERY_COMPLETE` | 清理快照（步驟 5），繼續 Phase 3 |
| `INCOMPLETE` | 若 retry_count < max_retries，再次從步驟 3 重試；否則標記為 partial 並通知 |

---

## 步驟 5：清理過期快照

定期清理過期或已成功恢復的快照，防止 `state/snapshots/` 目錄膨脹。

```bash
uv run python -X utf8 -c "
import json, os, glob
from datetime import datetime, timezone, timedelta

snap_dir = 'state/snapshots'
if not os.path.isdir(snap_dir):
    print('NO_SNAPSHOTS_DIR')
    exit(0)

now = datetime.now(timezone(timedelta(hours=8)))
cleaned = 0
kept = 0
for f in glob.glob(os.path.join(snap_dir, 'snapshot-*.json')):
    try:
        d = json.load(open(f, encoding='utf-8'))
        expires = datetime.fromisoformat(d.get('expires_at', '2000-01-01T00:00:00+08:00'))
        exhausted = d.get('retry_count', 0) >= d.get('max_retries', 2)
        if expires < now or exhausted:
            os.remove(f)
            cleaned += 1
        else:
            kept += 1
    except (json.JSONDecodeError, KeyError):
        os.remove(f)
        cleaned += 1

print(f'CLEANED: {cleaned} expired/exhausted snapshots removed, {kept} active snapshots kept')
"
```

**清理策略**：
- 過期（`expires_at` < now）→ 刪除
- 重試耗盡（`retry_count` >= `max_retries`）→ 刪除
- 最多保留 5 份快照（按 `created_at` 降序保留最新 5 份，刪除更舊的）

---

## 步驟 6：輸出恢復報告

將恢復結果寫入結構化報告，供 system-insight 和 scheduler-state 分析。

用 Write 工具建立 `state/last-recovery-report.json`：
```json
{
  "generated_at": "2026-03-23T16:45:00+08:00",
  "source_snapshot": "snapshot-xxx-phase1.json",
  "recovery_type": "phase2_partial_resume",
  "phases_skipped": [1],
  "tasks_skipped": ["tech_research"],
  "tasks_resumed": ["code_task", "kb_curator"],
  "result": "success",
  "time_saved_estimate_seconds": 120,
  "retry_count": 1
}
```

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| `state/snapshots/` 目錄不存在 | 建立目錄並標記為首次執行，無恢復可用 |
| 快照 JSON 損壞（parse 失敗） | 刪除損壞檔案，嘗試下一個可用快照 |
| 所有快照已過期或重試耗盡 | 回報無可恢復快照，交由 self-heal Skill 處理（Tier 1 完整重跑） |
| `recovery-plan.json` 指定的結果檔已不存在 | 將對應 task 從 `skip_tasks` 移至 `resume_tasks`，重新執行 |
| Phase 1 結果檔不存在（快照引用的路徑失效） | 快照無效，刪除並完整重跑 |

---

## 與現有系統的整合點

| 整合對象 | 整合方式 |
|---------|---------|
| `run-todoist-agent-team.ps1` | Phase 轉換前呼叫步驟 1 建立快照；Phase 失敗時呼叫步驟 2-3 嘗試恢復 |
| `self-heal` Skill | 恢復失敗時，交由 self-heal 的 Tier 1（重試）或 Tier 2（健康診斷）處理 |
| `scheduler-state` | 恢復成功後更新 `scheduler-state.json` 的成功/失敗記錄（由 PowerShell 寫入） |
| `state/run-fsm.json` | 恢復時讀取 FSM 狀態確認當前 Phase，恢復後更新 Phase 狀態 |
| `check-health.ps1` | 新增 [快照健康度] 區塊，顯示活躍快照數、過期快照數、最近恢復成功率 |

---

## 使用範例

### 場景 1：Phase 2 單一 Agent timeout

```
Phase 1 成功 → 建立快照（phase_completed=1）
Phase 2 執行中：tech_research 完成，code_task timeout
→ 偵測中斷 → 載入快照
→ 恢復計畫：skip Phase 1，skip tech_research，只跑 code_task + kb_curator
→ Phase 2 恢復成功 → Phase 3 組裝 → 清理快照
```

### 場景 2：Phase 3 組裝失敗

```
Phase 1 成功 → Phase 2 全部成功 → 建立快照（phase_completed=2）
Phase 3 組裝失敗（模板錯誤）
→ 偵測中斷 → 載入快照
→ 恢復計畫：skip Phase 1+2，直接重跑 Phase 3
→ 修正後 Phase 3 成功 → 清理快照
```

---

**版本歷史**：
- v1.0.0（2026-03-23）：初始正式版，5 步驟快照恢復流程 + 降級處理 + 系統整合點
