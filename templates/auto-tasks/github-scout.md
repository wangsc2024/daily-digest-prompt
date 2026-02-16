# 自動任務：GitHub 靈感蒐集

> 由 round-robin 自動觸發，每日最多 1 次（僅週三和週日執行）

## 第零步：星期檢查
用 Bash 執行 `date +%u` 取得星期幾（1=週一, 7=週日）。
- 若為 3（週三）或 7（週日）→ 繼續執行
- 其他天 → 輸出 DONE_CERT（status=DONE, quality_score=5, self_assessment="非執行日，跳過"）並結束

> 設計考量：作為自動任務可利用現有 round-robin 基礎設施，
> 非執行日消耗極少資源（僅 1 次 date 命令 + DONE_CERT 輸出，< 5 秒）。

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
依 github-scout SKILL.md 的步驟 1-6 執行。

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
    "day_check_passed": true,
    "search_completed": true,
    "analysis_done": true,
    "backlog_updated": true
  },
  "artifacts_produced": ["context/improvement-backlog.json"],
  "quality_score": 4,
  "self_assessment": "GitHub 靈感蒐集完成"
}
===DONE_CERT_END===
```
