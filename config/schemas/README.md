# Schemas 目錄

本目錄存放專案的 JSON Schema 檔案，用於驗證結構化輸出的格式與完整性。

## Schema 清單

| Schema 檔案 | 版本 | 用途 | 驗證對象 |
|------------|------|------|----------|
| `results-auto-task-schema.json` | v1.1.0 | 自動任務結果統一格式 | `results/todoist-auto-*.json`（29 個任務） |
| `execution-trace-schema.json` | v1.0.0 | Agent 執行追蹤統一格式 | `logs/structured/*.jsonl`、`system-insight.json` |

## 使用方式

### 驗證結果檔案

```bash
# 驗證自動任務結果檔案
uv run python tools/validate_results.py

# 驗證單一檔案
uv run python tools/validate_results.py results/todoist-auto-tech_research.json
```

### 驗證執行追蹤 (未來功能)

```bash
# 驗證 execution trace JSONL 日誌
# uv run python tools/validate_trace.py logs/structured/20260320_071500.jsonl
```

## Schema 設計原則

1. **向後相容**：允許 `additionalProperties: true`，支援未來擴充
2. **必填最小化**：僅核心欄位為 required，降低驗證失敗率
3. **語義清晰**：每個欄位都有 description 與 examples
4. **可驗證性**：使用 JSON Schema Draft 2020-12 標準，支援 `jsonschema` 驗證

## 新增 Schema 流程

1. 建立 `config/schemas/<name>-schema.json`
2. 在本 README.md 的清單表格新增一筆
3. 在 `docs/ARCHITECTURE.md` 的 `config/schemas/` 段落新增條目
4. 將產物路徑寫入 `context/workflow-forge-registry.json`
5. 若有對應驗證工具，在「使用方式」段落新增範例

## 參考資源

- [JSON Schema 官方文件](https://json-schema.org/)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/schema)
- [Python jsonschema 套件](https://python-jsonschema.readthedocs.io/)
