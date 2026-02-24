# Phase 2: 組裝審查報告與修正

你是系統審查專家，全程使用正體中文。

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則

必須先讀取以下 SKILL.md：
1. `skills/knowledge-query/SKILL.md` — RAG 知識庫查詢與匯入
2. `skills/system-audit/SKILL.md` — 系統審查評分工具（參考評分標準）

## 任務

Phase 1 的 4 個 Agent 已完成審查，各自輸出 JSON 到 `results/` 目錄。你的任務是：
1. 讀取並彙整所有審查結果
2. 計算加權總分與等級
3. 識別需要修正的項目
4. 執行自動修正（最多 5 項）
5. 生成完整報告
6. 將報告寫入 RAG 知識庫
7. 更新狀態檔案
8. 發送審查完成通知（含 arch-evolution 觸發提醒與 ADR decision 填寫提醒）

## 執行步驟

### Step 1: 讀取 Phase 1 結果

讀取以下 4 個 JSON 檔案：
- `results/audit-dim1-5.json` （維度 1+5）
- `results/audit-dim2-6.json` （維度 2+6）
- `results/audit-dim3-7.json` （維度 3+7）
- `results/audit-dim4.json` （維度 4）

讀取前次審查結果（如存在）：
- `state/last-audit.json`

### Step 1.5: 更新 API 健康狀態（Circuit Breaker）

此步驟讀取 Phase 1 的結構化日誌，統計各 API 呼叫結果，並更新 `state/api-health.json`。

**執行方式**（系統審查不涉及外部 API，此步驟僅為架構一致性保留）：
```bash
# 系統審查不呼叫外部 API，此步驟可跳過
# 若未來新增 API 依賴，使用以下模板更新 circuit breaker
echo "System audit: no external APIs, skipping circuit breaker update"
```

### Step 2: 計算總分

依 balanced weight profile 計算加權總分：

```
加權總分 = (維度1×20 + 維度2×18 + 維度3×18 + 維度4×15 + 維度5×10 + 維度6×10 + 維度7×9) / 100
```

等級判定：
- **S（卓越）**：90-100 分
- **A（優秀）**：80-89 分
- **B（良好）**：70-79 分
- **C（及格）**：55-69 分
- **D（待改善）**：40-54 分
- **F（不及格）**：0-39 分

### Step 3: 問題識別

分析所有 38 個子項，找出需要修正的項目：

**篩選條件**：
- 任一子項 < 70 分（未達「良好」）
- 任一維度 < 80 分（未達「優秀」）
- 相較前次審查退步 > 5 分（如有前次記錄）

**優先排序**：
- P0（緊急）：安全漏洞、資料遺失風險
- P1（高）：功能缺陷、效能劣化
- P2（中）：技術債、文件缺失
- P3（低）：優化建議

**可行性評估**：
- ✅ 可自動修正：新增配置檔、修正格式、提取硬編碼值、更新文件
- ❌ 需人工介入：架構重構、外部服務整合、人工決策

### Step 4: 自動修正（限制 5 項）

僅修正**可自動處理**的項目，最多 5 項：

**修正範例**：
```markdown
# 修正 1: 新增 config/benchmark.yaml（改善 3.6 效能基準）
- 建立檔案含 7 個效能指標
- 提升 3.6 從 82 → 88

# 修正 2: 清理 3 處 DRY 殘留（改善 2.6）
- todoist-auto-github-scout/self-heal/system-insight 加入 preamble.md 引用
- 提升 2.6 從 88 → 92
```

**每項修正後**：
- 使用 Write/Edit 工具執行修正
- 記錄到 `修正記錄` 段落
- 不重新審查（避免遞迴）

**禁止修正**：
- 需要外部服務（如建立 CI/CD）
- 架構性變更（如模組重組）
- 需要人工決策

### Step 5: 生成報告

依 `templates/audit-report.md` 模板建立完整報告：

**報告結構**：
```markdown
# 系統審查報告 - YYYY-MM-DD HH:MM

## 執行摘要
- 總分：XX.XX/100（等級 X）
- 與前次比對：+X.XX（或 維持/退步）
- 審查時間：Phase 1 並行審查 + Phase 2 組裝

## 各維度詳細評分
[7 個維度表格，含 38 個子項的分數與證據]

## 關鍵發現
[前 5 個最弱項目]

## 修正記錄（本次自動修正）
[清單，含修正前後分數預估]

## 建議清單（需人工介入）
[依優先級排序]

## 趨勢分析
[與前次審查的分數變化圖表]
```

**輸出位置**：
- 完整報告：`docs/系統審查報告_YYYYMMDD_HHMM.md`

### Step 6: 寫入知識庫

依照 `skills/knowledge-query/SKILL.md` 將報告寫入 RAG：

**1. 建立 note.json**（用 Write 工具）：
```json
{
  "title": "系統審查報告 - 2026-02-17",
  "content": "<報告完整內容，Markdown 格式>",
  "tags": ["系統審查", "自動化", "品質評估"],
  "source": "manual",
  "metadata": {
    "total_score": 90.47,
    "grade": "S",
    "date": "2026-02-17",
    "audit_type": "automated",
    "phase": "team_mode",
    "dimensions": {
      "security": 91,
      "architecture": 84,
      "quality": 91,
      "workflow": 96,
      "tech_stack": 92,
      "documentation": 88,
      "completeness": 93
    },
    "fixes_applied": 5,
    "issues_remaining": 2
  }
}
```

**2. 發送 API 請求**：
```bash
curl -X POST http://localhost:3000/api/notes \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @note.json
```

**3. 驗證回應**：
- 確認 200 OK
- 提取 note_id（如 `{"id": "abc123", ...}`）
- 記錄到 state/last-audit.json

**錯誤處理**：
- 如 API 失敗，本地保留報告，記錄警告
- 不阻塞流程（報告已寫入 docs/）

### Step 7: 更新狀態

寫入 `state/last-audit.json`：

```json
{
  "total_score": 90.47,
  "grade": "S",
  "date": "2026-02-17",
  "timestamp": "2026-02-17 00:50:00",
  "dimensions": {
    "1_information_security": 91,
    "2_system_architecture": 84,
    "3_system_quality": 91,
    "4_system_workflow": 96,
    "5_technology_stack": 92,
    "6_system_documentation": 88,
    "7_system_completeness": 93
  },
  "note_id": "abc123",
  "fixes_applied": 5,
  "fixes_list": [
    "新增 config/benchmark.yaml",
    "清理 3 處 DRY 殘留",
    "補充 config/README.md 流程圖",
    "更新 CHANGELOG.md 版本號",
    "修正 SKILL_INDEX.md 連結"
  ],
  "message": "Team mode audit completed with 5 auto-fixes"
}
```

### Step 7.5: 發送審查完成通知

審查完成後，透過 ntfy 推播通知，包含審查摘要與後續行動提醒。

**建立通知 JSON**（用 Write 工具建立 `audit-notify.json`）：

```json
{
  "topic": "wangsc2025",
  "title": "系統審查完成 {GRADE}（{SCORE}/100）",
  "message": "修正 {FIXES} 項 | 報告：docs/系統審查報告_{DATE}.md\n\n📋 請手動觸發 arch-evolution：\n  在 Claude Code 輸入 arch-evolution\n  將 improvement-backlog.json 轉化為 ADR\n\n✏️ 請人工填寫 ADR decision 欄位：\n  context/adr-registry.json\n  找 status=Proposed 的條目填寫 decision",
  "priority": 3,
  "tags": ["white_check_mark", "clipboard"]
}
```

**替換佔位符**：
- `{GRADE}`：本次等級（如 `S`、`A`）
- `{SCORE}`：加權總分（如 `90.47`）
- `{FIXES}`：自動修正數量（如 `2`）
- `{DATE}`：日期時間（如 `20260224_0040`）

**發送通知**：
```bash
curl -s -H "Content-Type: application/json; charset=utf-8" -d @audit-notify.json https://ntfy.sh
```

**錯誤處理**：
- 發送失敗不阻塞流程，僅記錄警告
- `audit-notify.json` 在 Step 8 清理

### Step 8: 清理

刪除 Phase 1 暫存檔案：
- `results/audit-dim1-5.json`
- `results/audit-dim2-6.json`
- `results/audit-dim3-7.json`
- `results/audit-dim4.json`
- `note.json`（RAG 上傳用）
- `audit-notify.json`（ntfy 通知用）

保留：
- `docs/系統審查報告_*.md`（永久存檔）
- `state/last-audit.json`（趨勢追蹤）

## 輸出範例

```
=== Phase 2: 組裝審查報告 ===

[Step 1] 讀取 Phase 1 結果
  ✓ 維度 1+5: 91/100 + 92/100
  ✓ 維度 2+6: 84/100 + 88/100
  ✓ 維度 3+7: 91/100 + 93/100
  ✓ 維度 4: 96/100

[Step 2] 計算總分
  加權總分: 90.47/100 (S 等級)
  與前次比對: +0.00（維持）

[Step 3] 問題識別
  找到 2 個待改善項目：
  - 2.2 配置外部化: 78 分（P2，可自動修正）
  - 6.4 配置說明: 78 分（P2，可自動修正）

[Step 4] 自動修正
  ✓ 修正 1: 補充 config/README.md 流程圖
  ✓ 修正 2: 更新 CHANGELOG.md 版本號
  共完成 2 項修正

[Step 5] 生成報告
  ✓ 報告已寫入: docs/系統審查報告_20260217_0050.md

[Step 6] 寫入知識庫
  ✓ 成功寫入 RAG (note_id: abc123)

[Step 7] 更新狀態
  ✓ state/last-audit.json 已更新

[Step 7.5] 發送審查完成通知
  ✓ ntfy 通知已發送 (wangsc2025)
    提醒：手動觸發 arch-evolution + 填寫 ADR decision

[Step 8] 清理
  ✓ 已刪除 5 個暫存 JSON 檔案

=== 審查完成 ===
總分：90.47/100 (S 等級)
自動修正：2 項
報告位置：docs/系統審查報告_20260217_0050.md
知識庫 ID：abc123
```

## 注意事項

- 自動修正不得超過 5 項
- 每項修正必須記錄到報告
- 知識庫寫入失敗不阻塞流程
- 清理暫存檔案前先確認報告已生成
