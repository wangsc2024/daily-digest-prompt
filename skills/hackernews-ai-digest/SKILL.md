---
name: hackernews-ai-digest
version: "1.0.0"
description: |
  Hacker News AI 新聞摘要。篩選 AI/LLM/ML 相關熱門文章，產出中文摘要。
  Use when: AI 新聞、LLM、GPT、Claude、機器學習、技術動態、Hacker News。
allowed-tools: Bash, Read, Write
cache-ttl: 120min
triggers:
  - "AI 新聞"
  - "LLM"
  - "GPT"
  - "Claude"
  - "機器學習"
  - "Hacker News"
  - "技術動態"
---

# Hacker News AI 新聞摘要（每日摘要簡化版）

透過 curl 呼叫 Hacker News 官方 API，篩選 AI 相關熱門文章，產出中文摘要。

## 執行步驟

### 步驟 1：取得熱門文章 ID

```bash
curl -s "https://hacker-news.firebaseio.com/v0/topstories.json"
```

回傳 JSON 陣列，取前 30 筆掃描即可。

### 步驟 2：逐筆取得文章詳情

```bash
curl -s "https://hacker-news.firebaseio.com/v0/item/{id}.json"
```

回傳格式：
```json
{
  "id": 12345678,
  "title": "Show HN: AI-powered code review tool",
  "url": "https://example.com/article",
  "score": 256,
  "descendants": 128,
  "by": "author_name"
}
```

### 步驟 3：篩選 AI 相關文章

用以下關鍵字篩選 title（不分大小寫）：
- AI, LLM, GPT, Claude, OpenAI, Anthropic, Gemini, DeepSeek
- machine learning, deep learning, neural network
- transformer, diffusion, RAG, fine-tuning, AGI
- 人工智慧, 大語言模型

### 步驟 4：產出摘要

從篩選結果中取前 3-5 則，格式：

```
🤖 AI 技術動態
- [中文標題翻譯]（🔥 分數 | 💬 評論數）
  原標題: English Title
```

## 注意事項

- HN API 無需認證，無速率限制（但請控制請求頻率）
- 如果掃描 30 筆後找不到 AI 相關文章，報告「今日無顯著 AI 新聞」
- 標題翻譯由 Claude 直接生成，不需外部翻譯 API
- 保留技術術語原文（如 LLM、RAG、Transformer）
