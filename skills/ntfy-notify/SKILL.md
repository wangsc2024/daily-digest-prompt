---
name: ntfy-notify
version: "2.0"
description: |
  透過 ntfy.sh 發送任務完成通知。當用戶說「完成後通知 xxx」、
  「做完通知 xxx」、「完成後提醒 xxx」時，xxx 即為 ntfy topic，
  任務完成後使用 Python requests 發送通知到 ntfy.sh/xxx。
  觸發關鍵字：通知、提醒、notify、完成後通知、做完通知、完成後提醒、處理完提醒
triggers:
  - "通知"
  - "提醒"
  - "notify"
  - "完成後通知"
  - "做完通知"
  - "完成後提醒"
  - "處理完提醒"
---

# ntfy 通知 (ntfy Notification Skill)

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

---

## JSON 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `topic` | 是 | 通知頻道名稱 |
| `message` | 是 | 通知內容 |
| `title` | 否 | 通知標題（支援中文） |
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
2. **建立 JSON 檔案**（使用 Write 工具）
3. **發送通知**（使用 Bash + curl）
4. **刪除暫存檔案**（清理）

**範例流程：**
```python
# 步驟 1: 建立 JSON 檔案
# 使用 Write 工具寫入 ntfy_notify.json

# 步驟 2: 發送通知
# curl -H "Content-Type: application/json; charset=utf-8" -d @ntfy_notify.json https://ntfy.sh

# 步驟 3: 清理暫存檔
# rm ntfy_notify.json
```

---

## 重要規則

1. **禁止使用附件功能**：發送通知時不要使用 `attach` 欄位，只發送純文字訊息
2. **必須使用 charset=utf-8**：確保中文正確顯示
3. **必須使用 https://ntfy.sh**：完整 URL，不要只用 ntfy.sh
4. **建議刪除暫存檔**：發送完成後清理 JSON 檔案

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

def notify(topic, title, message, tags=None, priority=None):
    """發送 ntfy 通知"""
    payload = {'topic': topic, 'title': title, 'message': message}
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
