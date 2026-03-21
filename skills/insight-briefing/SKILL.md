---
name: insight-briefing
version: "1.1.0"
description: |
  深度研究洞察簡報。依 config/insight-briefing-workflow.yaml 串接多種 Skill：研究策略→蒐集→洞察萃取→簡報產出→KB 匯入→通知。
  產出結構化 Markdown 簡報（可選 .pptx），複用 web-research、kb-research-strategist、knowledge-query、markdown-editor、ntfy-notify。
  Use when: 深度研究洞察簡報、insight briefing、研究簡報、多 Skill 研究簡報。
allowed-tools: [Bash, Read, Write, Edit, WebSearch, WebFetch, Glob, Grep]
cache-ttl: "N/A"
triggers:
  - "深度研究洞察簡報"
  - "insight briefing"
  - "研究簡報"
  - "多 Skill 研究簡報"
depends-on:
  - knowledge-query
  - web-research
  - kb-research-strategist
  - ntfy-notify
  - "config/dependencies.yaml"
optional-depends-on:
  - academic-paper-research
  - markdown-editor
---

# Insight Briefing — 深度研究洞察簡報

> **端點來源**：`config/dependencies.yaml`（deps key: `ntfy_notify`）— ADR-001 Phase 3

依 `config/insight-briefing-workflow.yaml` 定義的步驟依序執行，每一步**先讀取對應 Skill 的 SKILL.md 再執行**（Skill-First）。

執行鏈：
```
去重選題 → 研究策略（kb-research-strategist）→ 蒐集（web-research 或 academic-paper-research）
→ 洞察萃取 → Markdown 簡報產出 → 可選 .pptx → KB 匯入（knowledge-query）
→ 更新 research-registry → ntfy 通知 → 結果 JSON
```

---

## 步驟 0：前置讀取

1. 讀取 `templates/shared/preamble.md`（Skill-First + nul 禁令）
2. 讀取 `skills/SKILL_INDEX.md`（建立現有 Skill 地圖）
3. 讀取 `config/insight-briefing-workflow.yaml`（取得步驟順序與輸出路徑）

---

## 步驟 1：dedup_check（去重與選題）

- 讀取 `config/dedup-policy.yaml`、`context/research-registry.json`（若不存在則建立空 registry）
- 判定：3 天內同 topic 必須換題；7 天內同類型 ≥3 建議換方向
- 主題來源可擇一：`context/system-insight.json` 的 recommendations、`context/improvement-backlog.json`、或 research-registry 冷門方向，避免與 ai_deep_research 重複
- **輸出**：選定主題、關鍵詞列表，通過去重

---

## 步驟 2：research_strategy（kb-research-strategist）

1. **先讀取** `skills/kb-research-strategist/SKILL.md`
2. 以選定主題執行 KB 知識感測與研究策略（可讀取 `templates/shared/kb-depth-check.md` 依其流程執行，或依 kb-research-strategist 步驟 0→4）
3. 產出或更新 `context/kb-research-brief.json`（知識差距、下一階段建議）

---

## 步驟 3：gather（蒐集）

- **先讀取** `skills/web-research/SKILL.md`；若主題偏學術則再讀 `skills/academic-paper-research/SKILL.md`
- 依主題類型選擇：
  - 技術/產業/趨勢 → 以 web-research 流程：多角度搜尋、WebFetch、來源品質分級、摘要
  - 學術/文獻回顧 → 以 academic-paper-research 流程：研究問題、檢索策略、學術等級來源
- 遵守研究註冊表去重（web-research 步驟 0）
- **輸出**：蒐集來源清單、每篇摘要與關鍵點、品質評分

---

## 步驟 4：synthesize（洞察萃取）

- 交叉比對不同來源：共識點、分歧點、獨特洞見
- 提煉至少 5 點核心洞見，每點附證據要點或來源
- 無專屬 Skill；可參考 `skills/markdown-editor/SKILL.md` 做結構化整理
- **輸出**：核心洞見清單、共識/分歧摘要、證據要點（供下一步撰寫簡報）

---

## 步驟 5：briefing_output（Markdown 簡報）

1. **先讀取** `skills/markdown-editor/SKILL.md`（可選，用於格式與 TOC）
2. 確保目錄存在：`context/insight-briefings/`（不存在則用 Bash 執行 `mkdir -p context/insight-briefings` 或 PowerShell `New-Item -ItemType Directory -Force -Path context/insight-briefings`）
3. 產出結構化 Markdown 簡報，路徑：`context/insight-briefings/YYYY-MM-DD-{topic_slug}.md`
   - 標題、摘要（約 200 字）
   - 關鍵洞見（條列，含證據要點）
   - 建議行動或後續研究
   - 參考來源
4. topic_slug：主題的簡短英文或拼音 slug，不含空白與特殊字元

---

## 步驟 6：optional_pptx（可選）

- 若 `config/insight-briefing-workflow.yaml` 中 `optional_pptx: true`，可依 Cursor 全域 pptx Skill 或專案內指引，將簡報 Markdown 轉為 `context/insight-briefings/YYYY-MM-DD-{topic_slug}.pptx`
- 預設 `optional_pptx: false` 時可跳過

---

## 步驟 7：kb_import（knowledge-query）

1. **先讀取** `skills/knowledge-query/SKILL.md`
2. 將簡報 Markdown 內容匯入知識庫：
   - title 含 "insight-briefing" 或「深度研究洞察簡報」與主題
   - tags 含 "深度研究洞察簡報"、"insight-briefing"、主題標籤
3. 記錄 kb_note_id（若有）；若 KB 不可用，記錄 `kb_imported: false`，不影響 status

---

## 步驟 8：更新 research-registry（必做）

完成簡報產出與 KB 匯入後，將本次執行登記至 `context/research-registry.json`，供後續去重與冷卻檢查：

1. 讀取 `context/research-registry.json`（若不存在則用 Write 建立，含 `version`、`topics_index`、`entries`、`summary`）
2. 在 `entries` 陣列追加一筆：`task_type: "insight_briefing"`、`topic: "本次簡報主題"`、`date: "YYYY-MM-DD"`、`kb_note_title`（若有）、`kb_imported: true/false`
3. 更新頂層 `topics_index[本次 topic] = "YYYY-MM-DD"`
4. 更新 `summary`：`summary.total` += 1、`summary.by_type["insight_briefing"]` += 1（若 by_type 無此鍵則先設為 0 再加）、`summary.last_updated` = 今日日期
5. 移除超過 7 天的舊 entry（與 config/dedup-policy.yaml 的 retention_days 一致）

---

## 步驟 8b：backlog_feed（洞察轉 OODA 行動鏈）

> **目的**：insight_briefing（order 29）產出的系統改善洞察直接寫入 `context/improvement-backlog.json`，讓 arch_evolution（order 17）**下一輪即可決策**，無需人工中轉。

1. 掃描步驟 4（synthesize）產出的核心洞見清單，篩選含以下主題的條目：
   - Agent 架構 / Skill 設計 / Prompt 優化
   - 工作流程改善 / 系統整合 / 自動化效率
   - **排除**：純學術研究、特定技術框架調研、新聞趨勢（這類條目屬研究類，非系統改善）
2. 若篩選結果 = 0 條 → 跳過本步驟（無改善洞察時不寫入，避免噪音）
3. 讀取 `context/improvement-backlog.json`（不存在則建立 `{ "items": [] }`）
4. **24h 去重**：檢查 `items` 中是否已有 `source: "insight_briefing"` 且 `created_at` 為今日的條目；若有則跳過，避免同日多次執行時重複累積
5. 若無重複，取**最具系統改善價值的前 2 條**洞見，逐條追加：
   ```json
   {
     "id": "backlog_ib_<YYYYMMDD>_<topic_slug>",
     "source": "insight_briefing",
     "title": "研究洞察建議：<簡短洞見標題>",
     "description": "<洞見內容摘要，含來源主題與具體建議行動>",
     "priority": "medium",
     "effort": "medium",
     "created_at": "ISO 8601 時間戳",
     "status": "pending",
     "tags": ["insight_briefing", "research_derived", "<本次研究主題 slug>"]
   }
   ```
6. 用 Write 將更新後的完整 backlog 寫回 `context/improvement-backlog.json`

---

## 步驟 9：notify（ntfy-notify）

1. **先讀取** `skills/ntfy-notify/SKILL.md`；可讀取 `config/notification.yaml` 取得 `default_topic`（預設 wangsc2025）與 `send_steps`
2. 用 Write 建立 JSON 檔（UTF-8，檔名如 ntfy_insight_briefing.json），再以 curl 發送：`curl -H "Content-Type: application/json; charset=utf-8" -d @檔名 https://ntfy.sh`
3. 標題範例：`深度研究洞察簡報：[主題]`；priority 依 success/partial/failed 設定；topic 使用 notification.yaml 的 default_topic
4. 發送後刪除暫存 JSON 檔

---

## 步驟 10：結果 JSON

用 Write 建立 `results/todoist-auto-insight_briefing.json`（格式符合 config/schemas/results-auto-task-schema.json）：

```json
{
  "agent": "todoist-auto-insight_briefing",
  "task_key": "insight_briefing",
  "status": "success",
  "executed_at": "YYYY-MM-DDTHH:mm:ss+08:00",
  "execution_time_seconds": 0,
  "artifact": {
    "path": "context/insight-briefings/YYYY-MM-DD-{topic_slug}.md",
    "type": "report",
    "gap_addressed": null
  },
  "kb_imported": true,
  "kb_note_ids": [],
  "summary": "一句話摘要",
  "topic": "本次簡報主題"
}
```

- `status`：`success`、`partial`（例如 KB 未匯入但簡報已產出）、`failed`
- 若有 .pptx，於 `artifact` 內加 `pptx_path`（例：`context/insight-briefings/YYYY-MM-DD-{topic_slug}.pptx`）
- 格式需符合 `config/schemas/results-auto-task-schema.json`

---

## 降級處理

- **主題無法通過去重**：從 system-insight recommendations 或 improvement-backlog 擇一項作為主題，或擇冷門方向
- **gather 來源不足**：擴充關鍵詞、增加搜尋角度，至少 3 篇以上再進入 synthesize
- **KB 匯入失敗**：status 設為 `partial`，artifact.path 仍必填，message 註明 KB 未匯入
