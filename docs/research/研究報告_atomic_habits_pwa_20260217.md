# atomic_habits_pwa 專案系統設計研究報告

## 執行摘要

| 項目 | 值 |
|------|-----|
| 總分 | **71/100** |
| 等級 | **B 良好** |
| 審查日期 | 2026-02-17 |
| 專案類型 | Progressive Web App (React + TypeScript + Gun.js) |
| 權重模型 | balanced |
| 校準規則觸發 | 無 |

> 本專案具備專業水準：完整的測試架構（單元+整合+E2E+Mutation）、良好的安全防護（XSS 防護模組、CI 安全掃描）、PWA 離線能力。主要不足在於 App.tsx 單檔案過大（870 行）、Gun.js 資料無加密、CI 覆蓋率閘門未完整實作、manifest icons 使用外部佔位圖。

---

## 7 維度評分詳情

### 維度 1：資訊安全（權重 20%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 1.1 機密管理 | 80 | `.gitignore` 包含 `.env*`；`constants.ts` 中 VAPID_PUBLIC_KEY 透過 `import.meta.env` 取得；Grep 掃描無硬編碼密碼/Token | 環境變數用法正確，.gitignore 完整排除敏感檔案。VAPID 公鑰透過環境變數注入，無 private key 洩露。扣分：GUN_PEERS URL 和 NTFY_URL 硬編碼在 `constants.ts`，雖非機密但應可配置化。 |
| 1.2 輸入驗證 | 82 | `src/utils/securityUtils.ts` 提供完整 XSS 防護：`sanitizeInput`（移除 HTML 標籤+轉義+長度限制）、`validateCounterName`/`validateTimerName`/`validateHabitName`（防 HTML 注入+危險協議）、`safeHabitName`/`safeNumber`/`safeDate`/`safePercentage` | 有系統化的輸入驗證模組，覆蓋計數器、計時器、習慣名稱、統計數值。包含 null byte 移除、事件處理器檢測、危險協議檢測。扣分：`App.tsx` 中 `handleLogin` 的 `inputAccount` 僅做 trim，無長度限制或格式驗證。 |
| 1.3 存取控制 | 55 | 無 Hook/Guard 攔截機制；`allowedTools` 未限縮；帳號使用 localStorage 存儲 `accountId`，無密碼驗證；Gun.js 資料路徑 `/users/{accountId}` 任何知道 accountId 的人可存取 | 存取控制較弱。accountId 等同於密碼，但無加密、無 rate limiting、無 session 過期。SECURITY.md 已明確標示「無密碼加密」為已知限制。 |
| 1.4 依賴安全 | 78 | `package-lock.json` 存在（369KB）；`.github/dependabot.yml` 配置每週一自動檢查 npm + GitHub Actions；CI 包含 `npm audit` + Snyk 掃描 | 有完整的依賴鎖定和自動更新策略。扣分：CI 的 security job 設定 `continue-on-error: true`，漏洞不會阻擋部署。 |
| 1.5 傳輸安全 | 85 | Grep 搜尋 `http://` 僅在 `playwright.config.ts`（localhost 測試用）和 SVG xmlns 宣告。所有外部 API 呼叫使用 HTTPS：`https://relay-o.oopdoo.org.ua/gun`、`https://ntfy.sh/oopdoo`。`_headers` 檔案存在（Cloudflare 安全標頭配置）。 | 外部通訊全部 HTTPS，localhost 例外合理。 |
| 1.6 日誌安全 | 65 | 無結構化日誌系統；使用 `console.log`/`console.warn`/`console.error`；`pushService.ts:97` 記錄 `subscription.endpoint`（含敏感 token）；Service Worker 記錄版本資訊 | console.log 記錄 push subscription endpoint 可能洩露 token。無日誌輪轉或脫敏機制。但因為是前端 PWA，日誌僅存於用戶端瀏覽器 DevTools，風險有限。 |

**維度 1 平均分：74**

---

### 維度 2：系統架構（權重 18%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 2.1 關注點分離 | 65 | 頂層目錄：`src/`（components/services/utils/types/constants/hooks/styles）、`tests/`（按功能分）、`scripts/`、`specs/`、`public/`。但 `App.tsx`（870 行）混合了狀態管理、業務邏輯、UI 渲染。根目錄同時存在 `App.tsx`/`index.tsx`/`types.ts`/`constants.ts` 和 `src/` 目錄下的同類檔案。 | src/ 內部分層清晰（components/services/utils/types），但 App.tsx 是巨型單檔案（870 行），混合了習慣追蹤 + 計數器 + 計時器 + 多頁面導航的所有邏輯。根目錄 vs src/ 存在雙重結構，如 `types.ts`（根）vs `src/types/index.ts`。 |
| 2.2 配置外部化 | 55 | 常數定義在 `constants.ts`（GUN_PEERS、NTFY_URL、VAPID_PUBLIC_KEY、DEFAULT_VERSES）；無 config/ 目錄；環境變數僅 1 個（VITE_VAPID_PUBLIC_KEY）；快取 TTL 硬編碼在 `cacheService.ts`（DEFAULT_TTL = 3600000）；重試次數硬編碼在 `updateService.ts`（MAX_RETRIES = 3） | 部分配置透過 constants.ts 集中管理，但多數可調參數（快取 TTL、重試次數、timeout 值）散佈在各 service 檔案中硬編碼。無專門的 config 目錄或環境變數覆蓋機制。 |
| 2.3 耦合度 | 70 | Services（gunService、pushService、cacheService、updateService、themeService）各自獨立；Components 透過 props 通訊，無直接 import 其他 component。但 App.tsx 直接依賴所有 services 和 components，是核心耦合點。 | Services 間低耦合，Components 透過 props 解耦。主要問題在 App.tsx 集中了所有狀態和邏輯，形成星型依賴。引入 Context 或狀態管理庫可改善。 |
| 2.4 可擴展性 | 68 | 有 specs/ 目錄（5 個功能規格：auto-update、counter-timer、habit-tracking、statistics、theme-system）；新增元件有既定的 src/components/ 放置慣例；Code splitting 已實作（StatsView、CounterView、TimerView 使用 lazy loading）。但新增功能需修改 App.tsx（加 state + handler + route） | specs/ 目錄體現了有計畫的功能開發流程。但由於 App.tsx 是單一狀態中心，每個新功能都需要在 App.tsx 中加入狀態和處理器，觸碰檔案數低但該檔案已過大。 |
| 2.5 容錯設計 | 75 | `updateService.ts` 有完整的重試機制（指數退避、MAX_RETRIES=3）和超時保護（AbortController + 5000ms）；`sw.js` 的 fetch 事件有 cache-first 降級；`cacheService.ts` 有 `safeLocalStorageOperation` 包裝；`pushService.ts` 有 error handling 但無重試 | 更新服務有完善的重試+超時+降級。Service Worker 有 cache-first fallback。localStorage 操作有安全包裝。扣分：Gun.js 同步無顯式的失敗重試邏輯（依賴 Gun.js 內建機制）。 |
| 2.6 單一定義處 | 60 | 根目錄 `types.ts` 和 `src/types/index.ts` 存在重複/擴展關係；`App.tsx` 中計數器歸零和計時器歸零邏輯高度相似（`handleCounterReset` 和 `handleTimerReset`，各 50 行，結構幾乎相同）；streak 計算邏輯在 `handleToggleHabit`、`handleCounterReset`、`handleTimerReset` 中重複出現 | streak 計算邏輯重複了 3 次（handleToggleHabit/handleCounterReset/handleTimerReset），可抽取為共用函式。Counter 和 Timer 的歸零同步邏輯高度相似，可泛化。`securityUtils.ts` 的 `validateName` 是好的 DRY 示範。 |

**維度 2 平均分：66**

---

### 維度 3：系統品質（權重 18%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 3.1 測試覆蓋率 | 82 | 測試檔案 40 個（tests/ 目錄）：單元測試 28 個 + 整合測試 7 個 + E2E 測試 4 個 + setup 1 個。按功能分區：counter-timer(7)、theme-system(5)、statistics(10)、auto-update(4)、habit-tracking(4)、e2e(4)、utils(1)。`vitest.config.ts` 設定覆蓋率門檻 80%（lines/functions/branches/statements）。有 Stryker mutation testing 設定（break threshold 60%）。 | 測試架構完整：三層測試（Unit + Integration + E2E）、覆蓋率門檻 80%、mutation testing（Stryker）。測試數量充足（40 個測試檔）。扣分：未能即時執行以驗證實際覆蓋率數字。 |
| 3.2 程式碼品質 | 72 | `package.json` 配置 ESLint（eslint + react + react-hooks + typescript-eslint + complexity plugins）；有 `lint` 和 `lint:fix` 指令；TypeScript strict mode 啟用（`"strict": true`）；命名規範一致（camelCase for functions, PascalCase for components）。但 App.tsx 870 行過長。 | ESLint 配置完整，含 complexity 插件。TypeScript strict mode。CI 包含 lint + type-check。扣分：App.tsx 單檔案 870 行違反 SRP。 |
| 3.3 錯誤處理 | 75 | Grep 搜尋 try/catch：`updateService.ts`（15 處）、`audioUtils.ts`（14 處，含多層 fallback）、`cacheService.ts`（4 處，safeLocalStorageOperation 包裝）、`counterService.ts`（4 處）、`themeService.ts`（3 處）。大多數 catch 有 console.error 記錄。`pushService.ts` 所有 API 呼叫有 try/catch + 回傳 boolean 指示成功。 | 外部呼叫（fetch、localStorage、Audio API）普遍有 try/catch。`audioUtils.ts` 展示了多層 fallback 模式。扣分：`gunService.ts` 的 CRUD 操作無 try/catch（依賴 Gun.js 內部處理）。錯誤無分級（全部 console.error）。 |
| 3.4 品質驗證機制 | 75 | CI pipeline：lint → type-check → test → build（`ci.yml`）；覆蓋率檢查 job（但 TODO 標記尚未完成）；Stryker mutation testing 配置完整；specs/ 目錄有功能規格；`SECURITY.md` 有安全政策。無 quality gate / DONE_CERT。 | 有 CI 品質管線。有 mutation testing 配置。有安全掃描。有功能規格（specs/）。扣分：覆蓋率檢查 TODO 未完成；無正式的 quality gate 或 DONE_CERT 機制。 |
| 3.5 監控與可觀測性 | 45 | 無結構化日誌系統；無健康檢查腳本；無自動告警機制；僅使用 console.log/warn/error。Service Worker 有版本追蹤和更新通知。 | 作為前端 PWA，缺乏伺服器端監控是可以理解的。但即便是前端也可以有錯誤上報服務（如 Sentry）、效能監控（Web Vitals）。完全依賴 console 輸出。 |
| 3.6 效能基準 | 70 | `updateService.ts` 有 timeout 設定（DEFAULT_TIMEOUT=5000ms）；`cacheService.ts` 有 TTL 機制（DEFAULT_TTL=1h）+ 快取統計（`getCacheStats`）；`vitest.config.ts` 有測試 timeout（10000ms）；`vite.config.ts` 有 Code Splitting（manualChunks: recharts + stats）；`src/utils/streakOptimizer.ts` 有 streak 計算快取。 | 有多處效能優化：Code Splitting、快取服務、streak 計算快取、timeout 保護。扣分：無 Lighthouse 分數追蹤；無 bundle size 監控；無 Web Vitals 追蹤。 |

**維度 3 平均分：70**

---

### 維度 4：系統工作流（權重 15%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 4.1 自動化程度 | 78 | CI/CD 完整：push/PR 自動觸發 lint → type-check → test → build → coverage → security。Dependabot 每週自動檢查依賴更新。`prebuild` hook 自動生成版本號。Service Worker 自動檢測更新。部署到 Cloudflare Pages（git push 自動觸發）。 | 開發 → 測試 → 建置 → 部署 流程高度自動化。版本號生成、依賴更新、安全掃描均自動化。 |
| 4.2 並行效率 | 65 | CI 的 `ci` 和 `security` job 並行執行；`coverage` job 依賴 `ci` 完成。`vitest.config.ts` 配置 `threads: true, maxThreads: 4`。E2E 配置 `fullyParallel: true`。Stryker 配置 `concurrency: 4`。 | 測試執行有並行。但 CI 的 coverage job 串行等待 ci job（可能可以合併或並行）。 |
| 4.3 失敗恢復 | 72 | `updateService.ts`：指數退避重試（1s → 2s → 4s，max 3 次）。`sw.js`：fetch 失敗 fallback 到 cache。CI：Playwright E2E 在 CI 環境有 2 次重試（`retries: process.env.CI ? 2 : 0`）。`cacheService.ts`：localStorage 失敗有 fallback 值。 | 多處有失敗恢復機制。扣分：Gun.js 同步失敗無顯式處理；ntfy 通知失敗無重試。 |
| 4.4 狀態追蹤 | 60 | localStorage 持久化：accountId、user_settings、counters、timers、selected-theme、update-dismissed、current-version、stats cache。版本歷史透過 `version.json` 追蹤。無執行歷史查詢工具。 | 應用狀態透過 localStorage 持久化，跨 session 保留。但無系統化的狀態追蹤工具或歷史查詢機制。 |
| 4.5 排程管理 | 50 | 無排程系統（純前端 PWA，不需要伺服器排程）。ntfy 通知有延遲排程（`delayString` 參數）。Service Worker 版本檢查依賴瀏覽器生命週期事件。 | 作為前端 PWA，排程需求有限。ntfy 的延遲通知算是簡單排程。分數偏低但與專案性質匹配。 |

**維度 4 平均分：65**

---

### 維度 5：技術棧（權重 10%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 5.1 技術成熟度 | 85 | React 19.2.3（最新穩定版）、TypeScript 5.x（主流）、Vite 6.x（現代建置工具）、Tailwind CSS 3.x（主流）、Vitest 2.x（Vite 生態首選）、Playwright 1.48（穩定）、ESLint 8.x（成熟）。Gun.js 0.2020.1241（小眾但穩定的去中心化資料庫）。 | 核心技術棧全部為主流穩定版本。Gun.js 相對小眾但在去中心化場景合理。 |
| 5.2 版本管理 | 80 | `package-lock.json` 存在（369KB）；dependencies 使用 `^` 語義化版本（允許 minor 更新）；Dependabot 每週自動檢查更新。 | Lock file 完整。版本策略合理（`^` 允許安全的 minor 更新）。有自動化更新策略。 |
| 5.3 工具鏈完整性 | 85 | 開發：Vite dev server + React plugin + path alias。測試：Vitest（unit+integration）+ Playwright（E2E）+ Stryker（mutation）+ @testing-library。品質：ESLint（含 complexity 插件）+ TypeScript strict。建置：Vite build + Code Splitting + prebuild hook。部署：Cloudflare Pages + _headers + _redirects。監控：缺（無 Sentry/Web Vitals）。 | 工具鏈覆蓋 5/6 個階段（缺生產監控）。測試工具特別完整（4 種測試類型）。 |
| 5.4 跨平台相容性 | 70 | PWA 本質跨平台（Web 標準）；Playwright 配置僅 Chromium（未含 Firefox/Safari）；CSS 有 `-webkit-` 前綴和 safe area 支援；`index.html` 有 `<meta name="viewport">` 和 `apple-touch-icon`。 | PWA 天然跨平台。但 E2E 測試僅覆蓋 Chromium，Safari/Firefox 的 PWA 行為差異未測試。 |
| 5.5 技術債務 | 72 | `@deprecated` 標記 2 處（`src/types/index.ts:78,112`：linkedHabitName 已棄用）；TODO 1 處（`ci.yml:66`：覆蓋率檢查腳本）；`src/services/counterOptimized.ts` 標記為「未使用的優化版本」。`nul` 檔案存在於根目錄（已加入 .gitignore）。 | 技術債務較低。已知的 deprecated 項目有清晰標記。主要債務：CI 覆蓋率閘門 TODO 未完成、未使用的 counterOptimized.ts、根目錄的 nul 垃圾檔案。 |

**維度 5 平均分：78**

---

### 維度 6：系統文件（權重 10%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 6.1 架構文件 | 82 | `CLAUDE.md`（152 行）：完整的架構概述（去中心化同步、通知系統、PWA 離線、狀態管理）、技術決策說明、元件結構、資料流範例（建立/完成/同步 3 個場景）。`README.md`（42 行）：簡潔的功能和部署說明。 | CLAUDE.md 是出色的架構文件：涵蓋架構模式、技術決策理由、資料流圖、所有重要檔案路徑。 |
| 6.2 操作手冊 | 70 | `README.md` 含安裝（npm install）、開發（npm run dev）、部署（build + Cloudflare Pages）指引。`CLAUDE.md` 有完整的開發指令列表和環境變數說明。`SECURITY.md` 有安全最佳實踐。缺少疑難排解段落。 | 基本操作有文件化。缺少疑難排解指南（如：Gun.js 連線問題、Service Worker 更新問題、離線行為除錯）。 |
| 6.3 API / 介面文件 | 72 | `securityUtils.ts` 每個函式有完整的 JSDoc（參數、回傳值、範例）。`updateService.ts` 有完整的介面定義和函式文件。`cacheService.ts` 有清晰的 API 文件。但 `gunService.ts` 文件較少。`tests/README.md` 有測試目錄結構說明。 | 較新的模組（security、update、cache）有優質的 JSDoc。較早的模組（gun、push）文件較少。 |
| 6.4 配置說明 | 65 | `vite.config.ts` 有中文注釋（recharts 獨立打包說明）。`vitest.config.ts` 有詳細的中文注釋（覆蓋率門檻、排除原因等）。`stryker.conf.json` 有 `_comment` 欄位。但 `manifest.json` 無注釋（JSON 不支援）。 | TypeScript 配置檔有良好的注釋。JSON 配置因格式限制無注釋。 |
| 6.5 變更記錄 | 45 | Git log 僅 4 筆 commit，message 品質不一：「初步完成整合計數器及計時器尚未進行實機測試」、「新版UI」、「優化UI」、「BASE」。無 CHANGELOG.md。commit message 缺乏一致的格式（如 conventional commits）。 | 非常少的 commit 歷史（4 筆），message 格式不一致。缺少 CHANGELOG。Dependabot 配置了 conventional commit prefix（`chore(deps)`），但主線 commit 未遵循。 |

**維度 6 平均分：67**

---

### 維度 7：系統完成度（權重 9%）

| 子項 | 分數 | 證據 | 理由 |
|------|------|------|------|
| 7.1 功能完成度 | 78 | TODO 1 處（`ci.yml:66`）；FIXME/HACK/XXX 0 處。規劃功能均已實作：習慣追蹤、計數器、計時器、統計分析、主題系統、PWA 更新、離線支援、跨裝置同步、佛偈里程碑。specs/ 目錄 5 個功能規格均有對應實作。 | 規劃功能完成度高。僅 1 個 TODO（CI 覆蓋率腳本）。5 個功能模組均有規格和實作。 |
| 7.2 邊界處理 | 72 | `securityUtils.ts` 處理 null/undefined/超長/XSS。`cacheService.ts` 處理 localStorage 不可用。`updateService.ts` 處理網路錯誤/超時/JSON 解析錯誤/無效資料。`App.tsx:228` 處理「今天已完成」重複觸發。但 `handleLogin` 的帳號輸入無長度限制。 | 核心服務有良好的邊界處理。新增的模組（counter-timer、auto-update、statistics）邊界處理更完整。早期模組（habit-tracking）邊界處理較弱。 |
| 7.3 部署就緒 | 80 | 一鍵建置：`npm run build`（含 prebuild 生成 version.json + postbuild 複製 sw.js/manifest.json/_headers/_redirects）。Cloudflare Pages 部署配置完整。CI/CD 自動化。.env.example 存在。 | 部署流程高度自動化。從建置到部署幾乎無手動步驟。 |
| 7.4 整合完整性 | 68 | 整合測試覆蓋：`habitIntegration.test.ts`（計數器-習慣整合）、`gunSync.test.ts`（Gun.js 同步）、`themeIntegration.test.tsx`（主題系統）、`cacheInvalidation.test.ts`（快取失效）、`performanceTest.test.ts`（效能）、`tabPersistence.test.tsx`（Tab 持久化）。但 Gun.js 整合測試被 vitest 排除（需真實環境）。 | 有 6 個整合測試檔案覆蓋主要整合點。但 Gun.js 同步（核心功能）的整合測試被排除，僅在 E2E 層覆蓋。 |
| 7.5 生產穩定性 | 60 | 無伺服器端執行記錄。`commit:67669b6` 明確標註「尚未進行實機測試」。Service Worker 有版本追蹤。PWA 有離線 fallback。無法量化成功率。 | 最新 commit 承認未實機測試。作為 Cloudflare Pages 靜態網站，伺服器穩定性非主要問題。客戶端穩定性依賴瀏覽器環境。 |

**維度 7 平均分：72**

---

## 加權總分計算

| 維度 | 平均分 | 權重 | 加權分 |
|------|--------|------|--------|
| 資訊安全 | 74 | 20% | 14.8 |
| 系統架構 | 66 | 18% | 11.9 |
| 系統品質 | 70 | 18% | 12.6 |
| 系統工作流 | 65 | 15% | 9.8 |
| 技術棧 | 78 | 10% | 7.8 |
| 系統文件 | 67 | 10% | 6.7 |
| 系統完成度 | 72 | 9% | 6.5 |
| **加權總分** | | **100%** | **70.1 -> 71** |

校準規則檢查：
- 有自動化測試 -> 不觸發（品質上限 50）
- 有 securityUtils.ts + CI security scan -> 不觸發（安全上限 60）
- 有 CLAUDE.md + README.md -> 不觸發（文件上限 40）
- TODO 合計 1 處 -> 不觸發（完成度上限 50）
- 有 updateService 重試 + SW cache fallback -> 不觸發（工作流上限 55）
- Grep 無硬編碼密碼 -> 不觸發（安全上限 30）

**最終總分：71/100，等級：B 良好**

---

## PWA 特有面向深度分析

### Service Worker 實作品質

**註冊流程**：
- `index.tsx:11-18`：標準的 Service Worker 註冊，使用 `window.addEventListener('load')` 延遲註冊避免阻塞首次載入。
- `pushService.ts:159`：重複註冊（`navigator.serviceWorker.register('/sw.js')`），但瀏覽器會自動去重，無實質問題。

**快取策略**：
- `sw.js:114-122`：Cache-First 策略（先查快取，未命中則 fetch）。適合靜態資源。
- `sw.js:96-111`：version.json 例外，使用 Network-First（始終從網路取得，失敗 fallback cache）。確保版本檢測準確。
- 預快取列表僅包含 `/` 和 `/index.html`，其他資源按需快取。

**更新機制**：
- 不自動 `skipWaiting`，由前端控制更新時機（`sw.js:57`）。
- `PWAUpdatePrompt` 元件提供用戶主動更新的 UI（「有新版本可用」提示）。
- 更新流程：SW 安裝 → 前端偵測 → 用戶確認 → postMessage SKIP_WAITING → 重載頁面。
- `updateService.ts` 有完整的版本比較、24 小時靜默機制、指數退避重試。

**評分：78/100** - 實作穩健，更新機制完善。預快取列表過短（僅 2 個 URL），可加入 CSS/JS 主要資源。

### 離線體驗設計

**離線策略**：
- Service Worker 的 Cache-First 確保已訪問的頁面可離線存取。
- Gun.js 的 `localStorage: true` + `radisk: true` 提供本地資料持久化。
- 帳號 ID、設定、計數器、計時器均存於 localStorage，離線完全可用。

**數據同步**：
- Gun.js 提供 eventual consistency：離線操作自動在上線時同步。
- `subscribeToHabits` 使用 `.map().on()` 即時監聽變更，自動合併來自不同裝置的更新。

**衝突解決**：
- 依賴 Gun.js 內建的 CRDT（Conflict-free Replicated Data Type）機制。
- 同一欄位同時修改時，Gun.js 使用 HAM（Hypothetical Amnesia Machine）演算法解決衝突。

**用戶體驗**：
- 無離線指示器（用戶不知道自己是否離線）。
- 無同步狀態指示（用戶不知道資料是否已同步到其他裝置）。

**評分：70/100** - 離線功能基礎完善（得益於 Gun.js），但缺少離線/同步狀態的用戶端指示。

### 狀態管理架構

**選型**：
- 使用 React `useState` + `useCallback` + `useEffect` 原生 Hook，無外部狀態管理庫。
- Gun.js 的 `.on()` 訂閱作為外部資料來源，透過 callback 更新 React state。
- localStorage 作為次要持久化（計數器、計時器、設定、主題）。

**實作品質**：
- 所有 handler 使用 `useCallback` 包裝，避免不必要的重渲染。
- Lazy loading（`React.lazy`）用於 StatsView、CounterView、TimerView。
- 狀態集中在 App.tsx（13 個 useState），每個狀態管理一個面向。

**持久化機制**：
- Gun.js：habits、settings（跨裝置同步）
- localStorage：counters、timers、selected-theme、update-dismissed、stats-cache（僅本機）

**改進建議**：
- 引入 Context API 或 Zustand 將狀態從 App.tsx 拆分到各功能模組。
- 計數器/計時器目前僅存 localStorage，應考慮也透過 Gun.js 同步。

**評分：65/100** - 功能正確但架構不夠理想。App.tsx 870 行 + 13 個 useState 表明需要狀態管理重構。

### 效能優化實踐

**Code Splitting**：
- `vite.config.ts` 手動分割 recharts 和 stats 模組為獨立 chunk。
- `App.tsx` 使用 `React.lazy` 動態載入 StatsView、CounterView、TimerView。
- `Suspense` + `LoadingSkeleton` 提供載入中的骨架畫面。

**快取**：
- `cacheService.ts`：localStorage 快取統計計算結果（streak、heatmap、trend），TTL 1 小時。
- `streakOptimizer.ts`：streak 計算結果快取，避免重複計算。
- Service Worker：靜態資源 Cache-First。

**Bundle Size**：
- 主要依賴：react(~45KB) + react-dom(~130KB) + gun(~50KB) + recharts(~200KB) + lucide-react(~5KB per icon) + date-fns(tree-shakable)。
- recharts 是最大依賴，已透過 Code Splitting 延遲載入。

**Lighthouse 分數**：
- 未追蹤（無自動化 Lighthouse CI）。

**評分：72/100** - Code Splitting 和快取策略良好。可加入 Lighthouse CI 自動追蹤效能分數。

### PWA 最佳實踐符合度

| 項目 | 狀態 | 說明 |
|------|------|------|
| Service Worker | 有 | 離線快取 + 版本更新 + Push 通知 |
| Web App Manifest | 有 | name、short_name、display:standalone、theme_color |
| HTTPS | 有 | Cloudflare Pages 強制 HTTPS |
| 響應式設計 | 有 | max-w-2xl 容器 + safe area + mobile-first |
| App Shell | 部分 | Header + Bottom Nav 固定，內容區域動態載入 |
| 離線體驗 | 有 | Cache-First + Gun.js 本地儲存 |
| 安裝提示 | 缺 | 無 beforeinstallprompt 處理 |
| 自訂 Icons | 缺 | 使用 `https://picsum.photos` 隨機佔位圖 |
| Splash Screen | 缺 | 未設定 splash screen 相關 meta |

**評分：65/100** - 核心 PWA 功能完備。manifest icons 使用外部隨機圖片是明顯缺陷（離線時圖標可能不可用、每次安裝圖標不同）。

---

## TOP 5 改善建議（按優先級排序）

### 1. 拆分 App.tsx（影響：架構 +10, 品質 +5）
**問題**：App.tsx 870 行，包含 13 個 useState、10+ 個 handler、4 頁面路由。
**建議**：
- 引入 React Context 或 Zustand 管理全域狀態
- 抽取 `useHabits`、`useCounters`、`useTimers` 自定義 Hook
- 將頁面路由改用 React Router
**難度**：中 | **預期提升**：架構分 66→76

### 2. 替換 Manifest 佔位 Icons（影響：完成度 +5, PWA +10）
**問題**：`manifest.json` 的 icons 使用 `https://picsum.photos` 隨機圖片，離線時不可用，且每次載入圖標不同。
**建議**：設計專屬 icon 放在 `public/` 目錄，使用本地路徑。
**難度**：低 | **預期提升**：完成度分 72→77

### 3. 實作 CI 覆蓋率閘門（影響：品質 +3）
**問題**：`ci.yml:66` 有 TODO 標記，覆蓋率檢查腳本未完成。
**建議**：在 CI 中加入 `vitest run --coverage --reporter=json && node check-coverage.cjs`。
**難度**：低 | **預期提升**：品質分 70→73

### 4. 加入離線/同步狀態指示器（影響：工作流 +5, 完成度 +3）
**問題**：用戶無法得知離線狀態或資料同步狀態。
**建議**：監聽 `navigator.onLine` 事件，在 Header 顯示離線/同步中圖標。
**難度**：低 | **預期提升**：工作流分 65→70

### 5. 抽取 streak 計算為共用函式（影響：架構 +3）
**問題**：streak 計算邏輯在 handleToggleHabit/handleCounterReset/handleTimerReset 中重複 3 次。
**建議**：建立 `calculateNewStreak(lastDone: string, currentStreak: number): number` 共用函式。
**難度**：低 | **預期提升**：架構分 66→69

---

## 可借鏡的 PWA 設計模式

### 1. 去中心化同步架構（Gun.js）
本專案使用 Gun.js 實現無伺服器的跨裝置同步，是典型的 Local-First 架構。不需要後端伺服器，資料透過 relay peer 點對點同步。這個模式適合個人工具類 PWA，降低運維成本至零。

### 2. 雙通道通知系統
同時支援 ntfy.sh（HTTP-based，無需後端）和 Web Push API（原生瀏覽器通知）。ntfy.sh 作為輕量級替代方案，特別適合沒有後端的 PWA。

### 3. 輸入安全防護模組化
`securityUtils.ts` 提供了可複用的安全防護函式集（sanitize、validate、escape、safe display），包含完整的 XSS 防護（HTML 標籤移除、危險協議檢測、事件處理器過濾）。這個模組可以直接移植到其他專案。

### 4. 更新服務的三層設計
updateService.ts 的設計值得學習：
- **偵測層**：fetchVersionInfo + 重試 + 超時
- **決策層**：版本比較 + 24 小時靜默機制
- **執行層**：SW skipWaiting + 頁面重載

### 5. CSS 主題變數系統
透過 CSS 變數 + data-theme 屬性實現 7 種主題切換，含 FOUC 防護（頁面載入前套用主題）、300ms 平滑過渡動畫。這個方案不依賴 JavaScript runtime，效能優異。
