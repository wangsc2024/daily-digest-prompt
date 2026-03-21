# gpt-oss-20b + LlamaIndex + vLLM 完整執行方案（RTX 4090 / WSL2）

> 目標：在 **RTX 4090 24GB** 環境，用 **gpt-oss-20b** 建立一個可本地部署、可透過 **vLLM OpenAI-compatible server** 提供 API、並由 **LlamaIndex agent** 執行 **function calling / tool calling** 的完整方案。

---

## 1. 方案定位

這套方案適合以下需求：

- 本地或私有部署，不依賴外部雲端推理 API
- 需要 **function calling / tool calling**
- 要接 **LlamaIndex Agent / RAG / QueryEngineTool**
- 以 **繁體中文** 為主要輸出語言
- 使用 **RTX 4090** 做開發、測試與中小型負載

### 為什麼選這條路

`gpt-oss-20b` 是 OpenAI 發布的 open-weight 模型之一，官方定位包含 **tool use、structured outputs、可部署在自有基礎設施** 等能力；vLLM 提供 **OpenAI-compatible server**；LlamaIndex 則可透過 **OpenAI-like wrapper** 或自訂 LLM 對接第三方 OpenAI-compatible API。[1][2][3][4]

---

## 2. 架構總覽

```text
[使用者 / 前端]
      |
      v
[你的 Python App / FastAPI / CLI]
      |
      v
[LlamaIndex Agent]
  |        |         \
  |        |          \__ FunctionTool（天氣、查表、內部 API）
  |        |
  |        \__ QueryEngineTool（RAG / 本地知識庫）
  |
  v
[OpenAILike LLM Wrapper]
  |
  v
[vLLM OpenAI-compatible Server]
  |
  v
[gpt-oss-20b]
```

### 核心原則

1. **先驗證 serving，再接 agent**  
   不要一開始就把所有功能疊上去。
2. **先單工具、單參數，再擴增 schema**  
   工具呼叫穩定後再加複雜工具。
3. **先 4K / 8K context，再逐步放大**  
   4090 可開發，但不要一開始就追求 128K。
4. **模型做決策，應用程式做驗證**  
   tool arguments、JSON、schema 都要在應用端驗證。

---

## 3. 硬體與系統前提

## 建議環境

- GPU：NVIDIA RTX 4090 24GB
- OS：Windows 11 + WSL2 Ubuntu 22.04 或原生 Linux
- Python：3.10 或 3.11
- CUDA：以你安裝的 PyTorch / vLLM 相容版本為準
- 磁碟：至少保留 80GB 以上可用空間
- RAM：建議 32GB 以上

## 實務判斷

OpenAI 公開資訊指出 `gpt-oss-20b` 可在低資源裝置運行，而 `gpt-oss-120b` 偏向單張 80GB GPU 級別；因此 **4090 適合先做 `gpt-oss-20b` 開發與測試**，但高併發 production 仍需另外容量規劃。[1]

---

## 4. 專案目錄建議

```text
gptoss_llamaindex_agent/
├─ app/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ tools.py
│  ├─ rag.py
│  ├─ agent.py
│  └─ main.py
├─ data/
│  └─ sample_docs/
├─ scripts/
│  ├─ start_vllm.sh
│  ├─ test_openai_client.py
│  └─ test_tool_call.py
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

## 5. 安裝步驟

## 5.1 建立虛擬環境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

## 5.2 安裝套件

`requirements.txt` 建議先從這份開始：

```txt
vllm
openai
llama-index
llama-index-llms-openai-like
fastapi
uvicorn
pydantic
python-dotenv
```

安裝：

```bash
pip install -r requirements.txt
```

### 套件說明

- `vllm`：提供推理引擎與 OpenAI-compatible server。[2]
- `openai`：先直接用官方 client 驗證 server 是否正常。
- `llama-index`：agent、RAG、tool orchestration。
- `llama-index-llms-openai-like`：對接 OpenAI-compatible API 的 wrapper。[3][4]

> 注意：LlamaIndex 近年整合套件拆分較快，import path 可能隨版本微調；請以你實際安裝版本的官方文件為準。[3][4]

---

## 6. 模型準備

請先取得 `gpt-oss-20b` 權重，並記錄其本地路徑或模型 ID。

示例：

```bash
# 依你的實際來源下載，以下僅示意
# huggingface-cli download <model-id> --local-dir ./models/gpt-oss-20b
```

> 這份方案不把模型 ID 寫死，避免與你實際下載來源不一致。

---

## 7. 啟動 vLLM Server

建立 `scripts/start_vllm.sh`：

```bash
#!/usr/bin/env bash
set -e

MODEL_PATH="/path/to/gpt-oss-20b"
API_KEY="dummy-key"

vllm serve "$MODEL_PATH" \
  --dtype auto \
  --api-key "$API_KEY" \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192
```

加上執行權限：

```bash
chmod +x scripts/start_vllm.sh
```

啟動：

```bash
./scripts/start_vllm.sh
```

### 4090 的保守建議

- `--max-model-len 4096` 或 `8192` 起步
- `--gpu-memory-utilization 0.85 ~ 0.90`
- 先不要追求超長 context
- 先把 tool calling 跑穩，再調高 context

vLLM 官方文件明確說明可透過 `vllm serve` 提供 OpenAI-compatible server，並可使用 OpenAI Python client 呼叫。[2]

---

## 8. 第一步驗證：純 Chat Completion

建立 `scripts/test_openai_client.py`：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="dummy-key",
)

resp = client.chat.completions.create(
    model="gpt-oss-20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "請用一句繁體中文介紹你自己。"},
    ],
    temperature=0.2,
)

print(resp.choices[0].message)
```

執行：

```bash
python scripts/test_openai_client.py
```

### 驗收標準

- server 可連通
- 模型可正常生成
- 無 timeout / schema error / model not found

若這一步失敗，先不要接 LlamaIndex。

---

## 9. 第二步驗證：原生 Tool Calling

建立 `scripts/test_tool_call.py`：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="dummy-key",
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查詢指定城市天氣",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名稱"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

resp = client.chat.completions.create(
    model="gpt-oss-20b",
    messages=[
        {"role": "system", "content": "你是工具代理，遇到查詢任務時優先使用工具。"},
        {"role": "user", "content": "請查高雄天氣"},
    ],
    tools=tools,
    tool_choice="auto",
    temperature=0.1,
)

msg = resp.choices[0].message
print(msg)

if getattr(msg, "tool_calls", None):
    for tc in msg.tool_calls:
        print("tool:", tc.function.name)
        print("args:", tc.function.arguments)
else:
    print("No tool call returned.")
```

執行：

```bash
python scripts/test_tool_call.py
```

### 驗收標準

- 有 `tool_calls`
- `function.name == get_weather`
- arguments 是可解析 JSON

若這一步成功，代表：

- 模型
- vLLM server
- OpenAI-compatible tool schema

這三層已大致對齊。

---

## 10. LlamaIndex 接入方案

## 10.1 app/config.py

```python
from pydantic import BaseModel


class Settings(BaseModel):
    llm_model: str = "gpt-oss-20b"
    api_base: str = "http://127.0.0.1:8000/v1"
    api_key: str = "dummy-key"
    temperature: float = 0.1


settings = Settings()
```

## 10.2 app/tools.py

```python
def get_weather(city: str) -> str:
    fake_weather = {
        "高雄": "多雲，27 度，降雨機率 20%",
        "台北": "陰天，22 度，降雨機率 50%",
        "屏東": "晴時多雲，29 度，降雨機率 10%",
    }
    return fake_weather.get(city, f"{city} 天氣資料暫時不可用")
```

## 10.3 app/rag.py

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core.tools import QueryEngineTool, ToolMetadata


def build_kb_tool(data_dir: str = "./data/sample_docs"):
    docs = SimpleDirectoryReader(data_dir).load_data()
    index = VectorStoreIndex.from_documents(docs)
    query_engine = index.as_query_engine()

    return QueryEngineTool(
        query_engine=query_engine,
        metadata=ToolMetadata(
            name="kb_search",
            description="查詢本地知識庫文件，適合回答流程、說明文件與內部知識問題",
        ),
    )
```

## 10.4 app/agent.py

```python
from llama_index.core.agent import FunctionCallingAgentWorker
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai_like import OpenAILike

from app.config import settings
from app.tools import get_weather
from app.rag import build_kb_tool


def build_agent():
    weather_tool = FunctionTool.from_defaults(fn=get_weather)
    kb_tool = build_kb_tool()

    llm = OpenAILike(
        model=settings.llm_model,
        api_base=settings.api_base,
        api_key=settings.api_key,
        is_chat_model=True,
        is_function_calling_model=True,
        temperature=settings.temperature,
        system_prompt=(
            "你是企業知識代理。"
            "若問題需要查詢、計算或檢索文件，優先使用工具。"
            "不要編造工具結果。"
            "所有輸出使用繁體中文。"
        ),
    )

    agent = FunctionCallingAgentWorker.from_tools(
        tools=[weather_tool, kb_tool],
        llm=llm,
        verbose=True,
    ).as_agent()

    return agent
```

## 10.5 app/main.py

```python
from app.agent import build_agent


def main():
    agent = build_agent()

    question = "先查高雄天氣，再告訴我知識庫裡有沒有客服流程。"
    response = agent.chat(question)
    print(response)


if __name__ == "__main__":
    main()
```

執行：

```bash
python -m app.main
```

### 為什麼這樣接

LlamaIndex 官方文件說明：

- function calling agent 需要底層 LLM API 支援 tools / functions。[5]
- `OpenAILike` 是針對第三方 OpenAI-compatible API 的薄封裝。[3][4]
- 如需更細控制，也可改成自訂 `LLM` / `CustomLLM`。[6]

---

## 11. FastAPI 化（可選）

若你想把 agent 包成 API，建立 `app/api.py`：

```python
from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import build_agent

app = FastAPI(title="gpt-oss-20b LlamaIndex Agent")
agent = build_agent()


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def chat(req: ChatRequest):
    resp = agent.chat(req.message)
    return {"answer": str(resp)}
```

啟動：

```bash
uvicorn app.api:app --host 0.0.0.0 --port 9000 --reload
```

測試：

```bash
curl -X POST http://127.0.0.1:9000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"請查屏東天氣"}'
```

---

## 12. Prompt 與 Tool 設計準則

## System Prompt 建議

```text
你是企業知識代理。
規則：
1. 若需要文件、查詢或函式結果，優先使用工具。
2. 不要猜測工具參數；若上下文足夠，直接產生合理參數。
3. 工具回傳後，必須根據工具結果作答。
4. 若工具失敗，清楚說明失敗原因，不要編造結果。
5. 回答一律使用繁體中文。
```

## Tool Schema 設計原則

- 一個工具只做一件事
- 先用 `string`、`integer` 等簡單參數
- `description` 寫清楚觸發條件
- 先避免太深的巢狀 JSON
- 參數越簡單，tool call 成功率通常越高

---

## 13. 你最需要的應用層保護

模型即使支援 tool use，應用程式仍要負責：

1. **JSON 驗證**
2. **參數型別檢查**
3. **錯誤重試**
4. **工具超時處理**
5. **fallback 邏輯**

### 建議做法

- `temperature=0` 或 `0.1`
- 工具參數用 `pydantic` 驗證
- parse 失敗時 retry 1~2 次
- tool 執行失敗時，把錯誤訊息作為 tool result 回填
- 不要讓模型直接接觸高風險系統操作

---

## 14. 常見踩坑點與排除

## 問題 1：模型不出 tool call，只直接回答

### 可能原因
- system prompt 太弱
- tool description 太模糊
- schema 太複雜
- server 未完整支援 `tools`

### 處理方式
- 先只保留 1 個工具
- 只保留 1 個 string 參數
- 降低 temperature
- 在 system prompt 加上「遇到查詢任務優先使用工具」

---

## 問題 2：tool call 出來了，但 arguments 不是乾淨 JSON

### 處理方式
- 將 schema 簡化
- 改用 `temperature=0`
- 增加 JSON repair
- 在應用層重試
- 必要時退回 ReAct + JSON action 模式

---

## 問題 3：LlamaIndex import path 不一致

### 原因
LlamaIndex 近年整合包拆分頻繁，不同版本匯入路徑可能略有不同。[3][4][6]

### 處理方式
- 先用 `pip show llama-index llama-index-llms-openai-like`
- 以安裝版本的官方文件為準
- 若 `OpenAILike` 匯入失敗，改查對應版本 API reference

---

## 問題 4：4090 爆顯存

### 處理方式
- 降低 `--max-model-len`
- 降低併發
- 減少 history 長度
- 降低 batch
- 必要時改量化版本或縮小 context

---

## 15. 生產化建議

若你要進一步投入 production，建議補上：

- FastAPI / Nginx
- logging
- metrics
- prompt / tool audit log
- cache
- retry policy
- API auth
- queue / background worker
- 向量資料庫（FAISS / Qdrant / Milvus 等）
- 文件切塊與索引更新流程

### 建議演進順序

1. 單工具 function calling
2. 多工具 function calling
3. RAG 工具接入
4. FastAPI 封裝
5. 使用者 session / memory
6. 權限控管
7. 監控與容量規劃

---

## 16. 最小驗收清單

你可以用以下 checklist 驗證方案是否完成：

- [ ] vLLM server 可啟動
- [ ] OpenAI client 可完成 chat completion
- [ ] 原生 tool call 可正確返回 `tool_calls`
- [ ] LlamaIndex agent 可調用 `FunctionTool`
- [ ] LlamaIndex agent 可調用 `QueryEngineTool`
- [ ] 輸出全為繁體中文
- [ ] tool arguments 有驗證
- [ ] 發生錯誤時不會亂編結果
- [ ] 4090 可穩定執行至少 30 分鐘測試

---

## 17. 建議的啟動順序（實戰版）

```bash
# 1. 啟動 vLLM
./scripts/start_vllm.sh

# 2. 驗證 chat completion
python scripts/test_openai_client.py

# 3. 驗證 tool calling
python scripts/test_tool_call.py

# 4. 啟動 LlamaIndex CLI 測試
python -m app.main

# 5. 啟動 API
uvicorn app.api:app --host 0.0.0.0 --port 9000 --reload
```

---

## 18. 若 function calling 仍不穩的備援方案

若你的實際部署發現 OpenAI-compatible tools 在某版本組合上不夠穩，建議退一步使用：

### 備援架構

```text
使用者問題
   |
   v
LLM 輸出 JSON action
   |
   v
應用程式 parse / validate
   |
   v
執行工具
   |
   v
把結果回填給 LLM
```

這就是較傳統的 **ReAct / JSON action** 路線。LlamaIndex 官方同樣提供 function-calling agent 與 ReAct agent 等不同代理模式；當原生 tools 對齊不穩時，這是實務上很常見的 fallback。[5]

---

## 19. 最終建議

對你的場景，最合理的執行策略不是一口氣上完整 production，而是：

1. **先證明 `gpt-oss-20b + vLLM` 能穩定回 `tool_calls`**
2. **再接 LlamaIndex `OpenAILike`**
3. **再加 RAG 工具**
4. **最後才包成 FastAPI 服務**

真正的關鍵，不在於「模型名字」，而在於：

- OpenAI-compatible schema 是否完整對齊
- 工具設計是否簡潔
- 應用層是否有驗證與 fallback

只要這三點處理好，這套方案就能成為你本地 function-calling agent 的穩定基礎。

---

## 20. 參考資料

[1] OpenAI, *Introducing gpt-oss*  
https://openai.com/index/introducing-gpt-oss/

[2] vLLM, *OpenAI-Compatible Server*  
https://docs.vllm.ai/en/stable/serving/openai_compatible_server/

[3] LlamaIndex, *OpenAILike API Reference*  
https://developers.llamaindex.ai/python/framework-api-reference/llms/openai_like/

[4] PyPI, *llama-index-llms-openai-like*  
https://pypi.org/project/llama-index-llms-openai-like/

[5] LlamaIndex, *Workflow for a Function Calling Agent*  
https://developers.llamaindex.ai/python/examples/workflow/function_calling_agent/

[6] LlamaIndex, *Customizing LLMs within LlamaIndex Abstractions*  
https://developers.llamaindex.ai/python/framework/module_guides/models/llms/usage_custom/
