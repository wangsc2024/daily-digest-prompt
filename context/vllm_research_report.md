# vLLM — 開源 LLM 推理與 Serving 引擎深度研究：PagedAttention、V1 執行迴圈重構、OpenAI 相容介面與生產部署權衡（73.4K Stars, 2026-03）

研究日期：2026-03-18  
研究類型：ai_github_research  
系列階段：foundation  
本次研究專案：vLLM（73.4k stars）— 以 PagedAttention 與高吞吐排程為核心的開源 LLM 推理與服務引擎

## 專案概述

vLLM 是由 UC Berkeley Sky Computing Lab 起步、後續演化為社群驅動的開源 LLM inference/serving 引擎，目標很明確：讓大型模型推理「更快、更省記憶體、也更容易部署」。它解決的核心問題不是訓練，而是模型上線後最昂貴的那一段，也就是 KV cache 管理、批次排程、跨請求快取重用，以及把 Hugging Face 模型穩定變成可被應用程式呼叫的 API 服務。

從 GitHub 倉庫來看，vLLM 在 2026-03-18 已有約 73.4k stars、14.4k forks、約 1.7k issues、2k pull requests、2,331 位 contributors，最新 release 為 2026-03-11 的 `v0.17.1`。這個量級說明它不是單一研究原型，而是已被大量團隊拿來做實際 serving 的基礎設施。

## 技術架構

### 1. 核心設計：PagedAttention + 動態 KV Cache 管理

vLLM 最核心的技術資產是 2023 年 SOSP 論文提出的 PagedAttention。它把 KV cache 的配置方式借鑑作業系統分頁觀念，改成固定 block、可非連續配置，而不是要求每個 request 的 KV cache 在 GPU 記憶體中連成一大塊。這個設計直接降低碎片化與預留浪費，讓系統可以在相同 GPU 記憶體下容納更多同時請求。

論文結果顯示，vLLM 相對當時主流系統如 FasterTransformer、Orca，可在相近延遲下取得約 2 到 4 倍吞吐提升。這不是靠單一 CUDA kernel 小優化，而是把「記憶體管理」視為 LLM serving 的第一級瓶頸去重寫。

### 2. 執行層：Continuous Batching 與 Scheduler

GitHub README 顯示 vLLM 把 continuous batching、speculative decoding、chunked prefill、prefix caching 視為一級功能。這代表它不是單純包一個模型 forward，而是把不同 request 的 prompt 與 decode 流程放進同一個調度框架中，持續吃進新請求而不是等整批結束。

V1 架構文章更關鍵。官方在 2025-01-27 說明，V1 移除了舊版對 prefill / decode 的硬切分，改用更統一的 token scheduling 表示法，讓 scheduler 只需要決定每一步各 request 要處理多少 token。這讓 chunked prefill、prefix caching、speculative decoding 能共存於同一個調度模型，而不是各自補丁式地插進系統。

### 3. V1 重構重點

官方部落格列出的 V1 重點不只是「更快」，而是架構層面更乾淨：

- Optimized execution loop 與 API server，目標是減少 CPU overhead。
- Zero-overhead prefix caching：官方表示 V1 在 cache hit rate 為 0% 時吞吐損失可壓到 1% 以下，因此預設啟用 prefix caching。
- Clean architecture for tensor-parallel inference：scheduler 與 worker 拆開，靠傳遞增量狀態而不是厚重 IPC，讓單卡與多卡路徑更一致。
- 更好的 multimodal support，代表 vLLM 已從純文字 serving 引擎逐步延伸到音訊、視覺與 embedding / rerank 等 API。

官方數據指出，V1 相比 V0 可達到最高約 1.7x 吞吐提升。這說明 vLLM 的第二曲線不是新功能疊加，而是把 serving runtime 本身往「低 CPU 開銷、高排程效率」方向重構。

### 4. 介面層：OpenAI 相容 API 作為採用加速器

官方文件顯示，vLLM 提供 `vllm serve` CLI，可直接起一個 OpenAI-compatible HTTP server，並可用官方 OpenAI Python client 連接 `http://localhost:8000/v1`。除了 Chat / Completions，最新文件也涵蓋 Responses、Embeddings、Transcriptions、Translations、Rerank、Pooling 等端點。

這個設計的戰略價值很大：它把「模型 serving 引擎」包裝成團隊既有應用最容易接入的 API 形狀。若你的上層系統已經寫成 OpenAI SDK 客戶端，遷移到 vLLM 的心智與工程成本會低很多。

## 功能特色與差異化

相較同類推理引擎，vLLM 的差異化不在模型訓練，而在 serving runtime 的完整度：

1. 記憶體導向設計很強。PagedAttention 讓它在長上下文與高併發下仍能維持較佳 batch 容量。
2. 生態廣。README 顯示它支援 NVIDIA、AMD、Intel、Arm、TPU，還延伸到 Gaudi、Spyre、Ascend 等硬體插件。
3. 部署介面成熟。OpenAI 相容 API、Docker、Ray Serve LLM、KServe、BentoML 等整合，使它很適合放進既有 MLOps 流程。
4. 模型範圍大。除 decoder-only LLM，也涵蓋 MoE、embedding、multimodal。
5. 社群規模大。GitHub contributors 與使用者數量明顯高於多數新興引擎，對企業採用是重要訊號。

若和 SGLang 對比，vLLM 的優勢較偏向「更成熟、更保守、更廣泛整合」，而不是每個 benchmark 都是第一。近一年第三方比較常顯示 SGLang 在某些高併發場景吞吐更高，但 vLLM 在生態、文件與部署穩定性上更像預設選項。

## 使用方式

### 快速上手

```bash
pip install vllm
vllm serve NousResearch/Meta-Llama-3-8B-Instruct \
  --dtype auto \
  --api-key token-abc123
```

### 使用 OpenAI Python client 呼叫

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="token-abc123",
)

resp = client.chat.completions.create(
    model="NousResearch/Meta-Llama-3-8B-Instruct",
    messages=[{"role": "user", "content": "請用繁體中文摘要今日重點"}],
)

print(resp.choices[0].message.content)
```

### 在 daily-digest-prompt 的應用想法

如果未來要把本專案某些任務改為本地或自管模型，vLLM 很適合做底層推理閘道：

- 把摘要、翻譯、分類、重寫等低風險任務切到自架模型，降低外部 API 成本。
- 透過 OpenAI 相容介面，保留現有上層 client 形狀，減少替換成本。
- 若搭配 Qdrant / RAG，可把檢索後生成改為本地 serving，形成「本地 KB + 本地推理」路徑。

### 在 game 或互動應用的應用想法

- 遊戲中的 NPC 對話、任務說明生成、事件旁白，都可透過 vLLM 提供本地 API。
- 若是單機或 LAN 遊戲，vLLM 比直接嵌模型進遊戲程序更合理，因為模型生命週期與遊戲主迴圈可以分離。
- 高併發多人遊戲後端若需要大量文字回應，continuous batching 與 prefix caching 的價值會高於單純「能跑模型」。

## 社群活躍度

- GitHub Stars：約 73.4k
- Forks：約 14.4k
- Issues：約 1.7k
- Pull Requests：約 2k
- Contributors：約 2,331
- Used by：約 7.7k
- 最新 release：`v0.17.1`（2026-03-11）

從這些數字看，vLLM 已具備明顯平台級特徵。大量 issue / PR 一方面代表複雜度高，另一方面也代表使用面廣、硬體與模型支援持續擴張。對研究任務來說，這類專案比「新星但小社群」更值得建立基礎筆記，因為它較可能長期成為推理層標準件。

## 優缺點評估

### 優點

1. 核心問題打得很準：直接處理 LLM serving 最大成本之一的 KV cache 與排程。
2. 採用門檻低：OpenAI 相容 API 讓應用整合非常順手。
3. 硬體與模型覆蓋廣：對混合基礎設施團隊特別有利。
4. 社群與文件成熟：遇到問題時，通常能在官方文件、issue、論壇或社群中找到解法。
5. 可從單卡一路長到多卡、多節點：適合先驗證、再放量。

### 缺點

1. 系統複雜度高。你得到高效能，也必須接受更多 deployment / scheduler / parallelism 參數需要理解。
2. 並非所有 benchmark 都是第一。若 workload 極度偏向 prefix-heavy 或某些高併發場景，SGLang 可能更快。
3. 生產安全預設不夠。官方安全文件特別提醒，`torch.distributed` 相關 `TCPStore` 可能暴露在所有網卡；而 `--api-key` 只保護 `/v1` 路徑，不能當完整安全方案。
4. API 相容不等於行為完全一致。文件也指出部分模型需要自己補 chat template，否則 chat request 會直接失敗。

## 結論

如果你的需求是「把開源模型穩定、快速地變成服務」，vLLM 目前仍是最值得優先理解的開源推理引擎之一。它的真正護城河不是單一功能，而是把記憶體管理、排程、相容 API、生態整合與硬體覆蓋做成了一個可落地的 serving runtime。

對 daily-digest-prompt 而言，vLLM 最值得借鏡的不是直接把所有任務搬到本地模型，而是學它的系統觀：把推理視為獨立基礎設施層，讓上層工作流、RAG、Agent orchestration 與模型 runtime 解耦。這會比在每個 task script 裡直接綁定某家模型 API，更有長期可維護性。

## 參考來源

1. GitHub Repo: https://github.com/vllm-project/vllm
2. vLLM 官方文件（OpenAI-Compatible Server）: https://docs.vllm.ai/en/latest/serving/openai_compatible_server/
3. vLLM 官方部落格：V1 Alpha Release: https://vllm.ai/blog/v1-alpha-release
4. vLLM 官方安全文件: https://docs.vllm.ai/en/stable/usage/security/
5. SOSP 2023 論文：Efficient Memory Management for Large Language Model Serving with PagedAttention
6. vLLM vs TensorRT-LLM Production Guide: https://antoniobrundo.org/knowledge/vllm-vs-tensorrt-llm.html
7. vLLM vs SGLang Comparison: https://tim-wang-tecg-blog.pages.dev/llm/llm-benchmark-en/
