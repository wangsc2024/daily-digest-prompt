# 每日晨間佛偈推播 — 任務規格與驗收

> **任務類型**：CODE 型（cursor-cli 執行）  
> **相關 Skill**：ntfy-notify、cursor-cli  
> **腳本**：run-morning-verse.ps1  
> **排程**：HEARTBEAT.md → morning-verse（06:30）

---

## 1. 任務目標

每日早上 6:30（GMT+8 台北時間）向委託者提供一段**佛學偈頌**，內容具備「鼓勵精進用功」意旨，讓委託者在一天開始時得到正向精神激勵。

---

## 2. 執行要求

| 項目 | 規格 |
|------|------|
| **偈頌來源** | 佛教典籍（如《金剛經》《法華經》《雜阿含經》等）或公有領域佛教語錄 |
| **內容要求** | 明確傳達「鼓勵精進用功」訊息 |
| **時間** | 每日 06:30（±1 分鐘） |
| **傳遞方式** | ntfy 推播（topic: wangsc2025） |
| **格式** | 純文字，含偈頌全文 + 典籍/來源簡短註記 |
| **長度** | 建議 ≤150 中文字符（含來源） |

---

## 3. 實作架構

- **偈頌庫**：`data/buddhist-verses.json`（36 條，round-robin 選取）
- **日誌**：`state/verse-log.json`（記錄送出狀態、避免同日重複）
- **腳本**：`run-morning-verse.ps1 -Session morning`
- **排程**：Windows Task Scheduler（HEARTBEAT.md → setup-scheduler.ps1 -FromHeartbeat）

---

## 4. 驗收條件

- [x] **時間正確**：委託者於每日 06:30（±1 分鐘）收到訊息
- [x] **內容符合**：偈頌出自佛教典籍，明確包含「鼓勵精進用功」語意
- [x] **來源可查**：訊息附帶典籍/章節資訊，可於公開資料庫查證
- [x] **持續運作**：測試期（至少連續 3 天）內未出現遺漏或錯誤送訊

---

## 5. 故障處理

- **送訊失敗**：腳本內建 30 秒後重試一次
- **重試仍失敗**：發送 ntfy 告警（同 topic，priority 4，tags: warning）通知執行者
- **排程遺漏**：可手動執行 `pwsh -ExecutionPolicy Bypass -File run-morning-verse.ps1 -Session morning`

---

## 6. 參考

- ntfy-notify Skill：`skills/ntfy-notify/SKILL.md`
- 通知配置：`config/notification.yaml` → morning_verse
- 依賴配置：`config/dependencies.yaml` → ntfy_notify
