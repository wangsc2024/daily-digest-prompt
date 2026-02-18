---
name: digest-memory
version: "1.1.0"
description: |
  摘要記憶持久化。跨次追蹤連續天數、待辦統計、習慣/學習連續天數、Skill 使用率、趨勢洞察。
  Use when: 記憶、連續天數、上次執行、跨次追蹤、連續報到、streak、執行統計、趨勢、記憶追蹤。
allowed-tools: Read, Write
cache-ttl: N/A
triggers:
  - "記憶"
  - "連續天數"
  - "上次執行"
  - "跨次追蹤"
  - "記憶追蹤"
  - "連續報到"
  - "streak"
  - "執行統計"
  - "趨勢"
---

# Digest Memory Skill - 摘要記憶持久化

## 用途
在每日摘要 Agent 執行之間保持上下文記憶，實現跨次追蹤。

## 記憶檔案位置
`context/digest-memory.json`

## 讀取記憶（Agent 啟動時）

用 Read 工具讀取 `context/digest-memory.json`。若檔案不存在代表首次執行，跳過即可。

記憶檔案格式：
```json
{
  "schema_version": 2,
  "last_modified_by": "agent",
  "last_run": "2026-02-11T08:00:00+08:00",
  "last_run_status": "success",
  "run_count": 42,
  "todoist": {
    "total_tasks": 5,
    "completed_count": 3,
    "pending_items": ["未完成的任務名稱"]
  },
  "habits": {
    "streak_days": 14,
    "last_topic": "環境設計",
    "last_topic_date": "2026-02-11",
    "topics_history": ["身份認同", "習慣堆疊", "環境設計"]
  },
  "learning": {
    "streak_days": 14,
    "last_topic": "間隔重複",
    "last_topic_date": "2026-02-11",
    "topics_history": ["費曼技巧", "刻意練習", "間隔重複"]
  },
  "skill_usage": {
    "total_skills": 20,
    "used_skills": 10,
    "cache_hits": 2,
    "api_calls": 3,
    "cache_degraded": 0,
    "knowledge_imports": 0
  },
  "knowledge": {
    "total_notes": 42,
    "imports_today": 0,
    "top_tags": ["楞嚴經", "AI動態", "系統審查"]
  },
  "digest_summary": "昨日 5 項待辦完成 3 項，屏東新聞 2 則，AI 動態 3 則"
}
```

### Schema 版本說明
- `schema_version`：目前為 2。讀取時若缺少此欄位，視為 v1（向後相容）
- `last_modified_by`：寫入者標記（"agent" 或 "script"），便於除錯追蹤

## 使用記憶產生摘要開頭

若記憶存在，在摘要最上方加入「連續報到」區塊：
```
連續報到第 N 天
- 昨日待辦：完成 M/N 項（未完成：XXX）
- 習慣提示連續 N 天
- 學習技巧連續 N 天
```

## 寫入記憶（Agent 結束前，ntfy 通知之前）

每次執行結束時，用 Write 工具寫入更新後的 `context/digest-memory.json`。

更新規則：
1. `last_run`：當前時間（ISO 8601 格式）
2. `last_run_status`：整體執行狀態（success / partial / failed）
3. `run_count`：前次值 +1（首次為 1）
4. `todoist`：本次查詢到的待辦統計
5. `habits.streak_days`：若昨日有執行（last_run 在 24-48 小時內），+1；否則重置為 1
6. `habits.last_topic`：本次使用的習慣提示主題
7. `habits.topics_history`：保留最近 14 筆（覆蓋 2 週完整輪替週期）
8. `habits.last_topic_date`：本次使用主題的日期（格式 YYYY-MM-DD），用於同日去重
9. `learning`：同上邏輯（`topics_history` 14 筆 + `last_topic_date`）
10. `digest_summary`：本次摘要的一句話總結
11. `skill_usage`：本次 Skill 使用統計
    - `total_skills`：專案定義的 Skill 總數（目前為 20，含 17 核心 + 3 工具）
    - `used_skills`：本次實際使用的 Skill 數量
    - `cache_hits`：快取命中次數（從 api-cache 追蹤取得）
    - `api_calls`：API 實際呼叫次數
    - `cache_degraded`：降級使用過期快取次數（新增欄位）
    - `knowledge_imports`：本次匯入知識庫的筆記數
12. `knowledge`：知識庫健康資訊
    - `total_notes`：從 `/api/stats` 取得的筆記總數（查詢失敗則保留前次值）
    - `imports_today`：本次摘要匯入的筆記數
    - `top_tags`：從 `/api/notes/tags` 取得的前 5 大標籤（查詢失敗則保留前次值）
13. `trends`（可選，v2 新增）：最近 7 天趨勢資料，每天一筆
14. `insights`（可選，v2 新增）：Agent 自動提煉的跨天觀察

### trends 區塊格式（可選）
```json
"trends": [
  {
    "date": "2026-02-13",
    "tasks_total": 6,
    "tasks_completed": 0,
    "skills_used": 11,
    "cache_hits": 2,
    "api_calls": 3,
    "cache_degraded": 0
  }
]
```
- 保留最近 7 筆（超過則移除最舊的）
- 每次執行只更新當天的記錄（同日多次執行則覆蓋）

### insights 區塊格式（可選）
```json
"insights": [
  "HN 快取命中率連續 3 天偏低，建議檢查 TTL 設定",
  "楞嚴經研究已累計 15 篇，建議開始系統性整理"
]
```
- Agent 在寫入記憶時，觀察 trends 資料，提煉 1-2 則洞察
- 保留最近 5 則（超過則移除最舊的）
- 無特別發現時可為空陣列

## 計算連續天數的邏輯

以**本地日期**（+08:00 台灣時區）為準：

```
若 last_run 存在且 JSON 可正常解析：
  last_date = last_run 的日期部分（YYYY-MM-DD）
  today = 當前本地日期
  若 last_date == today：streak 不變（同日重複執行）
  若 last_date == yesterday：streak = 前次 streak + 1
  否則：streak = 1（中斷超過一天）
若 last_run 不存在或 JSON 損壞：
  streak = 1（重置）
```

### 關鍵規則
- **只有成功執行**（`last_run_status == "success"`）才計入連續天數
- **同日多次執行**不重複遞增，streak 維持不變
- **JSON 損壞**（讀取失敗或格式錯誤）→ 重置 streak 為 1，記錄警告

## 寫入規則
- `schema_version`：固定為 2
- `last_modified_by`：固定為 "agent"
- `last_run`：使用 ISO 8601 含時區格式（如 `2026-02-13T16:57:00+08:00`）

## 注意事項
- 用 Write 工具建立 JSON 檔案，確保 UTF-8 編碼
- JSON 內容不要包含控制字元，換行用 \n
- 記憶檔案不需要刪除，持續累積
