# 需求對話框架

> 在建立知識庫之前，透過結構化對話釐清使用者的需求。
> 收集足夠的資訊，讓 AI 能生成完整、準確、符合期望的知識筆記。

## 提問原則

1. **不預設答案**：每個問題都是開放式的
2. **層層深入**：從 What/Why → How → Depth
3. **總結確認**：所有提問結束後摘要確認

## 第一層：目的與範圍（What & Why）

### 必問問題

```
Q1: 你要建立什麼領域的知識庫？
    具體用途是什麼？（個人查閱、團隊共享、教學參考、專案支援...）

Q2: 這個領域的哪些部分是核心？
    有沒有明確不需要、可以排除的部分？

Q3: 你目前對這個領域了解多少？
    - 完全空白
    - 知道一些零散概念
    - 有一定基礎，想系統化
    - 某些方面很熟，想補足盲區

Q4: 你手邊有沒有已有的參考資料？
    （PDF、書籍、筆記、網頁書籤等）
```

## 第二層：技術與偏好（How）

### 必問問題

```
Q5: 你預計知識庫包含多少則筆記？
    （每則 1500 字以上，建議 15-30 則為一個完整領域）

Q6: 你偏好什麼內容風格？
    - 學術嚴謹：精確定義 + 經典引用 + 系統分析
    - 通俗易懂：白話解釋 + 生活類比 + 具體案例
    - 實務導向：聚焦應用 + 操作步驟 + 真實場景

Q7: 知識庫需要在哪些設備上使用？
    - 僅桌機/筆電
    - 桌機 + 手機/平板查閱
    - 多設備完整編輯

Q8: 你目前有在用 Obsidian 嗎？
    - 是，有成熟的 vault → 整合還是獨立？
    - 是，剛開始用 → 有裝哪些外掛？
    - 否，全新開始
```

## 第三層：內容深度（Depth）

### 必問問題

```
Q9: 你希望筆記的內容深度是什麼等級？
    - 入門級：白話解釋，避免術語，大量類比
    - 中級：使用專業術語但提供解釋，含原理和應用
    - 專家級：假設已有基礎，聚焦細微差異和進階議題

Q10: 有沒有你特別喜歡的教材、作者或解說風格？
     （幫助 AI 校準語調和內容取向）
```

## 對話結束：摘要確認

完成提問後，將所有回答整理為結構化摘要，請使用者確認：

```
好的，讓我確認我理解的：

📌 領域：{domain}
📐 範圍：聚焦在 {scope}，排除 {exclusions}
📊 現狀：{current_level}
📝 規模：約 {count} 則筆記，每則 1500 字以上
🎨 風格：{tone}，{depth_level} 深度
📱 設備：{sync_summary}
🗂️ Vault：{vault_plan}

這樣理解正確嗎？有沒有需要調整的？
```

確認後生成 `domain_profile.json` 並自動進入 Phase 1。

## domain_profile.json 結構

```json
{
  "domain": "領域名稱",
  "domain_en": "Domain Name in English",
  "created_at": "ISO 8601 timestamp",

  "purpose": {
    "motivation": "建庫動機",
    "use_case": "具體用途"
  },

  "scope": {
    "focus_areas": ["核心領域1", "核心領域2"],
    "exclusions": ["排除領域1"],
    "depth": "overview | intermediate | deep | expert",
    "max_notes": 30
  },

  "learner": {
    "current_level": "blank | scattered | foundational | partial_expert",
    "has_materials": false,
    "materials_description": ""
  },

  "technical": {
    "sync_needs": ["desktop", "mobile"],
    "sync_method": "git | obsidian_sync | syncthing | icloud | none",
    "existing_vault": false,
    "installed_plugins": []
  },

  "content": {
    "depth_level": "beginner | intermediate | expert",
    "tone": "academic | conversational | practical",
    "reference_style": "偏好的風格描述",
    "min_words_per_note": 1500
  },

  "generation": {
    "language": "zh-TW",
    "naming_style": "chinese",
    "zero_blank_policy": true
  }
}
```
