# hooks/ 目錄局部規則

## 規則外部化原則

攔截規則定義在 `config/hook-rules.yaml`，不在 Python 中硬編碼。
`FALLBACK_*` 常數只是 YAML 不可用的最後防線，內容應與 YAML 同步。
**新增攔截規則：只改 `hook-rules.yaml`（Python 零修改）。**

## 測試規範

- 每個 hook 對應 `tests/hooks/test_*.py`
- 新規則至少加：正常路徑 + 攔截路徑 + `warn_only` 路徑 各一個測試
- `uv run pytest tests/` 必須全部通過

## 日誌格式

- 位置：`logs/structured/YYYY-MM-DD.jsonl`
- 攔截：`level="blocked"`；警告：`level="warn"`
- 統一用 `hook_utils.log_blocked_event()`

## nul 禁令（機器強制）

- 禁止在 Bash 中使用 `> nul`、`2>nul`、`> NUL`（cmd 語法，在 bash 中會建立實體檔案）
- 禁止使用 Write 工具寫入任何名為 `nul` 的檔案路徑
- 要抑制輸出：`| Out-Null`（PowerShell）或 `> /dev/null`（bash）
- `hooks/pre_bash_guard.py` 和 `hooks/pre_write_guard.py` 在 runtime 攔截

## Hook 類型速查

| Hook | 觸發時機 | 主要功能 |
|------|---------|---------|
| `pre_bash_guard.py` | PreToolUse:Bash | nul 重導向、危險操作攔截 |
| `pre_write_guard.py` | PreToolUse:Write/Edit | nul 寫入、敏感檔案、schema 驗證 |
| `pre_read_guard.py` | PreToolUse:Read | 敏感路徑讀取攔截 |
| `post_tool_logger.py` | PostToolUse:* | 結構化 JSONL 日誌（自動標籤 + 50MB 輪轉） |
| `cjk_guard.py` | PostToolUse:Write/Edit | CJK 字元守衛（日文變體修正） |
| `on_stop_alert.py` | Stop | Session 結束健康檢查 + ntfy 告警 |
