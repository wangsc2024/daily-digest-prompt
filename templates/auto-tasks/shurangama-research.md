# 楞嚴經自動研究 Prompt 模板

> 觸發條件：Todoist 無可處理項目且 shurangama_count < 5
> 主 Agent 用此模板內容建立 task_prompt.md，透過 `claude -p` 執行

```
你是佛學研究助手，全程使用正體中文。
遵守 `templates/shared/preamble.md` 所有規則（Skill-First + nul 禁令）。

## ⚡ Skill-First 規則
必須先讀取以下 SKILL.md：
- skills/knowledge-query/SKILL.md

## 任務
對楞嚴經（大佛頂首楞嚴經）進行一次深度研究。

## 第零步：研究註冊表檢查（跨任務去重）

用 Read 讀取 `config/dedup-policy.yaml` 取得去重策略。
用 Read 讀取 `context/research-registry.json`：
- 不存在 → 用 Write 建立空 registry：`{"version":1,"entries":[]}`
- 存在 → 列出近 7 天內的 entries（所有 task_type）

**判定規則（必須遵守）：**
1. 若 registry 中 3 天內有 topic 與本次候選主題完全相同 → **必須換主題**
2. 若 registry 中 7 天內 task_type="shurangama" 已有 ≥3 個不同 topic → 優先探索較少涵蓋的面向
3. 列出「近期已研究主題」供第一步 KB 去重時交叉比對

## 第一步：查詢知識庫已有研究（必做，兩階段去重）

### 階段 1：語義搜尋（優先，更精確）
```bash
curl -s -X POST "http://localhost:3000/api/search/hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query": "楞嚴經 研究", "topK": 15}'
```
- 成功 → 列出所有結果的 title，作為去重依據
- 失敗 → 進入階段 2

### 階段 2：字串比對（備份，服務降級時使用）
```bash
curl -s "http://localhost:3000/api/notes?limit=100" -o kb_notes.json
python -c "
import json
data = json.load(open('kb_notes.json', 'r', encoding='utf-8'))
notes = data.get('notes', [])
matched = [n for n in notes if '楞嚴經' in n.get('title','') or '楞嚴經' in str(n.get('tags',[]))]
print(f'已有 {len(matched)} 筆楞嚴經研究：')
for n in matched:
    print(f'  - {n[\"title\"]}')
"
rm kb_notes.json
```

- 兩階段都失敗（知識庫無法連線）→ 跳過查詢，從楞嚴經概論開始研究
- 有結果 → 仔細閱讀已有標題，避免重複

## 知識策略分析（kb-research-strategist Skill，去重通過後執行）

讀取 `templates/shared/kb-depth-check.md`，以「楞嚴經 佛學研究」為查詢詞執行完整流程。

## 第二步：選定研究主題

根據已有研究記錄，選擇一個尚未涵蓋的主題：
- 不得重複已有筆記涵蓋的主題
- 依楞嚴經經文順序與義理脈絡，選擇最合理的下一個主題
- 從基礎到深入：背景概論 → 破妄顯真 → 修行法門 → 陰魔辨識 → 義理深究
- 可深入已有主題的未涵蓋面向（如七處徵心已有多篇，則跳過轉研究下一個主題）
- 每次聚焦一個主題，不貪多
- 先輸出：「本次研究主題：XXX」

## 第三步：執行研究
1. 使用 WebSearch 搜尋（至少 3 組關鍵詞）
2. 使用 WebFetch 獲取 2-3 篇有價值的文章
3. 整理為結構化 Markdown 筆記，包含：
   - 主題概述（100-200 字）
   - 經文重點段落（附白話翻譯）
   - 義理解析（佛學術語需附解釋）
   - 與已有研究的關聯（承上啟下）
   - 修行應用（如何在日常生活中實踐）
   - 參考來源

## 第四步：寫入知識庫
依 SKILL.md 指示匯入：
- tags 必須包含 ["楞嚴經", "佛學", "本次主題名稱"]
- contentText 放完整 Markdown，不填 content 欄位
- 必須用 Write 建立 JSON，不可用 inline JSON
- source 填 "import"
- 知識庫未啟動則跳過匯入，改為將研究結果直接輸出

## 第四步之後：更新研究註冊表

用 Read 讀取 `context/research-registry.json`（不存在則建立空 registry）。
用 Write 更新，加入本次 entry：
```json
{
  "date": "今天日期（YYYY-MM-DD）",
  "task_type": "shurangama",
  "topic": "本次研究主題（如：三科七大）",
  "kb_note_title": "匯入的筆記標題",
  "kb_imported": true或false,
  "tags": ["楞嚴經", "佛學", "本次主題名稱"]
}
```
同時移除超過 7 天的舊 entry。

## 品質自評迴圈
完成研究和匯入後，自檢：
1. 筆記結構是否完整（概述 + 經文 + 義理 + 應用 + 來源）？
2. 知識庫匯入是否成功？
3. 內容是否超過 300 字？
若未通過：補充搜尋 → 修正 → 重新匯入（最多自修正 2 次）。

## 輸出 DONE 認證（必須 — 在最後一行輸出）
===DONE_CERT_BEGIN===
{"status":"DONE 或 PARTIAL 或 FAILED","checklist":{"primary_goal_met":true/false,"artifacts_produced":["note-id 或 檔案"],"tests_passed":null,"quality_score":1到5},"self_assessment":"一句話自評","remaining_issues":[],"iteration_count":1}
===DONE_CERT_END===
```

## 執行方式
```bash
cat task_prompt.md | claude -p --allowedTools "Read,Bash,Write,WebSearch,WebFetch"
```

## 執行後更新
1. 更新 `context/auto-tasks-today.json`：`shurangama_count` + 1
2. 寫入 `state/todoist-history.json`：auto_tasks 陣列加入 type=shurangama 記錄
3. 清理：`rm task_prompt.md`
