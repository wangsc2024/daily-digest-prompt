# Cursor CLI 任務：法華經研究（fahua）

## 任務目標

對法華經（妙法蓮華經）進行深度研究，生成結構化研究摘要並匯入知識庫。

## 執行步驟

1. **讀取去重清單**：Read `context/research-registry.json`，只讀頂層 `topics_index` 欄位，確認本次研究主題近 7 天內未重複執行。

2. **知識庫查詢**：對以下搜尋詞各執行一次 KB hybrid search（POST http://localhost:3000/api/search/hybrid）：
   - 法華經、妙法蓮華經、一佛乘、開權顯實

3. **深度研究**：依照研究路徑逐步分析：
   - 經典概論 → 方便品（開權顯實）→ 譬喻品（三車火宅）→ 信解品 → 藥草喻品 → 化城喻品 → 壽量品 → 觀世音菩薩普門品 → 一佛乘義理

4. **生成研究報告**：撰寫包含以下章節的 Markdown 研究報告（1500-3000 字正體中文）：
   - 研究主題與核心義理
   - 重點章節解析（至少 3 個）
   - 修行實踐要點
   - 延伸閱讀建議

5. **寫入結果檔**：用 Write 工具將以下 JSON 寫入 `results/todoist-auto-fahua.json`：
   ```json
   {
     "agent": "todoist-auto-fahua",
     "backend": "cursor_cli",
     "status": "completed",
     "summary": "<研究摘要（100字以內）>",
     "topic": "<本次研究主題>",
     "generated_at": "<ISO8601時間戳>"
   }
   ```

6. **更新研究登錄表**：在 `context/research-registry.json` 的 `entries` 陣列追加新條目，同時更新 `topics_index` 欄位。

7. **匯入知識庫**：將研究報告以 POST http://localhost:3000/api/notes 格式匯入（source: "import"，tags: ["法華經", "佛學", "天台宗"]）。

## 注意事項
- 全程使用正體中文輸出
- 禁止使用 `> nul`，輸出抑制用 `> /dev/null` 或 `| Out-Null`
- 結果檔必須在執行完畢後存在

## 結構化摘要格式
執行完畢後必須提供：執行摘要、研究主題、重點義理（3條）、已更新的檔案清單、知識庫匯入狀態。
