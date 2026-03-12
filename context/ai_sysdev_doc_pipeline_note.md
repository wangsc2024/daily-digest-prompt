# AI 活文件管線實作：OpenAPI 文件、PR 摘要、Release Notes 與 llms.txt 自動同步

研究日期：2026-03-12  
研究類型：AI 系統開發 / 文件生成 / docs-as-code 實作  
系列：ai-living-documentation-pipeline（application 階段）

> 本文承接「AI 驅動的文件自動化」既有概論筆記，將焦點從「可生成什麼文件」推進到「如何把文件當成可持續交付產物」。核心做法是把 PR 摘要、OpenAPI 靜態文件、Release Notes 與 `llms.txt` 併入同一條 CI/CD 文件管線，讓程式碼變更自然帶出人類可讀與 LLM 可讀的雙軌文件。

## 技術概述

2025-2026 年的 AI 文件生成已不再只是幫開發者補 docstring，而是朝「活文件（Living Documentation）」演進：每次 pull request 都先產生變更摘要，每次 API 規格更新都自動重建靜態文件，每次 release 都根據標籤與作者規則生成可稽核的發行說明，最後再補一份給 LLM 與 Agent 取用的 `llms.txt`。這種做法的關鍵不是把文件外包給模型，而是把模型放在既有工程控制點之中，讓文件和原始碼、規格、標籤治理與發布節奏保持同步。

## 核心方法與工具

### 1. PR 層：用 GitHub Copilot 生成變更摘要
- GitHub Copilot 可在 pull request 描述或 comment 直接生成摘要，適合作為第一層「變更說明草稿」。
- 官方文件特別提醒：若 PR 描述已有既有內容，Copilot 不會自動吸收；最佳做法是先用空白描述生成，再由作者補上風險、回滾策略與驗證步驟。
- 工程上應把它視為 `draft changelog fragment`，而非可直接發布的最終說明。

### 2. Release 層：用 GitHub 自動產生 Release Notes
- GitHub Releases 可自動整理 merged PR、contributors 與完整 changelog 連結。
- 透過 `.github/release.yml` 可用 labels 與 authors 規則做分類與排除，避免 Dependabot、格式修正或內部維運噪音汙染發版說明。
- 這讓「變更日誌格式」從人工維護，轉成由標籤治理驅動。

### 3. API 層：以 Redocly CLI 建置 OpenAPI HTML 文件
- `redocly build-docs` 可以把 `openapi.yaml` 或設定檔中的 alias 直接輸出為靜態 HTML，適合放進 Pages、Cloudflare Pages 或 release artifact。
- 若同時搭配 `lint` 與 bundle，可把 API 文件建置變成 CI quality gate：規格不合法就阻擋文件發布。
- 自訂 Handlebars template 可插入版本、commit SHA、build time 與追蹤碼，讓文件可追溯。

### 4. LLM 層：用 `llms.txt` 補齊 Agent 友善入口
- `llms.txt` 規格主張在網站根目錄提供一份 Markdown 索引，集中說明站點背景、重點文件與可展開的明文連結。
- 對軟體文件站來說，這比直接讓 Agent 抓整站 HTML 更有效率，尤其適合收斂 API、架構、CLI 與操作流程。
- 若再生成 `llms-ctx.txt` / `llms-ctx-full.txt` 之類衍生檔，可提供「短上下文」與「完整上下文」兩種餵給 LLM 的素材。

## 實際工作流程（step-by-step）

1. 開發者提交 PR，先用 Copilot 產生 PR 摘要，補上風險、驗證步驟與相依變更。
2. PR merge 前，CI 檢查是否涉及 `openapi/`、`docs/`、`skills/`、`templates/` 或對外行為描述檔。
3. 若有 API 規格變動，執行 Redocly `lint`、`bundle`、`build-docs`，產出靜態 API 文件。
4. 若有使用者可感知變更，依 PR labels 產生對應 changelog fragment，供 release notes 匯總。
5. 發版時由 GitHub Releases 根據 `.github/release.yml` 自動整理分類後的 release notes。
6. 同步更新 `llms.txt`，把最新 API 文件、操作指南、prompt/skill 文件與關鍵 JSON schema 納入索引。
7. 部署文件站後，做 smoke test：確認 HTML 文件存在、release notes 正確分類、`/llms.txt` 可讀、鏈結無 404。
8. 以抽樣方式讓 LLM 或 agent 回答 3-5 個文件問題，驗證新文件是否真能被機器使用。

## 程式碼 / 配置範例

### `.github/release.yml`
```yaml
changelog:
  exclude:
    labels:
      - ignore-for-release
      - chore
    authors:
      - dependabot
  categories:
    - title: Breaking Changes
      labels:
        - breaking-change
    - title: Features
      labels:
        - enhancement
        - feature
    - title: Fixes
      labels:
        - bug
        - fix
    - title: Other Changes
      labels:
        - '*'
```

### `redocly.yaml`
```yaml
apis:
  digest@v1:
    root: ./openapi/openapi.yaml
lint:
  extends:
    - recommended
```

### GitHub Actions 文件工作流
```yaml
name: docs-pipeline
on:
  pull_request:
    paths:
      - 'openapi/**'
      - 'docs/**'
      - 'skills/**'
      - 'templates/**'
  push:
    branches: [main]

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm install -g @redocly/cli
      - run: redocly lint openapi/openapi.yaml
      - run: redocly build-docs openapi/openapi.yaml --output docs/api.html
      - run: python scripts/generate_llms_txt.py
      - uses: actions/upload-artifact@v4
        with:
          name: docs-site
          path: docs/
```

### `llms.txt`
```md
# Daily Digest Prompt

> AI 自動化研究與知識庫系統，提供技能、研究模板、匯入流程與結果檔格式。

## Core Docs
- [/docs/api.html](/docs/api.html): 對外 API 與資料格式
- [/templates/shared/preamble.md](/templates/shared/preamble.md): 所有 agent 共同規則
- [/skills/SKILL_INDEX.md](/skills/SKILL_INDEX.md): Skill 地圖與入口

## Optional
- [/context/research-registry.json](/context/research-registry.json): 近期研究索引
- [/results/](/results/): 任務結果輸出位置
```

## 效果量化

- GitHub 的研究指出，使用 Copilot 的開發者在受控實驗中完成任務速度平均快 **55%**，完成率為 **78%**，對照組為 **70%**。這個數字不能直接等同於「文件生成效率」，但可合理推論 AI 先產出 PR 摘要與文件草稿能降低撰寫說明的切換成本。
- 同一研究也顯示，受訪者中 **73%** 認為更能保持 flow、**87%** 認為重複工作上的心智負擔下降。對文件維護這類高重複、低即時回饋工作尤其 relevant。
- 依現有 KB 的文件自動化研究，手動文件維護常吃掉約 20-30% 的開發時間；若把 release note、API docs 與 LLM 文件入口自動化，較合理的工程目標是先把「手動整理發版說明與 API 文件」壓到只剩人工審稿與例外修正。

> 上述量化中，55% / 73% / 87% 來自 GitHub Copilot 研究，屬於一般開發生產力數據；套用到文件工作流是推論，不應直接當成你專案的保證值。

## 與本專案的應用場景（daily-digest-prompt 如何受益）

- `skills/`、`templates/`、`config/` 經常變動，但對外規則分散；可把核心規則整理為 `llms.txt` 與靜態 docs，讓後續 agent 更快理解專案。
- 目前研究結果與 prompt 規則更新後，常需要手動補摘要；PR 摘要可先提供變更草稿，減少整理 commit 與描述的時間。
- 若未來將本機 `localhost:3000` KB API 對內文件化，可用 OpenAPI + Redocly 生成 HTML，再將 URL 納入 `llms.txt`，使 agent 更容易查詢與匯入知識。
- `results/*.json` 已是結構化產物，適合再延伸出 release note fragment 或 weekly digest，自動總結一週新增研究與規則調整。

## 風險與注意事項

- PR 摘要是語意壓縮，不是事實來源；如果 diff 太大、跨多個 concern，摘要可能漏掉破壞性變更。
- 自動 release notes 仰賴 labels 品質；沒有標籤治理，輸出會變得混亂。
- `llms.txt` 只提供入口，不保證內容最新；若下游文件沒跟著部署，Agent 仍會讀到舊資訊。
- API 文件若只 build 不 lint，可能把結構錯誤的 OpenAPI 變成「看起來能用」的壞文件。
- 不應把內部敏感路徑、私有操作手冊或含 secrets 的文件直接列進 `llms.txt`。

## 參考來源

- GitHub Docs, Automatically generated release notes: https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes
- GitHub Docs, Creating a pull request summary with GitHub Copilot: https://docs.github.com/en/copilot/how-tos/use-copilot-for-common-tasks/create-a-pr-summary
- Redocly Docs, `build-docs`: https://redocly.com/docs/cli/commands/build-docs
- llmstxt.org, The /llms.txt file: https://llmstxt.org/index.html
- GitHub Blog, Research: quantifying GitHub Copilot’s impact on developer productivity and happiness: https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-on-developer-productivity-and-happiness/

## 既有知識交叉引用

- AI 驅動的文件自動化：API 文件生成、變更日誌自動化與 LLM 輔助文件維護（2026）
- AI-Driven Documentation Generation 完整指南 — LLM 輔助 API 文件生成、程式碼自動文件化與智能變更日誌自動化的工業級實踐（2026）
