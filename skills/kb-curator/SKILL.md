---
name: kb-curator
version: "3.0.0"
description: |
  知識庫治理工具。去重、品質評分、過期清理、主題分佈分析、內容品質深度評分（四維度：非知識/完整性/保留價值/知識價值）。
  Use when: 知識庫治理、KB 去重、筆記品質、過期清理、主題分佈、知識庫清理、內容評分。
allowed-tools: Bash, Read, Write
cache-ttl: 0min
triggers:
  - "知識庫治理"
  - "KB 去重"
  - "筆記品質"
  - "過期清理"
  - "主題分佈"
  - "kb-curator"
  - "清理"
  - "重複筆記"
  - "品質檢查"
  - "知識庫清理"
  - "筆記統計"
  - "內容評分"
  - "非知識"
  - "不完整"
  - "content scoring"
depends-on:
  - "knowledge-query"
  - "groq"
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

### 模組 E：內容品質深度評分（v3 四維度）

> **配置檔**：`config/kb-content-scoring.yaml` v3（四維度：A 非知識 15%、B 完整性 15%、C 保留價值 35%、D 知識價值 35%）
> **規格文件**：`specs/kb-content-scoring/spec.md`
> **目的**：識別非知識、不完整、低保留價值、低知識含量的內容

#### Step 1：資料取得

取得所有筆記的 contentText（全量）：

```bash
curl -s "http://localhost:3000/api/notes?limit=500" > cache/kb_scoring_raw.json
```

用 Python 提取必要欄位，減少記憶體用量：

```bash
uv run python -X utf8 -c "
import json
with open('cache/kb_scoring_raw.json', encoding='utf-8') as f:
    data = json.load(f)
notes = []
for n in data.get('notes', []):
    notes.append({
        'id': n.get('id', ''),
        'title': n.get('title', ''),
        'contentText': n.get('contentText', ''),
        'tags': n.get('tags', []),
        'source': n.get('source', ''),
        'updatedAt': n.get('updatedAt', '')
    })
with open('cache/kb_scoring_notes.json', 'w', encoding='utf-8') as f:
    json.dump(notes, f, ensure_ascii=False, indent=2)
print(f'已提取 {len(notes)} 筆筆記')
"
```

#### Step 2：規則型全量評分（四維度 A+B+C+D，含訊息熵）

將以下完整腳本寫入 `cache/scoring_step2.py` 後執行（`uv run python -X utf8 cache/scoring_step2.py`）。

```python
import json, math, re
from collections import Counter

with open('cache/kb_scoring_notes.json', encoding='utf-8') as f:
    notes = json.load(f)

# ── 訊息熵計算 ──
def char_entropy(text):
    if len(text) < 50:
        return None
    counter = Counter(text)
    n = len(text)
    return round(-sum((c/n) * math.log2(c/n) for c in counter.values()), 2)

def redundancy(text):
    H = char_entropy(text)
    if H is None:
        return None
    unique = len(set(text))
    H_max = math.log2(unique) if unique > 1 else 1
    return round(1 - H / H_max, 3)

# ══════════════════════════════════════════════
# 維度 A：非知識訊號（滿分 30，6 子項各 5 分）
# ══════════════════════════════════════════════
PATTERNS_A = {
    'A1': r'TODO|TBD|待補充|待續|\.\.\.|___',
    'A2': r'請填寫|請補充|本模板|\{\{.*\}\}',
    'A3': r'完成時間|執行結果|步驟\s*\d|status:|exit_code',
}

def score_non_knowledge(text):
    scores = {}
    flags = []
    for aid, pat in PATTERNS_A.items():
        matches = len(re.findall(pat, text, re.IGNORECASE))
        if matches == 0:
            scores[aid] = 5
        elif matches == 1:
            scores[aid] = 1
            flags.append(f'{aid}: 命中 1 次')
        else:
            scores[aid] = 0
            flags.append(f'{aid}: 命中 {matches} 次')

    urls = re.findall(r'https?://[^\s)]+', text)
    text_no_urls = re.sub(r'https?://[^\s)]+', '', text).strip()
    if len(urls) > 3 and len(text_no_urls) < 50:
        scores['A4'] = 0
        flags.append('A4: 純連結無脈絡')
    elif len(urls) > 3:
        scores['A4'] = 2
    else:
        scores['A4'] = 5

    tlen = len(text.strip())
    if tlen < 30: scores['A5'] = 0
    elif tlen < 50: scores['A5'] = 1
    elif tlen < 100: scores['A5'] = 2
    elif tlen < 200: scores['A5'] = 4
    else: scores['A5'] = 5
    if tlen < 30:
        flags.append(f'A5: 僅 {tlen} 字')

    scores['A6'] = 5
    return scores, flags

# ══════════════════════════════════════════════
# 維度 B：完整性訊號（滿分 30，6 子項各 5 分）
# ══════════════════════════════════════════════
DEPTH_KEYWORDS = {
    'foundation': r'概念|定義|架構|簡介|總覽',
    'mechanism': r'原理|機制|演算法|內部|實作細節',
    'application': r'範例|實作|部署|案例|程式碼',
    'optimization': r'效能|優化|benchmark|最佳實踐|trade-off',
    'synthesis': r'整合|跨|連結|比較|未來展望',
}
DEPTH_SCORES = {'foundation': 1, 'mechanism': 2, 'application': 3, 'optimization': 4, 'synthesis': 5}

def score_completeness(text):
    scores = {}
    flags = []

    headings = len(re.findall(r'^#{2,}', text, re.MULTILINE))
    lists = len(re.findall(r'^\s*[-*]|^\s*\d+\.', text, re.MULTILINE))
    if headings >= 3 and lists >= 3: scores['B1'] = 5
    elif headings >= 1 and lists >= 1: scores['B1'] = 4
    elif headings >= 1 or lists >= 1: scores['B1'] = 2
    else:
        scores['B1'] = 0
        flags.append('B1: 無結構')

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    n_para = len(paragraphs)
    avg_len = sum(len(p) for p in paragraphs) / max(n_para, 1)
    H = char_entropy(text)
    R = redundancy(text)

    b2 = 5
    if n_para < 2:
        b2 = min(b2, 1)
        flags.append(f'B2: 段落數不足({n_para})')
    if avg_len < 40:
        b2 = min(b2, 2)
    if H is not None:
        if H < 7:
            b2 = min(b2, 1)
            flags.append(f'B2: 字元熵偏低({H})')
        elif H > 12:
            b2 = min(b2, 2)
            flags.append(f'B2: 字元熵偏高({H})')
    if R is not None and R > 0.5:
        b2 = min(b2, 2)
        flags.append(f'B2: 冗餘度偏高({R})')
    scores['B2'] = b2

    concept_kw = len(re.findall(r'是|即|指|定義|說明|意指|原理|概念|機制|方法', text))
    if concept_kw >= 3: scores['B3'] = 4
    elif concept_kw >= 1: scores['B3'] = 2
    else:
        scores['B3'] = 0
        flags.append('B3: 無定義性語言')

    refs = len(re.findall(r'\[\d+\]|參考|來源|引用|https?://|\[\[', text))
    if refs >= 2: scores['B4'] = 5
    elif refs >= 1: scores['B4'] = 3
    else:
        scores['B4'] = 0
        flags.append('B4: 無引用來源')

    best_depth = 'none'
    for stage in ['synthesis', 'optimization', 'application', 'mechanism', 'foundation']:
        if re.search(DEPTH_KEYWORDS[stage], text):
            best_depth = stage
            break
    scores['B5'] = DEPTH_SCORES.get(best_depth, 0)
    if best_depth == 'none':
        flags.append('B5: 無深度關鍵字')

    tail = text[-100:] if len(text) >= 100 else text
    if re.search(r'待續|\.\.\.$|\(未完\)|\(to be continued\)', tail, re.IGNORECASE):
        scores['B6'] = 0
        flags.append('B6: 結尾不完整')
    else:
        scores['B6'] = 5

    return scores, flags, {'H': H, 'R': R, 'paragraphs': n_para, 'avg_paragraph_len': round(avg_len)}

# ══════════════════════════════════════════════
# 維度 C：保留價值（滿分 30，6 子項各 5 分）
# ══════════════════════════════════════════════
DERIVED_PATTERNS = {
    'podcast_script': r'主持人\s*[A-Z（]|Podcast\s*腳本|對話腳本|雙主持人',
    'auto_generated': r'生成時間|自動生成|Auto-generated|輸出：.*\.mp3|輸出：.*\.wav',
    'translation': r'^翻譯稿|^譯文|原文：|Original:',
}
OTHER_CARRIER = r'\.mp3|\.wav|\.pdf|\.docx|output.*podcasts|output.*audio'
CONVERSATIONAL = [
    r'你好|歡迎來到|今天我們|聽眾朋友',
    r'哇|嗯|對[！!]|沒錯|好問題',
    r'節目|下一集|本集|收聽',
]
LOW_TITLE = r'^Podcast\s*腳本：note-|^翻譯：note-|^note-[0-9a-f]|^untitled'
TASK_TITLE = r'^將.*匯出|^根據.*撰寫|^收集並|^蒐集.*並|^進行.*蒐集|^提供一份|^於今天.*提出|^\[WORKDIR'
MID_TITLE = r'^Podcast\s*腳本：[^n]'
FORMAT_CONV = r'改寫|腳本化|口語化|對話化|將.*轉為|based on note'
ORIGINAL_SIG = r'研究發現|分析結果|本文提出|本研究|歸納|比較分析|系統整理'
WORKFLOW_ARTIFACT = r'前置步驟\s*s?\d|前置步驟.*結果|\[前置步驟|執行摘要|驗收條件.*通過|所有.*均已通過'
WORKFLOW_CHANGELOG = r'## 優化概述|## 優化項目|### 問題\n|### 解法\n|### 效益'
WORKFLOW_TASK_RESULT = r'✅.*完成|✅.*執行|📚.*主要發現|任務完成|task completed'

def score_retention_value(title, text):
    scores = {}
    flags = []

    # C.1：衍生內容偵測
    derived_hit = False
    for name, pat in DERIVED_PATTERNS.items():
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            derived_hit = True
            flags.append(f'C1: 衍生內容({name})')
            break
    scores['C1'] = 0 if derived_hit else 5

    # C.2：已有其他載體
    if re.search(OTHER_CARRIER, text, re.IGNORECASE):
        scores['C2'] = 0
        flags.append('C2: 已有其他載體(mp3/pdf/docx)')
    else:
        scores['C2'] = 5

    # C.3：可檢索參考價值（口語化比例）
    conv_count = sum(len(re.findall(p, text)) for p in CONVERSATIONAL)
    total_chars = max(len(text), 1)
    conv_ratio = conv_count * 5 / total_chars
    if conv_ratio > 0.03:
        scores['C3'] = 0
        flags.append(f'C3: 口語化比例高({conv_count} 次)')
    elif conv_ratio > 0.01:
        scores['C3'] = 2
        flags.append(f'C3: 口語化比例中({conv_count} 次)')
    else:
        scores['C3'] = 5

    # C.4：原創獨立價值（含工作流程中間產物偵測）
    if re.search(FORMAT_CONV, text, re.IGNORECASE):
        scores['C4'] = 0
        flags.append('C4: 格式轉換非原創')
    elif re.search(WORKFLOW_ARTIFACT, text, re.MULTILINE):
        scores['C4'] = 0
        flags.append('C4: 工作流程中間產物')
    elif re.search(ORIGINAL_SIG, text):
        scores['C4'] = 5
    else:
        scores['C4'] = 3

    # C.5：標題資訊性（含任務指令型偵測）
    if re.search(LOW_TITLE, title, re.IGNORECASE):
        scores['C5'] = 0
        flags.append('C5: 標題為 ID/代號')
    elif re.search(TASK_TITLE, title, re.IGNORECASE):
        scores['C5'] = 0
        flags.append('C5: 標題為任務指令')
    elif re.search(MID_TITLE, title, re.IGNORECASE):
        scores['C5'] = 2
        flags.append('C5: 標題有前綴')
    else:
        scores['C5'] = 5

    # C.6：工作流程中間產物（Agent 執行結果/變更紀錄/commit log）
    wf_hit = False
    for pat in [WORKFLOW_ARTIFACT, WORKFLOW_CHANGELOG, WORKFLOW_TASK_RESULT]:
        if re.search(pat, text, re.MULTILINE):
            wf_hit = True
            break
    if wf_hit:
        scores['C6'] = 0
        flags.append('C6: 工作流程/變更紀錄')
    else:
        scores['C6'] = 5

    return scores, flags, derived_hit

# ══════════════════════════════════════════════
# 維度 D：知識價值（滿分 25，5 子項各 5 分）
# ══════════════════════════════════════════════
PROJ_SPEC = r'daily-digest-prompt|D:\\Source|C:\\Users|D:/Source|hook_utils|post_tool_logger|kb_scoring|groq-relay|run-agent|run-todoist|HEARTBEAT\.md'
GENERAL_KW = r'理論|原理|方法論|框架|模式|策略|思想|哲學|歷史|比較|分析|研究|文獻'
EXPLAIN_KW = r'因為|因此|所以|原因|這是因為|其原理|之所以|本質上|換言之|意味著|根本原因|背後|邏輯是'
PROCED_KW = r'先|然後|接著|最後|步驟|執行|完成|建立|修改|更新|刪除|部署|安裝|設定|啟動'
DATE_KW = r'2026-\d{2}-\d{2}|20260\d{5}|今天|昨天|明天|今日|本週|上週|本月'
TIME_KW = r'於.*\d{1,2}[：:]\d{2}|\d{1,2}點|今天\s*\d'
REUSE_KW = r'什麼是|如何|為什麼|常見|最佳實踐|完整指南|深度分析|研究報告|文獻回顧'
ONETIME_KW = r'## 任務|## 執行結果|## 優化項目|## 變更|修正紀錄|commit|PR #|issue #'
KNOW_KW = r'概念|原理|方法|技術|框架|模式|策略|理論|思想|哲學|傳統|分析|研究|比較|歷史|演進|文獻|學術|定義|分類|系統|體系|脈絡'
OPER_KW = r'執行|完成|建立|修改|更新|刪除|部署|安裝|設定|啟動|修正|優化|重構|遷移|備份|測試|驗證|輸出|匯出|匯入'

def score_knowledge_value(title, text):
    scores = {}
    flags = []

    # D.1：通用性
    ps_count = len(re.findall(PROJ_SPEC, text, re.IGNORECASE))
    gk_count = len(re.findall(GENERAL_KW, text))
    if ps_count >= 5:
        scores['D1'] = 0; flags.append(f'D1: 專案特定({ps_count}次)')
    elif ps_count >= 1 and gk_count <= ps_count:
        scores['D1'] = 1; flags.append(f'D1: 偏專案({ps_count}vs{gk_count})')
    elif gk_count > ps_count * 2:
        scores['D1'] = 5
    elif gk_count > ps_count:
        scores['D1'] = 4
    elif gk_count >= 1:
        scores['D1'] = 3
    else:
        scores['D1'] = 2

    # D.2：解釋深度
    ex_count = len(re.findall(EXPLAIN_KW, text))
    pr_count = len(re.findall(PROCED_KW, text))
    if ex_count > pr_count and ex_count >= 3:
        scores['D2'] = 5
    elif ex_count > 0 and ex_count >= pr_count:
        scores['D2'] = 3
    elif pr_count > 0 and ex_count > 0:
        scores['D2'] = 1
    else:
        scores['D2'] = 0 if pr_count > 0 else 2
        if pr_count > ex_count * 2:
            flags.append(f'D2: 程序主導({pr_count}vs{ex_count})')

    # D.3：時效獨立性
    date_count = len(re.findall(DATE_KW, text))
    time_count = len(re.findall(TIME_KW, text))
    total_time = date_count + time_count
    title_has_date = bool(re.search(r'2026-\d{2}-\d{2}|20260\d{5}', title))
    if total_time >= 3 or title_has_date:
        scores['D3'] = 0; flags.append(f'D3: 時效綁定({total_time})')
    elif total_time >= 1:
        scores['D3'] = 3
    else:
        scores['D3'] = 5

    # D.4：複用潛力
    reuse_count = len(re.findall(REUSE_KW, text))
    onetime_count = len(re.findall(ONETIME_KW, text, re.MULTILINE))
    if reuse_count > onetime_count and reuse_count >= 2:
        scores['D4'] = 5
    elif reuse_count > 0 and onetime_count == 0:
        scores['D4'] = 4
    elif reuse_count > 0 and onetime_count > 0:
        scores['D4'] = 3
    elif onetime_count > 0:
        scores['D4'] = 0; flags.append(f'D4: 一次性({onetime_count})')
    else:
        scores['D4'] = 3

    # D.5：知識密度
    kn_count = len(re.findall(KNOW_KW, text))
    op_count = len(re.findall(OPER_KW, text))
    if kn_count > op_count * 2 and kn_count >= 5:
        scores['D5'] = 5
    elif kn_count > op_count:
        scores['D5'] = 4
    elif kn_count > 0 and op_count > 0 and abs(kn_count - op_count) <= 3:
        scores['D5'] = 3
    elif op_count > kn_count:
        scores['D5'] = 1; flags.append(f'D5: 操作>知識({op_count}vs{kn_count})')
    elif op_count > kn_count * 2:
        scores['D5'] = 0
    else:
        scores['D5'] = 2

    return scores, flags

# ══════════════════════════════════════════════
# 校準 Hard Caps
# ══════════════════════════════════════════════
def apply_calibration(text, dim_a_raw, dim_b_raw, dim_c_raw, c_derived_hit, c2_hit):
    max_total = 100

    if len(text.strip()) < 30:
        max_total = 20

    if re.search(r'TODO|TBD|待補充', text, re.IGNORECASE):
        dim_a_raw = max(0, dim_a_raw - 15)

    if not re.search(r'^#{2,}', text, re.MULTILINE) and not re.search(r'^\s*[-*]', text, re.MULTILINE):
        dim_b_raw = min(dim_b_raw, 40)

    H = char_entropy(text)
    if H is not None and H < 5:
        dim_a_raw = max(0, dim_a_raw - 10)

    # C 維度 hard cap：衍生內容 → C 總分上限 10
    if c_derived_hit:
        dim_c_raw = min(dim_c_raw, 10)

    # 衍生 + 已有載體 → 總分上限 35
    if c_derived_hit and c2_hit:
        max_total = min(max_total, 35)

    return max(0, dim_a_raw), max(0, dim_b_raw), max(0, dim_c_raw), max_total

# ══════════════════════════════════════════════
# 等級判定（v2 門檻）
# ══════════════════════════════════════════════
GRADES = [('S',90),('A',75),('B',60),('C',45),('D',30),('F',0)]
ACTIONS = {'S':'可作為範本','A':'保留','B':'保留，可優化','C':'建議優化補強','D':'低價值，建議歸檔或刪除','F':'無保留價值，優先刪除'}
def grade_for(score):
    for g, m in GRADES:
        if score >= m:
            return g, ACTIONS[g]
    return 'F', ACTIONS['F']

# ══════════════════════════════════════════════
# 主迴圈
# ══════════════════════════════════════════════
results = []
for note in notes:
    text = note.get('contentText', '')
    title = note.get('title', '')

    a_scores, a_flags = score_non_knowledge(text)
    b_scores, b_flags, entropy_info = score_completeness(text)
    c_scores, c_flags, c_derived_hit = score_retention_value(title, text)
    d_scores, d_flags = score_knowledge_value(title, text)

    # 維度原始分：(子項合計 / 子項滿分) * 權重
    dim_a_raw = sum(a_scores.values()) / 30 * 15   # A: 15%
    dim_b_raw = sum(b_scores.values()) / 30 * 15   # B: 15%
    dim_c_raw = sum(c_scores.values()) / 30 * 35   # C: 35%（6 子項，滿分 30）
    dim_d_raw = sum(d_scores.values()) / 25 * 35   # D: 35%（5 子項，滿分 25）

    c2_hit = c_scores.get('C2', 5) == 0
    dim_a, dim_b, dim_c, max_total = apply_calibration(text, dim_a_raw, dim_b_raw, dim_c_raw, c_derived_hit, c2_hit)
    dim_d = max(0, dim_d_raw)

    total = min(round(dim_a + dim_b + dim_c + dim_d), max_total)
    grade, action = grade_for(total)

    results.append({
        'note_id': note['id'],
        'title': title,
        'total_score': total,
        'grade': grade,
        'dimensions': {
            'non_knowledge': {'score': round(dim_a), 'raw': round(dim_a_raw, 1), 'details': a_scores, 'flags': a_flags},
            'completeness': {'score': round(dim_b), 'raw': round(dim_b_raw, 1), 'details': b_scores, 'flags': b_flags},
            'retention_value': {'score': round(dim_c), 'raw': round(dim_c_raw, 1), 'details': c_scores, 'flags': c_flags},
            'knowledge_value': {'score': round(dim_d), 'raw': round(dim_d_raw, 1), 'details': d_scores, 'flags': d_flags}
        },
        'entropy': entropy_info,
        'llm': {'used': False},
        'action': action,
        'non_knowledge_flag_count': len(a_flags),
        'retention_flag_count': len(c_flags),
        'knowledge_flag_count': len(d_flags)
    })

with open('cache/kb_scoring_heuristic.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

low = [r for r in results if r['total_score'] < 45 or r['non_knowledge_flag_count'] >= 2 or r['retention_flag_count'] >= 3 or r['knowledge_flag_count'] >= 3]
print(f'全量評分完成：{len(results)} 筆，低分/邊界：{len(low)} 筆需 LLM 抽樣')
for g, m in GRADES:
    cnt = sum(1 for r in results if r['grade'] == g)
    if cnt > 0:
        print(f'  {g}: {cnt} 筆')
```

#### Step 3：LLM 抽樣評分

先確認 Groq Relay 可用：
```bash
curl -s --max-time 3 http://localhost:3002/groq/health
```

- 若 Relay 可用 → 篩選 `total_score < 45` 或 `non_knowledge_flag_count >= 2` 或 `retention_flag_count >= 3` 的筆記
- 逐筆呼叫（最多 20 筆，間隔 13 秒）：

```bash
# 用 Write 工具建立 /tmp/groq-kb-score.json：
# {"mode": "kb_score", "content": "<contentText 前 2000 字>"}
curl -s --max-time 20 -X POST http://localhost:3002/groq/chat \
  -H "Content-Type: application/json; charset=utf-8" \
  -d @/tmp/groq-kb-score.json
```

回傳 JSON 格式：
```json
{
  "result": {
    "concept_count": 5,
    "depth_level": "mechanism",
    "info_density": "medium",
    "is_knowledge": true,
    "is_derived": false,
    "retention_value": "high",
    "issues": ["缺少來源引用"]
  }
}
```

將 LLM 結果合併到對應筆記的評分中，更新 B.3/B.5 與 C.1/C.4 分數。

- 若 Relay 不可用 → 記錄 `llm_skipped: true`，使用規則評分結果

#### Step 4：報告產出

將以下完整腳本寫入 `cache/scoring_step4.py` 後執行。

```python
import json
from datetime import datetime, timezone, timedelta

with open('cache/kb_scoring_heuristic.json', encoding='utf-8') as f:
    results = json.load(f)

tz = timezone(timedelta(hours=8))
now = datetime.now(tz).isoformat()

dist = {}
for r in results:
    g = r['grade']
    dist[g] = dist.get(g, 0) + 1

non_knowledge = [{'note_id': r['note_id'], 'title': r['title'], 'score': r['total_score'],
                   'flags': r['dimensions']['non_knowledge']['flags']}
                  for r in results if r['grade'] == 'F']

low_retention = [{'note_id': r['note_id'], 'title': r['title'], 'score': r['total_score'],
                   'flags': r['dimensions']['retention_value']['flags'],
                   'c_score': r['dimensions']['retention_value']['score']}
                  for r in results if r['dimensions']['retention_value']['score'] <= 10]

incomplete = [{'note_id': r['note_id'], 'title': r['title'], 'score': r['total_score'],
               'gaps': r['dimensions']['completeness']['flags']}
              for r in results if r['grade'] == 'D']

entropy_anomalies = [{'note_id': r['note_id'], 'title': r['title'],
                       'H': r['entropy'].get('H'), 'R': r['entropy'].get('R')}
                      for r in results
                      if r['entropy'].get('H') is not None and (r['entropy']['H'] < 7 or r['entropy']['H'] > 12)]

llm_scored = [r for r in results if r.get('llm', {}).get('used')]

low_knowledge = [{'note_id': r['note_id'], 'title': r['title'], 'score': r['total_score'],
                   'flags': r['dimensions']['knowledge_value']['flags'],
                   'd_score': r['dimensions']['knowledge_value']['score']}
                  for r in results if r['dimensions']['knowledge_value']['score'] <= 10]

report = {
    'generated_at': now,
    'version': 3,
    'scoring_dimensions': 'A(non_knowledge 15%) + B(completeness 15%) + C(retention_value 35%) + D(knowledge_value 35%)',
    'total_notes': len(results),
    'score_distribution': dist,
    'avg_score': round(sum(r['total_score'] for r in results) / max(len(results), 1)),
    'non_knowledge_candidates': non_knowledge,
    'low_retention_candidates': low_retention,
    'low_knowledge_candidates': low_knowledge,
    'incomplete_candidates': incomplete,
    'entropy_anomalies': entropy_anomalies,
    'llm_summary': {
        'scored': len(llm_scored),
        'skipped': len(results) - len(llm_scored),
    },
    'recommendations': [
        {'action': 'delete', 'count': len(non_knowledge), 'criteria': 'grade F (無保留價值)'},
        {'action': 'archive_or_delete', 'count': len(low_retention), 'criteria': 'retention_value score <= 10 (衍生/過渡內容)'},
        {'action': 'review_knowledge', 'count': len(low_knowledge), 'criteria': 'knowledge_value score <= 10 (低知識含量)'},
        {'action': 'enrich_or_archive', 'count': len(incomplete), 'criteria': 'grade D (低價值)'},
        {'action': 'review_entropy', 'count': len(entropy_anomalies), 'criteria': 'entropy anomaly'},
    ],
    'per_note_scores': results
}

with open('results/kb-content-score-report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f'報告已輸出至 results/kb-content-score-report.json')
print(f'總筆記：{len(results)}')
print(f'分布：{dist}')
print(f'非知識候選（F）：{len(non_knowledge)} 筆')
print(f'低保留價值候選：{len(low_retention)} 筆')
print(f'低知識價值候選：{len(low_knowledge)} 筆')
print(f'不完整候選（D）：{len(incomplete)} 筆')
print(f'熵異常：{len(entropy_anomalies)} 筆')
```

#### 清理暫存檔

```bash
Remove-Item cache/kb_scoring_raw.json, cache/kb_scoring_notes.json, cache/kb_scoring_heuristic.json, cache/scoring_step2.py, cache/scoring_step4.py -Force -ErrorAction SilentlyContinue
```

## 執行流程

1. 先確認知識庫服務可用：`curl -s http://localhost:3000/api/health`
2. 依序執行模組 A → B → C → D → E（可選擇只執行部分模組）
3. 彙整結果為 JSON 報告
4. 若為自動任務，將報告匯入知識庫（透過 knowledge-query Skill）

> **單獨執行模組 E**：若只需內容評分，可跳過 A-D，直接執行模組 E。

## 輸出格式

```json
{
  "generated_at": "ISO timestamp",
  "total_notes": 150,
  "duplicates": {"exact": 2, "similar": 5, "details": [...]},
  "quality": {"avg_score": 3.2, "low_quality_count": 10},
  "expired": {"candidates": 3, "details": [...]},
  "distribution": {"top_tags": {...}, "over_concentrated": [...], "under_represented": [...]}
}
```

## 錯誤處理
- 知識庫服務未啟動 → 記錄錯誤並結束，不中斷 Agent 主流程
- API 回應超時 → 重試 1 次（間隔 5 秒），仍失敗則跳過
- 筆記數量為 0 → 輸出空報告，不報錯

## 批次導入後清理

批次導入（如大量匯入 `cache/notes_temp.json`）完成後，必須清理暫存檔，避免 cache/ 目錄累積大型檔案：

```bash
# 批次導入完成後執行
rm -f cache/notes_temp.json
```

如 `cache/generate_site.py` 或其他非快取用途的腳本出現在 cache/ 目錄，請移至 `tools/` 目錄：
```bash
mv cache/generate_site.py tools/generate_site.py
```

## 安全邊界
- 僅分析和建議，不自動刪除任何筆記
- 透過 API 操作，不直接修改資料庫
