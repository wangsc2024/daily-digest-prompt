# P0 優化實施報告 — 2026-02-28

## 總覽

本次實施為系統借鑑洞察優化計畫的 **Week 1 Day 1-2 項目（P0 緊急修復 + Gun.js P0 + 可視化看板）**，共完成 **8 個優化項目**：G1、G2、G3、G17、G18、G19、VZ1、VZ2。

測試驗證：**532/532 全數通過**（+ 36 較前一 session 新增）。

---

## 實施項目詳情

### G1 — 原子寫入保護（P0 緊急）

**問題**：`CircuitBreaker._save_state()` 使用普通 `json.dump()` 直接寫入，多個並行 Agent 同時更新 `state/api-health.json` 時可能造成 JSON 損壞。

**修改檔案**：
- `hooks/hook_utils.py`（+21 行）：新增 `atomic_write_json(filepath, data)` 函式
  - 實現：write-to-temp（`tempfile.NamedTemporaryFile`）+ `os.replace()`（POSIX + Windows NTFS 原子操作）
  - 自動建立目錄（`os.makedirs`）
- `hooks/agent_guardian.py`（+5 行，-2 行）：`CircuitBreaker._save_state()` 改呼叫 `atomic_write_json`
  - 含 `try/except ImportError` fallback（確保 hook_utils 不可用時仍能運作）

**技術要點**：`os.replace()` 在 Python 3.3+ 保證原子性，即使目標已存在也會無條件覆蓋，不留下中間狀態。

---

### G2 — auto-tasks-today 版本戳（P0 緊急）

**問題**：兩個 `run-todoist-agent-team.ps1` 排程若重疊，Phase 3 的 `read-modify-write` 會互相覆蓋計數，導致任務執行次數記錄偏低。

**修改檔案**：
- `prompts/team/todoist-assemble.md`（步驟 3 + 9 行）：新增版本戳樂觀鎖邏輯
  - 讀取時記錄 `write_version`（不存在視為 0）
  - 寫入時遞增版本；若偵測到衝突（版本不符），以各 `*_count` 欄位最大值合併
- `context/auto-tasks-today.json`（+1 欄位）：新增 `"write_version": 0`

**設計決策**：採用「最大值合併」而非「後者覆蓋」，確保計數不會因競態而遺失。

---

### G3 — Trace ID Phase 標記（P0 緊急）

**問題**：`DIGEST_TRACE_ID` 已生成並傳遞，但 JSONL 日誌缺少 Phase 資訊，無法區分「哪個工具呼叫屬於哪個 Phase / Agent」，調試困難。

**修改檔案**：
- `hooks/post_tool_logger.py`（+2 行）：JSONL entry 新增 `"phase"` 和 `"agent"` 欄位（讀取 `AGENT_PHASE`、`AGENT_NAME` 環境變數）
- `run-agent-team.ps1`（Phase 1 +2 行，Phase 2 +2 行）：
  - Phase 1 Start-Job：`AGENT_PHASE=phase1`，`AGENT_NAME=$agentName`
  - Phase 2 直接執行：`$env:AGENT_PHASE="phase2"`，`$env:AGENT_NAME="assemble-digest"`
- `run-todoist-agent-team.ps1`（各 Phase +2 行，共 +8 行）：
  - Phase 1：`AGENT_PHASE=phase1`，`AGENT_NAME=todoist-query`
  - Phase 2 tasks：`AGENT_PHASE=phase2`，`AGENT_NAME=$taskName`
  - Phase 2 auto：`AGENT_PHASE=phase2-auto`，`AGENT_NAME=$agentName`
  - Phase 3：`AGENT_PHASE=phase3`，`AGENT_NAME=todoist-assemble`
- `run-system-audit-team.ps1`（Phase 1 +2 行，Phase 2 +2 行）：
  - Phase 1：`AGENT_PHASE=phase1`，`AGENT_NAME=$agentName`（dim1-5/dim2-6/dim3-7/dim4）
  - Phase 2：`AGENT_PHASE=phase2`，`AGENT_NAME=assemble-audit`

**效益**：JSONL 日誌現在可依 `phase` 過濾，快速定位問題發生在哪個 Phase 的哪個 Agent。

---

### G17 — Gun.js ACK 邏輯與超時修正（Gun.js P0）

**問題**：`index.html` L1060 的 `resolve(!ack.err)` 語義模糊（`null`/`undefined` 均為 falsy，即使成功也可能 ack.err 為 null 而非成功標誌）；5s 超時在行動網路 / relay 冷啟動時過短。

**修改**：`D:\Source\my-gun-relay\index.html`
- L1057：`setTimeout(..., 5000)` → `setTimeout(..., 12000)`（+7s）
- L1060：`resolve(!ack.err)` → `resolve(ack && ack.ok === true)`（明確語義）

---

### G18 — 重連去重強化（Gun.js P0）

**問題**：
- B2：`.map().on()` 不在重連時清理，重連後 Gun 重推歷史訊息，24h TTL 去重 Map 若已過期則舊訊息再次顯示
- B3：`sentMessageIds` 在重連後未清理，他人訊息被誤判為自己發送（顯示藍泡）

**修改**：`D:\Source\my-gun-relay\index.html`

新增 `listenerRef` 變數與 `attachMessageListener()` 函式：
```javascript
function attachMessageListener() {
    if (listenerRef) {
        gun.get(chatRoomName).map().off();
        sentMessageIds.clear();  // 清理自己訊息集合
        listenerRef = null;
    }
    const seenThisSession = new Set();  // 本次 session 去重
    listenerRef = async (data, id) => {
        if (seenThisSession.has(id)) return;
        if (displayedMessages.has(id)) return;
        seenThisSession.add(id);
        try {
            const decryptedMsg = await SEA.decrypt(data, sharedSecret);
            if (decryptedMsg) { displayedMessages.set(id, Date.now()); displayMessage(decryptedMsg, id); }
        } catch (err) { console.warn('[Gun] 解密失敗 id=%s err=%s', id, err?.message); }
    };
    gun.get(chatRoomName).map().on(listenerRef);
}
```
原 `.on()` 呼叫替換為 `attachMessageListener()`，實現**雙層去重**：
- 層 1：`seenThisSession`（本次連線 Set）
- 層 2：`displayedMessages`（24h TTL Map）

---

### G19 — bot.js 啟用 radisk 持久化（Gun.js P0）

**問題**：`D:\Source\wsc-bot01\bot.js` L163 的 `Gun({ peers: [...] })` 未啟用 `radisk`，bot 重啟後 Gun graph 全部消失，pending 任務遺失。

**修改**：
```javascript
// 修前
const gun = Gun({ peers: GUN_RELAY_URL ? [GUN_RELAY_URL] : [] });

// 修後
const gun = Gun({
    peers: GUN_RELAY_URL ? [GUN_RELAY_URL] : [],
    radisk: true,       // 持久化至 data/radata/（重啟後恢復 Gun graph）
    axe: false,         // 避免 put ACK 異常
    localStorage: false,
});
```

---

### VZ1 — 今日自動任務看板（check-health.ps1）

**新增功能**：`check-health.ps1` 末尾新增 `[今日自動任務看板]` 區塊（+62 行）

讀取 `context/auto-tasks-today.json` + `config/frequency-limits.yaml`，顯示：

```
[今日自動任務看板]
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  任務名稱          今/限  進度        狀態
  ──────────────────────────────────────────────────────
  楞嚴經研究    0/5   ░░░░░   (今日未執行)
  教觀綱宗研究  0/3   ░░░     (今日未執行)
  AI 深度研究   1/4   █░░░    ✓
  系統洞察分析  1/1   █       ✓完成
  ...
  ──────────────────────────────────────────────────────
  總計: 10/45 次 (22%)  ███░░░░░░░░░░░░
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**顏色編碼**：未執行(灰)、進行中(青)、完成(綠)

---

### VZ2 — 7 天完成矩陣（query-logs.ps1）

**新增功能**：`query-logs.ps1 -Mode task-board -Days N`（預設 7 天，+75 行）

讀取 `state/todoist-history.json`，輸出橫向日期 × 縱向任務的 ASCII 矩陣：

```
[自動任務 7 天完成矩陣]
  任務名稱       02/22  02/23  02/24  02/25  02/26  02/27  02/28
  ─────────────────────────────────────────────────────────────────
  楞嚴經研究      ████   ███    ████   ███    ████   ███    ████
  AI 深度研       ██     ██     ███    ██     ███    ██     ██
  系統洞察         █      █      █      █      █      █      █
  ...
  ─────────────────────────────────────────────────────────────────
  圖例：░=0次  █=1  ██=2  ███=3  ████=4+
  ⚠ 連續 3 天以上未執行（可能饑餓）：- GitHub 靈感蒐集
```

**飢餓偵測**：自動亮顯連續 3 天以上未執行的任務（黃色警示）。

---

## 測試結果

```
532 passed in 5.51s
```

所有 532 個測試全數通過，無回歸問題。

---

## 修改檔案總覽

| 檔案 | 優化項目 | 變更內容 |
|------|---------|---------|
| `hooks/hook_utils.py` | G1 | +21 行：`atomic_write_json()` |
| `hooks/agent_guardian.py` | G1 | +5/-2 行：`_save_state()` 改原子寫入 |
| `hooks/post_tool_logger.py` | G3 | +2 行：JSONL entry 加 `phase`/`agent` |
| `prompts/team/todoist-assemble.md` | G2 | +9 行：版本戳樂觀鎖邏輯 |
| `context/auto-tasks-today.json` | G2 | +1 欄位：`write_version: 0` |
| `run-agent-team.ps1` | G3 | +4 行：Phase 1/2 環境變數 |
| `run-todoist-agent-team.ps1` | G3 | +8 行：Phase 1/2/2-auto/3 環境變數 |
| `run-system-audit-team.ps1` | G3 | +4 行：Phase 1/2 環境變數 |
| `D:\Source\my-gun-relay\index.html` | G17/G18 | +32/-10 行：ACK 修正 + 重連去重 |
| `D:\Source\wsc-bot01\bot.js` | G19 | +4/-1 行：radisk 啟用 |
| `check-health.ps1` | VZ1 | +62 行：ASCII 任務看板 |
| `query-logs.ps1` | VZ2 | +76 行：7 天矩陣 + 飢餓偵測 |

**淨增行數**：約 +225 行

---

## 下一步（Week 1 Day 3-5）

- **G4**：Phase 協議文檔（`specs/interface-spec/phase-results.md`）
- **G5**：Skill 別名映射修正（`config/routing.yaml`）
- **G6**：自動任務輪轉算法精確化（`todoist-query.md`）
- **G7**：Hook 邊界案例補充（`hook-rules.yaml` + 測試）
- **G20**：Bot epub 簽章驗證（SEA.sign/verify）
- **G21**：API Key sessionStorage 遷移
- **G22**：排程 API 指數退避（index.html）
