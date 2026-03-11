# P1/P2/P3 優化實施報告 — 2026-02-28

## 總覽

本報告涵蓋系統借鑑洞察優化計畫的 **Week 1 Day 3-5（P1）+ Week 2（P2）+ Month 2（P3）** 項目，共完成 **15 個優化項目**：G4、G5、G6、G7、G20-22（P1）、G8-9、G11-12（P2）、G13-14（P3），並由 Code Review Agent 發現 3 個問題（已修復）。

測試驗證：**532/532 全數通過**（與 P0 完成時相同）。

---

## P1 實施項目（5 項 + 3 Gun.js）

### G4 — Phase 協議文檔（Interface Spec）

**新建檔案**：`specs/interface-spec/phase-results.md`（210 行）

定義所有 Phase 間結果檔案的 JSON schema：
- `todoist-plan.json` 完整 schema（plan_type, tasks, auto_tasks）
- `results/fetch-*.json`、`results/todoist-auto-*.json` schema
- Phase 3 容錯規則（結果數不足 → 部分通知模式）
- `schema_version: 1` 版本追蹤

---

### G5 — Skill 別名映射修正

**問題**：`routing.yaml` 中的 `"程式開發（Plan-Then-Execute）"` 在 `skills/` 目錄無對應 SKILL.md，交叉驗證會誤報。

**修改檔案**：
- `config/routing.yaml`（+7 行）：新增 `skill_aliases` 區段：
  ```yaml
  skill_aliases:
    "程式開發（Plan-Then-Execute）":
      type: template_driven
      template: "templates/sub-agent/code-task.md"
      no_skill_file: true
  ```
- `hooks/validate_config.py`（+30 行）：`_load_routing_skill_aliases()` 函數，讀取 `no_skill_file: true` 別名，`check_routing_consistency()` 跳過這些別名的 SKILL.md 驗證

---

### G6 — 自動任務輪轉算法精確化

**問題**：`git_push`（order=13）末位調整後，`next_execution_order_after` 計算說明不夠精確。

**修改檔案**：
- `prompts/team/todoist-query.md`（步驟 2.5 +8 行）：新增精確偽代碼：
  ```
  next_execution_order_after = max(selected_tasks原始orders) % 18 + 1
  ⚠️ git_push 末位調整不影響此計算：仍以其原始 order=13 參與 max() 計算
  範例：若選中 [11, 13(git_push→末), 15]，max=15，next_after = 15 % 18 + 1 = 16
  ```

---

### G7 — Hook 邊界案例補充

**修改檔案**：
- `config/hook-rules.yaml`（+30 行）：
  - 新增 `sensitive-env-powershell` bash 規則（攔截 `$env:TOKEN|$env:KEY` 等管道輸出）
  - 新增 `benign_output_patterns` 區段（28 個模式，含中文：`"錯誤: 0"`, `"失敗: 0"`）
- `hooks/post_tool_logger.py`（+25 行）：
  - `_BENIGN_PATTERNS_FALLBACK` 保留硬編碼備援
  - `_load_benign_patterns_from_yaml()` 從 YAML 載入（失敗時回退硬編碼）
  - 模組層級 `BENIGN_PATTERNS = _load_benign_patterns_from_yaml()`

---

### G20 — Bot epub 簽章驗證防 MITM

**修改檔案**：
- `D:\Source\wsc-bot01\bot.js`（+6 行）：廣播 epub + 附加自身簽章
  ```javascript
  const epubSig = await SEA.sign(myPair.epub, myPair);
  gun.get('wsc-bot/handshake').put({ epub: myPair.epub, sig: epubSig });
  ```
- `D:\Source\my-gun-relay\index.html`（+12 行）：連線前驗證簽章
  ```javascript
  const verified = await SEA.verify(hw.sig, hw.epub);
  if (verified !== hw.epub) throw new Error('Bot epub 驗證失敗');
  ```

---

### G21 — API Key sessionStorage 遷移

**修改檔案**：`D:\Source\my-gun-relay\index.html`（+5/-5 行）
- `localStorage.getItem/setItem('gun_bot_api_key')` → `sessionStorage`
- 標籤頁關閉即清除，避免跨 session 持久化

---

### G22 — 排程 API 指數退避

**修改檔案**：`D:\Source\my-gun-relay\index.html`（+25 行）
- 新增 `scheduleFailCount` 計數器
- 新增 `fetchWithTimeout()` 函數（AbortController + 8s 超時）
- 退避策略：`Math.min(1000 * Math.pow(2, failCount), 30000)`（2s → 4s → 8s → 30s 上限）

---

## P2 實施項目（4 項）

### G8 — Phase 執行時間線

**修改檔案**：
- `run-agent-team.ps1`（+35 行）：`$phase1Start`/`$phase2Start` 計時，`phase_breakdown` 欄位加入 scheduler-state 記錄
- `run-todoist-agent-team.ps1`（+45 行）：同上，含 Phase 3 計時
- `run-system-audit-team.ps1`（+35 行）：同上，Phase 1/2 計時
- `query-logs.ps1`（+120 行）：新增 `Show-Timeline` 函數，`-Mode timeline` 顯示最近 5 筆 Phase 耗時 ASCII 條形圖

**`phase_breakdown` 結構**（存入 scheduler-state.json）：
```json
{
  "phase1_seconds": 58,
  "phase2_seconds": 195,
  "phase1_agents": ["todoist", "news", "hackernews", "gmail", "security"]
}
```

---

### G9 — 失敗分類統計

**新建檔案**：`state/failure-stats.json`

**修改檔案**：
- `run-agent-team.ps1`（+60 行）：`Update-FailureStats` 函數，Phase 1/2 失敗呼叫
- `run-todoist-agent-team.ps1`（+63 行）：同上，Phase 0/1/2/3 失敗各 8 個呼叫點
- `check-health.ps1`（+48 行）：`[失敗分類統計（近 7 天）]` 區塊，5 種分類長條圖

**5 種失敗分類**：`timeout`、`api_error`、`circuit_open`、`phase_failure`、`parse_error`

---

### G11 — YAML 交叉驗證

**修改檔案**：
- `hooks/validate_config.py`（+183 行）：
  - `check_skill_references()`：frequency-limits.yaml 的 skill 引用驗證
  - `check_template_references()`：routing.yaml 的 template 路徑驗證
  - `check_frequency_template_references()`：frequency-limits.yaml 的 template 路徑驗證
  - `--cross-validate` / `--strict` 命令列 flag
- `check-health.ps1`（+27 行）：`[YAML 交叉驗證]` 區塊

**執行結果**：`python hooks/validate_config.py --cross-validate`
```
[交叉驗證]
  ✓ 所有引用均有效（技能、模板路徑）
```

---

### G12 — Token 預算管理（輕量版）

**新建檔案**：`state/token-usage.json`

**修改檔案**：
- `hooks/post_tool_logger.py`（+57 行）：`_update_token_usage()` + `_find_token_usage_file()`，每次 PostToolUse 後累積（字元 ÷ 3.5 估算），**使用 .lock 檔案保護 read-modify-write**（審查後修復）
- `hooks/on_stop_alert.py`（+36 行）：`_check_token_budget()`，超過 1.5M tokens 時附加 ntfy warning
- `check-health.ps1`（+43 行）：`[今日 Token 估算]` 區塊，含 20 格進度條

---

## P3 實施項目（2 項）

### G13 — Skill 依賴圖可視化

**修改 SKILL.md**（4 個加入 `depends-on:`）：
- `skills/system-audit/SKILL.md`：`depends-on: [skill-scanner]`
- `skills/arch-evolution/SKILL.md`：`depends-on: [system-audit, system-insight]`（已有）
- `skills/ntfy-notify/SKILL.md`、`skills/api-cache/SKILL.md`、`skills/scheduler-state/SKILL.md`：`depends-on: []`

**修改檔案**：`hooks/validate_config.py`（+341 行）：
- `_load_skill_dependencies()`：掃描所有 SKILL.md frontmatter 的 `depends-on` 欄位
- `detect_cycles()`：DFS path tracking 偵測循環依賴
- `generate_skill_dag()`：輸出 Graphviz DOT 格式依賴圖
- `--skill-dag` / `--dag-output` 命令列 flag

**執行結果**：
```
[Skill 依賴圖]
  ✓ 無循環依賴（23 個 Skill，11 條依賴邊）
```

已偵測到的依賴邊（含其他 SKILL.md 已有的 `depends-on`）：
- `arch-evolution` → `system-audit`, `system-insight`
- `github-scout` → `web-research`, `knowledge-query`, `ntfy-notify`
- `system-audit` → `skill-scanner`
- `pingtung-policy-expert` → `pingtung-news`
- 等共 11 條

---

### G14 — 3 態 FSM（PowerShell 版）

**新建檔案**：`state/run-fsm.json`、`logs/structured/fsm-transitions.jsonl`

**修改檔案**：
- `run-agent-team.ps1`（+168 行）：`Set-FsmState` 函數 + 6 個 Phase 邊界呼叫點
- `run-todoist-agent-team.ps1`（+173 行）：同上 + Phase 3（共 12 個呼叫點）
- `run-system-audit-team.ps1`（+101 行）：同上，7 個呼叫點
- `check-health.ps1`（+45 行）：`[FSM 執行狀態（近期）]` 區塊

**FSM 狀態**：`pending` → `running` → `completed` / `failed`

**特性**：
- `run-fsm.json`：write-to-tmp + `Move-Item` 原子操作
- `fsm-transitions.jsonl`：append-only，完整歷史軌跡
- 24 小時自動清理舊 run 記錄

---

## Code Review 修復（3 項）

由 Code Review Agent 發現後立即修復：

| 問題 | 等級 | 修復內容 |
|------|------|---------|
| `atomic_write_json()` tempfile 洩漏 | Critical | 加入 `try/finally` + `os.remove(tmp_path)` |
| `_update_token_usage()` 並行競態 | Critical | 加入 `.lock` 檔案保護 read-modify-write（與 CircuitBreaker 相同模式） |
| `check_skill_references()` 防禦缺口 | Important | 加入 `isinstance(task_cfg, dict)` 檢查（兩處） |

---

## 測試結果

```
532 passed in 3.45s
```

所有 532 個測試全數通過，無回歸問題。

---

## 修改檔案總覽

| 檔案 | 優化項目 | 淨增行數 |
|------|---------|---------|
| `config/routing.yaml` | G5 | +7 |
| `hooks/validate_config.py` | G5、G11、G13 + Fix | +557 |
| `hooks/post_tool_logger.py` | G7、G12 + Fix | +82 |
| `hooks/on_stop_alert.py` | G12 | +36 |
| `hooks/hook_utils.py` | Fix（G1 後修強化） | +10 |
| `prompts/team/todoist-query.md` | G6 | +8 |
| `specs/interface-spec/phase-results.md` | G4（新建） | +210 |
| `config/hook-rules.yaml` | G7 | +30 |
| `run-agent-team.ps1` | G8、G9、G14 | +263 |
| `run-todoist-agent-team.ps1` | G8、G9、G14 | +281 |
| `run-system-audit-team.ps1` | G8、G14 | +136 |
| `query-logs.ps1` | G8 | +120 |
| `check-health.ps1` | G9、G11、G12、G14 | +163 |
| `state/failure-stats.json` | G9（新建） | — |
| `D:\Source\wsc-bot01\bot.js` | G20 | +6 |
| `D:\Source\my-gun-relay\index.html` | G20、G21、G22 | +42 |
| 4 個 SKILL.md | G13 | +4 |

**淨增行數**：約 +1,955 行（P1+P2+P3 合計）

---

## 系統評分預估

| 時間點 | 評分 | 主要改善 |
|--------|------|---------|
| P0 完成後 | 82/100 | P0 BUG 清零 + VZ 可視化 |
| P1 完成後 | 85/100 | Interface Spec + Skill 別名 + Hook 邊界 + Gun.js P1 |
| P2 完成後 | 90/100 | Phase 時間線 + 失敗分類 + 交叉驗證 + Token 預算 |
| P3 完成後 | 93/100 | Skill DAG + FSM 狀態追蹤 |

---

## 下一步（選用 P3 延伸）

- **G15**：OODA 工作流引擎（`ooda-workflow.yaml` 配置驅動，估時 12-20h）
- **Gun.js 整合**：G28（chatroom Phase 1 注入）→ G29（chatroom-scheduler.py）
- **VZ3/VZ4**：Phase 時間線視覺化（依賴 G8）+ 聊天室執行摘要推播（依賴 Gun.js 整合）
