#!/usr/bin/env python3
"""
tools/score-kb-notes.py
知識庫筆記品質評分工具

輸入：從 KB API (localhost:3000) 查詢所有筆記
輸出：state/kb-note-scores.json（30 日滾動窗口）

評分維度（共 100 分）：
  content_length    (0-25)：內容字數，1000+ = 滿分
  structure_quality (0-20)：結構品質（標題/列表/表格/程式碼區塊）
  source_citation   (0-20)：來源引用數量與多樣性
  podcast_suit      (0-20)：播客適合度（敘述句/對話感/非純程式碼）
  recency           (0-15)：新舊程度（7 天內 = 高分）

使用方式：
    uv run python tools/score-kb-notes.py
    uv run python tools/score-kb-notes.py --top 10         # 只輸出前 10 名
    uv run python tools/score-kb-notes.py --limit 100      # 查詢最多 100 筆
"""

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── 設定 ────────────────────────────────────────────────
PROJECT_DIR   = Path(__file__).parent.parent
SCORES_PATH   = PROJECT_DIR / "state" / "kb-note-scores.json"
try:
    from tools.config_loader import get_kb_api_base
    KB_API_BASE = get_kb_api_base()
except ImportError:
    KB_API_BASE = "http://localhost:3000"
ROLLING_DAYS  = 30
DEFAULT_LIMIT = 200


# ─── 評分函式 ─────────────────────────────────────────────

def score_content_length(text: str) -> int:
    """(0-25) 內容長度：字元數越多，品質越高"""
    n = len(text.strip())
    if n >= 1500: return 25
    if n >= 800:  return 18
    if n >= 400:  return 11
    if n >= 100:  return 5
    return 0


def score_structure_quality(text: str) -> int:
    """(0-20) 結構品質：有 Markdown 格式元素表示筆記組織完整"""
    pts = 0
    if re.search(r'^#{1,3}\s', text, re.MULTILINE): pts += 8   # 標題
    if re.search(r'^\s*[-*]\s', text, re.MULTILINE): pts += 5  # 無序列表
    if re.search(r'^\s*\d+\.\s', text, re.MULTILINE): pts += 4 # 有序列表
    if re.search(r'\|\s.+\s\|', text): pts += 3                # 表格
    return min(pts, 20)


def score_source_citation(text: str) -> int:
    """(0-20) 來源引用：引用越多越可信"""
    urls = set(re.findall(r'https?://[^\s\)\"\'<>]+', text))
    n = len(urls)
    if n >= 4: return 20
    if n >= 2: return 13
    if n >= 1: return 7
    return 0


def score_podcast_suitability(text: str, title: str = "") -> int:
    """(0-20) 播客適合度：敘述性強、有對話感、非純程式碼"""
    pts = 0

    # 敘述句數量（中文句號/問號/驚嘆號）
    cn_sentences = len(re.findall(r'[。！？]', text))
    en_sentences = len(re.findall(r'[.!?]\s', text))
    sentences = cn_sentences + en_sentences
    if sentences >= 15: pts += 10
    elif sentences >= 8: pts += 7
    elif sentences >= 3: pts += 4

    # 對話友善關鍵詞
    dialogue_kw = ['研究', '發現', '表示', '認為', '建議', '重要', '關鍵',
                   '應用', '實踐', '影響', '分析', '解釋', '說明', '例如']
    matches = sum(1 for kw in dialogue_kw if kw in text)
    pts += min(matches * 1, 6)

    # 扣分：程式碼區塊過多（純程式碼筆記不適合口播）
    code_blocks = text.count('```')
    if code_blocks >= 6: pts -= 8
    elif code_blocks >= 3: pts -= 3

    # 加分：有標題（適合介紹段）
    if title and len(title) > 4: pts += 4

    return max(0, min(pts, 20))


def score_recency(created_at: str) -> int:
    """(0-15) 新舊程度：越新越優先進入播客"""
    try:
        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days_old = (datetime.now(timezone.utc) - dt).days
        if days_old <= 1:   return 15
        if days_old <= 3:   return 13
        if days_old <= 7:   return 10
        if days_old <= 30:  return 6
        return 2
    except Exception:
        return 5


def score_note(note: dict) -> dict:
    """對單筆筆記評分，回傳帶 total 的評分結果。"""
    title   = note.get('title', '')
    content = note.get('contentText', note.get('content_text', ''))
    if isinstance(content, dict):
        # Tiptap JSON 格式：提取純文字
        content = json.dumps(content, ensure_ascii=False)

    created_at = (note.get('createdAt') or note.get('created_at') or
                  note.get('updatedAt') or note.get('updated_at') or '')

    dims = {
        'content_length':    score_content_length(content),
        'structure_quality': score_structure_quality(content),
        'source_citation':   score_source_citation(content),
        'podcast_suit':      score_podcast_suitability(content, title),
        'recency':           score_recency(created_at),
    }
    total = sum(dims.values())
    return {
        'note_id':    note.get('id', ''),
        'title':      title,
        'total':      total,
        'dims':       dims,
        'scored_at':  datetime.now(timezone.utc).isoformat(),
        'created_at': created_at,
        'tags':       note.get('tags', []),
    }


# ─── KB API 查詢 ────────────────────────────────────────────

def fetch_notes(limit: int = DEFAULT_LIMIT) -> list[dict]:
    """從 KB API 查詢筆記（GET /api/notes）。"""
    url = f"{KB_API_BASE}/api/notes?limit={limit}&sort=createdAt&order=desc"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode('utf-8'))
            # 相容多種回傳格式
            if isinstance(raw, list):
                return raw
            return raw.get('data', raw.get('notes', raw.get('results', [])))
    except urllib.error.URLError as e:
        print(f"[ERROR] KB API 連線失敗 ({KB_API_BASE}): {e}")
        return []
    except Exception as e:
        print(f"[ERROR] 查詢筆記失敗: {e}")
        return []


def check_kb_health() -> bool:
    """確認 KB API 服務存活。"""
    try:
        req = urllib.request.Request(f"{KB_API_BASE}/api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# ─── 滾動窗口管理 ────────────────────────────────────────────

def load_scores() -> dict:
    if SCORES_PATH.exists():
        try:
            return json.loads(SCORES_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"version": 1, "scored_at": "", "notes": [], "top_10": []}


def save_scores(data: dict):
    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ─── 主程式 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="知識庫筆記品質評分")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"查詢筆記數量上限（預設 {DEFAULT_LIMIT}）")
    parser.add_argument("--top", type=int, default=10,
                        help="輸出前 N 名筆記（預設 10）")
    parser.add_argument("--json", action="store_true",
                        help="輸出 JSON 格式（供其他工具讀取）")
    args = parser.parse_args()

    # 健康檢查
    if not check_kb_health():
        print("[WARN] KB API 服務未啟動，跳過評分")
        return

    # 查詢筆記
    print(f"[INFO] 查詢 KB 筆記（上限 {args.limit} 筆）...")
    notes = fetch_notes(limit=args.limit)
    if not notes:
        print("[WARN] 未取得任何筆記")
        return
    print(f"[INFO] 取得 {len(notes)} 筆筆記，開始評分...")

    # 評分
    scored = []
    for note in notes:
        try:
            scored.append(score_note(note))
        except Exception as e:
            print(f"[WARN] 評分失敗 ({note.get('id','?')}): {e}")

    # 排序
    scored.sort(key=lambda x: x['total'], reverse=True)

    # 更新滾動窗口
    cutoff = datetime.now(timezone.utc) - timedelta(days=ROLLING_DAYS)
    existing = load_scores()
    old_notes = [n for n in existing.get('notes', [])
                 if n.get('note_id') not in {s['note_id'] for s in scored}
                 and _parse_dt(n.get('scored_at', '')) >= cutoff]

    all_scored = scored + old_notes
    all_scored.sort(key=lambda x: x['total'], reverse=True)

    result = {
        "version":  1,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "total_notes": len(all_scored),
        "top_10":   all_scored[:10],
        "notes":    all_scored,
    }
    save_scores(result)
    print(f"[INFO] 評分完成，共 {len(all_scored)} 筆，已存入 {SCORES_PATH}")

    # 輸出結果
    top_n = all_scored[:args.top]
    if args.json:
        print(json.dumps(top_n, ensure_ascii=False, indent=2))
    else:
        print(f"\n📊 Top {args.top} 筆記（播客適合度排行）:")
        print("-" * 72)
        for i, n in enumerate(top_n, 1):
            d = n['dims']
            print(f"{i:2d}. [{n['total']:3d}/100] {n['title'][:40]}")
            print(f"     長度={d['content_length']:2d} 結構={d['structure_quality']:2d} "
                  f"引用={d['source_citation']:2d} 播客={d['podcast_suit']:2d} "
                  f"新舊={d['recency']:2d}")
        print("-" * 72)
        # 低分警示
        low = [n for n in all_scored if n['total'] < 40]
        if low:
            print(f"[KBQualityAlert] {len(low)} 筆筆記評分 < 40，建議補充來源與內容")


def _parse_dt(s: str) -> datetime:
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    main()
