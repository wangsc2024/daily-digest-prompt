# 交付說明與字數驗證（非規則本文）

## 規則文字（與 `guess-number-rules.txt` 同步）

```
系統隨機產生一數字。玩家輸入猜測；若太大或太小會被告知，猜中即勝。
```

## 字數檢查

- 以「字元」計：含中文、全形標點，共 **33** 字元（上限 50）。
- 驗證方式：手動逐字點算；亦可於複製到 `D:\source\game_web` 後執行：
  `pwsh -NoProfile -Command "(Get-Content -Raw 'guess-number-rules.txt').Length"`（注意：此為 .NET 字元長度，與「中文字符」規則一致時建議仍以人工對照為準）。

## 目錄位置說明

本機自動化環境僅能寫入工作區內路徑。請將整個 `game_web` 目錄複製或同步至 **`D:\source\game_web`** 以符合任務指定產出路徑。
