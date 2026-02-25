---
name: arch-evolution
version: "1.0.0"
description: |
  架構演化追蹤器。整合系統審查結果、技術債掃描、依賴圖分析，
  產出持久化 ADR、技術債 backlog 與 OODA 閉環調度建議。
  靈感來源：learn-claude-code 的 +1 原則、ADR 精神、OODA 迴圈。
  Use when: 架構決策追蹤、ADR 管理、技術債盤點、依賴圖補強、OODA 調度、架構治理、漸進式改進計畫。
allowed-tools: Read, Bash, Write, Glob, Grep
cache-ttl: N/A
triggers:
  - "架構決策"
  - "ADR"
  - "技術債"
  - "依賴圖"
  - "OODA"
  - "arch-evolution"
  - "架構治理"
  - "漸進式改進"
  - "改進計畫"
  - "架構演化"
depends-on:
  - "system-audit"
  - "system-insight"
---

# Arch Evolution — 架構演化追蹤器

整合架構審查循環的四個核心職能，填補 ADR 缺失、技術債消失、依賴圖隱式、OODA 分散等系統缺口。

```
Observe  → system-insight（metrics 感測）
Orient   → system-audit（維度評分診斷）
Decide   → arch-evolution（本 Skill：ADR 選擇 + +1 行動）← 缺失的一環
Act      → self-heal（異常修復）/ 手動實作 ADR
```

## 功能模組速查

| 模組 | 職責 | 輸出 |
|------|------|------|
| A：ADR 生成 | improvement-backlog → 持久化 ADR | `context/adr-registry.json` |
| B：技術債追蹤 | 全專案 Grep → 增量比較 backlog | `context/tech-debt-backlog.json` |
| C：依賴圖補強 | 掃描隱式依賴 → 建議清單 | stdout 報告（不自動修改） |
| D：OODA 調度 | 整合 A/B/C 結果 → +1 行動建議 | `context/arch-evolution-report.json` |

互動式模式：使用者可選擇執行所有模組（`完整 arch-evolution`）或單一模組（`僅 ADR`、`掃描技術債` 等）。

---

## 步驟 0：讀取現有狀態

依序嘗試讀取（不存在則跳過，不中斷）：

1. `state/last-audit.json`（維度分數、上次審查日期）
2. `context/system-insight.json`（7 指標 + alerts）
3. `context/improvement-backlog.json`（github-scout 改進建議）
4. `context/adr-registry.json`（已有 ADR，用於去重）
5. `context/tech-debt-backlog.json`（上次技術債掃描結果）

---

## 模組 A：ADR 生成

**觸發條件**：improvement-backlog 有 P0/P1 建議未轉化為 ADR，或使用者要求「建立 ADR」。

**A1：篩選待轉化建議**

讀取 `context/improvement-backlog.json`，篩選 priority=P0 或 P1 的條目。
對照 `context/adr-registry.json`（若存在），依 `source_pattern` 欄位去重，排除已有 ADR 的建議。

**A2：生成 ADR 記錄**

為每條建議建立一筆 ADR：

```json
{
  "id": "ADR-YYYYMMDD-NNN",
  "title": "...",
  "status": "Proposed",
  "implementation_status": "pending",
  "created_at": "YYYY-MM-DD",
  "source": "improvement-backlog",
  "source_pattern": "<improvement-backlog 的 pattern 欄位>",
  "priority": "P0|P1",
  "effort": "low|medium|high",
  "context": "<從 description 提取問題背景>",
  "decision": "",
  "consequences": { "positive": [], "negative": [] },
  "related_files": [],
  "notes": ""
}
```

> **`decision` 欄位留空**：架構決策需人工填寫接受/拒絕理由，LLM 不自動填寫。

**A3：寫入 adr-registry.json**

讀取現有（若存在）→ 追加新 ADR → 更新 summary（total/proposed/accepted/rejected/superseded）→ 寫回。

---

## 模組 B：技術債追蹤

**B1：全專案掃描**

用 Grep 工具分別搜尋 5 個關鍵字。每個搜尋使用以下參數：

```
Grep 搜尋參數：
  pattern: "FIXME|TODO|HACK|XXX|臨時"
  path: D:\Source\daily-digest-prompt
  glob: "*.py"  （第一輪）
  glob: "*.ps1" （第二輪）
  glob: "*.md"  （第三輪，限 skills/ 和 prompts/）
  output_mode: "content"
  -n: true
```

排除目錄（用 Grep 的 path 參數限縮，或結果中手動過濾）：
- `logs/`、`cache/`、`context/`、`state/`、`results/`、`docs/`

> **效率提示**：可並行發起 3 次 Grep（py/ps1/md），加速掃描。

每筆記錄：檔案相對路徑、行號、原始行文字（去除前後空白）、關鍵字類型。

**B2：優先級分類**

| 關鍵字 | 預設優先級 |
|--------|-----------|
| FIXME、HACK | P1（已知問題/臨時繞過） |
| TODO、XXX、臨時 | P2（計畫項目/待注意） |

**B3：增量比較**

讀取 `context/tech-debt-backlog.json`（若存在）：
- 新增條目（本次有、上次無）→ 設定 `first_seen_at = today`
- 已消除條目（上次有、本次無）→ 標記 `status: resolved`
- 持續存在條目 → 計算 `age_days`（今日 - first_seen_at）

**B4：長期未處理提示**

在報告末尾標注：age_days > 7 且 priority=P1 的條目，提醒人工處理或轉為 Todoist 任務。
若 FIXME+HACK 總數 > 10，列出建議優先清理的前 3 條。

**B5：寫入 tech-debt-backlog.json**（格式見「輸出格式」章節）

---

## 模組 C：依賴圖補強

**目的**：現有 22 個 Skills 中只有 4 個宣告 `depends-on`，但實際隱式依賴更多。

**C1：讀取所有 SKILL.md**

用 Glob 找出 `skills/*/SKILL.md`，讀取每個的 frontmatter（name、depends-on、allowed-tools）和步驟文字。

**C2：隱式依賴推斷規則**

| 推斷規則 | 說明 |
|---------|------|
| 步驟文字含「research-registry」且未宣告 depends-on web-research | 推斷依賴 web-research |
| 步驟文字含「knowledge-query」且未宣告 | 推斷依賴 knowledge-query |
| 步驟文字含「ntfy」且未宣告 | 推斷依賴 ntfy-notify |
| 步驟文字含「api-cache」且未宣告 | 推斷依賴 api-cache |
| SKILL_INDEX 的依賴關係表有記載但 frontmatter 未宣告 | 直接補強建議 |

**C3：產出建議清單**

以 stdout 方式輸出建議，**不自動修改任何 SKILL.md**（修改 SKILL.md 需人工確認）。

```
依賴圖補強建議
==============
github-scout → 建議新增 depends-on: [web-research, knowledge-query]
  證據：步驟 5 使用 research-registry；步驟 6 匯入 KB

kb-curator → 建議新增 depends-on: [knowledge-query]
  證據：步驟 2-4 反覆呼叫 KB API

[共發現 N 個 Skill 有未宣告的隱式依賴]
```

---

## 模組 D：OODA 調度

**目的**：整合 system-insight alerts 和 adr-registry，用 +1 原則選出本次最值得執行的 1 個改進行動。

**D1：讀取 OODA 狀態**

讀取 `context/system-insight.json` 的 `alerts` 欄位：

| alert 等級 | 決策方向 |
|-----------|---------|
| critical | 優先從技術債 backlog 選 1 條 P1 處理；建議優先排程 self-heal |
| warning | 從 adr-registry 選 1 條 `effort=low` 且 `status=Proposed` 的 ADR |
| 無 alert | 從 adr-registry 選 1 條 `effort=medium` 且最高 priority 的 ADR |

若 `system-insight.json` 不存在或超過 24 小時，OODA 模組降級：輸出「建議先執行 system-insight 自動任務後再調度」。

**D2：+1 原則篩選**

從符合條件的 ADR 中選出 1 條，生成具體執行步驟（3–5 步，每步可在單次 Agent session 內完成）。

**D3：輸出 OODA 報告**（格式見「輸出格式」章節）

---

## 輸出格式

### adr-registry.json

```json
{
  "version": 1,
  "updated_at": "2026-02-24T10:00:00+08:00",
  "summary": {
    "total": 3,
    "proposed": 2,
    "accepted": 1,
    "rejected": 0,
    "superseded": 0
  },
  "records": [
    {
      "id": "ADR-20260224-001",
      "title": "依賴注入模式取代硬編碼 API 端點",
      "status": "Proposed",
      "implementation_status": "pending",
      "created_at": "2026-02-24",
      "source": "improvement-backlog",
      "source_pattern": "依賴注入（Dependency Injection）模式",
      "priority": "P0",
      "effort": "high",
      "context": "Skill 模板硬編碼 API 端點，難以在測試環境替換",
      "decision": "",
      "consequences": {
        "positive": ["測試可用 mock 端點", "端點集中管理"],
        "negative": ["需修改所有 SKILL.md", "引入間接層"]
      },
      "related_files": ["config/pipeline.yaml", "templates/shared/preamble.md"],
      "notes": ""
    }
  ]
}
```

### tech-debt-backlog.json

```json
{
  "version": 1,
  "last_scanned_at": "2026-02-24T10:05:00+08:00",
  "summary": {
    "total": 5,
    "by_type": { "FIXME": 1, "TODO": 3, "HACK": 1 },
    "by_priority": { "P1": 2, "P2": 3 },
    "new_since_last": 1,
    "resolved_since_last": 0
  },
  "items": [
    {
      "id": "TD-20260224-001",
      "type": "TODO",
      "priority": "P2",
      "file": "hooks/pre_bash_guard.py",
      "line": 42,
      "text": "# TODO: 支援正則表達式匹配模式",
      "first_seen_at": "2026-02-24",
      "last_seen_at": "2026-02-24",
      "age_days": 0,
      "status": "open"
    }
  ]
}
```

### arch-evolution-report.json

```json
{
  "version": 1,
  "generated_at": "2026-02-24T10:10:00+08:00",
  "modules_executed": ["A", "B", "C", "D"],
  "adr_summary": { "total": 3, "new_this_run": 2, "proposed": 2, "accepted": 1 },
  "debt_summary": { "total": 5, "p1_count": 2, "new_since_last": 1, "resolved_since_last": 0 },
  "dependency_suggestions": 2,
  "ooda_cycle": {
    "observe": { "timestamp": "...", "metrics_available": true },
    "orient": { "last_audit_date": "2026-02-24", "lowest_dimension": "2_system_architecture", "lowest_score": 84 },
    "decide": { "selected_adr_id": "ADR-20260224-003", "rationale": "effort=medium，最高 priority 且有明確 related_files" },
    "act": {
      "next_action_title": "輸出 Schema 驗證層",
      "steps": [
        "步驟 1：在 templates/shared/quality-gate.md 新增 JSON Schema 驗證段落",
        "步驟 2：更新 done-cert.md 格式要求",
        "步驟 3：在 on_stop_alert.py 增加格式一致性檢查"
      ],
      "estimated_sessions": 1
    }
  }
}
```

---

## 整合點

### 讀取（輸入）

| 來源 | 用途 | 模組 |
|------|------|------|
| `state/last-audit.json` | 維度分數、最低維度識別 | A、D |
| `context/system-insight.json` | alerts 決定 OODA 行動 | D |
| `context/improvement-backlog.json` | P0/P1 建議轉化為 ADR | A |
| `context/adr-registry.json` | 去重、讀取現有 ADR 狀態 | A、D |
| `context/tech-debt-backlog.json` | 增量比較技術債 | B |
| `skills/*/SKILL.md`（全部） | 掃描 depends-on 宣告 | C |

### 寫入（輸出）

| 目標 | 操作 | 模組 |
|------|------|------|
| `context/adr-registry.json` | 追加 ADR、更新狀態 | A |
| `context/tech-debt-backlog.json` | 增量更新技術債 | B |
| `context/arch-evolution-report.json` | 完整 OODA 報告 | D |

### 不自動修改

| 目標 | 理由 |
|------|------|
| `skills/*/SKILL.md` | 模組 C 僅產出建議，修改需人工確認 |
| Todoist 任務 | 避免低優先級技術債污染清單；報告末尾附加建議 |
| `config/frequency-limits.yaml` | 排程修改需透過 task-manager Skill |

---

## 錯誤處理

| 錯誤情境 | 降級策略 |
|---------|---------|
| `last-audit.json` 不存在 | 模組 A/D 降級：從 improvement-backlog 直接轉化，跳過分數分析 |
| `system-insight.json` 超過 24 小時 | 模組 D 降級：輸出「建議先執行 system-insight 後再調度」 |
| `improvement-backlog.json` 為空/不存在 | 模組 A：跳過轉化，通知使用者「需先執行 github-scout」 |
| `adr-registry.json` 損壞（JSON parse 失敗） | 備份原始檔（加 `.bak` 後綴），重建空 registry |
| Grep 掃描無結果 | 模組 B：記錄「零技術債」，更新 last_scanned_at |

---

## 注意事項

- **互動式工具**：由使用者手動觸發，不透過 Todoist 路由
- **ADR decision 人工填寫**：`decision` 欄位初始為空，需人工判斷後填寫接受/拒絕理由
- **+1 原則**：OODA 模組 D 每次只選 1 個行動，避免多頭並進導致改進效果分散
- **scheduler-state.json 唯讀**：此 Skill 不寫入 scheduler-state.json（PowerShell 腳本獨佔寫入）
- **執行時間估計**：完整 4 模組約 5–10 分鐘；單一模組 1–3 分鐘
