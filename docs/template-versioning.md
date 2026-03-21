# Prompt/模板版本追蹤指引

> ADR-20260320-034 | 建立時間：2026-03-20

## 設計目標

將 prompts/team/*.md 和 templates/auto-tasks/*.md 納入版本追蹤，使每個結果 JSON 都能追溯到產生它的 prompt 版本，防止因 prompt 靜默漂移而導致結果品質下降。

## 版本格式

採用 [SemVer 2.0.0](https://semver.org/)：`major.minor.patch`

| 版本類型 | 觸發條件 | 範例 |
|---------|---------|------|
| **major** | 重大邏輯變更（步驟重組、輸出格式大改） | 1.0.0 → 2.0.0 |
| **minor** | 新增功能或步驟，但向下相容 | 1.0.0 → 1.1.0 |
| **patch** | 措辭修正、錯字修改、非邏輯性調整 | 1.0.0 → 1.0.1 |

## Frontmatter 格式

每個 prompt 文件開頭應包含：

```yaml
---
name: "todoist-auto-arch_evolution"
template_type: "team_prompt"           # team_prompt | auto_task_template
version: "1.0.0"
released_at: "2026-03-20"
---
```

## 版本發布流程

### 草稿階段

1. 修改 prompt 內容
2. 在本地驗證（手動執行一次，確認輸出符合預期）
3. 若輸出格式有變更，更新 `config/schemas/agent-result.schema.json`

### 提升為穩定版

1. 更新 frontmatter 中的 `version` 欄位（遵守 SemVer）
2. 更新 `released_at` 為當前日期
3. 執行 `uv run python tools/add_prompt_versions.py` 同步 `state/template-versions.json`
4. 提交 git（commit message 格式：`chore(prompts): bump {name} to v{version}`）

### Major 版本保留規則

Major 版本升級時（如 1.x.x → 2.0.0）：
- 舊版本 prompt 重命名為 `{name}-v1.md` 保留 30 天
- `state/template-versions.json` 記錄版本歷史
- 在 `context/improvement-backlog.json` 加入「驗證新版 prompt 相容性」P1 任務

## 結果 JSON 版本欄位

每個 `results/todoist-auto-*.json` 應包含：

```json
{
  "prompt_version": "1.0.0",
  "template_version": "1.0.0",
  "prompt_source": "prompts/team/todoist-auto-arch_evolution.md",
  ...
}
```

這些欄位由各 Agent 在寫入結果時自行填入（對應其讀取的 prompt frontmatter）。

## 工具與自動化

| 工具 | 用途 |
|------|------|
| `tools/add_prompt_versions.py` | 批次加入/更新 frontmatter，同步 state/template-versions.json |
| `state/template-versions.json` | 版本歷史記錄（供 check-health.ps1 + system-insight 消費） |
| `config/schemas/agent-result.schema.json` | 定義 prompt_version 等欄位的 schema |

## 查詢指令

```bash
# 查看所有 prompt 目前版本
uv run python tools/add_prompt_versions.py --dry-run

# 找出 result JSON 沒有 prompt_version 的比例
uv run python -c "
import json, glob
files = glob.glob('results/todoist-auto-*.json')
missing = sum(1 for f in files if not json.loads(open(f).read()).get('prompt_version'))
print(f'{missing}/{len(files)} 缺少 prompt_version')
"
```

## 版本歷史

| 版本 | 日期 | 說明 |
|------|------|------|
| v1.0.0 | 2026-03-20 | 初始建立（ADR-034 實作） |
