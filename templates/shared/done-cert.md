# DONE 認證格式（所有子 Agent 必須在最後一行輸出）

在所有工作完成後，必須輸出以下格式。即使失敗也要輸出，status 設為 FAILED。

```
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["產出物清單"],"tests_passed":true/false/null,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[],"iteration_count":N}
===DONE_CERT_END===
```

## 欄位說明
- `status`: DONE（完成）/ PARTIAL（部分完成）/ FAILED（失敗）
- `primary_goal_met`: 主要目標是否達成
- `artifacts_produced`: 產出物清單（commit hash、檔案路徑、匯入筆記數等）
- `tests_passed`: 測試是否通過（無測試則 null）
- `quality_score`: 1-5 分自評品質
- `self_assessment`: 一句話自我評估
- `remaining_issues`: 殘留問題列表（空陣列表示無殘留）
- `iteration_count`: 第幾次迭代
