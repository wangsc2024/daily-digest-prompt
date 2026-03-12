# 自動任務：系統洞察分析

> 由 round-robin 自動觸發，每日最多 1 次

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則。

## Skill-First
必須先讀取 `skills/system-insight/SKILL.md`，依其步驟執行。

## 研究註冊表檢查
本任務為系統維護類型，不需要研究註冊表去重。

## 執行步驟
依 system-insight SKILL.md 的步驟 1-4 執行。

## 驗證閉環子步驟（Validation Loop）

在步驟 1-4 完成後，執行以下驗證子步驟（若 `context/arch-decision.json` 有 `execution_status=success` 的項目）：

**5. 驗證既有修復效果**
用 Read 讀取 `context/arch-decision.json`：
- 若不存在或無 `execution_status=success` 的項目 → 跳過此子步驟
- 對每個最近執行成功（`execution_status=success`）的 `immediate_fix` 項目：
  1. 讀取 `verification` 欄位描述的驗證方法
  2. 使用 Grep/Read/Bash 確認修改是否仍然生效（例：YAML 注釋是否存在、依賴是否已安裝）
  3. 記錄驗證結果至 `arch-decision.json` 對應條目的 `validation_result` 欄位：
     - 驗證成功：`"validation_result": "verified_ok"`
     - 驗證失敗（修復已消失）：`"validation_result": "regression_detected"`，並重置 `execution_status = "pending"` 以觸發下次 self-heal 重新修復

此驗證確保「已執行」的修復不是靜默失敗的假修復，形成 Observe→Verify 的閉環確認。

## 輸出
完成後用 Write 建立 `task_result.txt`，包含 DONE_CERT：
```
===DONE_CERT_BEGIN===
{
  "status": "DONE",
  "task_type": "system-insight",
  "checklist": {
    "jsonl_analyzed": true,
    "state_analyzed": true,
    "insight_written": true,
    "alerts_checked": true
  },
  "artifacts_produced": ["context/system-insight.json"],
  "quality_score": 4,
  "self_assessment": "系統洞察報告已產出"
}
===DONE_CERT_END===
```
