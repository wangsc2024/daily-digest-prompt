# skills/ 目錄局部規則

## SKILL.md frontmatter 必填欄位

```yaml
name: skill-name
version: X.Y.Z
description: |
  一句話說明 Skill 用途。
  Use when: <觸發時機描述>
allowed-tools: [Read, Bash, ...]
triggers:
  - 關鍵字1
  - 關鍵字2
  - 關鍵字3
```

`validate_config.py` 會驗證 `name`、`version`、`description`、`allowed-tools`、`triggers`（≥3 個）；缺少時在 `check-health.ps1` 中告警。

## allowed-tools 最小權限原則

- 只列入實際需要的工具
- 唯讀 Skill（如 `scheduler-state`）：只含 `Read`，禁止 `Write`/`Edit`
- 研究類 Skill：必須含 `WebSearch`、`WebFetch`

## 版本更新規則

| 變更類型 | 版本號更新 |
|---------|---------|
| 修改步驟、規則等實質內容 | minor：+0.1.0 |
| 修改格式、備注、範例 | patch：+0.0.1 |

## Skill 計畫檔存放

計畫檔一律放在 `docs/plans/` 目錄下（格式：`{feature}-plan.md`）。
