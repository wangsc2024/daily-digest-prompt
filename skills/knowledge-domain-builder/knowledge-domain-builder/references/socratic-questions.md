# 柏拉圖式提問框架

> 蘇格拉底相信，真正的知識不是灌輸，而是透過提問從對話者心中「接生」出來。
> 這個階段的目標不只是收集需求，而是幫助使用者思考清楚自己到底要什麼。

## 提問原則

1. **不預設答案**：每個問題都是開放式的，不暗示「正確」選項
2. **層層深入**：從 Why → What → How，每層建立在前一層的回答之上
3. **適時追問**：如果回答模糊，用「你說的 X 具體是指什麼？」追問
4. **反映矛盾**：如果回答之間有矛盾，溫和地指出讓使用者重新思考
5. **總結確認**：每層結束後摘要使用者的回答，確認理解一致

## 第一層：目的與本質（Why）

這一層探索使用者學習的根本動機。許多人以為自己知道為什麼要學，但深入追問後會發現更深層的原因。

### 必問問題

```
Q1: 你為什麼想學「{domain}」這個領域？
    是什麼事件或情境觸發了這個念頭？

Q2: 假設三個月後你已經「學會」了，你的日常會有什麼不同？
    你會用它來做什麼？

Q3: 你心中的「學會」是什麼樣貌？
    - 能向完全不懂的人系統性地講解？
    - 能在工作中靈活運用解決問題？
    - 建立一個隨時可查閱的參考體系？
    - 還是其他？
```

### 追問模板

- 「你提到想___，能舉一個具體的情境嗎？」
- 「如果只能達成一件事，你最希望是什麼？」
- 「這個領域對你是長期投資，還是解決眼前的問題？」

## 第二層：邊界與範圍（What）

這一層定義知識庫的疆域。一個好的知識庫不是「什麼都有」，而是「該有的都有，不該有的一個都沒有」。

### 必問問題

```
Q4: 這個領域很廣，你最關心的「核心區域」是哪些？
    有沒有你明確不需要、可以排除的部分？

Q5: 你目前對這個領域了解多少？
    - 完全空白，連基本術語都不知道
    - 知道一些零散概念，但不成體系
    - 有一定基礎，想要系統化和深化
    - 某些方面很熟，想補足盲區

Q6: 你手邊有沒有已有的學習資料？
    （PDF、書籍、課程筆記、網頁書籤等）
    如果有，可以上傳或描述它們。
```

### 追問模板

- 「你提到不需要___，是因為已經會了，還是跟你的目標無關？」
- 「如果把這個領域想像成一棵樹，你想要整棵樹，還是某幾根主要的枝幹？」

## 第三層：限制與偏好（How）

這一層收集實作層面的約束條件，直接影響知識庫的結構設計。

### 必問問題

```
Q7: 你預計每天能投入多少時間學習？
    （這會影響知識點的粒度和總量）

Q8: 你偏好什麼學習方式？
    - 理論先行（先懂原理再實作）
    - 實作導向（邊做邊學）
    - 案例驅動（從真實案例倒推原理）

Q9: 知識庫需要在哪些設備上使用？
    - 僅桌機/筆電
    - 桌機 + 手機/平板查閱
    - 多設備完整編輯
    
Q10: 你目前有在用 Obsidian 嗎？
     - 是，有成熟的 vault → 要整合進去還是獨立建新的？
     - 是，剛開始用 → 有安裝哪些外掛？
     - 否，全新開始
```

## 對話結束：摘要確認

完成三層提問後，將所有回答整理為結構化摘要，用使用者能理解的語言呈現，請使用者確認：

```
好的，讓我確認我理解的：

📌 目的：你想學「{domain}」，主要是為了 {purpose_summary}
📐 範圍：聚焦在 {scope}，排除 {exclusions}
📊 現狀：目前 {current_level}，{has_materials ? "手邊有一些資料" : "從零開始"}
⏰ 節奏：每天約 {time} 學習，偏好 {style} 方式
📱 設備：需要 {sync_summary}
🗂️ Vault：{vault_plan}

這樣理解正確嗎？有沒有需要調整的？
```

使用者確認後，生成 `domain_profile.json` 並自動進入 Phase 1。

## domain_profile.json 結構

```json
{
  "domain": "領域名稱",
  "domain_en": "Domain Name in English",
  "created_at": "ISO 8601 timestamp",
  
  "purpose": {
    "motivation": "學習動機",
    "success_criteria": "學會的定義",
    "timeframe": "long_term | short_term | ongoing",
    "use_case": "具體應用場景"
  },
  
  "scope": {
    "focus_areas": ["核心關注領域1", "核心關注領域2"],
    "exclusions": ["排除的領域1"],
    "depth": "overview | intermediate | deep | expert",
    "max_atomic_notes": 80
  },
  
  "learner": {
    "current_level": "blank | scattered | foundational | partial_expert",
    "has_materials": false,
    "materials_description": "",
    "daily_time_minutes": 30,
    "learning_style": "theory_first | practice_first | case_driven"
  },
  
  "technical": {
    "sync_needs": ["desktop", "mobile"],
    "sync_method": "git | obsidian_sync | syncthing | icloud | none",
    "existing_vault": false,
    "vault_path": "",
    "installed_plugins": []
  },
  
  "generation": {
    "language": "zh-TW",
    "naming_style": "chinese",
    "include_english_terms": true,
    "note_template_style": "feynman"
  }
}
```
