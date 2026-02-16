---
name: kb-curator
version: "1.0.0"
description: |
  知識庫治理工具。去重、品質評分、過期清理、主題分佈分析。
  Use when: 知識庫治理、KB 去重、筆記品質、過期清理、主題分佈。
allowed-tools: Read, Write, Bash
triggers:
  - "知識庫治理"
  - "KB 去重"
  - "筆記品質"
  - "過期清理"
  - "主題分佈"
  - "kb-curator"
---

# KB Curator Skill（知識庫治理工具）

提供知識庫的品質管理功能，確保 KB 內容不重複、不過時、品質一致。

## 功能模組

### 模組 A：去重掃描
1. 取得所有筆記列表：
```bash
curl -s "http://localhost:3000/api/notes?limit=200"
```
2. 兩階段去重：
   - **完全重複**：標題完全相同的筆記 → 保留最新的一筆
   - **近似重複**：使用 Python difflib 計算相似度
```bash
python -c "
import json, difflib
data = json.load(open('kb_all.json', encoding='utf-8'))
notes = data.get('notes', [])
titles = [n.get('title','') for n in notes]
dupes = []
for i in range(len(titles)):
    for j in range(i+1, len(titles)):
        ratio = difflib.SequenceMatcher(None, titles[i], titles[j]).ratio()
        if ratio > 0.85:
            dupes.append({'a': titles[i], 'b': titles[j], 'similarity': round(ratio,2)})
print(json.dumps(dupes, ensure_ascii=False, indent=2))
"
```
3. 輸出去重報告（不自動刪除，僅建議）

### 模組 B：品質評分
為每筆筆記計算品質分數：
| 因子 | 權重 | 說明 |
|------|------|------|
| 內容長度 | 20% | < 50 字 = 0分, 50-200 = 3分, > 200 = 5分 |
| 有標籤 | 20% | 0 標籤 = 0分, 1-2 = 3分, 3+ = 5分 |
| 有來源 | 20% | 無 = 0分, manual = 3分, web/import = 5分 |
| 最近更新 | 20% | > 90 天 = 1分, 30-90 = 3分, < 30 = 5分 |
| 有外部連結 | 20% | 無 = 0分, 有 = 5分 |

### 模組 C：過期清理建議
- 標記超過 180 天未更新且品質分 < 2 的筆記
- 輸出建議清理清單（不自動刪除）

### 模組 D：主題分佈分析
- 依標籤統計各主題筆記數量
- 識別過度集中的主題（佔比 > 30%）
- 識別覆蓋不足的主題

## 輸出格式
產出 JSON 報告至標準輸出或指定檔案。

## 安全邊界
- 僅分析和建議，不自動刪除任何筆記
- 透過 API 操作，不直接修改資料庫
