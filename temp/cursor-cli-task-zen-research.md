# Cursor CLI 任務檔：禪宗研究報告

## 任務目標
- 依 `skills/cursor-cli/SKILL.md`、`skills/web-research/SKILL.md`、`skills/knowledge-query/SKILL.md` 執行禪宗研究。
- 產出正體中文的結構化研究報告。
- 先於 CLI 內實際執行知識庫查詢/去重；僅失敗時才說明 fallback。

## 採用 Skills
1. `cursor-cli`：遵循任務檔先行、Skill-First、外部功能先執行原則。
2. `web-research`：依來源品質分級、摘要、交叉驗證、研究註冊表更新。
3. `knowledge-query`：查詢既有筆記、重複檢查、必要時匯入知識庫。

## 執行步驟
1. 讀取相關 Skill 與研究規則。
2. 查詢 `context/research-registry.json` 與知識庫現有內容，避免重複。
3. 使用 WebSearch/WebFetch 蒐集至少 5 個來源。
4. 撰寫詳細研究報告與品質自評 JSON。
5. 先做 KB 去重，再決定是否匯入。
6. 更新 `context/research-registry.json`。

## 最後回報格式
- ✅ 執行摘要
- 📚 主要發現
- 💾 知識庫
- 🔗 延伸方向
