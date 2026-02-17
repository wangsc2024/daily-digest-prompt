# gemini-cli 專案深度研究與架構洞察報告

## 執行摘要

- **研究日期**：2026-02-17
- **GitHub URL**：https://github.com/wangsc2024/gemini-cli.git（fork 自 google-gemini/gemini-cli）
- **專案類型**：Google 官方開源 Gemini AI CLI 工具
- **版本**：v0.30.0-nightly
- **授權**：Apache 2.0
- **技術棧**：Node.js 20+ / TypeScript / React (Ink) / esbuild / Vitest
- **規模**：4,664 commits、1,449 TypeScript 檔案、6 個 monorepo packages
- **核心價值**：終端機優先的 AI Agent，具備完整的 Hook/Skill/Agent/Policy/Safety/MCP 體系

---

## 專案架構分析

### Monorepo 結構

```
packages/
  cli/          # 前端 UI（React/Ink 渲染終端機介面）
  core/         # 後端邏輯（API 編排、工具執行、排程器）
  sdk/          # 程式化 SDK（GeminiCliAgent 類別，讓外部專案嵌入 Agent）
  a2a-server/   # 實驗性 Agent-to-Agent 伺服器
  test-utils/   # 測試工具
  vscode-ide-companion/  # VS Code 配套擴展
```

### 核心模組地圖（packages/core/src/）

| 模組 | 功能 | 檔案數/行數估計 |
|------|------|----------------|
| `agents/` | Agent 定義、載入、執行、子 Agent、A2A 通訊 | ~34 檔 |
| `scheduler/` | 工具呼叫排程、狀態管理、確認流程、策略執行 | ~14 檔 |
| `tools/` | 內建工具（Read/Write/Edit/Shell/Grep/Glob/MCP/WebFetch 等） | ~60+ 檔 |
| `hooks/` | Hook 系統（BeforeTool/AfterTool/BeforeAgent 等 11 種事件） | ~18 檔 |
| `skills/` | Skill 載入器與管理器（SKILL.md frontmatter 解析） | ~8 檔 |
| `policy/` | 策略引擎（TOML 配置、規則匹配、Shell 安全檢查） | ~14 檔 |
| `safety/` | 安全檢查框架（SafetyCheckInput/Decision 協議） | ~10 檔 |
| `routing/` | 模型路由（Composite/Classifier/Fallback/Override 策略鏈） | ~7 檔 |
| `prompts/` | Prompt 建構與管理 | ~10 檔 |
| `config/` | 配置管理（模型、記憶體、常數） | ~10 檔 |
| `services/` | 服務層（檔案探索、Git、Session、上下文管理） | ~10 檔 |

### 技術棧

| 層面 | 技術 |
|------|------|
| 語言 | TypeScript（嚴格模式 + ESLint + Prettier） |
| 執行環境 | Node.js >= 20.0.0 |
| UI 框架 | React + Ink（終端機 React 渲染器） |
| 構建 | esbuild（快速打包） |
| 測試 | Vitest + ink-testing-library + msw（mock service worker） |
| 包管理 | npm workspaces（monorepo） |
| API | @google/genai SDK |
| MCP | Model Context Protocol 完整支援 |

---

## 深度分析：關鍵機制

### 1. CLI 設計模式

**命令解析架構**：
- 採用 **React/Ink** 框架渲染終端機 UI，這是一個獨特的設計選擇
- 主要入口 `gemini.tsx` 是一個 React 元件，使用 `ink` 的 `render()` 啟動
- 互動模式由 `AppContainer.tsx`（75,498 行！）處理所有狀態
- 非互動模式由 `nonInteractiveCli.ts` 處理 `-p` 參數的 headless 執行

**子命令組織策略**：
- 使用 slash commands（`/help`、`/chat`、`/model`、`/bug` 等）
- 自定義命令支援（Custom Commands）
- `@` 前綴用於 MCP 伺服器呼叫（`@github`、`@slack`）

**使用者體驗設計亮點**：
- 主題系統（Solarized Dark/Light 等多主題）
- Vim 模式支援（`VimModeProvider`）
- Kitty 鍵盤協議支援
- Session 瀏覽器（儲存/恢復對話）
- 自動檢查更新機制
- 備用螢幕緩衝區（Alternate Screen Buffer）
- 滑鼠事件處理

### 2. Agent 編排策略

**Agent 定義系統**（高度結構化）：
```typescript
interface LocalAgentDefinition {
  kind: 'local';
  name: string;
  description: string;
  promptConfig: PromptConfig;   // systemPrompt + query + initialMessages
  modelConfig: ModelConfig;      // 模型選擇
  runConfig: RunConfig;          // maxTurns(15) + maxTimeMinutes(5)
  toolConfig?: ToolConfig;       // 允許的工具清單
  outputConfig?: OutputConfig;   // 結構化輸出 schema (Zod)
}

interface RemoteAgentDefinition {
  kind: 'remote';
  agentCardUrl: string;          // A2A 協議遠端 Agent
  auth?: A2AAuthConfig;
}
```

**Agent 載入器**（agentLoader.ts）：
- 從 Markdown 檔案 YAML frontmatter 載入 Agent 定義
- 支援 local + remote 兩種 Agent
- Zod schema 驗證 frontmatter 格式
- 檔案 hash 用於 Agent 認可機制（防止未經確認的外部 Agent）

**Agent 執行器**（LocalAgentExecutor）：
- 完整的 Agent Loop：prompt → model response → tool calls → repeat
- `complete_task` 工具作為終止信號
- 支援 `AgentTerminateMode`：GOAL / ERROR / TIMEOUT / MAX_TURNS / ABORTED
- Chat 壓縮服務（上下文接近上限時自動壓縮）
- 子 Agent 活動事件流（SubagentActivityEvent）

**Agent Registry**：
- 集中管理所有 Agent 的註冊與發現
- 支援動態重載（模型變更時自動刷新）
- Agent 認可機制（未確認的 Agent 不會自動執行）

**A2A（Agent-to-Agent）**：
- 實驗性質的 Agent 間通訊伺服器
- 支援遠端 Agent 呼叫（透過 AgentCard URL）
- HTTP 層 + 認證（API Key / Bearer Token）

### 3. Hook 系統（重點比較對象）

Gemini CLI 的 Hook 系統與本專案的 Hook 系統有顯著差異：

**事件類型**（11 種 vs 本專案 5 種）：
| Gemini CLI Hook 事件 | 對應本專案 |
|---------------------|-----------|
| `BeforeTool` | `PreToolUse:Bash/Write/Edit` |
| `AfterTool` | `PostToolUse:*` |
| `BeforeAgent` | 無（更細粒度） |
| `AfterAgent` | 無 |
| `SessionStart` | 無 |
| `SessionEnd` | `Stop` |
| `Notification` | 無 |
| `PreCompress` | 無 |
| `BeforeModel` | 無 |
| `AfterModel` | 無 |
| `BeforeToolSelection` | 無 |

**Hook 決策類型**：`ask` / `block` / `deny` / `approve` / `allow`（本專案僅 `allow` / `block`）

**配置來源分層**：Project > User > System > Extensions（四層優先級）

**Hook 翻譯器**（hookTranslator.ts）：
- 將內部 API 格式轉換為 Hook 可消費的格式
- LLM Request/Response 類型定義清晰

### 4. Skill 系統

**Skill 定義格式**（與本專案高度相似！）：
```typescript
interface SkillDefinition {
  name: string;
  description: string;
  location: string;  // SKILL.md 絕對路徑
  body: string;      // Markdown 正文
  disabled?: boolean;
  isBuiltin?: boolean;
}
```

**Skill 載入優先級**：Extensions(低) → User → Workspace(高)

**Skill 發現路徑**：
1. Built-in skills（`packages/core/src/skills/builtin/`）
2. Extension skills
3. User skills（`~/.gemini/skills/`）
4. User agent skills（`~/.agents/skills/`）
5. Project skills（`.gemini/skills/`）
6. Project agent skills（`.agents/skills/`）

**Skill 啟用機制**：
- `ActivateSkillTool` 是一個內建工具，Agent 呼叫它來啟用 Skill
- Skill 啟用後其 body 被注入到系統提示中

### 5. Policy Engine（策略引擎）

**核心設計**：
- TOML 格式的策略配置檔（vs 本專案的 YAML）
- 規則匹配支援：工具名稱、參數 pattern（正則）、Approval Mode
- 通配符支援：`serverName__*` 匹配 MCP 伺服器的所有工具
- Shell 安全分析：解析 shell 指令、檢測重導向

**Safety Checker 協議**（protocol.ts）：
```typescript
interface SafetyCheckInput {
  protocolVersion: '1.0.0';
  toolCall: FunctionCall;
  context: {
    environment: { cwd, workspaces };
    history?: { turns: ConversationTurn[] };
  };
  config?: unknown;
}
// Decision: ALLOW / DENY / ASK_USER
```
- 外部 Safety Checker 透過 stdin/stdout 通訊
- 與本專案的 Python hook 透過 JSON stdin/stdout 類似

### 6. 模型路由策略

**CompositeStrategy 鏈**（按優先級排序）：
1. `FallbackStrategy` - 錯誤後備模型
2. `OverrideStrategy` - 使用者手動指定
3. `ClassifierStrategy` - LLM 分類器選擇模型
4. `NumericalClassifierStrategy` - 數值分類
5. `DefaultStrategy` - 預設模型

**路由指標追蹤**：ModelRoutingEvent 記錄每次路由決策（模型、來源、延遲、推理原因）

### 7. 重試與容錯

**retryWithBackoff 機制**（比本專案更成熟）：
- 指數退避 + 隨機抖動（jitter）
- 可重試錯誤分類：429、5xx、網路錯誤（ECONNRESET 等）
- SSL/TLS 暫時錯誤處理
- 持續 429 時自動 fallback 到較小模型
- ValidationRequiredError 處理（需要使用者驗證）
- AbortSignal 支援（可取消）
- RetryableQuotaError vs TerminalQuotaError 區分

### 8. SDK 設計（GeminiCliAgent）

**程式化 Agent API**：
```typescript
const agent = new GeminiCliAgent({
  instructions: 'You are a helpful assistant.',
  tools: [addTool],
  skills: [skillDir('./my-skill')],
  model: 'gemini-2.5-flash',
  cwd: '/path/to/dir',
});

for await (const chunk of agent.sendStream('prompt')) {
  console.log(chunk);
}
```

**SessionContext**：
```typescript
interface SessionContext {
  sessionId: string;
  transcript: Message[];
  cwd: string;
  timestamp: string;
  fs: AgentFilesystem;   // 沙箱化的檔案系統
  shell: AgentShell;     // 沙箱化的 Shell
  agent: GeminiCliAgent;
}
```

---

## 可移植技術清單（按優先級）

### P0（高優先級，可直接移植）

1. **指數退避重試機制**
   - **來源**：`packages/core/src/utils/retry.ts`
   - **現狀**：本專案使用簡單重試（固定間隔 60s/120s）
   - **可移植性**：高。retryWithBackoff 模式可直接適配到 PowerShell 腳本
   - **效益**：減少 API 429 錯誤、提升成功率
   - **實作方式**：在 `run-*.ps1` 中實作指數退避函式，初始 5s、最大 30s、加隨機 jitter

2. **Safety Checker 協議標準化**
   - **來源**：`packages/core/src/safety/protocol.ts`
   - **現狀**：本專案 hooks 用自定義 JSON 格式
   - **可移植性**：高。SafetyCheckInput/SafetyCheckResult 的 protocolVersion 機制
   - **效益**：Hook 協議可演進而不破壞向下相容
   - **實作方式**：在 `hooks/hook_utils.py` 中加入 `protocol_version` 欄位

3. **Agent 終止模式分類**
   - **來源**：`packages/core/src/agents/types.ts` 的 `AgentTerminateMode`
   - **現狀**：本專案僅記錄成功/失敗
   - **可移植性**：高。直接對應到 scheduler-state.json 的結果欄位
   - **效益**：更精確的執行結果分析（GOAL/ERROR/TIMEOUT/MAX_TURNS/ABORTED）
   - **實作方式**：擴展 scheduler-state.json 的 result 欄位

### P1（中優先級，需適配後移植）

4. **模型路由策略鏈**
   - **來源**：`packages/core/src/routing/`
   - **現狀**：本專案無模型路由（固定 claude -p）
   - **可移植性**：中。概念可移植但需大幅適配
   - **效益**：不同任務類型可使用不同模型（如研究用 opus、一般用 sonnet）
   - **實作方式**：在 `config/routing.yaml` 中新增 model_routing 區段

5. **Hook 事件擴展（BeforeAgent/AfterAgent）**
   - **來源**：`packages/core/src/hooks/types.ts`
   - **現狀**：本專案 5 種 Hook 事件
   - **可移植性**：中。需修改 .claude/settings.json
   - **效益**：Agent 層級的攔截與監控
   - **實作方式**：等 Claude Code 原生支援更多 Hook 事件

6. **Agent 認可機制**
   - **來源**：`packages/core/src/agents/acknowledgedAgents.ts`
   - **現狀**：本專案的 Agent 不需認可
   - **可移植性**：中。概念可用於 Skill 安全驗證
   - **效益**：防止未授權的 Skill 被自動執行
   - **實作方式**：在 SKILL_INDEX.md 中新增 hash 驗證機制

7. **結構化輸出 Schema (Zod)**
   - **來源**：Agent OutputConfig 使用 Zod schema
   - **現狀**：本專案的子 Agent 輸出為自由格式 JSON
   - **可移植性**：中。Python 版本可用 Pydantic
   - **效益**：確保子 Agent 輸出格式一致
   - **實作方式**：在 `templates/sub-agent/` 中加入 JSON Schema 定義

### P2（低優先級，參考學習）

8. **React/Ink 終端機 UI**
   - **來源**：`packages/cli/` 整體
   - **現狀**：本專案無互動式 UI
   - **可移植性**：低。技術棧完全不同（Node.js vs PowerShell/Python）
   - **效益**：如果未來需要互動式管理介面
   - **學習重點**：Context 設計模式、主題系統

9. **SDK 嵌入模式**
   - **來源**：`packages/sdk/`
   - **現狀**：本專案不需要被嵌入
   - **可移植性**：低
   - **學習重點**：GeminiCliAgent 的 sendStream API 設計

10. **A2A 協議（Agent-to-Agent）**
    - **來源**：`packages/a2a-server/`
    - **現狀**：本專案使用 PowerShell Start-Job 並行
    - **可移植性**：低。實驗性質，且需 HTTP 伺服器
    - **學習重點**：Agent 間通訊的標準化方式

---

## 與 daily-digest-prompt 比較

### Claude Code vs Gemini CLI

| 面向 | daily-digest-prompt (Claude) | gemini-cli (Gemini) | 比較分析 |
|------|------------------------------|---------------------|---------|
| **執行模式** | 排程 + 非互動式（`claude -p`） | CLI 互動式 + 非互動式（`gemini -p`） | Gemini 更全面，本專案專注排程自動化 |
| **Agent 編排** | PowerShell Team 模式（Start-Job 並行） | TypeScript Agent Registry + Executor | Gemini 更結構化，本專案更輕量靈活 |
| **配置管理** | YAML + Markdown 外部化（config/ + templates/） | TOML Policy + YAML Frontmatter | 理念相似，本專案的外部化程度更高 |
| **錯誤處理** | 固定間隔重試（60s/120s） | 指數退避 + jitter + 模型降級 | **Gemini 明顯更成熟** |
| **Hook 系統** | Python 腳本（5 事件，stdin/stdout JSON） | TypeScript（11 事件，結構化協議） | Gemini 事件更豐富，本專案規則外部化更好 |
| **Skill 系統** | 20 個 SKILL.md（自定義 frontmatter） | SKILL.md（name + description frontmatter） | **格式高度一致**，可互通 |
| **安全機制** | pre_bash_guard + pre_write_guard + pre_read_guard | PolicyEngine + SafetyChecker + Shell 解析 | Gemini 更系統化，本專案規則更實用 |
| **模型路由** | 無（固定 Claude） | CompositeStrategy 策略鏈 | Gemini 更靈活 |
| **通知** | ntfy.sh | 無內建（依賴 MCP） | 本專案通知系統更完善 |
| **快取** | JSON 檔案快取 + TTL | Token 快取 | 不同層次的快取 |
| **記憶** | digest-memory.json + 連續天數 | Session checkpointing | 不同需求 |
| **去重** | 三層去重（registry + KB + policy） | 無 | **本專案獨有** |
| **測試** | 306 個 Python 測試 | 海量 Vitest 測試 | Gemini 測試覆蓋更廣 |

### 設計理念比較

| 理念 | daily-digest-prompt | gemini-cli |
|------|--------------------|-----------|
| **架構範式** | 文件驅動（Prompt 是薄層調度器） | 程式碼驅動（TypeScript 類別體系） |
| **外部化程度** | 極高（改配置不改 prompt） | 中等（Hook/Skill 外部化，核心邏輯程式碼內） |
| **並行策略** | OS 層面（PowerShell Start-Job） | 應用層面（async/await + scheduler） |
| **擴展性** | Skill + 自動任務 + Hook | Skill + MCP + Extension + Agent + Hook |
| **複雜度** | 精簡聚焦（20 Skills、6 hooks） | 企業級（1,449 TS 檔案、完整平台） |

---

## 學習要點與最佳實踐

### 1. 結構化 Agent 定義
Gemini CLI 的 `AgentDefinition` 類型系統非常清晰。每個 Agent 有明確的 `promptConfig`、`modelConfig`、`runConfig`、`toolConfig`。這比本專案的 Markdown prompt 模板更結構化，但也更僵硬。**建議**：保持本專案的彈性，但考慮在 `config/` 中加入 Agent 配置 schema。

### 2. 策略鏈設計（CompositeStrategy）
模型路由的策略鏈模式（Fallback → Override → Classifier → Default）是經典的 Chain of Responsibility 設計模式。**建議**：可應用到本專案的模板選擇邏輯（目前在 `routing.yaml` 中用三層規則模擬）。

### 3. 協議版本化
`SafetyCheckInput.protocolVersion: '1.0.0'` 確保了 Hook 協議的演進能力。**建議**：在本專案的 hook JSON 格式中加入 `protocol_version` 欄位。

### 4. Skill 格式一致性
Gemini CLI 與本專案的 SKILL.md 格式高度相似（YAML frontmatter + Markdown body）。這代表**本專案的 Skill 格式是業界標準做法**。

### 5. 重試的精密分類
Gemini CLI 區分了 `TerminalQuotaError`（不可重試）、`RetryableQuotaError`（可重試+有 retry delay）、`ValidationRequiredError`（需使用者動作），以及一般 5xx 錯誤。這比本專案的二元重試（成功/失敗）更精密。

---

## 改善建議（針對本專案）

### 高優先級

1. **升級重試機制**：從固定間隔改為指數退避 + jitter，在 `run-*.ps1` 中實作
2. **Hook 協議版本化**：在 hook JSON 中加入 `protocol_version`，確保未來可演進
3. **擴展執行結果分類**：scheduler-state.json 的 result 從 success/fail 擴展為 5 種（goal/error/timeout/max_turns/aborted）

### 中優先級

4. **模型路由**：考慮在不同任務類型使用不同模型（opus for 研究、sonnet for 一般）
5. **Agent 輸出 Schema**：在子 Agent 模板中定義結構化輸出 schema
6. **Skill hash 驗證**：在 SKILL_INDEX.md 中加入 Skill 檔案 hash，偵測未授權修改

### 低優先級

7. **更多 Hook 事件**：等 Claude Code 支援後，加入 SessionStart/SessionEnd 事件
8. **A2A 概念**：未來如果有多專案協作需求，可參考 A2A 協議設計

---

## 協同整合提案

### 直接整合（可行）

| 項目 | 方式 | 效益 |
|------|------|------|
| 指數退避函式 | 在 PowerShell 中實作 `Invoke-WithRetry` cmdlet | 減少 API 錯誤 |
| 執行結果分類 | 擴展 scheduler-state.json schema | 更精確的健康報告 |
| 協議版本化 | 在 hook_utils.py 中加入版本欄位 | 向前相容能力 |

### 適配後整合（需調整）

| 項目 | 方式 | 需求 |
|------|------|------|
| 模型路由 | config/routing.yaml 新增 model 欄位 | Claude Code CLI 支援模型指定 |
| Agent 認可 | Skill hash + SKILL_INDEX.md 驗證 | 修改 validate_config.py |

### 不適合整合

| 項目 | 原因 |
|------|------|
| React/Ink UI | 技術棧完全不同 |
| SDK 嵌入模式 | 本專案不需要被外部嵌入 |
| A2A 伺服器 | 過度工程化，PowerShell Start-Job 已足夠 |
| MCP 伺服器管理 | Claude Code 自帶 MCP 支援 |
| TypeScript 工具系統 | 本專案用 Python hooks + Claude Code 原生工具 |

---

## 總結

gemini-cli 是一個企業級的 AI CLI 工具，架構成熟度遠高於本專案。然而，本專案的**文件驅動架構**和**外部化配置策略**在某些方面反而更靈活。兩者的 Skill 系統格式高度一致，證明本專案的設計方向正確。

**最值得學習的三個技術**：
1. 指數退避重試（立即可用）
2. 協議版本化（簡單且重要）
3. 執行結果精細分類（提升可觀測性）

**本專案的獨有優勢**：
1. 研究去重機制（三層防重複）
2. 自動任務輪轉（18 任務 round-robin）
3. 通知系統（ntfy 即時推播）
4. 文件驅動架構（改配置不改 prompt）
5. 跨次記憶持久化（連續天數、習慣追蹤）
