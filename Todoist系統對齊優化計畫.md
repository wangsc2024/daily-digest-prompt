# Todoist 系統對齊優化計畫

> 日期：2026-02-15
> 執行方式：Agent Team（3 並行 + 1 串行 + API 操作 + 驗證）

---

## 1. 背景與問題

審查發現 Todoist 任務與系統路由配置之間存在嚴重脫節：

| 問題 | 嚴重度 | 說明 |
|------|--------|------|
| Tier 1 標籤完全失效 | Critical | `@code` 等前綴從未在 Todoist 出現，Tier 1 命中率 = 0% |
| 遊戲優化無 Skill | Critical | 佔 39% 任務量（7/18）卻無對應 Skill 和路由 |
| 自動任務永不觸發 | Critical | 18 筆循環任務阻斷「無可處理項目」條件 |
| 計分同質化 | Warning | 15 筆 P2 全部同分 2.4，排序不可預期 |
| Tier 2 關鍵字缺口 | Warning | 遊戲/深度思維/Cloudflare/GitHub 等無關鍵字覆蓋 |
| Skill-Todoist 無同步 | Warning | 新增 Todoist 標籤時系統無法偵測路由缺口 |

**核心根因**：系統「以 Skill 為中心」，Todoist「以用戶需求為中心」，兩者缺乏同步。

---

## 2. Agent Team 執行架構

```
Team Lead（本次對話）
│
├── Phase 1: 並行修改（3 Agents 同時啟動）
│   ├── Agent A: config-updater    → 修改 config/*.yaml + HEARTBEAT.md（5 檔）
│   ├── Agent B: skill-creator     → 建立 game-design Skill + game-task 模板（2 檔）
│   └── Agent C: prompt-updater    → 修改 prompts/team/*.md + hour-todoist-prompt.md（4 檔）
│
├── Phase 2: 串行整合（Phase 1 完成後）
│   └── Agent D: index-integrator  → 更新 SKILL_INDEX.md + quality-gate.md + 模板引用（5 檔）
│
├── Phase 3: Todoist API 操作（Phase 2 完成後）
│   └── Team Lead 直接執行（刪除 5 筆 + 更新 2 筆 + 新增 1 筆）
│
└── Phase 4: 驗證
    └── Team Lead 交叉驗證所有檔案一致性
```

---

## 3. 變更詳細內容

### 3.1 Agent A: config-updater（配置層）

#### A1. `config/scoring.yaml` — 計分改版 v2

| 項目 | 舊值 | 新值 |
|------|------|------|
| version | 1 | 2 |
| max_tasks_per_run | 2 | 3 |
| formula | 3 因子 | 6 因子 |

**新增 3 個計分因子**：

```yaml
# 時間緊迫度（due date 距今天越近分數越高）
time_proximity_bonus:
  overdue: 1.5       # 已過期
  today: 1.3         # 今天到期
  tomorrow: 1.1      # 明天
  this_week: 1.0     # 本週
  no_due: 0.9        # 無截止日

# 標籤數量加成（更多標籤 = 更明確分類）
label_count_bonus:
  "0": 1.0
  "1": 1.05
  "2": 1.1
  "3+": 1.15

# 執行重複懲罰（避免同類型任務連續執行）
recency_penalty:
  enabled: true
  overlap_0_1: 1.0    # 0-1 個標籤重疊：無懲罰
  overlap_2: 0.85     # 2 個重疊
  overlap_3_plus: 0.7 # 3+ 個重疊
```

**完整公式**：
```
綜合分數 = Todoist 優先級分 × 信心度 × 描述加成 × 時間緊迫度 × 標籤數量加成 × 重複懲罰
```

**計分驗證範例**：

| 任務 | 舊分數 | 新分數 | 改善 |
|------|--------|--------|------|
| P1「深度瞭解待辦」(4標籤, today, Tier2) | 2.4 | 4.78 | +99% |
| P2 遊戲優化 (2標籤, today, Tier1) | 2.4 | 4.29 | +79% |
| P2 研究AI (1標籤+desc, today, Tier2) | 2.88 | 3.93 | +36% |
| P4 拍照 (0標籤, 未來, 跳過) | 0.6 | 0.54 | 被排除 |

---

#### A2. `config/routing.yaml` — 路由全面改版

##### Tier 1：`@` 前綴 → `^` + 中文標籤

**匹配規則**：`^prefix` 去掉 `^` 後與 Todoist labels 陣列完全比對。多標籤命中多個映射時，合併 skills 並取最寬 allowedTools。

| 新標籤 | 映射 Skill | allowedTools | 模板 |
|--------|-----------|-------------|------|
| `^Claude Code` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^GitHub` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^研究` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^深度思維` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^邏輯思維` | deep-research + knowledge-query | Read,Bash,Write,WebSearch,WebFetch | research-task.md |
| `^知識庫` | knowledge-query | Read,Bash,Write | skill-task.md |
| `^AI` | hackernews-ai-digest | Read,Bash,Write | skill-task.md |
| `^遊戲優化` | game-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^遊戲開發` | game-design | Read,Bash,Write,Edit,Glob,Grep | game-task.md |
| `^專案優化` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^網站優化` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |
| `^UI/UX` | 程式開發（Plan-Then-Execute） | Read,Bash,Write,Edit,Glob,Grep | code-task.md |

> 保留 `@news`、`@write` 供未來使用。

##### Tier 2：關鍵字擴充（+5 組）

| 新增關鍵字 | 匹配 Skill |
|-----------|-----------|
| 遊戲, game, 遊戲設計, 遊戲品質, HTML5 | game-design |
| 深度思維, 洞見, 報告, 分析, 反思 | knowledge-query |
| Cloudflare, Pages, 部署, 網站, CDN | game-design |
| GitHub, 開源, trending, repository | （依語義判斷） |
| 專案, 重構, 效能, performance | （依語義判斷） |

##### 新增：Skill 同步檢查（sync_check）

```yaml
sync_check:
  enabled: true
  description: "路由後檢查是否有 Todoist 標籤不在映射中"
  frequency: "每次執行，同一標籤 24h 內只提醒一次"
  tracking_field: "context/auto-tasks-today.json → warned_labels"
```

---

#### A3. `config/frequency-limits.yaml` — 觸發模式改革

新增雙觸發模式：

```yaml
trigger_modes:
  - name: "無可處理項目"
    description: "步驟 2 三層路由篩選後無任何可處理任務"
  - name: "今日任務全部完成"
    description: "步驟 4 執行完畢後重新查詢 Todoist，可處理項目 = 0"
```

tracking schema 新增 `warned_labels: []` 欄位。

---

#### A4. `config/notification.yaml`

通知模板末尾新增 Skill 同步警告區塊：
```
⚠️ Skill 同步提醒（如有未匹配標籤）
- 未匹配標籤：[列表]
- 建議更新 config/routing.yaml
```

---

#### A5. `HEARTBEAT.md` — Timeout 調整

| 排程 | 舊 timeout | 新 timeout | 原因 |
|------|-----------|-----------|------|
| todoist-team | 1800s (30min) | 2400s (40min) | 配合 max_tasks_per_run=3 |

---

### 3.2 Agent B: skill-creator（Skill 層）

#### B1. `skills/game-design/SKILL.md` — 新 Skill

**品質四大標準**（針對過去遊戲品質不佳的強制要求）：

| 標準 | 關鍵指標 |
|------|---------|
| 程式碼品質 | requestAnimationFrame、AABB/SAT 碰撞、資源預載、記憶體回收、鍵盤+滑鼠+觸控 |
| UX 品質 | 回饋延遲 < 100ms、漸進難度、響應式、WCAG AA 4.5:1 |
| 效能標準 | 60 FPS、首載 < 3s、單幀 < 16ms |
| 部署流程 | Cloudflare Pages 靜態部署 + 驗證 URL |

含知識庫整合（查詢 + 回寫）和 6 項程式碼審查清單。

#### B2. `templates/sub-agent/game-task.md` — 遊戲優化模板

8 Phase 流程（強調「品質第一」）：

```
Phase A: 現狀分析（不修改）→ 品質問題清單
Phase B: 知識庫查詢 → 歷史最佳實踐
Phase C: 規劃修改清單 → 優先級排序 + FPS/UX 改善標注
Phase D: 逐項實作 → 每改一項即驗證
Phase E: 整合驗證 → 完整流程 + 響應式 + 效能
Phase F: 部署 → Cloudflare Pages（若適用）
Phase G: 知識庫回寫 → 設計心得匯入 RAG
Phase H: 品質自評 → 最多自修正 2 次 + DONE_CERT
```

---

### 3.3 Agent C: prompt-updater（Prompt 層）

#### C1. `hour-todoist-prompt.md`

| 修改 | 位置 | 內容 |
|------|------|------|
| 計分公式 | 步驟 3 | 6 因子公式 + 說明 |
| Skill 同步檢查 | 新增步驟 2.9 | 收集 labels → 比對映射 → 輸出未匹配警告 |
| 自動任務觸發 | 新增步驟 4.6 | 完成後重查 Todoist → 無剩餘則觸發自動任務 |
| 觸發描述 | 步驟 2.5 | 「無待辦時**或**今日任務全部完成後觸發」 |

#### C2. `prompts/team/todoist-query.md`

- Tier 1 標籤表全面替換為 `^` + 中文（12 行）
- 計分 6 因子表格
- `取前 2 名` → `取前 3 名`
- 新增步驟 2.9 + plan JSON 加入 `sync_warnings` 欄位

#### C3. `prompts/team/todoist-assemble.md`

- `1-2 個` → `1-3 個`
- 新增步驟 2.5：完成後自動任務觸發判斷
- 通知模板加入 sync 警告

#### C4. `run-todoist-agent.ps1`

- `$MaxDurationSeconds`: 1800 → 2100（35min，配合 3 任務）

---

### 3.4 Agent D: index-integrator（索引整合層）

| 檔案 | 變更 |
|------|------|
| `skills/SKILL_INDEX.md` | 13 核心 + 1 工具 Skill、`^` 標籤路由表、決策樹新增遊戲、外部服務新增 Cloudflare |
| `templates/shared/quality-gate.md` | `@code` → `^Claude Code`、`@research` → `^研究`、新增遊戲驗證區塊 |
| `templates/sub-agent/code-task.md` | 使用時機更新為 `^Claude Code / ^GitHub / ^專案優化` |
| `templates/sub-agent/research-task.md` | 使用時機更新為 `^研究 / ^深度思維 / ^邏輯思維` |
| `CLAUDE.md` | Skill 數量更新為 14 個（13 核心 + 1 工具） |

---

### 3.5 Phase 3: Todoist API 操作

#### 刪除 5 筆遊戲優化任務（從 7 筆減為 2 筆）

| 動作 | 任務 ID | 時段 | 說明 |
|------|---------|------|------|
| **保留** | `6g2FHx9GPXf73qxX` | 10:00 | 白天品質優化 |
| **保留** | `6g2FHxPvqp5j7gj5` | 20:00 | 晚間品質優化 |
| 刪除 | `6g2FHx56jf3fFg45` | 09:00 | 與 10:00 重複 |
| 刪除 | `6g2FHxGCjfp5g94X` | 16:00 | 過密 |
| 刪除 | `6g2FHxMHcMfFgQp5` | 18:00 | 過密 |
| 刪除 | `6g2FHxV3vW6VWHh5` | 23:00 | 過晚 |
| 刪除 | `6g2FHx5WGXxgVw65` | 01:00（增加遊戲） | 合併到優化中 |

#### 更新保留的 2 筆遊戲任務描述

新增品質要求：
```
品質要求（必遵守）：
1. 先讀取 skills/game-design/SKILL.md
2. 先分析現有品質問題再修改
3. 目標 60FPS、響應式支援、無 console 錯誤
4. 每個修改有明確品質提升目的
5. 完成後知識庫回寫設計筆記
```

#### 新增「設計遊戲」研究任務

| 欄位 | 值 |
|------|------|
| content | 研究遊戲設計最佳實踐並寫入 RAG 知識庫 |
| labels | 研究, 遊戲開發, 知識庫 |
| priority | 3（P2） |
| due_string | every day at 11:00 |
| description | 研究 HTML5 遊戲設計模式、UX 最佳實踐、效能優化技巧。去重查詢知識庫後，選擇未覆蓋的主題深入研究。成果匯入 RAG 知識庫。 |

**路由驗證**：標籤 `研究`+`遊戲開發`+`知識庫` → Tier 1 命中 `^研究`（research-task.md）+ `^遊戲開發`（game-design）+ `^知識庫`（knowledge-query）→ 合併 skills。

---

## 4. Todoist-Skill 同步機制設計

### 問題
新增 Todoist 標籤時，routing.yaml 和 SKILL_INDEX.md 未同步更新，導致路由缺口。

### 解決方案：三層防線

```
第一層：即時偵測（每次執行）
  routing.yaml sync_check → 比對 labels vs 映射表 → 輸出未匹配警告

第二層：通知提醒（每次有缺口時）
  ntfy 通知末尾附加：⚠️ 未匹配標籤：[列表]

第三層：歷史追蹤（24h 去重）
  auto-tasks-today.json → warned_labels → 同標籤 24h 內只提醒一次
```

### 資料流

```
Todoist API 回傳任務
  → 提取所有 labels（去重）
  → 比對 routing.yaml label_routing 映射
  → 未匹配標籤 → 檢查 warned_labels（24h 去重）
  → 新發現 → 加入 warned_labels + 寫入 plan JSON sync_warnings
  → Phase 3 assembly 讀取 sync_warnings → 通知附加警告
```

---

## 5. 修改清單摘要

### 新建檔案（2）

| 檔案 | Agent | 用途 |
|------|-------|------|
| `skills/game-design/SKILL.md` | B | 遊戲設計與優化 Skill |
| `templates/sub-agent/game-task.md` | B | 遊戲優化子 Agent 模板 |

### 修改檔案（14）

| 檔案 | Agent | 變更摘要 |
|------|-------|---------|
| `config/scoring.yaml` | A | v2 計分：max=3 + 3 新因子 |
| `config/routing.yaml` | A | ^中文標籤 + 遊戲關鍵字 + 補缺 + sync_check |
| `config/frequency-limits.yaml` | A | trigger_modes + warned_labels |
| `config/notification.yaml` | A | sync 警告模板 |
| `HEARTBEAT.md` | A | todoist-team timeout 2400 |
| `hour-todoist-prompt.md` | C | 6 因子計分 + 步驟 2.9 + 步驟 4.6 |
| `prompts/team/todoist-query.md` | C | ^標籤 + 計分 + max=3 + sync |
| `prompts/team/todoist-assemble.md` | C | max=3 + 步驟 2.5 完成後觸發 |
| `run-todoist-agent.ps1` | C | MaxDuration 2100 |
| `skills/SKILL_INDEX.md` | D | 14 Skill + ^標籤表 + 決策樹 |
| `templates/shared/quality-gate.md` | D | ^標籤引用 + 遊戲驗證 |
| `templates/sub-agent/code-task.md` | D | 使用時機 ^標籤 |
| `templates/sub-agent/research-task.md` | D | 使用時機 ^標籤 |
| `CLAUDE.md` | D | Skill 數量 14 個 |

### Todoist API 操作（8 筆）

| 操作 | 數量 | 說明 |
|------|------|------|
| DELETE | 5 | 刪除多餘遊戲優化任務 |
| UPDATE | 2 | 更新保留任務描述（品質要求） |
| CREATE | 1 | 新增遊戲設計研究任務 |

---

## 6. 驗證計畫

### 6.1 路由一致性

- [ ] routing.yaml 所有 `^xxx` 去前綴後存在於 Todoist 實際標籤
- [ ] SKILL_INDEX.md 標籤路由表 = routing.yaml label_routing
- [ ] todoist-query.md Tier 1 表 = routing.yaml label_routing
- [ ] 所有 `template` 引用在 `templates/sub-agent/` 存在

### 6.2 計分正確性

- [ ] P1 任務分數 > P2 任務分數（區分度 > 10%）
- [ ] 有 description 的任務 > 無 description 的同級任務
- [ ] overdue 任務 > today 任務 > tomorrow 任務
- [ ] 重複標籤任務受到懲罰

### 6.3 自動任務觸發

- [ ] hour-todoist-prompt.md 步驟 4.6 邏輯完整
- [ ] todoist-assemble.md 步驟 2.5 在 plan_type="tasks" + success 時觸發
- [ ] frequency-limits.yaml trigger_modes 文件齊全

### 6.4 Skill 同步

- [ ] sync_check 段落存在於 routing.yaml
- [ ] warned_labels 欄位存在於 initial_schema
- [ ] plan JSON 含 sync_warnings 欄位

### 6.5 Todoist 任務

- [ ] 遊戲優化任務 = 2 筆
- [ ] 新研究任務存在，標籤 = 研究+遊戲開發+知識庫
- [ ] 保留任務描述含品質要求

---

## 7. Timeout 架構總覽

| 層級 | 舊值 | 新值 | 說明 |
|------|------|------|------|
| 子 Agent 單次 | 600,000ms (10min) | 不變 | 單個任務執行上限 |
| 單一模式總時限 | 1800s (30min) | **2100s (35min)** | 配合 3 任務 |
| 團隊 Phase 1 | 300s (5min) | 不變 | 查詢+路由+規劃 |
| 團隊 Phase 2 | 動態計算 | 不變 | buffer + max(任務 timeout) |
| 團隊 Phase 3 | 180s (3min) | 不變 | 組裝+通知 |
| 團隊排程上限 | 1800s (30min) | **2400s (40min)** | 安全邊界 |
| 單一排程上限 | 3600s (60min) | 不變 | 已足夠 |

---

## 8. 風險評估

| 變更 | 風險 | 緩解措施 |
|------|------|---------|
| Tier 1 標籤改版 | 中（中文拼寫錯誤導致不匹配） | Phase 4 交叉驗證 Todoist 實際標籤 |
| 計分 v2 | 中（Agent 誤解 6 因子公式） | output_format 含各因子欄位便於除錯 |
| 自動任務觸發改革 | 中高（額外 API 呼叫 + 團隊模式複雜） | 團隊模式僅記錄建議不執行 |
| game-design Skill | 低（新檔案無依賴） | 遵循現有 SKILL.md 格式 |
| Todoist 任務操作 | 低（可逆） | API 操作前確認 ID |
| sync_check 機制 | 低（僅診斷不影響執行） | warned_labels 24h 去重 |
