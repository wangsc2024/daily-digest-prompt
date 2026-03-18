---
name: skill-forge
version: "1.0.0"
description: |
  Skill 鑄造廠。分析系統三大上下文（improvement-backlog、adr-registry、system-insight），
  識別最高價值的能力缺口，基於知識庫深研自動生成完整可用的 SKILL.md，
  並執行格式驗證、LLM 自評分（≥7/10）、安全掃描後整合至 SKILL_INDEX.md。
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
  - ntfy-notify
  - knowledge-query
  - "config/dependencies.yaml"
---

# Skill Forge — 知識庫驅動的 Skill 自動生成器

> **端點來源**：`config/dependencies.yaml`（deps key: `knowledge_query, ntfy_notify`）— ADR-001 Phase 3

## 設計哲學

本 Skill 是**元認知 Skill**：不執行具體領域任務，而是分析系統自身的能力空白，製造新的 Skill 來填補。

執行鏈：
```
觀測（三大上下文）→ 識別（優先級矩陣 + 開創性門檻）→ 去重（Explore 子 Agent）
→ 研究（kb-research-strategist）→ 生成（SKILL.md）→ 驗證（格式 + 字數 + LLM 自評分）
→ 安全掃描（skill-scanner）→ 整合（SKILL_INDEX.md）→ 通知
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令，遵守其中所有規則）
2. 讀取 `skills/SKILL_INDEX.md`（建立現有 Skill 的完整認知地圖）

---

## 步驟 1：三大上下文並行讀取

同時讀取以下三個信號來源，提取「Skill 化信號」清單：

**1a. `context/improvement-backlog.json`**
- 篩選條件：`effort` = low 或 medium，且 `description` 未被現有 Skill 直接覆蓋
- 重點關注：描述中含「缺乏工具」「無法自動化」「需要 Agent 能力」「無 Skill 支援」的項目

**1b. `context/adr-registry.json`**
- 篩選條件：`implementation_status` = pending 或 partial
- 判斷：ADR 的 `decision` 欄位是否暗示需要一個新 Skill 才能執行（而非只是修改配置）

**1c. `context/system-insight.json`**
- 提取：`alerts[]`（critical/warning）、`recommendations[]`、`skill_heatmap`（top 5）
- 識別：高頻 Skill 的未覆蓋子需求，以及 critical alert 指向的功能缺口

**輸出**：產生候選 Skill 清單（每個候選含 what/why/signal_source 三要素）

---

## 步驟 2：優先級矩陣評分 + 開創性門檻

### 2a. 優先級評分（滿分 100 分）

對每個候選 Skill 計算分數，選取**最高分 1 個**：

```
信號強度評分（0-40 分）：
  system-insight critical alert       → 40 分
  improvement-backlog P1 項目         → 35 分
  ADR pending + effort=medium         → 25 分
  improvement-backlog P2 項目         → 20 分
  system-insight warning              → 20 分
  skill_heatmap top-3 的子需求        → 15 分

技術可行性評分（0-30 分）：
  只需 Read/Write/Bash/Grep/Glob      → 30 分
  需外部 API（可快取）                → 20 分
  需 WebSearch                        → 15 分
  需安裝新工具                        → 5 分

KB 支援度評分（0-30 分）：
  KB 有 3+ 篇相關筆記                 → 30 分
  KB 有 1-2 篇相關筆記                → 20 分
  KB 無相關筆記                       → 5 分

去重罰分（-30 至 0 分）：
  現有 Skill 80%+ 覆蓋 → -30 分（排除，選次高分）
  現有 Skill 50-80% 覆蓋 → -15 分
  現有 Skill <50% 覆蓋  → 0 分
```

### 2b. 開創性門檻（必要條件，不達標即排除）

對評分最高的候選，進行開創性評估：

> 「這個 Skill 的能力，能否透過**組合現有 2-3 個 Skill** 完全達成？」
>
> - 若「可以」→ 排除此候選，選次高分，重新評估
> - 若「否」→ 通過，繼續步驟 3

**通過判斷標準**：需要以下任一新要素
- 新的 API 整合或資料來源
- 新的決策邏輯（不是現有邏輯的組合）
- 現有 Skill 沒有的輸出格式或儲存目標
- 跨系統整合（需要兩個以上外部系統交互）

**不通過判斷標準**：本質上是「先呼叫 A Skill，再呼叫 B Skill」的流程包裝，沒有新增系統能力

**⚠️ 終止條件**：若所有候選均已排除（候選清單耗盡），不要無限循環。
立即查閱本 Skill 底部「降級處理總覽」的「所有候選均不通過開創性門檻」條目，
降低門檻至「提供主要功能改善」，選開創性評分最高的候選繼續執行。

---

## 步驟 3：去重確認（委派 Explore 子 Agent）

**保護主 Context Window**：30 個 SKILL.md 合計 >100KB，不直接讀取。

委派 Explore 子 Agent 執行：
> 掃描 `skills/` 目錄下所有子目錄的 `SKILL.md`，讀取每個的前 30 行（frontmatter 區段）。
> 回傳 JSON 陣列，每個元素格式：
> `{"skill": "目錄名", "triggers": [...], "description_keywords": ["前50字的關鍵詞"]}`
> 純 JSON，不含 markdown 包裝。

主 Agent 接收後（≤6KB 摘要），計算候選 Skill 目的關鍵詞與現有 Skill 的 `triggers + description_keywords` 的重疊率：
- 重疊率 > 60% → 排除，選次高分候選，重複步驟 3
- 重疊率 ≤ 60% → 通過

---

## 步驟 4：KB 深研（呼叫 kb-research-strategist）

讀取 `skills/kb-research-strategist/SKILL.md`，以選定的 Skill **主題**為研究主題，執行完整 7 步驟流程，輸出 `context/kb-research-brief.json`。

**研究目標**（明確告知 kb-research-strategist）：收集足以生成具體可執行 Skill 步驟的知識：
- 目標技術/API 的具體端點、命令格式、回應結構
- Windows/PowerShell 用法（避免 Linux-only 語法）
- 已知失敗模式與降級策略
- 相關 Python 套件（需透過 `uv run python` 呼叫）

### 版本決策（依 KB 研究結果，判斷順序如下）

讀取 `context/kb-research-brief.json`，**依序**判斷：

```
1. 若 recommendation == "skip_kb_down"
   → v0.1.0（KB 不可用，kb_foundation 整個區塊可能不存在，直接判定）
2. 否則讀取 kb_foundation.notes_analyzed（注意：是巢狀路徑，非頂層欄位）
   → notes_analyzed ≥ 3 且 recommendation 為 deepen/series_continue → v1.0.0
   → notes_analyzed 1-2 → v0.5.0
   → notes_analyzed 0（或欄位缺失）→ v0.1.0（知識不足，等同草稿）
```

| 生成版本 | SKILL.md 標記 |
|--------|--------------|
| **v1.0.0** | 正式版，無額外標記 |
| **v0.5.0** | description 末尾加「⚠️ 知識基礎薄弱，建議透過 skill-audit 補強」 |
| **v0.1.0** | description 開頭加「⚠️ 草稿版（KB 不可用時生成）」 |

版本號決定後，將其記錄為 **`$VERSION`**（例如 `v1.0.0`），供步驟 5 frontmatter 及步驟 10b 引用。**後續步驟禁止重新判斷版本**，一律沿用此處決定的 `$VERSION`。

---

## 步驟 5：生成 SKILL.md

依以下輸入生成完整的 SKILL.md，寫入 `skills/{skill_name}/SKILL.md`：

**輸入**：
- 步驟 1 的信號上下文（what/why/signal_source）
- `context/kb-research-brief.json`（how 的知識基礎）
- 步驟 3 子 Agent 回傳中最相似的現有 Skill（格式參考，取 triggers 與候選最接近的）

**生成約束（嚴格遵守，每條違反均導致步驟 6 失敗）**：

1. **Frontmatter 完整性**：必含 name、version（依步驟 4 決定）、description（含 "Use when"）、allowed-tools、cache-ttl、triggers ≥ 3 個、depends-on
2. **步驟結構**：步驟有編號，每步說明輸入/輸出/操作
3. **降級章節**：必含「降級處理」或「錯誤處理」段落
4. **無佔位符**：禁止「此處填入你的邏輯」「TODO」「<your-api-key>」等
5. **Windows 相容性**：
   - curl POST 必須用 Write 建立 JSON 檔再 `-d @file.json`，不用 inline JSON
   - Python 用 `uv run python`，不用裸 `python`
   - 禁止 `> nul`，用 `> /dev/null 2>&1`
6. **本體字數 ≥ 600 字元**（frontmatter 以外的步驟內容）

---

## 步驟 6：格式驗證 + 內容字數下限

```bash
uv run python -X utf8 -c "
import yaml, sys
fname = 'skills/{skill_name}/SKILL.md'
content = open(fname, encoding='utf-8').read()
parts = content.split('---')
data = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
body = '---'.join(parts[2:]) if len(parts) >= 3 else ''
required = ['name','version','description','allowed-tools','cache-ttl','triggers']
missing = [f for f in required if f not in data]
has_use_when = 'Use when' in data.get('description', '')
triggers_ok = len(data.get('triggers', [])) >= 3
body_ok = len(body.strip()) >= 600
passed = not missing and has_use_when and triggers_ok and body_ok
print(f'MISSING: {missing}')
print(f'HAS_USE_WHEN: {has_use_when}')
print(f'TRIGGERS_COUNT: {len(data.get(\"triggers\", []))}')
print(f'BODY_CHARS: {len(body.strip())}')
print(f'PASS: {passed}')
"
```

**驗證標準**：
- `MISSING: []`（必填欄位齊全）
- `HAS_USE_WHEN: True`
- `TRIGGERS_COUNT: ≥ 3`
- `BODY_CHARS: ≥ 600`

若任一不通過，用 Edit 工具修正，最多重試 **2 輪**。
2 輪後仍失敗 → 在結果 JSON 記錄 `status: "format_failed"`，跳至步驟 10（不整合）。

---

## 步驟 6.5：LLM 自評分（Reflexion 品質閘門）

格式驗證通過後，切換為**批評者角色**重新審閱剛生成的 SKILL.md。

以下 5 個維度各打 1-10 分，計算**平均分**：

| 維度 | 評分標準（10 分 = 最佳） |
|------|----------------------|
| **完整性** | 步驟涵蓋完整執行流程？是否有降級、輸出格式說明？ |
| **可執行性** | 每步驟有具體指令/命令/JSON 格式？還是只有抽象描述？ |
| **系統價值** | 真實解決 improvement-backlog 或 system-insight 的問題？ |
| **開創性** | 提供現有 30 個 Skill 組合無法達成的新能力？ |
| **Windows 相容性** | curl 用 Write 建 JSON 檔？避免 `> nul`？用 `uv run python`？ |

**執行流程（強制解析，防止評分造假）**：

1. 切換批評者角色，對 5 個維度給出整數評分（1-10）
2. 將評分**先寫入暫存檔** `context/skill_forge_score.json`（用 Write 工具）：
   ```json
   {"completeness": 8, "actionability": 7, "system_value": 9, "originality": 8, "windows_compat": 10}
   ```
3. 用 Python **強制計算**均值並驗證一致性（LLM 不得自行計算，避免偏差）：
   ```bash
   uv run python -X utf8 -c "
   import json
   s = json.load(open('context/skill_forge_score.json', encoding='utf-8'))
   keys = ['completeness','actionability','system_value','originality','windows_compat']
   avg = sum(s[k] for k in keys) / 5
   passed = avg >= 7.0
   print(f'AVERAGE: {avg:.2f}')
   print(f'PASS: {passed}')
   print(f'MIN_DIM: {min(keys, key=lambda k: s[k])}={s[min(keys, key=lambda k: s[k])]}')
   "
   ```
4. 依 Python 輸出的 `PASS` 決定行動（非 LLM 自判）：
   - `PASS: True` → 繼續步驟 7
   - `PASS: False`，`AVERAGE ≥ 5.0` → 依 `MIN_DIM` 指示的最低分維度修改 SKILL.md，
     **先重新執行步驟 6 格式驗證（確保修改未破壞 frontmatter 格式，`PASS: True`）**，
     再重新評分（最多 **1 次**）：先執行 `rm context/skill_forge_score.json`（若存在），再重新執行步驟 6.5 的第 1-4 項。
     **重評後仍 < 7.0（無論平均分）**：將版本降至 v0.5.0（更新 frontmatter + description 末尾加「⚠️ 品質分 {average}/10，建議後續 skill-audit 改善」），記錄 `status: "partial"`，繼續步驟 7
   - `PASS: False`，`AVERAGE < 5.0` → 記錄 `status: "quality_rejected"`，跳至步驟 10
5. 刪除暫存檔：`rm context/skill_forge_score.json`
6. 將最終評分與 Python 計算的 `average`、`pass` 寫入結果 JSON `quality_score` 欄位

**注意**：`quality_score.average` 和 `quality_score.pass` 必須使用 Python 計算結果，禁止 LLM 自行填入。

| 平均分（Python 計算） | 動作 |
|---------------------|------|
| ≥ 7.0 | 通過品質門檻，繼續步驟 7 |
| 5.0–6.9 | 依 MIN_DIM 修改，重新評分（最多 1 次） |
| < 5.0 | `status: "quality_rejected"`，跳至步驟 10 |

---

## 步驟 7：skill-scanner 安全掃描

讀取 `skills/skill-scanner/SKILL.md`，依其指示對新生成的 Skill 執行掃描。

**結果處理**：

| 掃描結果 | `status` | `integration_status` | 處理方式 |
|---------|----------|---------------------|---------|
| clean / warning（低嚴重度） | `success` | `integrated` | 繼續步驟 8 |
| medium / high finding | `partial` | `held_for_review` | **不**更新 SKILL_INDEX.md；建立 `ntfy_scanner_alert.json` 發送告警（Write + curl）；跳至步驟 10 |
| scanner 不存在 | `success` | `integrated` | 標記 `scanner_skipped: true`；繼續步驟 8 |

**scanner blocked 告警**（用 Write 建立 `ntfy_scanner_alert.json` 再發送）：
```json
{
  "topic": "wangsc2025",
  "title": "⚠️ skill-forge：scanner 攔截",
  "message": "{skill_name} 生成後被 skill-scanner 攔截（{medium/high} finding），已暫緩整合，請人工審查 skills/{skill_name}/SKILL.md",
  "priority": 4,
  "tags": ["warning", "shield"]
}
```
```bash
curl -s -X POST https://ntfy.sh \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @ntfy_scanner_alert.json
rm ntfy_scanner_alert.json
```
（JSON 發送時必須 POST 到根網址 `https://ntfy.sh`，不可用 `https://ntfy.sh/wangsc2025`，否則整段 JSON 會變成通知內文。）

---

## 步驟 8：SKILL_INDEX.md 整合

**前提（任一不符均跳過本步驟，直接至步驟 9）**：
- 步驟 6 格式驗證通過（非 `format_failed`）
- 步驟 6.5 品質評分 `PASS: True`（非 `quality_rejected`）
- 步驟 7 掃描結果為 `clean` 或 `warning`（非 `held_for_review`）



1. 用 Read 讀取 `skills/SKILL_INDEX.md`
2. 在「工具 Skill」表格末尾用 Edit 追加一列：
   ```
   | N | {skill-name} | {一句話用途} | {triggers 前 3 個，用「、」分隔} |
   ```
3. 更新速查表頂部的 Skill 總數（加 1）
4. 若生成版本為 v0.1.0，在 Skill 名稱後加 `[草稿]` 標記

---

## 步驟 9：匯入知識庫

讀取 `skills/knowledge-query/SKILL.md`，依其指示將本次生成報告匯入 KB。

建立 `kb_import_note.json`（用 Write 工具，確保 UTF-8）：
```json
{
  "title": "skill-forge 生成報告：{skill_name}（{YYYY-MM-DD}）",
  "contentText": "## 生成摘要\n信號來源：{signal_source}\n信號項目：{signal_item}\n\n## 候選評分\n{最高分候選的評分細節}\n\n## KB 研究結果\n{kb_research_brief 的 research_plan.primary_question}\n\n## 生成版本\n{version}，原因：{版本決策原因}\n\n## 品質評分\n完整性={completeness}，可執行性={actionability}，系統價值={system_value}，開創性={originality}，相容性={windows_compat}，平均={average}\n\n## 整合結果\n{integration_status}",
  "source": "import",
  "tags": ["skill-forge", "Skill生成", "系統改進", "{skill_name}"]
}
```

執行匯入並驗證結果：
```bash
IMPORT_RESP=$(curl -s -w "\n%{http_code}" -X POST http://localhost:3000/api/import \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @kb_import_note.json)
IMPORT_HTTP=$(echo "$IMPORT_RESP" | tail -1)
if [ "$IMPORT_HTTP" = "200" ] || [ "$IMPORT_HTTP" = "201" ]; then
  echo "KB_IMPORT_OK: HTTP $IMPORT_HTTP"
else
  echo "KB_IMPORT_FAILED: HTTP $IMPORT_HTTP"
fi
rm kb_import_note.json
```

依 `KB_IMPORT_OK/FAILED` 設定步驟 10b 的 `kb_imported` 欄位（`true` / `false`）。
`kb_imported: false` 且 SKILL 已整合時，`status` 設為 `"partial"`。

**降級**（KB 不可用，curl connection refused）：跳過此步驟，記錄 `kb_imported: false`，繼續步驟 10。
若步驟 8 已整合（`skill_index_updated: true`），`status` 同樣設為 `"partial"`（與匯入失敗路徑一致）。

---

## 步驟 10：發送通知 + 寫入結果 JSON

### 10a. ntfy 通知

依 `status` 選擇通知標題與圖示（用 Write 工具建立 `ntfy_skill_forge.json`）：

| `status` | `title` | `tags` | `priority` |
|---------|---------|--------|-----------|
| `success` / `partial` | `🔨 skill-forge：{skill_name} 已生成` | `["hammer","sparkles"]` | 3 |
| `quality_rejected` | `❌ skill-forge：品質未達標（{average}/10）` | `["x","warning"]` | 4 |
| `format_failed` | `❌ skill-forge：格式驗證失敗` | `["x","warning"]` | 4 |

```json
{
  "topic": "wangsc2025",
  "title": "（依上表選擇）",
  "message": "版本 {version}｜{signal_source} 信號｜品質分 {average}/10｜{integration_status}",
  "priority": （依上表選擇）,
  "tags": （依上表選擇）
}
```

```bash
curl -s -X POST https://ntfy.sh \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @ntfy_skill_forge.json
rm ntfy_skill_forge.json
```
（JSON 發送時必須 POST 到根網址 `https://ntfy.sh`，不可用 `https://ntfy.sh/wangsc2025`，否則整段 JSON 會變成通知內文。）

### 10b. 結果 JSON

**各執行路徑的欄位速查表**（填寫 10b JSON 時依此覆寫預設值）：

| 執行路徑 | `status` | `integration_status` | `skill_index_updated` | `kb_imported` |
|---------|----------|---------------------|----------------------|--------------|
| 完整成功 | `success` | `integrated` | `true` | `true` |
| 成功但 KB 匯入失敗 | `partial` | `integrated` | `true` | `false` |
| scanner blocked | `partial` | `held_for_review` | `false` | `true`（若 KB 已匯入）|
| 品質未達標（5.0-6.9 修正後仍 < 7.0，降至 v0.5.0） | `partial` | `integrated` | `true` | `true` |
| 品質拒絕（< 5.0） | `quality_rejected` | `quality_rejected` | `false` | `false` |
| 格式驗證失敗 | `format_failed` | `format_failed` | `false` | `false` |

`status` 欄位說明：
- `success`：完整通過所有步驟並整合
- `partial`：生成成功但 scanner blocked 或 KB 匯入失敗
- `quality_rejected`：步驟 6.5 平均分 < 5.0（未修正或修正後仍不達）
- `format_failed`：步驟 6 格式驗證 2 輪後仍失敗

用 Write 工具建立 `results/todoist-auto-skill_forge.json`：
```json
{
  "agent": "todoist-auto-skill_forge",
  "task_type": "auto",
  "task_key": "skill_forge",
  "status": "success",
  "generated_skill": {
    "name": "{skill_name}",
    "path": "skills/{skill_name}/SKILL.md",
    "version": "{version}",
    "is_draft": false,
    "signal_source": "{improvement-backlog | adr-registry | system-insight}",
    "signal_item": "{對應信號的描述}",
    "originality_passed": true
  },
  "kb_research": {
    "used": true,
    "series_id": null,
    "stage": "{research_stage}",
    "notes_analyzed": 0,
    "recommendation": "{deepen | series_continue | skip_kb_down}"
  },
  "quality_score": {
    "completeness": 0,
    "actionability": 0,
    "system_value": 0,
    "originality": 0,
    "windows_compat": 0,
    "average": 0.0,
    "pass": true,
    "rejection_reason": null
  },
  "scanner_result": {
    "status": "{clean | warning | blocked | scanner_unavailable}",
    "findings_count": 0,
    "scanner_skipped": false
  },
  "skill_index_updated": true,
  "kb_imported": true,
  "integration_status": "{integrated | held_for_review | quality_rejected | format_failed}",
  "summary": "{一句話摘要，含生成 Skill 名稱與主要解決的問題}",
  "error": null
}
```

---

## 降級處理總覽

| 情境 | 處理方式 |
|------|---------|
| 三大上下文均無信號 | 選 SKILL_INDEX.md 中「depends-on 鏈最短」的空缺主題，自行設計 Skill |
| KB API 不可用 | 生成 v0.1.0 草稿版，依 improvement-backlog 描述直接生成 |
| skill-scanner 不存在 | 標記 `scanner_skipped: true`，繼續整合 |
| 所有候選均不通過開創性門檻 | 選開創性評分最高的候選，降低門檻至「提供主要功能改善」即可 |
| 品質平均分 5.0-6.9（修正後仍 < 7.0） | 版本降至 v0.5.0，description 末尾加「⚠️ 品質分 X/10，建議後續 skill-audit 改善」，`status: "partial"`，繼續整合 |

---

**版本歷史**：
- v1.0.0（2026-03）：初始正式版
- v1.0.1（2026-03-19）：移除步驟 10b 重複內容（skill-audit 發現）
