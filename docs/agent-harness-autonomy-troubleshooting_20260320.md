# Agent Harness 自主管理故障排除指南

## 1. `autonomous-runtime.json` 沒生成
- 檢查：
  - `python tools/autonomous_harness.py --format json`
  - `config/autonomous-harness.yaml` 是否可讀
- 常見原因：
  - YAML 語法錯誤
  - `state/` 目錄無寫入權限

## 2. CPU / memory 指標是 `null`
- 原因：
  - 執行帳號無法讀取 Windows counter / CIM
  - 主機安全政策限制 PowerShell counter
- 處理：
  - 用排程帳號手動執行：

```powershell
powershell -NoProfile -Command "(Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples[0].CookedValue"
```

## 3. GPU 指標缺失
- 原因：
  - 主機未安裝 NVIDIA driver 或 `nvidia-smi`
- 處理：
  - 執行 `nvidia-smi`
  - 若無 GPU，可忽略，系統仍可依 CPU / memory 降載

## 4. 新增 auto-task 後沒有被 supervisor 偵測
- 檢查：
  - 檔案是否放在 `templates/auto-tasks/*.md`
  - 檔名是否符合命名規則
- 驗證：

```powershell
python tools/autonomous_harness.py --format json
Get-Content state/autonomous-agent-registry.json
```

## 5. `run-todoist-agent-team.ps1` 沒套用 runtime policy
- 檢查 log 是否有：
  - `[Autonomy] runtime mode=...`
  - `[Autonomy] auto-tasks adjusted: ...`
- 若沒有：
  - 確認 `state/autonomous-runtime.json` 存在且 JSON 可解析

## 6. pytest 失敗但腳本可跑
- 目前已知問題：
  - 本機 `pytest` 使用的暫存目錄 ACL 被拒絕，會在 setup 階段失敗
- 判斷方式：
  - 若錯誤出現在 `tmpdir.py` / `pathlib.py` 的目錄建立或清理，而不是測試 assertion，屬環境問題
- 建議：
  - 以具完整權限的測試帳號執行
  - 或修正主機對暫存資料夾的 ACL

## 7. recovery queue 持續堆積
- 檢查：
  - `state/autonomous-recovery-queue.json`
  - `state/autonomous-harness-plan.json`
- 原因：
  - 目前 queue 已建立，但沒有獨立 consumer 常駐處理所有 action
- 建議：
  - 下一階段新增 recovery worker，專責消費 `pending` 項目
