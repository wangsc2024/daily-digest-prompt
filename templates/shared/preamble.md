# 共用前言（所有 Agent prompt 引用此文件）

## 語言
全程使用正體中文。

## Skill-First 核心規則
1. **先讀索引**：執行前必須先讀取 `skills/SKILL_INDEX.md`，建立完整的 Skill 認知地圖
2. **先讀 SKILL.md 再動手**：每個步驟都必須先讀取對應的 SKILL.md，嚴格依指示操作
3. **能用 Skill 就用 Skill**：禁止自行拼湊 API 呼叫或邏輯
4. **Skill 鏈式組合**：積極串聯多個 Skill（如：todoist → knowledge-query → ntfy-notify）
5. **所有外部 API 必經 api-cache**：任何 curl 呼叫前，必須先走快取流程

## 禁止行為
- 不讀 SKILL.md 就直接呼叫 API
- 自行拼 curl 指令而不參考 SKILL.md 中的正確格式
- 跳過 api-cache 直接呼叫外部服務
- 執行結束不更新記憶和狀態

## Context 保護：重量操作委派子 Agent

當任務需要**讀取 5 個以上檔案**或**執行耗時搜尋**時，必須用 Agent 工具委派子 Agent，主 Agent 只接收摘要 JSON：

| 操作類型 | 委派方式 |
|---------|---------|
| 讀取多個 SKILL.md / log 檔案 | `subagent_type=Explore`，指定搜尋範圍 |
| 複雜分析（log 審查、狀態比對） | `subagent_type=general-purpose`，傳回結構化結果 |
| 研究 / WebFetch 多篇 | `subagent_type=general-purpose`，傳回摘要 |

> **禁止**：主 Agent 直接累積大量檔案內容後再分析（OOM 風險）。
> **正確**：子 Agent 分析後傳回 ≤ 200 行 JSON 摘要，主 Agent 根據摘要決策。

## 重要禁令：禁止產生 nul 檔案
- 絕對禁止在 Bash 指令中使用 `> nul`、`2>nul`、`> NUL`，這會在 Windows 上產生名為 nul 的實體檔案
- 絕對禁止用 Write 工具建立名為 nul 的檔案
- 需要抑制輸出時改用 `> /dev/null 2>&1`
- 刪除暫存檔時直接用 `rm filename`，不要重導向到 nul
