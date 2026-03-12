# AI Agent CLI 的六角架構（Ports & Adapters）實作模式

研究日期：2026-03-10  
研究類型：技術研究

今日任務涉及技術：[RAG 知識庫、Vite 靜態同步、OpenClaw 六角架構、測試與品質閘門、Mechanistic Interpretability、論證映射、GitHub 專案研究、Skill 驅動工作流]

本次研究主題：AI Agent CLI 的六角架構（Ports & Adapters）實作模式（因知識庫尚無此主題的深入研究）

## 技術概述

六角架構（Hexagonal Architecture／Ports & Adapters）由 Alistair Cockburn 提出，核心思想是把應用程式的「決策核心」與 UI、資料庫、外部 API、排程器、CLI 等基礎設施解耦。到了 2026 年，這個模式在 AI Agent 與 CLI 型產品上特別有價值：模型供應商、通訊渠道、工具執行器、工作區檔案系統、WebSocket 控制面都高度可替換，若沒有明確的 ports 邊界，專案很快會演化成難測、難換模型、難加新通道的巨石。OpenClaw 的 Gateway/CLI/Skills/Nodes 設計，正是六角架構在 Agent 系統中的具體實踐。

## 研究前知識策略分析

### KB 現況
- 知識庫已有 OpenClaw 專案級洞察筆記，也提到六角架構，但偏向「專案觀察」與功能盤點。
- 目前缺的是一篇**抽象到可遷移的方法論筆記**：如何把六角架構真正落地到 AI Agent CLI 專案，而不只是理解某個熱門專案。
- 因此本次研究角度鎖定為：**把 OpenClaw 的實作拆解成可套用到 daily-digest-prompt 類專案的結構模式**。

### 知識缺口
- 尚缺少針對「primary / secondary adapters 在 Agent 專案的對映」的系統整理。
- 尚缺少「如何把 Skills、Webhooks、排程、知識庫、通知等能力收斂到 ports」的具體設計規則。
- 尚缺少「在 Windows/CLI/多工具環境下，如何避免 domain 被 shell、HTTP、prompt 細節污染」的實務指南。

## 核心概念與原理

### 1. 核心不是模型，而是用例協調
Cockburn 原始論文強調：應用核心應能在沒有 UI、沒有資料庫的情況下獨立執行與測試。對 AI Agent 專案來說，真正的核心通常不是某個 LLM SDK，而是：
- 任務分解與路由
- 狀態轉移與回合控制
- 工具使用政策
- 記憶讀寫規則
- 成功／失敗／降級決策

也就是說，**模型供應商只是 adapter，不該是核心**。

### 2. Port 是「能力契約」，不是技術封裝
在一般 Web 專案裡，port 常被理解成 repository interface；但在 Agent 系統中，port 應更廣：
- `ModelPort`：產生回應、工具呼叫、結構化輸出
- `MemoryPort`：查詢／寫入長短期記憶
- `TaskPort`：讀取任務、標記完成、追加備註
- `KnowledgeBasePort`：混合檢索、筆記匯入、去重查詢
- `NotificationPort`：推播、摘要通知、失敗告警
- `ExecutionPort`：命令執行、檔案讀寫、沙箱策略

Port 應描述「我要什麼能力」，而不是「我要呼叫哪個 SDK」。

### 3. Adapter 負責翻譯與防腐層
Adapter 的責任是把外界協定轉成內部可理解的命令／查詢。
- Todoist API、KB HTTP API、ntfy、PowerShell、GitHub、Web Search 都是 adapter。
- Prompt 格式、JSON payload、exit code、HTTP status、shell quoting 都應止步於 adapter。
- 這層同時也是防腐層（anti-corruption layer）：避免第三方 API 命名與資料格式直接滲透到核心。

### 4. AI Agent 的 primary / secondary adapters 對映
參考 AWS 對 primary 與 secondary adapters 的定義，可把 Agent CLI 專案對映為：
- **Primary adapters（驅動核心）**：CLI 命令、排程器、Webhook、聊天訊息、批次任務、測試夾具
- **Secondary adapters（被核心呼叫）**：LLM provider、向量檢索、SQLite/JSON 檔案、Git、通知服務、瀏覽器控制、系統命令

這個分類很重要，因為它直接決定測試策略與資料流方向。

### 5. OpenClaw 的 2026 演進，證明六角架構適合 Agent 系統
從 OpenClaw 官方文件與 GitHub README 可觀察到幾個值得注意的 2026 特徵：
- 單一 Gateway 作為控制面，統一路由 WebSocket、Web UI、CLI、行動節點與自動化入口。
- WebSocket 協定型別化，並用 JSON Schema 驗證訊框，降低多 client / node 協作複雜度。
- 技能系統明確分層：bundled、managed/local、workspace，並有 precedence 與 gating 規則。
- pairing、sandbox、token、device approval 等安全控制被放在架構層，而非補丁式追加。
- GitHub 頁面顯示該專案於 2026-03-09 釋出 `openclaw 2026.3.8`，且已達 296k stars、1,149 位貢獻者，代表這類架構已在大規模社群壓力下持續演化。

我根據官方文件推論：OpenClaw 的成功不只是功能多，而是它把「控制面、能力擴展、安全邊界」都做成可替換的 ports/adapters 關係，因此可以在不重寫核心的前提下快速擴張渠道、裝置與技能。

## 最佳實踐

### 1. 先定義用例 Port，再接外部服務
先寫 `KnowledgeBasePort.search()`、`TaskPort.complete()`、`NotifierPort.publish()` 這類介面，再決定背後是 HTTP、檔案還是 shell。這能避免核心被 API 細節綁死。

### 2. 讓測試成為第一個 primary adapter
AWS 文件建議從一開始就用 TDD 與 mock objects；對 Agent 專案更應如此。先用假的 `ModelPort`、`KBPort`、`NotificationPort` 驗證流程，再接真服務，可大幅降低 prompt/debug 成本。

### 3. 把策略與 I/O 分離
像去重規則、冷卻天數、品質閘門、fallback 條件，屬於 domain policy；HTTP 重試、curl 參數、PowerShell quoting、JSON 序列化則屬於 adapter。兩者混在一起時，維護成本會迅速爆炸。

### 4. 為每種外部能力建立明確錯誤語意
不要把所有失敗都丟成字串。應區分：
- 可重試失敗（timeout、429、暫時無法連線）
- 不可重試失敗（認證錯誤、schema 錯誤）
- 降級可接受（KB 離線但仍可完成研究）
- 安全阻擋（未配對裝置、未允許的命令、缺少 sandbox 條件）

### 5. Skills 也應視為 adapter，不是核心規則本身
Skill 是「如何呼叫能力」的知識封裝；核心仍應保有任務狀態機與決策規則。否則技能格式一改，整個系統會跟著斷裂。

### 6. 控制面與執行面分離
OpenClaw 的 Gateway/Node 拆分很有啟發：控制決策與設備側能力不應耦合。對 daily-digest-prompt 而言，也可將「任務協調」與「實際執行 shell / HTTP / KB 匯入」分為不同層。

## 常見陷阱

- **把 LLM SDK 寫進 domain**：之後換模型供應商、加結構化輸出、加 fallback 都會痛苦。
- **把 prompt 當 domain model**：prompt 應該是 adapter 資產，不是業務真相來源。
- **port 設計過細或過粗**：過細會造成介面爆炸；過粗則退化成 `AgentService.doEverything()`。
- **把 shell 命令視為核心流程**：shell 只是執行器 adapter；決策規則不能藏在命令字串裡。
- **沒有安全邊界**：skills、webhooks、device pairing、sandbox 若不是一級架構概念，後期幾乎一定出事。
- **只測 end-to-end**：Agent 系統若只靠整合測試，定位問題會非常慢；應增加 domain 級單元測試與 adapter 契約測試。

## 與本專案的關聯

`daily-digest-prompt` 很適合沿六角架構再整理一次：
- 將 `Todoist`、`知識庫`、`ntfy`、`WebSearch`、`Git` 視為 secondary adapters。
- 將 `自動任務模板`、`CLI 執行`、`排程器`、`品質檢查` 視為 primary adapters。
- 將「研究去重、選題、KB 可用時匯入、KB 離線時降級、DONE_CERT 生成」收斂為 domain workflow。
- 讓模板只描述流程與政策，實際 I/O 細節由 skill 或 adapter 負責。

### 具體可落地重構方向
1. 建立 `ports/`：定義 `KnowledgeBasePort`、`TodoistPort`、`NotificationPort`、`WebResearchPort`。
2. 建立 `adapters/`：封裝 localhost KB API、Todoist API、ntfy、web search、檔案系統。
3. 建立 `domain/`：放研究選題器、去重規則、品質評分、降級策略。
4. 建立 `entrypoints/`：對應 auto-task、手動 CLI、排程器觸發。
5. 補上契約測試：確認每個 adapter 對錯誤碼、逾時、空結果的行為一致。

## 程式碼範例

```ts
interface KnowledgeBasePort {
  healthCheck(): Promise<boolean>;
  hybridSearch(query: string, topK: number): Promise<SearchHit[]>;
  importMarkdown(note: {
    title: string;
    contentText: string;
    tags: string[];
    source: 'import';
  }): Promise<{ imported: number; noteIds: string[] }>;
}

interface ResearchWorkflowPort {
  getTodayCompletedTasks(): Promise<CompletedTask[]>;
  saveResult(result: ResearchResult): Promise<void>;
}

class TechResearchService {
  constructor(
    private readonly kb: KnowledgeBasePort,
    private readonly workflow: ResearchWorkflowPort,
  ) {}

  async run(topic: string, markdown: string) {
    const kbAvailable = await this.kb.healthCheck();
    if (kbAvailable) {
      const hits = await this.kb.hybridSearch(topic, 10);
      const duplicated = hits.some(hit => hit.score >= 0.85);
      if (!duplicated) {
        await this.kb.importMarkdown({
          title: `${topic} 實作指南`,
          contentText: markdown,
          tags: ['技術研究', topic, 'daily-digest'],
          source: 'import',
        });
      }
    }

    await this.workflow.saveResult({ topic, kbImported: kbAvailable });
  }
}
```

這段重點不在語法，而在依賴方向：`TechResearchService` 不知道 HTTP、curl、JSON 檔案或 PowerShell；它只依賴 ports。

## 結論

若把 AI Agent CLI 視為「很多工具拼起來的腳本集合」，系統會越做越難測；若把它視為「以用例為中心、以 ports 為邊界、以 adapters 接世界的可演化應用」，就能同時得到擴充性、測試性與安全性。OpenClaw 在 2026 年的控制面、型別化通訊、技能分層與配對安全機制，證明六角架構不只是企業後端老模式，而是新一代 Agent 系統的實戰骨架。

## 參考來源

1. Alistair Cockburn, Hexagonal Architecture 原始文章：<https://alistair.cockburn.us/hexagonal-architecture>
2. AWS Prescriptive Guidance, Hexagonal architecture pattern：<https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/hexagonal-architecture.html>
3. AWS Prescriptive Guidance, Best practices：<https://docs.aws.amazon.com/prescriptive-guidance/latest/hexagonal-architectures/best-practices.html>
4. OpenClaw Docs, Gateway Architecture（2026-01-22）：<https://docs.openclaw.ai/concepts/architecture>
5. OpenClaw Docs, Skills：<https://docs.openclaw.ai/tools/skills>
6. OpenClaw Docs, Pairing：<https://docs.openclaw.ai/channels/pairing>
7. OpenClaw GitHub README / releases：<https://github.com/openclaw/openclaw>
