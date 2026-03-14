# Plan: skill-forge — 知識庫驅動的 Skill 自動生成器

## Context

本系統已有 30 個 Skill，但沒有任何「生成新 Skill」的能力。
`context/improvement-backlog.json` 記錄了 5 個待改善項目，
`context/system-insight.json` 顯示快取命中率僅 14.57%（目標 40%），
`context/adr-registry.json` 有 6 個 ADR 狀態為 partial/pending。
這些上下文是「系統最需要什麼」的信號，但目前無機制自動將其轉化為 Skill。

**目的**：建立 `skill-forge` Skill，讓排程器每日自動分析三大上下文，
基於知識庫深研，生成一個能提升/增加/優化本系統功能的新 SKILL.md，
並自動整合進 SKILL_INDEX.md。

---

## 需要建立/修改的檔案（共 5 個）

| 操作 | 路徑 | 說明 |
|------|------|------|
| CREATE | `skills/skill-forge/SKILL.md` | Skill 核心定義（10 步驟） |
| CREATE | `prompts/team/todoist-auto-skill_forge.md` | 排程自動任務 Prompt |
| MODIFY | `config/frequency-limits.yaml` | 新增 `skill_forge` 任務定義 |
| MODIFY | `config/timeouts.yaml` | 新增 `skill_forge: 900` |
| MODIFY | `skills/SKILL_INDEX.md` | 登錄第 31 個 Skill |

---

## 實作計畫

### 1. `skills/skill-forge/SKILL.md`

#### Frontmatter

```yaml
---
name: skill-forge
version: "1.0.0"
description: |
  Skill 鑄造廠。分析系統三大上下文（improvement-backlog、adr-registry、system-insight），
  識別最高價值的能力缺口，基於知識庫深研自動生成完整可用的 SKILL.md，
  並執行格式驗證、安全掃描後整合至 SKILL_INDEX.md。
  Use when: 排程自動 Skill 生成、系統能力缺口識別、新 Skill 鑄造、ADR 技術方案落地。
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "skill-forge"
  - "生成 Skill"
  - "新增 Skill"
  - "Skill 缺口"
  - "能力缺口"
  - "Skill 鑄造"
  - "自動生成技能"
depends-on:
  - kb-research-strategist
  - skill-scanner
---
```

#### 10 步驟執行邏輯

**步驟 0：前置讀取**
- 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
- 讀取 `skills/SKILL_INDEX.md`（現有 30 個 Skill 認知地圖）

**步驟 1：三大上下文並行讀取**

同時讀取三個信號來源，提取「Skill 化信號」：
- `context/improvement-backlog.json`：取 effort=low/medium 且未被現有 Skill 覆蓋的項目
- `context/adr-registry.json`：取 `implementation_status=pending/partial` 的 ADR，判斷是否需要新 Skill 落地
- `context/system-insight.json`：取 `alerts[]`（critical/warning）和 `recommendations[]`，識別功能缺口

**步驟 2：優先級矩陣評分**（滿分 100 分，選最高 1 個）

```
信號強度（0-40）：
  system-insight critical alert → 40
  improvement-backlog P1 → 35
  ADR pending + effort=medium → 25
  improvement-backlog P2 → 20
  system-insight warning → 20
  skill_heatmap top-3 子需求 → 15

技術可行性（0-30）：
  只需 Read/Write/Bash → 30
  需外部 API（可快取）→ 20
  需 WebSearch → 15

KB 支援度（0-30）：
  KB 有 3+ 篇相關筆記 → 30
  KB 有 1-2 篇相關筆記 → 20
  KB 無相關筆記 → 5

去重罰分（0 to -30）：
  現有 Skill 80%+ 覆蓋 → -30（排除，選次高分）
  現有 Skill 50-80% 覆蓋 → -15
```

**開創性門檻**（必要條件，非加分項）：

候選 Skill 必須通過開創性測試才能進入後續步驟：

> 「這個 Skill 提供的能力，能否透過**組合現有 2-3 個 Skill** 達成？」
>
> 若答案是「可以」→ 排除此候選，選次高分。
> 若答案是「否，現有 Skill 的組合無法完成此任務」→ 通過。

判斷標準（LLM 在步驟 2 自行評估）：
- **通過**：需要新的 API 整合、新的決策邏輯、新的外部資料來源，或現有 Skill 沒有的輸出格式
- **不通過**：本質上是「先呼叫 A Skill，再呼叫 B Skill」的流程包裝，沒有新增系統能力

**步驟 3：去重確認（委派 Explore 子 Agent）**

主 Agent 委派子 Agent 掃描 `skills/` 下所有 `SKILL.md` 前 30 行，
回傳結構化 JSON（skill 名稱 + triggers + description_keywords），
主 Agent 只接收摘要（每個 Skill ≈ 200 bytes，30 個 ≈ 6KB，保護主 Context Window）。

對候選 Skill 的目的關鍵詞計算與現有 Skill 的重疊率，
若 > 60% 則選次高分候選，標記降級原因。

**步驟 4：KB 深研（呼叫 kb-research-strategist）**

讀取 `skills/kb-research-strategist/SKILL.md`，
以選定的 Skill 主題為研究主題，執行完整 7 步驟，
輸出 `context/kb-research-brief.json`。

研究目標：收集足以讓 LLM 生成具體可執行 Skill 步驟的知識：
- 目標 Skill 的 API 端點/命令格式/輸出結構
- Windows/PowerShell 用法
- 可能的失敗模式與降級策略

**降級與版本機制**：

| KB 研究狀態 | 生成版本 | 說明 |
|------------|--------|------|
| `recommendation: deepen/series_continue`，`notes_analyzed ≥ 3` | **v1.0.0** | 知識充足，正式版 |
| `notes_analyzed: 1-2`（知識薄弱）| **v0.5.0** | 半草稿，description 末尾加注「建議透過 skill-audit 補強」 |
| `recommendation: skip_kb_down`（KB 不可用）| **v0.1.0** | 草稿版，description 開頭加「⚠️ 草稿版（KB 不可用時生成）」，整合時歸類為「草稿 Skill」 |

版本號寫入 frontmatter `version:` 欄位，`skills/SKILL_INDEX.md` 的版本欄顯示實際版本號，草稿版標記 `[草稿]`。

**步驟 5：生成 SKILL.md**

依以下輸入生成完整的 SKILL.md，寫入 `skills/{skill_name}/SKILL.md`：
- 步驟 1 的信號上下文（`what` 和 `why`）
- `context/kb-research-brief.json`（`how` 的知識基礎）
- 步驟 3 子 Agent 回傳中最相似的現有 Skill（格式參考）

**生成約束（嚴格遵守）**：
1. Frontmatter 含：name、version、description（含 "Use when"）、allowed-tools、cache-ttl、triggers ≥ 3、depends-on
2. 步驟有編號，每步有輸入/輸出說明
3. 必含降級處理章節
4. 不用佔位符（不允許「此處填入你的邏輯」）
5. curl 呼叫必須用 Write 建立 JSON 檔（Windows 環境限制）
6. 禁止 `> nul`，用 `> /dev/null 2>&1`

**步驟 6：格式驗證 + 內容字數下限**

```bash
uv run python -X utf8 -c "
import yaml, sys
content = open('skills/{skill_name}/SKILL.md', encoding='utf-8').read()
data = yaml.safe_load(content.split('---')[1])
required = ['name','version','description','allowed-tools','cache-ttl','triggers']
missing = [f for f in required if f not in data]
body = content.split('---', 2)[2] if content.count('---') >= 2 else ''
print('MISSING:', missing)
print('HAS_USE_WHEN:', 'Use when' in data.get('description',''))
print('TRIGGERS_COUNT:', len(data.get('triggers',[])))
print('BODY_CHARS:', len(body))
print('PASS:', not missing and 'Use when' in data.get('description','') and len(data.get('triggers',[])) >= 3 and len(body) >= 600)
"
```

驗證標準：
- Frontmatter 必填欄位齊全
- `description` 含 "Use when"，`triggers` ≥ 3 個
- **步驟本體（frontmatter 以外）字數 ≥ 600 字元**（防止空洞型 Skill）

若驗證失敗，用 Edit 修正，最多重試 2 輪。

**步驟 6.5：LLM 自評分（Reflexion 品質閘門）**

格式驗證通過後，進行第二輪自我批評評估：

Agent 以**批評者角色**（非生成者）重新評估剛生成的 SKILL.md，
對以下 5 個維度各打 1-10 分，計算平均分：

| 維度 | 說明 |
|------|------|
| **完整性** | 步驟是否涵蓋完整執行流程（含降級、輸出格式） |
| **可執行性** | 每個步驟是否有具體指令/命令/JSON 格式，而非抽象描述 |
| **系統價值** | 是否真實解決 improvement-backlog 或 system-insight 的問題 |
| **開創性** | 是否提供現有 30 個 Skill 組合無法達成的新能力 |
| **Windows 相容性** | curl 是否用 Write 建立 JSON 檔、是否避免 `> nul`、是否使用 uv run python |

**閾值規則**：
- 平均分 ≥ 7.0 → 通過品質門檻，繼續步驟 7
- 平均分 5.0-6.9 → 依自評的最低分維度修改 SKILL.md，重新評分（最多 1 次）
- 平均分 < 5.0 → 此次生成失敗，在結果 JSON 記錄 `status: "quality_rejected"`，
  不整合 SKILL_INDEX.md，記錄拒絕原因供下次參考

自評結果加入結果 JSON：
```json
"quality_score": {
  "completeness": 8,
  "actionability": 7,
  "system_value": 9,
  "originality": 8,
  "windows_compat": 10,
  "average": 8.4,
  "pass": true
}
```

**步驟 7：skill-scanner 安全掃描**

讀取 `skills/skill-scanner/SKILL.md`，對新生成的 Skill 執行掃描。
- clean / warning → 繼續整合
- medium/high finding → 記錄 `integration_status: "held_for_review"`，
  不更新 SKILL_INDEX.md，發送 ntfy 告警
- scanner 不存在 → 標記 `scanner_skipped: true`，繼續整合

**步驟 8：SKILL_INDEX.md 整合**

用 Read + Edit 在 SKILL_INDEX.md 的工具 Skill 表格末尾追加一列，
並更新速查表頂部的 Skill 總數數字（30 → 31）。

**步驟 9：匯入知識庫**

依 `skills/knowledge-query/SKILL.md`，將本次生成報告匯入 KB：
- title: `skill-forge 生成報告：{skill_name}（{日期}）`
- tags: `["skill-forge", "Skill生成", "系統改進", "{skill_name}"]`
- source: `"import"`

**步驟 10：通知 + 結果 JSON**

發送 ntfy（topic: wangsc2025），寫入 `results/todoist-auto-skill_forge.json`：

```json
{
  "agent": "todoist-auto-skill_forge",
  "task_type": "auto",
  "task_key": "skill_forge",
  "status": "success | partial | quality_rejected | failed",
  "generated_skill": {
    "name": "生成的 Skill 名稱",
    "path": "skills/{skill_name}/SKILL.md",
    "version": "1.0.0 | 0.5.0 | 0.1.0",
    "is_draft": false,
    "signal_source": "improvement-backlog | adr-registry | system-insight",
    "signal_item": "對應信號描述",
    "originality_passed": true
  },
  "kb_research": { "used": true, "series_id": null, "stage": "...", "notes_analyzed": 3 },
  "quality_score": {
    "completeness": 8,
    "actionability": 7,
    "system_value": 9,
    "originality": 8,
    "windows_compat": 10,
    "average": 8.4,
    "pass": true,
    "rejection_reason": null
  },
  "scanner_result": { "status": "clean", "findings_count": 0 },
  "skill_index_updated": true,
  "kb_imported": true,
  "integration_status": "integrated | held_for_review | quality_rejected",
  "summary": "一句話摘要",
  "error": null
}
```

---

### 2. `prompts/team/todoist-auto-skill_forge.md`

```markdown
# Skill 鑄造 Agent（skill-forge）

你是 Skill 鑄造 Agent，全程使用正體中文。
任務：分析系統能力缺口，生成一個新的可用 Skill。
完成後寫入 `results/todoist-auto-skill_forge.json`。

## 共用規則
先讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）。

必須先讀取以下 SKILL.md：
- `skills/SKILL_INDEX.md`
- `skills/skill-forge/SKILL.md`
- `skills/knowledge-query/SKILL.md`
- `skills/ntfy-notify/SKILL.md`

## 執行
依 `skills/skill-forge/SKILL.md` 的完整 10 步驟執行。

## 禁止事項
- 禁止修改 scheduler-state.json、config/frequency-limits.yaml、config/timeouts.yaml
- 禁止修改現有任何 SKILL.md（只能建立新 Skill）
- 禁止修改現有 prompts/team/ 下的任何 prompt 檔案
- 禁止使用 `> nul`（用 `> /dev/null 2>&1`）
```

**注意**：此 Prompt 是**單階段**（無計數器型多階段），
每次執行即為完整的生成閉環。

---

### 3. `config/frequency-limits.yaml` 修改

**① 在 `initial_schema` JSON 字串新增計數欄位**（`podcast_jiaoguangzong_count` 後）：
```
    "skill_forge_count": 0,
```

**② 在 `tasks:` 區塊末尾（`podcast_jiaoguangzong` 後）新增任務**：
```yaml
  # --- Skill 鑄造群組（共 1 次/日）---
  skill_forge:
    name: "Skill 自動鑄造"
    daily_limit: 1
    counter_field: "skill_forge_count"
    template: "prompts/team/todoist-auto-skill_forge.md"
    template_version: 1
    history_type: "skill_forge"
    execution_order: 24
    skills: [kb-research-strategist, skill-scanner, knowledge-query, ntfy-notify]
    description: "分析三大上下文（improvement-backlog + adr-registry + system-insight）識別 Skill 缺口，基於 KB 深研自動生成完整可用的 SKILL.md，安全驗證後整合至 SKILL_INDEX.md"
```

**③ 更新群組摘要注釋**（第 259-268 行附近）：
```yaml
# 群組摘要（11 群組，23 任務，合計 25 次/日）：
# ...（在末尾加）
#   Skill 鑄造:      #24    (1 次/日) — skill-forge(1)
```

**④ 更新每日上限摘要注釋**（第 601 行附近）：
```yaml
# Skill 鑄造（claude_sonnet 預設）：skill-forge(1) = 1
# 合計：15 次/日（...）
```

**後端選擇**：`skill_forge` 不加入 `task_rules` 任何後端，
預設使用 `claude_sonnet`（空 cli_flag，即當前環境的 claude-sonnet-4-6），
這是最適合創意生成型任務的選擇。

---

### 4. `config/timeouts.yaml` 修改

在 `phase2_timeout_by_task:` 區塊末尾（`podcast_jiaoguangzong: 2400` 後）新增：
```yaml
    # === Skill 鑄造（claude_sonnet 預設）===
    skill_forge: 900            # 上下文讀取(30s) + 子Agent去重(60s) + KB研究(300s) + Skill生成(120s) + 驗證整合(120s)
```

---

### 5. `skills/SKILL_INDEX.md` 修改

在工具 Skill 表格末尾追加一列：
```
| 31 | skill-forge | 分析系統需求缺口，自動鑄造新 SKILL.md | skill-forge、生成 Skill、Skill 缺口 |
```

並更新頂部速查表的 Skill 計數（「19 核心 + 7 工具 = 26 個」→ 根據實際數字調整）。

---

## 驗證方法

1. **自動任務一致性驗證**：
   ```bash
   uv run python hooks/validate_config.py --check-auto-tasks
   ```
   確認 `skill_forge` 的 task_key 與 prompt 檔名（`todoist-auto-skill_forge.md`）一致。

2. **系統健康檢查**：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File check-health.ps1
   ```
   確認「自動任務一致性」區塊通過。

3. **手動首次執行（驗證端對端）**：
   ```powershell
   pwsh -ExecutionPolicy Bypass -File run-todoist-agent-team.ps1
   ```
   執行後確認：
   - `results/todoist-auto-skill_forge.json` 存在，`agent` = `"todoist-auto-skill_forge"`
   - `skills/{新 skill 名}/SKILL.md` 存在，frontmatter 格式正確
   - `skills/SKILL_INDEX.md` 有新增一列
   - ntfy topic `wangsc2025` 收到通知

4. **Frontmatter 格式驗證**（手動執行）：
   ```bash
   uv run python -X utf8 -c "
   import yaml, glob
   for f in glob.glob('skills/*/SKILL.md'):
       d = yaml.safe_load(open(f, encoding='utf-8').read().split('---')[1])
       missing = [k for k in ['name','version','description','triggers'] if k not in d]
       if missing: print(f, 'MISSING:', missing)
   "
   ```

---

## 設計決策說明

| 決策 | 理由 |
|------|------|
| 單階段執行（無計數器） | Skill 生成是完整原子操作，不像 ai_deep_research 需跨次積累 |
| daily_limit=1 | 品質優先；每個 Skill 需觀察期；避免遞歸爆炸（skill-forge 生成 skill-forge 的 Skill）|
| 預設 claude_sonnet（不加 task_rules）| 4.6 是最強大的創意生成模型，適合撰寫複雜 SKILL.md |
| 委派子 Agent 做去重掃描 | 30 個 SKILL.md 合計 >100KB，違反主 Context 保護原則 |
| 新 Skill 預設歸類「工具 Skill」| 保留人工確認點，避免 skill-forge 的輸出直接觸發更多自動化 |
