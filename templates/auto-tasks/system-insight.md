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
