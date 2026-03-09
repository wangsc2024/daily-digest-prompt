---
name: markdown-editor
version: "1.0.0"
description: |
  Markdown 格式編輯與內容總結 Skill。涵蓋 CommonMark/GFM 全語法參考、跨平台差異、自動化工具（目錄生成、連結替換、AI 摘要）。
  Use when: 編輯 Markdown、產生摘要、格式化文件、產生目錄、批量替換連結、Markdown 語法查詢，or when user mentions Markdown, md, 格式化, 摘要, TOC, 目錄生成.
allowed-tools: Read, Write, Edit, Bash
cache-ttl: N/A
triggers:
  - Markdown
  - md
  - 格式化
  - 摘要
  - TOC
  - 目錄生成
  - 表格
  - 程式碼區塊
  - 連結替換
  - Markdown 編輯
  - 內容總結
  - 文件排版
  - GFM
  - CommonMark
---

# Markdown 格式編輯與內容總結 Skill

提供 Markdown 全語法參考、跨平台差異對照、以及自動化編輯/摘要工具。

## 適用情境

當你需要：
- 查詢 Markdown 語法（CommonMark / GFM / 擴充）
- 編輯或格式化 Markdown 文件
- 自動產生目錄（TOC）
- 批量替換圖片路徑或連結
- 從長篇 Markdown 產生結構化摘要
- 確認語法在不同平台（GitHub/GitLab/VS Code/Obsidian）的渲染差異

## 核心資源

| 資源 | 路徑 | 用途 |
|------|------|------|
| 完整語法指南 | `skills/markdown-editor/Markdown_Skill_Guide.md` | 15+ 語法完整說明 |
| 快速參考卡 | `skills/markdown-editor/Markdown_Quick_Reference.md` | 5 分鐘速查 |
| 自動化工具 | `tools/markdown-tools.py` | TOC/連結替換/摘要 |

## 快速使用

### 1. 查詢語法
讀取 `skills/markdown-editor/Markdown_Skill_Guide.md` 中對應章節。

### 2. 自動產生目錄
```bash
uv run python tools/markdown-tools.py toc <file.md>
```

### 3. 批量替換圖片路徑
```bash
uv run python tools/markdown-tools.py replace-links <file.md> --old-prefix "/old/path" --new-prefix "/new/path"
```

### 4. 產生內容摘要
```bash
uv run python tools/markdown-tools.py summarize <file.md> --max-sentences 5
```

### 5. 格式驗證（lint）
```bash
uv run python tools/markdown-tools.py lint <file.md>
```

## 執行步驟

1. **讀取本 SKILL.md** 了解可用功能
2. **依需求選擇操作**：
   - 語法查詢 → 讀 Markdown_Skill_Guide.md
   - 格式編輯 → 使用 Edit 工具 + 參考指南
   - 批量操作 → 使用 `tools/markdown-tools.py`
   - 摘要產生 → 使用 summarize 子命令
3. **驗證結果**：確認輸出符合預期格式

## 語法速查（前 10 項）

| # | 語法 | 標記 | 範例 |
|---|------|------|------|
| 1 | 標題 | `# ~ ######` | `## 二級標題` |
| 2 | 粗體 | `**text**` | **粗體** |
| 3 | 斜體 | `*text*` | *斜體* |
| 4 | 刪除線 | `~~text~~` | ~~刪除~~ (GFM) |
| 5 | 連結 | `[text](url)` | [範例](https://example.com) |
| 6 | 圖片 | `![alt](url)` | `![logo](logo.png)` |
| 7 | 程式碼 | `` `code` `` | `inline code` |
| 8 | 區塊引用 | `> text` | > 引用文字 |
| 9 | 無序列表 | `- item` | - 項目 |
| 10 | 有序列表 | `1. item` | 1. 項目 |

> 完整 15+ 語法含邊界條件與跨平台差異，見 `Markdown_Skill_Guide.md`。

## 注意事項

- **平台差異**：表格對齊、腳註、數學公式在不同渲染器行為不同，指南中有詳細對照表
- **安全性**：HTML 內嵌需留意 XSS 風險，GFM 會過濾 `<script>`、`<style>` 等標籤
- **編碼**：所有工具輸出 UTF-8，Windows 環境需確認終端編碼
- **摘要品質**：規則式摘要適合結構化文件，非結構化長文建議搭配 AI API
