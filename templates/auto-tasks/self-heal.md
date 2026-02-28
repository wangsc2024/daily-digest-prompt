# 自動任務：自愈迴圈

> 由 round-robin 自動觸發，每日最多 3 次

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則。

## 前置檢查（降級機制）
用 Read 讀取 `context/system-insight.json`：
- 若不存在或修改時間超過 24 小時 → 跳過步驟 1 的資料分析，僅執行步驟 2 中不依賴該檔案的修復項（b/c/d/e）
- 在報告中標註「system-insight 資料不可用，部分檢查已跳過」

## 自愈流程

### 步驟 1：分析系統健康（需 system-insight.json）
讀取 `context/system-insight.json`（由 system-insight Skill 產生）：
- 分析 alerts 中是否有 critical 等級
- 識別 high_failure_hours（高失敗率時段）
- 檢查 skill_usage_coverage 是否偏低

### 步驟 2：識別並修復可自動修復的問題

#### a. [需 system-insight] 高失敗率 API 快取清除
- 若某 API 來源失敗率 > 30% → 刪除對應 `cache/*.json` 強制下次重抓
- 支援的快取：todoist.json, pingtung-news.json, hackernews.json, gmail.json

#### b. research-registry.json 過期清理
- 讀取 `context/research-registry.json`
- 移除 entries 中 timestamp 超過 7 天的條目
- 保持 version 欄位不變

#### c. auto-tasks-today.json 跨日歸零
- 讀取 `context/auto-tasks-today.json`
- 若 date 欄位 ≠ 今天 → 重置所有計數為 0，保留 `next_execution_order`

#### d. logs/structured/ 單檔大小檢查
- 用 Bash 檢查 `logs/structured/` 下所有 .jsonl 檔案大小
- 若任何檔案 > 50MB → 輪轉（重命名為 .rotated，僅保留最新 1 個）

#### e. run-once-*.ps1 殘留清理
- 掃描專案根目錄的 `run-once-*.ps1` 和 `task_prompt_once*.md`
- 對每個檔案，檢查對應 Windows 排程是否存在
- 若排程不存在 → 安全刪除殘留檔案

#### f. Chatroom 整合健康檢查（G28）
用 Read 讀取 `state/api-health.json`：
- 找出 `gun-bot` 的 circuit_breaker 狀態
- 若 state="open"（API 連續失敗）→ 刪除 `cache/chatroom.json`（強制下次重抓）+ 記錄到 alerts

用 Bash 檢查 `cache/chatroom.json` 修改時間：
```bash
python -c "
import json, os, datetime
path = 'cache/chatroom.json'
if os.path.exists(path):
    age = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(path))
    print(f'age_minutes:{int(age.total_seconds()/60)}')
    with open(path) as f:
        data = json.load(f)
    print(f'source:{data.get(\"source\",\"unknown\")}')
else:
    print('age_minutes:-1')
"
```
- 若 age_minutes > 120 且 source != "api" → 刪除 `cache/chatroom.json`（過期降級快取清理）
- 若 age_minutes = -1（不存在）→ 正常，無需處理

### 步驟 3：記錄修復行為
每項修復動作記錄到結構化日誌（透過工具呼叫自動被 post_tool_logger.py 記錄）。

### 步驟 4：驗證修復結果
- 對每項修復重新檢查，確認已修復
- 統計：修復嘗試 N 項，成功 M 項

### 步驟 5：發送修復報告
若有修復動作 → 依 `skills/ntfy-notify/SKILL.md` 發送通知：
- 標題：「自愈報告 | YYYY-MM-DD HH:mm」
- 內容：修復摘要

## 安全邊界（不可自動修復）
以下問題僅通知不修復：
- **scheduler-state.json** → 備份 + 通知人工介入（PS1 層 try-catch 已處理崩潰回復）
- **SKILL.md 內容異常** → 通知不修改（由 pre_write_guard.py 保護）
- **config/*.yaml 缺失** → 通知不重建

## 輸出
完成後用 Write 建立 `task_result.txt`，包含 DONE_CERT：
```
===DONE_CERT_BEGIN===
{
  "status": "DONE",
  "task_type": "self-heal",
  "checklist": {
    "analysis_done": true,
    "repairs_attempted": N,
    "repairs_succeeded": M,
    "notification_sent": true
  },
  "artifacts_produced": [],
  "quality_score": 4,
  "self_assessment": "自愈迴圈完成，修復 M/N 項"
}
===DONE_CERT_END===
```
