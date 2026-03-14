# config/ 配置文件說明

所有可變邏輯外部化於此目錄，修改配置無需動 prompt 或程式碼。

## 配置文件速查

| 檔案 | 用途 | 主要引用者 | 修改影響 |
|------|------|-----------|---------|
| `pipeline.yaml` | 每日摘要管線步驟定義 | daily-digest-prompt.md | 調整摘要執行順序與步驟 |
| `routing.yaml` | Todoist 三層路由規則 | hour-todoist-prompt.md | 調整任務→Skill 映射、標籤路由 |
| `cache-policy.yaml` | 各 API 快取 TTL 與降級策略 | daily-digest-prompt.md、api-cache SKILL | 調整快取時效與降級時限 |
| `frequency-limits.yaml` | 自動任務頻率限制 + 模型選擇規則（19 個任務，47 次/日） | hour-todoist-prompt.md、run-todoist-agent-team.ps1 | 調整自動任務每日執行次數上限、後端分派規則 |
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
| `llm-router.yaml` | LLM 路由規則（Groq vs Claude 分工） | groq SKILL、fetch-hackernews、fetch-news | 調整 LLM 任務分配策略（注意：Todoist 多後端規則已合併至 frequency-limits.yaml） |
| `creative-game-mode.yaml` | 創意遊戲模式配置 | creative-game-optimize 自動任務 | 調整遊戲創意評估參數 |
| `ooda-workflow.yaml` | OODA 閉環工作流配置 | system-insight、arch-evolution | 調整 OODA 步驟啟用狀態 |
| `retro-games.yaml` | 復古遊戲評鑑配置 | game-design SKILL | 調整遊戲品質評估標準 |
| `slo.yaml` | SLO 服務等級目標 | check-health.ps1 | 調整可用性與延遲目標門檻 |
| `podcast.yaml` | Podcast 生成配置 | article-to-podcast.ps1 | 調整語音合成、音訊格式參數 |
| `media-pipeline.yaml` | 媒體管線配置（影片/音訊） | compose_video.py、concat_audio.py | 調整影片合成與音訊串接參數 |
| `tts-abbreviation-rules.yaml` | TTS 縮寫展開規則 | article-to-podcast.ps1 | 調整語音合成的縮寫念法 |
| `notification-events.yaml` | 自癒機制 ntfy 通知事件集中配置（OODA 閉環事件） | arch-evolution、self-heal、on_stop_alert.py | 調整通知事件標題、等級、去重策略 |
| `budget.yaml` | LLM 用量預算配置（每日/月度 token 上限） | budget_guard.py、llm_router.py | 調整 Claude/Groq 用量上限與告警閾值 |
| `agent-pool.yaml` | Agent Pool 並行度與 done_cert 策略配置 | coordinator.py、done_cert.py | 調整 Agent 並行數量、timeout 繼承來源 |
| `kb-content-scoring.yaml` | KB 知識庫內容評分系統配置 | kb-curator SKILL、groq-relay.js | 調整知識庫內容品質評分規則 |
| `schemas/` | YAML 驗證 Schema 目錄 | validate_config.py | 修改配置驗證規則 |

## 版本管理

每個 YAML 檔案頂部含 `version:` 欄位，修改時應遞增版本號。

## 修改原則

1. **改配置不改 prompt**：可變參數一律在此目錄修改
2. **注釋充分**：每個欄位應有用途說明（目標註解密度 ≥ 20%）
3. **向下相容**：新增欄位不應破壞既有邏輯（hooks 有 fallback 機制）

## 驗證流程

修改任一 YAML 後，執行驗證確保格式正確：

```bash
# 驗證所有 YAML schema（7 個已定義 schema）
uv run python hooks/validate_config.py

# 檢查配置膨脹度量
pwsh -File analyze-config.ps1

# 確認 Hook 規則載入（修改 hook-rules.yaml 後）
uv run python hooks/pre_bash_guard.py < test-input.json
```

## 修改範例

```yaml
# 調整自動任務頻率（config/frequency-limits.yaml）
# 1. 找到目標任務區段
# 2. 修改 daily_limit 值
# 3. 遞增頂部 version 欄位
# 4. 執行 validate_config.py 驗證

# 調整 Hook 攔截規則（config/hook-rules.yaml）
# 1. 在對應類別（bash_rules/write_rules/read_rules）新增規則
# 2. 指定 pattern（regex）、severity、action
# 3. 遞增 version 欄位
# 4. 測試：uv run pytest tests/hooks/ -k "test_pre_bash"
```

## 配置階層

```
config/
├── 核心管線：pipeline.yaml, routing.yaml, scoring.yaml
├── 頻率控制：frequency-limits.yaml, cache-policy.yaml, timeouts.yaml
├── 安全規則：hook-rules.yaml, audit-scoring.yaml
├── 通知/格式：notification.yaml, digest-format.md
├── LLM 路由：llm-router.yaml（Groq/Claude 分工；Todoist 多後端規則已合併至 frequency-limits.yaml）
├── 品質監控：benchmark.yaml, health-scoring.yaml, slo.yaml
├── 研究策略：dedup-policy.yaml, topic-rotation.yaml
├── 特殊領域：creative-game-mode.yaml, retro-games.yaml, podcast.yaml
├── 媒體管線：media-pipeline.yaml, tts-abbreviation-rules.yaml
├── OODA 工作流：ooda-workflow.yaml
├── 通知事件：notification-events.yaml（自癒機制事件定義）
├── 預算治理：budget.yaml（Token 上限 + 告警閾值）
├── Agent Pool：agent-pool.yaml（並行度 + done_cert）
├── 知識庫評分：kb-content-scoring.yaml（KB 內容品質評分）
└── schemas/：YAML 驗證 Schema 定義
```
