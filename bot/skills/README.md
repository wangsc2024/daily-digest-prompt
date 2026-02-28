# Skills — AI 技能模板

本目錄存放所有 **Skill**（`.md` 檔案），供系統依情境載入並替換變數後送交 AI。  
載入與管理邏輯在 `lib/skills.js`，意圖分類與工作流分解在 `lib/classifier.js` 中呼叫。

## 格式

- 副檔名：`.md`
- 變數：在內容中使用 `{{變數名}}`，載入時會由呼叫端傳入的 `vars` 替換（會做 escape，防止 prompt injection）。

## 目前技能一覽

| 技能名稱 | 檔案 | 用途 | 常用變數 |
|----------|------|------|----------|
| intent-classifier | intent-classifier.md | 意圖分類（週期/定時/工作流/即時、研究型） | userMessage, currentDatetime, timezone |
| workflow-decomposer | workflow-decomposer.md | 複合任務分解為有序步驟 | userMessage |
| quick-answer | quick-answer.md | 簡短實質回答（單次任務即時回饋） | userMessage |

## 新增 Skill

1. 在本目錄新增 `你的技能名稱.md`（檔名即 skill 名稱，不含 `.md`）。
2. 內容中需要動態代入的地方寫 `{{變數名}}`。
3. 在程式中載入並傳入變數：
   ```js
   const skills = require('./lib/skills');
   const prompt = skills.loadSkill('你的技能名稱', { 變數名: '值' });
   ```
4. 若由 classifier 使用，需在 `lib/classifier.js` 中新增對應的呼叫（例如新函式內呼叫 `skills.loadSkill(...)` 並呼叫 Groq API）。

## API

- **GET /api/skills** — 回傳 `{ total, skills: ['intent-classifier', 'quick-answer', 'workflow-decomposer'] }`，用於查詢目前有哪些技能。

## 開發

- 技能檔會依名稱快取；修改 `.md` 後若需立即生效，可重啟程式，或由程式呼叫 `skills.clearCache()` / `skills.clearCache('技能名')` 清除快取。
- 技能目錄可由環境變數 `WSC_BOT_SKILLS_DIR` 覆寫（預設為專案根目錄下的 `skills/`）。
