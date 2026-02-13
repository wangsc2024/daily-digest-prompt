---
name: skill-scanner
description: |
  Cisco AI Defense Skill Scanner — 掃描專案內所有 Skill，偵測安全風險（注入、資料洩露、權限提升等）。
  Use when: 安全掃描、Skill 審查、安全稽核
  Triggers: 安全掃描, skill 掃描, security scan, audit skills, 安全稽核, 掃描技能
version: "1.0.0"
---

# Skill Scanner — AI Agent 技能安全掃描

使用 Cisco AI Defense Skill Scanner 掃描 `skills/` 目錄下所有 Skill，
偵測潛在安全風險（prompt injection、data exfiltration、privilege escalation 等）。

## 快速使用

### 掃描全部 Skills（推薦）

```bash
D:/Python311/Scripts/skill-scanner.exe scan-all D:/Source/daily-digest-prompt/skills --recursive --format summary
```

### 掃描單一 Skill

```bash
D:/Python311/Scripts/skill-scanner.exe scan D:/Source/daily-digest-prompt/skills/todoist --format summary
```

### 含行為分析（Python AST dataflow）

```bash
D:/Python311/Scripts/skill-scanner.exe scan-all D:/Source/daily-digest-prompt/skills --recursive --use-behavioral --format summary
```

### JSON 輸出（機器可讀）

```bash
D:/Python311/Scripts/skill-scanner.exe scan-all D:/Source/daily-digest-prompt/skills --recursive --format json
```

## PowerShell 便捷腳本

```powershell
.\scan-skills.ps1                          # 快速總覽
.\scan-skills.ps1 -Format markdown         # 完整報告
.\scan-skills.ps1 -SkillName todoist       # 掃描單一 Skill
.\scan-skills.ps1 -UseBehavioral           # 含行為分析
.\scan-skills.ps1 -FailOnFindings          # CI 模式（有風險則失敗）
```

## 輸出格式

| 格式 | 用途 |
|------|------|
| `summary` | 快速總覽（預設） |
| `json` | 機器可讀，適合 Agent 處理 |
| `markdown` | 完整報告，適合文件保存 |
| `table` | 終端機表格顯示 |
| `sarif` | GitHub Code Scanning 整合 |

## 掃描引擎

| 引擎 | 旗標 | 需要 API Key | 說明 |
|------|------|-------------|------|
| 靜態分析 | （預設） | 否 | YAML + YARA 規則比對 |
| 行為分析 | `--use-behavioral` | 否 | Python AST 資料流分析 |
| LLM 分析 | `--use-llm` | 是（`SKILL_SCANNER_LLM_API_KEY`） | 語義分析 |
| 病毒掃描 | `--use-virustotal` | 是（`VIRUSTOTAL_API_KEY`） | 二進位惡意程式掃描 |

## 注意事項

- 靜態分析無需任何 API Key，可直接使用
- `--use-llm` 需設定環境變數 `SKILL_SCANNER_LLM_API_KEY`
- 本專案 Skill 均為純 Markdown，靜態分析即可覆蓋主要風險
- 建議定期執行（每週一次或新增 Skill 時）
- Windows 環境直接呼叫 `D:/Python311/Scripts/skill-scanner.exe`
