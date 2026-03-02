## 知識策略分析（kb-research-strategist，去重通過後執行）

### Phase A：執行 Skill

讀取 `skills/kb-research-strategist/SKILL.md`，以本次候選研究主題為查詢詞執行全部步驟（0–5）。
結果輸出至 `context/kb-research-brief.json`。

### Phase B：讀取研究簡報，調整計畫

Read `context/kb-research-brief.json`，依 `recommendation` 決定：

**`"deepen"` 或 `"series_continue"`**：
- 採用 `research_plan.primary_question` 作為核心研究問題
- 依 `research_plan.steps` 執行（使用各步驟的 `search_keywords`）
- 研究報告引言加入：「本文為 [series.series_id] 系列第 [series.current_stage] 階段，
  承接 [kb_foundation.covered_concepts]，深入探討 [knowledge_gaps[0].gap]」
- KB 匯入使用 `kb_enrichment_plan.tags`，contentText 含 `references_from_existing` 交叉引用

**`"explore_new"`**：
- 按原計畫自由選題，但 Skill 已開新系列（foundation 階段）
- 研究完成後仍須執行 Phase C 更新系列

**`"skip_kb_down"`**：
- KB 不可用，但若有現有系列則依系列計畫執行
- 無系列時按原有去重結果自由選題

### Phase C：研究完成後更新系列狀態

讀取 `context/kb-research-brief.json` 的 `series_update` 欄位。

```bash
python -X utf8 -c "
import json
from datetime import date

with open('context/research-series.json', 'r', encoding='utf-8') as f:
    series_data = json.load(f)

with open('context/kb-research-brief.json', 'r', encoding='utf-8') as f:
    brief = json.load(f)

su = brief.get('series_update', {})
sid = su.get('series_id')
stage = su.get('stage_to_update')
new_status = su.get('new_status', 'in_progress')
note_title = brief.get('research_plan', {}).get('kb_enrichment_plan', {}).get('new_note_title', '')
new_concepts = brief.get('kb_foundation', {}).get('missing_concepts', [])

if sid and sid in series_data.get('series', {}):
    s = series_data['series'][sid]
    stages = s.get('stages', {})
    if stage and stage in stages:
        stages[stage]['status'] = new_status
        if new_status == 'completed':
            stages[stage]['completed_at'] = str(date.today())
        if note_title:
            stages[stage].setdefault('kb_notes', []).append(note_title)
        if new_concepts:
            stages[stage].setdefault('covered_concepts', []).extend(new_concepts)
    stage_order = ['foundation', 'mechanism', 'application', 'optimization', 'synthesis']
    completed = sum(1 for st in stage_order if stages.get(st, {}).get('status') == 'completed')
    s['completion_pct'] = completed * 20
    s['last_active'] = str(date.today())
    if su.get('next_stage_hint'):
        s['next_research_hint'] = su['next_stage_hint']
    # 推進 current_stage
    if new_status == 'completed' and stage in stage_order:
        idx = stage_order.index(stage)
        if idx + 1 < len(stage_order):
            next_stage = stage_order[idx + 1]
            s['current_stage'] = next_stage
            if next_stage not in stages:
                stages[next_stage] = {'status': 'pending'}
elif sid:
    # 新系列：始終從 foundation 階段開始（SKILL.md 情境 C）
    # current_stage 依據 foundation 實際完成狀態決定，不以 note_title 是否存在做判斷
    foundation_status = new_status if stage == 'foundation' else 'pending'
    foundation_stage = {
        'status': foundation_status,
        'started_at': str(date.today()),
        'kb_notes': [note_title] if note_title else [],
        'covered_concepts': []
    }
    if foundation_status == 'completed':
        foundation_stage['completed_at'] = str(date.today())
    current_stage = 'mechanism' if foundation_status == 'completed' else 'foundation'
    series_data.setdefault('series', {})[sid] = {
        'series_id': sid,
        'domain': brief.get('research_topic', sid),
        'description': '',
        'initiated_at': str(date.today()),
        'last_active': str(date.today()),
        'tags': brief.get('series', {}).get('tags', []),
        'stages': {
            'foundation': foundation_stage,
            'mechanism': {'status': 'pending'},
            'application': {'status': 'pending'},
            'optimization': {'status': 'pending'},
            'synthesis': {'status': 'pending'}
        },
        'current_stage': current_stage,
        'completion_pct': 20 if foundation_status == 'completed' else 0,
        'related_series': [],
        'next_research_hint': su.get('next_stage_hint', '')
    }

from datetime import datetime, timezone, timedelta
tz = timezone(timedelta(hours=8))
series_data['updated_at'] = datetime.now(tz).isoformat()

with open('context/research-series.json', 'w', encoding='utf-8') as f:
    json.dump(series_data, f, ensure_ascii=False, indent=2)

print('research-series.json 已更新')
"
```

### Phase D：清理

```bash
rm context/kb-research-brief.json
```
