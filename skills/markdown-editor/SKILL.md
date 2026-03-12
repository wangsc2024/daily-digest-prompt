---
name: markdown-editor
version: "2.0.0"
description: |
  Markdown 指令、編輯與總結 Skill。依知識庫「Markdown 指令、編輯與總結 Skill 完整指南」建立，涵蓋 CommonMark 0.30 + GFM 全語法（33 種指令）、解析機制、MD 格式編輯流程、內容總結方法（TOC/大綱/摘要）、跨平台渲染差異。
  Use when: 編輯或格式化 Markdown、產生目錄或摘要、查詢語法、批次連結替換、表格/程式碼區塊/引用撰寫、確認 GitHub/Typora/VS Code 相容性。
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
  - 大綱
  - 錨點
  - 腳註
  - Mermaid
  - 告警區塊
references:
  - docs/research/Markdown_指令_編輯與總結_skill.md
---

# Markdown 指令、編輯與總結 Skill

本 Skill 依知識庫 **《Markdown 指令、編輯與總結 Skill 完整指南》** 建立。基準規範：CommonMark 0.30 + GitHub Flavored Markdown (GFM)；適用渲染器：GitHub、Typora、VS Code 內建預覽。

---

## 何時使用本 Skill

- 查詢 Markdown 語法（含邊界條件與渲染器差異）
- 編輯或格式化 .md 檔案（結構、表格、連結、程式碼區塊）
- 產生 TOC、大綱、摘要或關鍵詞
- 批次替換連結/路徑、標題編號、清單排序
- 確認語法在 GitHub / Typora / VS Code / Obsidian 的相容性

**完整指南路徑**：`docs/research/Markdown_指令_編輯與總結_skill.md`（33 種指令詳解、解析機制、編輯七步驟、摘要準則、附錄兼容性矩陣）。

---

## 兩大 Skill 流程（指令 → 決策 → 輸出）

| Skill | 輸入 | 核心決策 | 輸出 |
|-------|------|----------|------|
| **MD 格式編輯** | 原始文件 + 編輯意圖 | 語法選擇、結構調整、批次處理 | 格式正確的 .md 檔案 |
| **內容總結** | 完整 .md 檔案 | 層級萃取、重點判斷、長度控制 | 大綱 / 摘要 / TOC |

---

## 常用 Markdown 指令速查（Top 10）

| 指令 | 語法範例 | 注意事項 |
|------|----------|----------|
| 標題 | `# H1` ~ `###### H6` | `#` 後必須有空格 |
| 粗體/斜體 | `**粗體**` `*斜體*` | 建議用 `**`/`*`，避免 `__`/`_` 詞中衝突 |
| 清單 | `- item` `1. item` | 無序用 `-`，有序用 `1.` |
| 任務清單 | `- [ ] 待辦` `- [x] 完成` | GFM 擴展，GitHub 支援 |
| 程式碼 | `` `code` `` 或 ` ```lang ` | 區塊支援語法高亮 |
| 表格 | `\| H1 \| H2 \|\n\|---|---\|` | 必須有表頭分隔行 |
| 連結 | `[text](url)` | 重複 URL 用參考式 `[text][id]` |
| 圖片 | `![alt](path)` | 相對路徑避免跨平台問題 |
| 引用 | `> text` | 可嵌套 `> >` |
| 分隔線 | `---` 或 `***` | 前後需空行 |

**完整 33 種指令**（含腳註、Mermaid、告警區塊、數學公式等）見 `docs/research/Markdown_指令_編輯與總結_skill.md`。

**重要規則**：`#` 後必須有空格；粗體/斜體建議用 `**`/`*`；表格為 GFM 擴展，表頭分隔行必須存在。

---

## MD 格式編輯 — 執行步驟

1. **確認渲染環境**：文件將在 GitHub / 部落格 / Obsidian 等何處渲染，決定可用語法範圍。
2. **建立檔案骨架**：先寫標題層級，再填內容。
3. **撰寫內容**：依上表與完整指南第三章選擇語法；CJK 建議粗體用 `**`。
4. **插入圖表**：圖片用相對路徑；圖表用 Mermaid（` ```mermaid `）。
5. **連結**：重複 URL 用參考式連結；錨點依 GitHub 規則（小寫、空格→`-`、去標點）。
6. **表格**：表頭行 + 分隔行（`:---` 靠左、`:---:` 置中、`---:` 靠右）；欄位數以表頭為準。
7. **預覽驗證**：在目標渲染器確認。

**批次操作範例**（詳見完整指南 4.1）：
- 連結絕對→相對：正則替換 `\]\(https://github\.com/.../(.+?)\)` → `](./$1)`。
- 標題編號、清單排序：可依指南內 Python 腳本邏輯實作或呼叫專案工具。

---

## 內容總結 — 類型與輸出

| 摘要類型 | 用途 | 輸出格式 |
|----------|------|----------|
| **目錄 (TOC)** | 文件導航 | 帶錨點的清單 |
| **大綱 (Outline)** | 快速理解結構 | 標題層級樹 |
| **摘要 (Summary)** | 核心內容 | 1–3 段文字 |
| **關鍵詞** | 搜尋與分類 | 標籤清單 |
| **精華段落** | 重點擷取 | 引用區塊 |

**摘要準則**：層級與原文一致；獨立可讀；項目帶錨點回溯；TOC 項 ≤50 字元、摘要段 ≤3 句；優先使用 CommonMark 以保兼容。

**實作方式**（見完整指南第五章）：
- 手動：`<!-- summary:start -->` … `<!-- summary:end -->` 區塊 + 擷取腳本。
- 大綱：依標題萃取（跳過程式碼區塊與 front matter）。
- TOC：依標題產生錨點清單（slugify：小寫、空格→`-`、重複加後綴）；可搭配 VS Code「Markdown All in One」或專案 `tools/markdown-tools.py`。

---

## 專案內工具

**工具可用性檢查**：執行前先確認 `tools/markdown-tools.py` 存在。

| 功能 | 指令 | 降級方案 |
|------|------|----------|
| 產生 TOC | `uv run python tools/markdown-tools.py toc <file.md>` | 手動萃取標題：`grep '^#' file.md` |
| 替換連結 | `uv run python tools/markdown-tools.py replace-links <file.md> --old "..." --new "..."` | 使用 Edit 工具逐項替換 |
| 摘要 | `uv run python tools/markdown-tools.py summarize <file.md> --max-sentences 5` | 讀取檔案後手動摘要（依第五章準則） |
| Lint | `uv run python tools/markdown-tools.py lint <file.md>` | 依完整指南 4.3 手動檢查規則 |

**降級流程**：
```bash
# 1. 檢查工具
test -f tools/markdown-tools.py && echo "TOOL_AVAILABLE" || echo "USE_FALLBACK"

# 2. 若不存在，依上表「降級方案」欄執行等效操作
```

---

## 快捷鍵與設定（摘要）

- **VS Code**：粗體 `Ctrl+B`、斜體 `Ctrl+I`、預覽 `Ctrl+Shift+V`、TOC 用「Markdown All in One」建立。
- **Typora**：連結 `Ctrl+K`、表格 `Ctrl+T`、程式碼 `Ctrl+Shift+K`。
- **markdownlint**：建議開啟 MD001/MD004/MD009；可關閉 MD013（行長）、MD033（HTML）；MD024 可設 `siblings_only`。

完整設定範例見完整指南 4.2–4.3。

---

## 注意事項

- **平台差異**：腳註、定義清單、`==高亮==`、告警區塊等在 GitHub/Typora/VS Code 支援度不同，見完整指南附錄 A。
- **安全**：GitHub 會過濾 `<script>`、`<style>`、`<iframe>` 等；行內 HTML 僅用允許標籤。
- **編碼**：輸出一律 UTF-8；Windows 終端需注意編碼。
- **Git 協作**：可採語意換行（一行一句）、表格簡潔格式（不強制對齊 `|`）、`*.md merge=union` 減少衝突。

---

## 參考

- **完整指南**：`docs/research/Markdown_指令_編輯與總結_skill.md`（33 種指令詳解、解析機制、編輯七步驟、摘要方法、附錄 A/B）。
- **CommonMark 0.30**：https://spec.commonmark.org/0.30/
- **GFM**：https://github.github.com/gfm/
