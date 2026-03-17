---
name: prompt-lint
version: "1.0.0"
description: |
  Prompt 模板靜態分析工具。掃描 prompts/ 與 templates/ 目錄下的 .md 檔案，
  偵測 7 類反模式（過長模板、缺少 preamble 引用、hardcoded 端點、冗餘指令、
  未匹配變數、缺少降級段落、重複 Skill 引用），產出結構化報告並追蹤趨勢。
  協助降低 avg_io_per_call、減少 loop-suspected 事件、提升 prompt 品質。
  Use when: prompt 品質檢查、模板膨脹偵測、反模式掃描、prompt 優化建議、模板衛生檢查。
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "prompt-lint"
  - "prompt 檢查"
  - "模板分析"
  - "prompt 品質"
  - "模板膨脹"
  - "prompt 反模式"
  - "prompt 優化"
depends-on:
  - system-insight
  - "config/dependencies.yaml"
---

# prompt-lint：Prompt 模板靜態分析工具

> **端點來源**：`config/dependencies.yaml`（deps key: `knowledge_query`）— ADR-001 Phase 3

## 設計目標

系統目前有 60+ 個 prompt/template 檔案，avg_io_per_call 仍超標 2.5 倍（12,419 vs 目標 5,000），
loop-suspected 事件高達 1,187 次。本 Skill 透過靜態分析識別 prompt 品質問題的根因，
提供可行動的修改建議。

---

## 步驟 0：前置準備

1. 讀取 `templates/shared/preamble.md`（確認共用前言規範）
2. 讀取 `skills/SKILL_INDEX.md`（建立 Skill 認知地圖，用於規則 R5 檢查）

---

## 步驟 1：收集目標檔案

用 Glob 工具收集所有待分析檔案：

```
prompts/**/*.md
templates/**/*.md
```

過濾條件：
- 排除 `templates/shared/preamble.md`（它是被引用的，不是引用者）
- 排除 `templates/shared/done-cert.md`（固定格式模板）

記錄 `total_files` 數量。

---

## 步驟 2：逐檔執行 7 條規則檢查

對每個檔案依序檢查以下規則，記錄所有違規項：

### R1：模板過長（token 膨脹風險）

```bash
uv run python -X utf8 -c "
import sys
fname = sys.argv[1]
content = open(fname, encoding='utf-8').read()
lines = content.strip().split('\n')
chars = len(content)
# 警告閾值：超過 300 行或 15,000 字元
if len(lines) > 300 or chars > 15000:
    print(f'R1_WARN: {fname} lines={len(lines)} chars={chars}')
elif len(lines) > 200 or chars > 10000:
    print(f'R1_INFO: {fname} lines={len(lines)} chars={chars}')
else:
    print(f'R1_OK: {fname}')
" <filepath>
```

**判斷標準**：
- WARN：>300 行 或 >15,000 字元（建議拆分或外部化配置）
- INFO：>200 行 或 >10,000 字元（關注但可接受）
- OK：其他

### R2：缺少 preamble 引用

用 Grep 搜尋檔案內容是否包含 `preamble.md` 或 `templates/shared/preamble`：

- `prompts/team/*.md` 和主 prompt（`*-prompt.md`）**必須**引用 preamble
- `templates/sub-agent/*.md` 和 `templates/auto-tasks/*.md` 可選（但建議）

**判斷標準**：
- WARN：prompts/team/ 下的檔案未引用 preamble
- INFO：其他目錄的檔案未引用

### R3：Hardcoded 端點或路徑

用 Grep 搜尋以下 pattern：
- `http://localhost:\d+`（應引用 config 或 SKILL.md）
- `https://api\.todoist\.com`（應透過 todoist Skill）
- `https://ntfy\.sh`（應透過 ntfy-notify Skill，除非在 SKILL.md 內）

**判斷標準**：
- WARN：在 prompt/template 中直接寫入 API 端點（繞過 Skill）
- OK：引用 Skill 或 config 取得端點

### R4：冗餘指令偵測

用 Grep 搜尋重複出現的指令片段：
- `禁止.*nul`（若 preamble 已含，重複宣告浪費 token）
- `全程使用正體中文`（若 preamble 已含）
- `先讀取.*SKILL_INDEX`（若 preamble 已含）

**判斷標準**：
- INFO：重複宣告已在 preamble 中定義的規則（建議刪除，依賴 preamble 引用）

### R5：SKILL.md 引用一致性

比對檔案中提及的 Skill 名稱與 SKILL_INDEX.md 的現有 Skill 清單：
- 提到的 Skill 名稱是否存在於索引中？
- 路徑 `skills/<name>/SKILL.md` 是否正確？

**判斷標準**：
- WARN：引用了不存在的 Skill 名稱

### R6：缺少降級/錯誤處理段落

用 Grep 搜尋是否包含「降級」「錯誤處理」「失敗」「fallback」等關鍵字：

**判斷標準**：
- INFO：prompt/template 無降級處理描述（agent 可能在 API 失敗時無所適從）

### R7：未匹配的模板變數

用 Grep 搜尋 `\{[a-z_]+\}` 或 `<[A-Z_]+>` 等佔位符 pattern：
- 純文件說明中的範例可忽略
- 實際指令中的未替換變數需標記

**判斷標準**：
- WARN：指令區塊（```bash 或非引用段落）中有未替換的佔位符

---

## 步驟 3：計算摘要統計

```python
summary = {
    "total_files": N,
    "files_with_warnings": N,
    "files_with_info": N,
    "clean_files": N,
    "rule_violation_counts": {
        "R1_overlong": N,
        "R2_no_preamble": N,
        "R3_hardcoded_endpoint": N,
        "R4_redundant_directive": N,
        "R5_invalid_skill_ref": N,
        "R6_no_fallback": N,
        "R7_unmatched_var": N
    },
    "top_offenders": [
        {"file": "path", "warnings": N, "infos": N}
    ]
}
```

---

## 步驟 4：產出報告

用 Write 建立 `state/prompt-lint-report.json`：

```json
{
  "generated_at": "ISO timestamp",
  "version": "0.5.0",
  "total_files": 0,
  "summary": { "...如步驟 3..." },
  "violations": [
    {
      "file": "prompts/team/todoist-auto-xxx.md",
      "rule": "R1",
      "severity": "warn",
      "detail": "lines=350 chars=18000，建議拆分配置到 YAML",
      "suggestion": "將步驟 N 的配置表移至 config/ 目錄"
    }
  ],
  "trend": {
    "previous_total_warnings": null,
    "current_total_warnings": 0,
    "delta": null
  }
}
```

**趨勢追蹤**：若 `state/prompt-lint-report.json` 已存在，讀取上一次的 `summary.files_with_warnings` 與本次比較，計算 delta。

---

## 步驟 5：建議與優先級排序

依以下優先級排序修正建議：
1. **R3（hardcoded 端點）**：安全性最高，直接繞過 Skill 的端點可能導致 cache miss
2. **R1（過長模板）**：直接影響 token 消耗與 IO
3. **R5（無效 Skill 引用）**：可能導致 agent 執行錯誤
4. **R2（缺少 preamble）**：影響規範一致性
5. **R4/R6/R7**：品質改善型

輸出 Top 3 可行動建議（含具體檔案路徑與修改方向）。

---

## 降級處理

| 情境 | 處理方式 |
|------|---------|
| 檔案過多（>100 個） | 僅掃描 prompts/team/ 和 templates/auto-tasks/（最高優先級目錄） |
| Grep 工具異常 | 改用 Python re 模組逐檔掃描 |
| SKILL_INDEX.md 不存在 | 跳過 R5 規則，標記 `r5_skipped: true` |
| 上次報告不存在 | `trend.previous_total_warnings: null`，不計算趨勢 |

---

## 輸出範例

### prompt-lint-report.json 範例

```json
{
  "generated_at": "2026-03-16T14:30:00+08:00",
  "version": "1.0.0",
  "total_files": 68,
  "summary": {
    "total_files": 68,
    "files_with_warnings": 8,
    "files_with_info": 15,
    "clean_files": 45,
    "rule_violation_counts": {
      "R1_overlong": 3,
      "R2_no_preamble": 5,
      "R3_hardcoded_endpoint": 2,
      "R4_redundant_directive": 7,
      "R5_invalid_skill_ref": 0,
      "R6_no_fallback": 12,
      "R7_unmatched_var": 1
    },
    "top_offenders": [
      {"file": "prompts/team/todoist-assemble.md", "warnings": 2, "infos": 3},
      {"file": "templates/auto-tasks/ai-deep-research.md", "warnings": 1, "infos": 2}
    ]
  },
  "violations": [
    {
      "file": "prompts/team/todoist-assemble.md",
      "rule": "R1",
      "severity": "warn",
      "detail": "lines=350 chars=18500，建議拆分配置到 YAML",
      "suggestion": "將步驟 3 的路由表移至 config/routing.yaml"
    },
    {
      "file": "templates/auto-tasks/podcast-create.md",
      "rule": "R3",
      "severity": "warn",
      "detail": "直接 hardcoded http://localhost:3000/api/import",
      "suggestion": "改用 knowledge-query Skill，透過 SKILL.md 取得端點"
    }
  ],
  "trend": {
    "previous_total_warnings": 12,
    "current_total_warnings": 8,
    "delta": -4
  }
}
```

### Top 3 可行動建議範例

```
【優先級 P0】修正 R3 違規（2 個檔案）
- prompts/team/todoist-auto-podcast_create.md:45
  建議：改用 knowledge-query Skill 匯入筆記
- templates/auto-tasks/git-push.md:23
  建議：改用 ntfy-notify Skill 發送通知

【優先級 P1】優化 R1 過長模板（3 個檔案）
- prompts/team/todoist-assemble.md (350 行)
  建議：路由表移至 config/routing.yaml
- templates/auto-tasks/ai-deep-research.md (280 行)
  建議：研究框架移至 templates/shared/research-framework.md

【優先級 P2】補充 R6 降級處理（12 個檔案）
- 建議在步驟末尾增加「降級處理」段落
```

---

## 常見問題

### Q1：R4 冗餘指令誤報怎麼處理？
**A**：R4 規則會檢查 prompt 中是否重複宣告 preamble.md 已有的規則。若確實需要強調某規則，可在該規則前加註解：
```markdown
<!-- 此處重複強調 nul 禁令，因本任務高風險 -->
禁止使用 > nul
```

### Q2：如何解讀 trend delta？
**A**：
- delta < 0：違規數量減少（改善中）
- delta > 0：違規數量增加（需關注）
- delta = 0 或 null：無變化或無歷史數據

### Q3：什麼情況下會觸發 R1 WARN？
**A**：模板超過 300 行或 15,000 字元。建議將大型配置表、重複的步驟模板外部化到 config/ 或 templates/shared/。

### Q4：手動執行 prompt-lint
**A**：
```bash
echo "執行 prompt-lint 掃描所有模板" | claude -p skills/prompt-lint/SKILL.md
```

---

## 注意事項

- 本 Skill 為唯讀分析，不修改任何 prompt/template 檔案
- 報告存放於 `state/prompt-lint-report.json`（可被 system-insight 引用）
- R4 規則需配合 preamble.md 內容判斷，避免誤報
- 所有 Python 腳本使用 `uv run python -X utf8` 執行
- 禁止 `> nul`，使用 `> /dev/null 2>&1`
