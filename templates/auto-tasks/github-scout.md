---
name: "github-scout"
template_type: "auto_task_template"
version: "2.0.0"
released_at: "2026-03-22"
---
# 自動任務：GitHub 靈感蒐集

> 由 round-robin 自動觸發，每日最多 2 次，全天執行

## 共用規則
先讀取 `templates/shared/preamble.md`，遵守其中所有規則。

## Skill-First
必須先讀取 `skills/github-scout/SKILL.md`，依其步驟執行。

## 研究註冊表檢查
用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 檢查近 7 天是否已有 task_type=github_scout 的條目
- 若 3 天內已有同主題 → 選擇不同搜尋主題

## 執行步驟
依 github-scout SKILL.md 的步驟 1-6 執行（搜尋、篩選、分析、產出改進建議、寫入 backlog、KB 匯入）。

## 落實方案研擬與審查（新增）
依 github-scout SKILL.md 的步驟 7-10 執行：
- 步驟 7：針對高優先級建議研擬落實方案並存入 KB
- 步驟 8：審查方案可行性與穩定性（最多 3 輪優化）
- 步驟 9：對通過審查的方案主動落實（低風險直接執行，高風險輸出計畫）
- 步驟 10：落實後驗證並輸出通知

## 研究註冊表更新
完成後將本次研究寫入 `context/research-registry.json`：
```json
{
  "task_type": "github_scout",
  "topic": "本次搜尋主題",
  "timestamp": "ISO timestamp",
  "output": "context/improvement-backlog.json"
}
```

## 輸出
完成後用 Write 建立 `task_result.txt`，包含 DONE_CERT：
```
===DONE_CERT_BEGIN===
{
  "status": "DONE",
  "task_type": "github-scout",
  "checklist": {
    "search_completed": true,
    "analysis_done": true,
    "backlog_updated": true,
    "implementation_plan_stored": true,
    "review_passed": true,
    "implemented": true
  },
  "artifacts_produced": ["context/improvement-backlog.json"],
  "report_urls": ["https://github.com/..."],
  "quality_score": 4,
  "self_assessment": "GitHub 靈感蒐集、落實方案研擬、審查並落實完成"
}
===DONE_CERT_END===
```
