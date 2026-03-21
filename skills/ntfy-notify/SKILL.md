---
name: ntfy-notify
version: "2.0.3"
description: |
  透過 ntfy.sh 發送任務完成通知。當用戶說「完成後通知 xxx」、
  「做完通知 xxx」、「完成後提醒 xxx」時，xxx 即為 ntfy topic，
  任務完成後使用 JSON 檔案 + curl 發送到 **https://ntfy.sh 根網址**（topic 寫在 JSON 內，見下文「常見錯誤」）。
  Use when: 任務完成推播、即時提醒、通知發送、排程結果通知、告警推播。
allowed-tools: Bash, Read, Write
cache-ttl: 0min
depends-on:
  - config/dependencies.yaml
  - skills/markdown-editor/SKILL.md
triggers:
  - "通知"
  - "提醒"
  - "notify"
  - "完成後通知"
  - "做完通知"
  - "完成後提醒"
  - "處理完提醒"
  - "推播"
  - "ntfy"
  - "訊息推送"
  - "告警"
---

# ntfy 通知 (ntfy Notification Skill)

## 依賴注入（DI）

> 端點來源：`config/dependencies.yaml` → `skills.ntfy_notify`（ADR-001 Phase 3）
> 執行前讀取 YAML 取得 `base_url` 與 `topic`；若 YAML 不可讀則 fallback 使用下方預設值。
>
> **讀取片段**（在需要呼叫 API 的步驟前執行）：
> ```bash
> BASE=$(uv run python -X utf8 -c "import yaml; d=yaml.safe_load(open('config/dependencies.yaml')); print(d['skills']['ntfy_notify']['api']['base_url'])" 2>/dev/null || echo "https://ntfy.sh")
> TOPIC=$(uv run python -X utf8 -c "import yaml; d=yaml.safe_load(open('config/dependencies.yaml')); print(d['skills']['ntfy_notify']['topic'])" 2>/dev/null || echo "wangsc2025")
> ```
>
> `base_url` fallback：`https://ntfy.sh`；`topic` fallback：`wangsc2025`。

任務完成後透過 ntfy.sh 發送推播通知，讓你在手機或桌面即時收到任務狀態。

**v2.0 更新**：改用 Python requests 發送通知，取代原有的 curl 方案。

## 什麼是 ntfy？

[ntfy](https://ntfy.sh) 是一個簡單的 HTTP-based 推播通知服務：
- 完全免費、開源
- 無需註冊或 API Key
- 支援 iOS、Android、桌面通知
- 只需要一個 topic 名稱即可接收通知

## 觸發條件

當用戶指令中包含以下模式時觸發：

| 用戶指令範例 | 提取的 topic |
|-------------|-------------|
| 「做完這個功能後通知 wangsc2025」 | `wangsc2025` |
| 「完成後通知 my-alerts」 | `my-alerts` |
| 「處理完提醒 test123」 | `test123` |

### 觸發關鍵字

- `通知 + topic名稱`
- `提醒 + topic名稱`
- `完成後通知 + topic名稱`
- `做完通知 + topic名稱`

## 官方文件對齊

發送行為以 [ntfy Publishing](https://docs.ntfy.sh/publish/) 為準，專案內常用段落：

| 主題 | 文件錨點 |
|------|----------|
| JSON 發布（根 URL、`topic` 必填等） | [Publish as JSON](https://docs.ntfy.sh/publish/#publish-as-json) |
| `markdown` 欄位與 Markdown 語法範圍 | [Markdown formatting](https://docs.ntfy.sh/publish/#markdown-formatting) |
| HTTP 標頭別名（`Markdown` / `X-Markdown` / `md`） | 同上節（純文字 body 情境；**JSON 發布建議用 body 內 `markdown: true`**） |

### ntfy Markdown 適用範圍（官方摘要）

> 來源：[Markdown formatting](https://docs.ntfy.sh/publish/#markdown-formatting)。ntfy 指向 [Markdown Guide — Basic Syntax](https://www.markdownguide.org/basic-syntax/) 作為語法參考，但**實際支援集合以官方列表為準**（非整份 GFM／CommonMark）。

**開關（預設純文字）**

- JSON 發布：`"markdown": true`（[欄位說明](https://docs.ntfy.sh/publish/#publish-as-json)）。
- 純文字 POST：HTTP 標頭 `X-Markdown`（別名 `Markdown`、`md`）設為 `true` / `1` / `yes`，或 `Content-Type: text/markdown`。

**客戶端（重要）**

- 官方原文：**Supported Markdown features (web app only for now)**。亦即文件明列的格式化能力，**以網頁版檢視較完整**；iOS／Android 等 App 內通知可能接近純文字或精簡顯示。**推播內文請以「全客戶端可讀的純文字＋保守 Markdown」為原則**，勿假設表格或程式碼區塊在手機上排版完美。

**官方明列支援的類型**（與文件條目一一對應）

| 類型 | 說明／語法提示 |
|------|----------------|
| Horizontal rules | `---` |
| Blockquotes | `>` 開頭 |
| Lists | `-` 無序、`1.` 有序 |
| Headings | `#`～`######`（`#` 後須空格） |
| Code | 围栏程式碼區塊與行內反引號 |
| Images | `![說明](https://…)` |
| Links | `[文字](https://…)` |
| Emphasis | `**粗體**`、`*斜體*` |

**官方該節未列出**（勿依賴於 ntfy）：GFM **表格**、**任務清單** `- [ ]`、**刪除線** `~~…~~`、**Mermaid**、`> [!NOTE]` 等告警區塊、腳註等擴展語法。

**與 `markdown-editor` Skill**：撰寫 `message` 時可 Read **`skills/markdown-editor/SKILL.md`** 核對標題／清單／粗體等**基礎寫法**，但**可用品項以上表為準**，不得假設 ntfy 等同 GitHub 預覽。

---

## 通知發送格式（跨平台）

**重要：使用 JSON 檔案方式發送，確保 Windows/macOS/Linux 都能正常運作。**

### 標準流程（推薦）

**步驟 1：建立 JSON 檔案**

```json
{
  "topic": "TOPIC",
  "title": "任務完成",
  "message": "訊息內容",
  "tags": ["white_check_mark"]
}
```

純文字可省略 `markdown`。若 `message` 含 `##`、清單、`**粗體**` 等 Markdown，請加 **`"markdown": true`**（[官方 JSON 欄位表](https://docs.ntfy.sh/publish/#publish-as-json)）。

**步驟 2：使用 curl 發送**

```bash
curl -H "Content-Type: application/json; charset=utf-8" -d @payload.json https://ntfy.sh
```

### 為什麼使用檔案方式？

| 環境 | 直接 JSON 字串 | 檔案方式 |
|------|---------------|---------|
| macOS/Linux | ✅ 正常 | ✅ 正常 |
| Windows | ❌ 編碼問題 | ✅ 正常 |
| 中文支援 | ⚠️ 可能亂碼 | ✅ 完美 |

### 常見錯誤：通知內文變成整段 `{ "topic": ... }`

若使用 **JSON 檔** 發送，**POST 目標必須是** `https://ntfy.sh`（路徑為空）。**不要**使用 `https://ntfy.sh/你的topic`。

| 寫法 | 結果 |
|------|------|
| `-d @payload.json https://ntfy.sh` | ✅ 伺服器解析 JSON，`title` / `message` 分開顯示 |
| `-d @payload.json https://ntfy.sh/wangsc2025` | ❌ 整份 JSON 被當成純文字訊息，手機上只看到原始 JSON |

`topic` 請只放在 JSON 的 `"topic"` 欄位（與專案內 `skills/skill-forge/SKILL.md` 說明一致）。

---

## JSON 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `topic` | 是 | 通知頻道名稱 |
| `message` | 是 | 通知內容 |
| `title` | 否 | 通知標題（支援中文） |
| `markdown` | 否 | `true` 時依 Markdown 渲染 `message`（官方 bool 欄位） |
| `tags` | 否 | 標籤陣列，自動轉為 emoji |
| `priority` | 否 | 優先級 1-5（5 最高） |
| `click` | 否 | 點擊通知開啟的 URL |
| `delay` | 否 | 延遲發送（如 "30m", "1h"） |

---

## 完整範例

### 範例 1: 成功通知

**JSON 檔案 (ntfy_success.json)：**
```json
{
  "topic": "wangsc2025",
  "title": "任務完成",
  "message": "React project created at ./my-react-app",
  "tags": ["white_check_mark"]
}
```

**發送指令：**
```bash
curl -H "Content-Type: application/json; charset=utf-8" -d @ntfy_success.json https://ntfy.sh
```

### 範例 2: 失敗通知

**JSON 檔案 (ntfy_fail.json)：**
```json
{
  "topic": "ci-alerts",
  "title": "測試失敗",
  "message": "3 tests failed in test_auth.py",
  "priority": 4,
  "tags": ["x", "test_tube"]
}
```

**發送指令：**
```bash
curl -H "Content-Type: application/json; charset=utf-8" -d @ntfy_fail.json https://ntfy.sh
```

### 範例 3: 測試通過

**JSON 檔案 (ntfy_test.json)：**
```json
{
  "topic": "ci-alerts",
  "title": "測試通過",
  "message": "46 tests passed, 85% coverage",
  "tags": ["white_check_mark", "test_tube"]
}
```

### 範例 4: 部署成功

**JSON 檔案 (ntfy_deploy.json)：**
```json
{
  "topic": "ops-team",
  "title": "部署成功",
  "message": "v2.1.0 deployed to production",
  "tags": ["rocket", "white_check_mark"]
}
```

### 範例 5: 帶連結

**JSON 檔案 (ntfy_pr.json)：**
```json
{
  "topic": "dev-team",
  "title": "PR 已合併",
  "message": "PR #123 merged to main",
  "tags": ["white_check_mark"],
  "click": "https://github.com/user/repo/pull/123"
}
```

### 範例 6: 高優先級（緊急）

**JSON 檔案 (ntfy_urgent.json)：**
```json
{
  "topic": "ops-alerts",
  "title": "緊急",
  "message": "Server down! CPU usage 100%",
  "priority": 5,
  "tags": ["fire", "warning"]
}
```

### 範例 7: 延遲通知

**JSON 檔案 (ntfy_delay.json)：**
```json
{
  "topic": "reminders",
  "title": "提醒",
  "message": "30 分鐘後記得休息",
  "delay": "30m"
}
```

## macOS/Linux 快捷方式

在 macOS/Linux 環境下，也可以直接使用 JSON 字串（但仍建議檔案方式以確保一致性）：

```bash
# 成功通知
curl -H "Content-Type: application/json" -d '{"topic":"TOPIC","title":"任務完成","message":"描述","tags":["white_check_mark"]}' ntfy.sh

# 失敗通知
curl -H "Content-Type: application/json" -d '{"topic":"TOPIC","title":"任務失敗","message":"描述","priority":4,"tags":["x"]}' ntfy.sh
```

## 實作流程（Claude 執行時）

當用戶要求「完成後通知 xxx」時，Claude 應：

1. **執行用戶要求的任務**
2. **建立通知 JSON 檔案**（使用 Write 工具）
3. **寫入 ntfy 日誌**（每次通知都記錄，詳見下方「通知日誌記錄」）
4. **發送通知**（使用 Bash + curl，捕捉 exit code）
5. **刪除暫存通知檔**（保留日誌檔）

**範例流程：**
```python
# 步驟 1: 建立 JSON 檔案
# 使用 Write 工具寫入 ntfy_notify.json

# 步驟 2: 發送通知，捕捉 HTTP 狀態碼
# HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
#   -H "Content-Type: application/json; charset=utf-8" \
#   -d @ntfy_notify.json https://ntfy.sh)

# 步驟 3: 寫入 ntfy 日誌（見下方格式）

# 步驟 4: 清理暫存檔
# rm ntfy_notify.json
```

---

## 通知日誌記錄

**每次發送 ntfy 通知，必須同時寫入一筆日誌**到 `logs/ntfy/` 目錄。
這些日誌供 `ntfy_review` 自動任務（Claude Opus 4.6）每日審查，識別優化機會。

### 日誌流程

```bash
# 步驟 1：確保目錄存在
mkdir -p logs/ntfy

# 步驟 2：取得時間戳與環境變數
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# agent：優先用排程注入的 $AGENT_NAME；互動模式下固定為 "claude-code-interactive"
AGENT_NAME=${AGENT_NAME:-"claude-code-interactive"}
# trace_id：優先用排程注入的 $DIGEST_TRACE_ID；互動模式下生成 "interactive-YYYYMMDD_HHmmss"
TRACE_ID=${DIGEST_TRACE_ID:-"interactive-${TIMESTAMP}"}

# 步驟 3：發送通知並捕捉結果
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @ntfy_notify.json https://ntfy.sh)
CURL_OK=$([ "$HTTP_CODE" = "200" ] && echo true || echo false)
```

**步驟 4：用 Write 工具寫入日誌檔**，路徑格式：
`logs/ntfy/YYYYMMDD_HHmmss_<topic>.json`

### 日誌格式

```json
{
  "timestamp": "2026-03-15T10:00:00+08:00",
  "topic": "wangsc2025",
  "title": "任務完成",
  "message": "訊息內容",
  "tags": ["white_check_mark"],
  "priority": null,
  "agent": "auto-podcast_jiaoguangzong",
  "trace_id": "abc123...",
  "http_status": 200,
  "sent": true
}
```

| 欄位 | 說明 |
|------|------|
| `timestamp` | ISO 8601，Asia/Taipei |
| `topic` | ntfy topic 名稱 |
| `title` / `message` / `tags` / `priority` | 同通知 payload |
| `agent` | 從環境變數 `$AGENT_NAME` 取得 |
| `trace_id` | 從環境變數 `$DIGEST_TRACE_ID` 取得 |
| `http_status` | curl 回傳的 HTTP 狀態碼（200 = 成功） |
| `sent` | `true` = 200 OK，`false` = 其他 |

### 完整範例（含日誌）

```bash
# 1. 建立通知 payload（Write 工具）
# → ntfy_payload_tmp.json

# 2. 發送並捕捉狀態碼
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @ntfy_payload_tmp.json https://ntfy.sh)

# 3. 用 Write 工具寫入日誌
# → logs/ntfy/20260315_100000_wangsc2025.json

# 4. 刪除暫存 payload
rm ntfy_payload_tmp.json
# 注意：日誌檔保留，不刪除
```

> **注意**：日誌檔名中的 topic 若含特殊字元，替換為底線（`/` → `_`）。

---

## 重要規則

1. **禁止使用附件功能**：發送通知時不要使用 `attach` 欄位，只發送純文字訊息
2. **必須使用 charset=utf-8**：確保中文正確顯示
3. **JSON 發送時 POST 至 `https://ntfy.sh`（根網址）**：完整 URL；**禁止** `https://ntfy.sh/<topic>` 搭配 JSON body（否則內文會變整段 JSON）
4. **Markdown**：`message` 使用 Markdown 語法時必加 **`"markdown": true`**；撰寫規則參考 **`skills/markdown-editor/SKILL.md`**
5. **建議刪除暫存檔**：發送完成後清理 JSON 檔案

---

## 快速範本

### 成功通知（一行版）

```python
import requests; requests.post('https://ntfy.sh', json={'topic':'TOPIC','title':'任務完成','message':'DESCRIPTION','tags':['white_check_mark']}, headers={'Content-Type':'application/json'}, timeout=10)
```

### 失敗通知（一行版）

```python
import requests; requests.post('https://ntfy.sh', json={'topic':'TOPIC','title':'任務失敗','message':'DESCRIPTION','priority':4,'tags':['x']}, headers={'Content-Type':'application/json'}, timeout=10)
```

### 完整函數版

```python
import requests

def notify(topic, title, message, tags=None, priority=None, markdown=False):
    """發送 ntfy 通知"""
    payload = {'topic': topic, 'title': title, 'message': message}
    if markdown:
        payload['markdown'] = True
    if tags:
        payload['tags'] = tags
    if priority:
        payload['priority'] = priority

    try:
        r = requests.post('https://ntfy.sh', json=payload,
                         headers={'Content-Type': 'application/json'},
                         timeout=10)
        return r.status_code == 200
    except:
        return False

# 使用
notify('wangsc2025', '任務完成', '簽辦公文專家 skill 已優化為 v2.0', ['white_check_mark'])
```

---

## 如何接收通知

1. **手機 App**
   - iOS: [App Store](https://apps.apple.com/app/ntfy/id1625396347)
   - Android: [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy)

2. **訂閱 Topic**
   - 開啟 App → 點擊 + → 輸入 topic 名稱

3. **桌面通知**
   - 訪問 https://ntfy.sh/YOUR_TOPIC
   - 允許瀏覽器通知

---

## 常用 Tags

Tags 會自動轉換為 emoji：

| Tag | Emoji | 用途 |
|-----|-------|------|
| `white_check_mark` | ✅ | 成功 |
| `x` | ❌ | 失敗 |
| `warning` | ⚠️ | 警告 |
| `hourglass_flowing_sand` | ⏳ | 進行中 |
| `rocket` | 🚀 | 部署 |
| `test_tube` | 🧪 | 測試 |
| `package` | 📦 | 打包 |
| `bug` | 🐛 | Bug |
| `chart` | 📊 | 報告 |
| `tada` | 🎉 | 慶祝 |
| `fire` | 🔥 | 緊急 |
| `computer` | 💻 | 開發 |
| `memo` | 📝 | 文件 |

## 快速範本（JSON 檔案）

**成功通知 (success.json)：**
```json
{
  "topic": "TOPIC",
  "title": "任務完成",
  "message": "DESCRIPTION",
  "tags": ["white_check_mark"]
}
```

**失敗通知 (fail.json)：**
```json
{
  "topic": "TOPIC",
  "title": "任務失敗",
  "message": "DESCRIPTION",
  "priority": 4,
  "tags": ["x"]
}
```

**進度通知 (progress.json)：**
```json
{
  "topic": "TOPIC",
  "title": "進行中",
  "message": "Progress: 50%",
  "tags": ["hourglass_flowing_sand"]
}
```

## 注意事項

- Topic 是公開的，使用不易猜測的名稱
- 避免放敏感資訊
- 免費版每天約 250 條限制
- Windows 環境必須使用檔案方式發送 JSON

---

**Generated by Skill Seekers** | ntfy Notification Skill | 測試驗證：2026-01-16
