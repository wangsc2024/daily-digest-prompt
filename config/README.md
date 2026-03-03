# config/ 配置文件說明

所有可變邏輯外部化於此目錄，修改配置無需動 prompt 或程式碼。

## 配置文件速查

| 檔案 | 用途 | 主要引用者 | 修改影響 |
|------|------|-----------|---------|
| `pipeline.yaml` | 每日摘要管線步驟定義 | daily-digest-prompt.md | 調整摘要執行順序與步驟 |
| `routing.yaml` | Todoist 三層路由規則 | hour-todoist-prompt.md | 調整任務→Skill 映射、標籤路由 |
| `cache-policy.yaml` | 各 API 快取 TTL 與降級策略 | daily-digest-prompt.md、api-cache SKILL | 調整快取時效與降級時限 |
| `frequency-limits.yaml` | 自動任務頻率限制（19 個任務，47 次/日） | hour-todoist-prompt.md | 調整自動任務每日執行次數上限 |
| `scoring.yaml` | TaskSense 優先級計分規則 | hour-todoist-prompt.md | 調整任務排序權重與計分公式 |
| `notification.yaml` | ntfy 通知配置 | hour-todoist-prompt.md、assemble-digest.md | 調整通知 topic、標籤、模板 |
| `dedup-policy.yaml` | 研究去重策略 | 所有研究模板 | 調整冷卻天數、飽和閾值 |
| `topic-rotation.yaml` | 主題輪替配置 | learning-mastery SKILL | 調整學習主題輪替邏輯 |
| `hook-rules.yaml` | Hook 攔截規則定義 | hooks/*.py | 調整 Bash/Write/Read 攔截規則 |
| `health-scoring.yaml` | 健康評分維度權重 | query-logs.ps1 | 調整健康評分 6 維度權重 |
| `audit-scoring.yaml` | 系統審查評分規則 | system-audit SKILL | 調整審查維度權重、等級門檻 |
| `benchmark.yaml` | 系統效能基準線 | system-insight SKILL | 調整效能目標門檻 |
| `timeouts.yaml` | 各階段超時值集中管理 | run-*.ps1 腳本 | 調整執行超時與重試間隔 |
| `digest-format.md` | 摘要輸出排版模板 | daily-digest-prompt.md、assemble-digest.md | 調整摘要通知排版格式 |
| `llm-router.yaml` | LLM 路由規則（Groq vs Claude 分工） | groq SKILL、fetch-hackernews、fetch-news | 調整 LLM 任務分配策略 |
| `creative-game-mode.yaml` | 創意遊戲模式配置 | creative-game-optimize 自動任務 | 調整遊戲創意評估參數 |
| `ooda-workflow.yaml` | OODA 閉環工作流配置 | system-insight、arch-evolution | 調整 OODA 步驟啟用狀態 |
| `retro-games.yaml` | 復古遊戲評鑑配置 | game-design SKILL | 調整遊戲品質評估標準 |
| `schemas/` | YAML 驗證 Schema 目錄 | validate_config.py | 修改配置驗證規則 |

## 版本管理

每個 YAML 檔案頂部含 `version:` 欄位，修改時應遞增版本號。

## 修改原則

1. **改配置不改 prompt**：可變參數一律在此目錄修改
2. **注釋充分**：每個欄位應有用途說明
3. **向下相容**：新增欄位不應破壞既有邏輯（hooks 有 fallback 機制）
