#!/usr/bin/env python3
"""
tools/run_podcast_create.py
Podcast 生成任務（podcast_create）完整流程：
  1. KB hybrid search 選材（排除佛學類）
  2. 30 天去重
  3. 生成雙主持人對話腳本
  4. TTS 合成、音訊合併、R2 上傳
  5. 寫入結果檔、更新 history、發送 ntfy
"""
import argparse
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
HISTORY_PATH = PROJECT_DIR / "context" / "podcast-history.json"
PODCAST_CFG = PROJECT_DIR / "config" / "podcast.yaml"


def podcast_series_display_name(task_key: str) -> str:
    try:
        import yaml

        data = yaml.safe_load(PODCAST_CFG.read_text(encoding="utf-8")) or {}
        n = data.get("notification") or {}
        by = n.get("series_by_task") or {}
        return str(by.get(task_key) or n.get("series_default") or "知識電台").strip()
    except Exception:
        return "知識電台"
# 與任務規格一致：僅排除佛學／佛教／淨土類標籤（不額外擴張）
EXCLUDE_TAGS = {"佛學", "佛教", "淨土"}
COOLDOWN_DAYS = 30
KB_BASE = "http://localhost:3000"
PODCAST_QUERY = "技術 AI 研究 學習 工具"


def fetch_hybrid_search(query: str, top_k: int = 15) -> list[dict]:
    """POST /api/search/hybrid"""
    url = f"{KB_BASE}/api/search/hybrid"
    body = json.dumps({"query": query, "topK": top_k}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("items", [])


def fetch_note(note_id: str) -> dict | None:
    """GET /api/notes/{id}"""
    url = f"{KB_BASE}/api/notes/{note_id}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def load_used_note_ids(within_days: int = 30) -> set[str]:
    """從 podcast-history 取得近期已用 note_id"""
    used = set()
    if not HISTORY_PATH.exists():
        return used
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        # summary.recent_note_ids（可能混雜字串與物件）
        for x in data.get("summary", {}).get("recent_note_ids", []):
            if isinstance(x, str):
                used.add(x)
            elif isinstance(x, dict) and x.get("note_id"):
                used.add(x["note_id"])
        # entries（依 used_at 篩選 30 天內）
        cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
        for e in data.get("entries", []):
            used_at = e.get("used_at", "")
            if not used_at:
                continue
            try:
                dt = datetime.fromisoformat(used_at.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff and e.get("note_id"):
                    used.add(e["note_id"])
            except Exception:
                pass
        # episodes 最近 30 天
        for ep in data.get("episodes", [])[:20]:
            created = ep.get("created_at", "")
            if not created:
                continue
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    for nid in ep.get("notes_used", []):
                        if isinstance(nid, str):
                            used.add(nid)
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] 讀取 podcast-history 失敗: {e}")
    return used


def has_excluded_tag(tags: list[str]) -> bool:
    """是否含有排除標籤"""
    if not tags:
        return False
    tag_set = {str(t).strip() for t in tags}
    return bool(tag_set & EXCLUDE_TAGS)


def fetch_notes_list(limit: int = 250) -> list[dict]:
    """GET /api/notes?limit=…（hybrid 無結果時的後備選材）"""
    url = f"{KB_BASE}/api/notes?limit={limit}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("notes", data if isinstance(data, list) else [])
    except Exception as e:
        print(f"[WARN] 無法取得筆記列表: {e}")
        return []


def _note_updated_ts(note: dict) -> float:
    raw = note.get("updatedAt") or note.get("createdAt") or ""
    if not raw:
        return 0.0
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def fallback_rank_notes(notes: list[dict], used: set[str], query: str) -> list[dict]:
    """依查詢詞命中數 + 更新時間排序（模擬相關性＋新鮮度）。"""
    tokens = [t.strip() for t in query.split() if t.strip()]
    scored: list[tuple[int, float, dict]] = []
    for n in notes:
        if n.get("isDeleted"):
            continue
        nid = n.get("id")
        if not nid or nid in used:
            continue
        if has_excluded_tag(n.get("tags") or []):
            continue
        blob = (n.get("title") or "") + "\n" + str(n.get("contentText") or "")
        rel = sum(1 for t in tokens if t and t in blob)
        ts = _note_updated_ts(n)
        scored.append((rel, ts, n))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for rel, _ts, n in scored:
        nid = n.get("id")
        if not nid or nid in seen:
            continue
        if rel == 0 and out:
            continue
        seen.add(nid)
        out.append(n)
        if len(out) >= 3:
            break
    if len(out) < 3:
        for rel, _ts, n in scored:
            if rel != 0:
                continue
            nid = n.get("id")
            if not nid or nid in seen:
                continue
            seen.add(nid)
            out.append(n)
            if len(out) >= 3:
                break
    return out[:3]


def select_top3_notes() -> list[dict]:
    """選出 3 篇非佛學、未在 30 天內使用的高分筆記"""
    items = fetch_hybrid_search(PODCAST_QUERY, top_k=20)
    used = load_used_note_ids(COOLDOWN_DAYS)
    candidates: list[dict] = []
    for item in items:
        mid = item.get("metadata", {})
        note_id = item.get("id") or mid.get("id") or mid.get("noteId")
        tags = mid.get("tags", []) or []
        if has_excluded_tag(tags):
            continue
        if note_id and note_id in used:
            continue
        score = item.get("score", 0)
        candidates.append({"id": note_id, "score": score, "metadata": mid})
        if len(candidates) >= 3:
            break

    if len(candidates) < 3:
        print("[INFO] hybrid search 結果不足，改以 /api/notes 後備排序選材…")
        ranked = fallback_rank_notes(fetch_notes_list(300), used, PODCAST_QUERY)
        for n in ranked:
            nid = n.get("id")
            if nid and not any(c.get("id") == nid for c in candidates):
                candidates.append({"id": nid, "score": 0.0, "metadata": n})
            if len(candidates) >= 3:
                break

    result = []
    for c in candidates[:3]:
        note = fetch_note(c["id"])
        if note:
            result.append(note)
    return result


def _expand_abbrev(t: str) -> str:
    """簡易縮寫展開供 TTS（AI、API、LLM 等）"""
    for abbr, exp in [("AI", "A I"), ("API", "A P I"), ("LLM", "L L M"), ("RAG", "R A G")]:
        t = re.sub(rf"\b{re.escape(abbr)}\b", exp, t)
    return t


def generate_script(notes: list[dict]) -> list[dict]:
    """依 3 篇筆記生成雙主持人對話腳本（30-50 輪）"""
    turns: list[dict] = []
    titles = [n.get("title", "") for n in notes]
    contents = []
    for n in notes:
        ct = n.get("contentText", n.get("content_text", ""))
        if isinstance(ct, dict):
            ct = json.dumps(ct, ensure_ascii=False)
        contents.append((ct or "")[:3000])

    def add(host: str, text: str):
        speaker = "Host-A" if host == "host_a" else "Host-B"
        turns.append({
            "turn": len(turns) + 1,
            "speaker": speaker,
            "text": text,
            "tts_text": _expand_abbrev(text),
        })

    # 開場（3 輪）
    add("host_a", "大家好，歡迎收聽今天的知識電台。")
    add("host_b", "嗨！今天我們要聊三篇很有意思的技術與學習主題。")
    add("host_a", f"沒錯，我們選了 {titles[0][:35]}{'…' if len(titles[0]) > 35 else ''}、{titles[1][:35] if len(titles) > 1 else ''}{'…' if len(titles) > 1 and len(titles[1]) > 35 else ''} 等主題。")

    # 三篇筆記，每篇約 8-12 輪對話
    for idx, (title, content) in enumerate(zip(titles, contents)):
        parts = re.split(r"[。！？\n]+", content)
        parts = [p.strip() for p in parts if len(p.strip()) > 12]
        parts = [p for p in parts if not re.match(r"^[|\s\-:=]+$", p)][:8]
        if not parts:
            parts = [content[:250] + "…" if len(content) > 250 else content] if content else ["這篇筆記涵蓋多個重點。"]
        ord_name = ["第一", "第二", "第三"][idx] if idx < 3 else "這"
        add("host_a", f"我們先來看{ord_name}篇：{title[:40]}{'…' if len(title) > 40 else ''}。")
        add("host_b", "嗯，這篇主要在講什麼？")
        for j, p in enumerate(parts):
            if len(p) > 100:
                p = p[:100] + "…"
            if j % 2 == 0:
                add("host_a", p)
                if j + 1 < len(parts):
                    add("host_b", "原來如此，還有呢？")
            else:
                add("host_b", "有意思！")
                add("host_a", p)
        if idx < 2:
            add("host_b", "好，我們接著看下一篇。")

    # 結尾（2 輪）
    add("host_a", "以上就是本集的三個主題分享，謝謝收聽！")
    add("host_b", "我們下集再見！")

    out = []
    for i, t in enumerate(turns[:50], 1):
        t = dict(t)
        t["turn"] = i
        out.append(t)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Podcast 生成任務")
    parser.add_argument("--dry-run", action="store_true", help="僅選材與生成腳本，不執行 TTS/R2")
    parser.add_argument("--skip-tts", action="store_true", help="跳過 TTS 與後製")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc)
    date_str = ts.strftime("%Y%m%d")
    time_str = ts.strftime("%Y%m%d_%H%M%S")
    script_dir = PROJECT_DIR / "podcasts" / date_str
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / f"script_{time_str}.jsonl"
    audio_dir = script_dir / f"audio_{time_str}"
    mp3_path = script_dir / f"podcast_{time_str}.mp3"

    print("[1/6] 評分選材（hybrid search + 排除佛學 + 30 天去重）…")
    notes = select_top3_notes()
    if len(notes) < 3:
        print(f"[ERROR] 僅取得 {len(notes)} 筆筆記，需至少 3 筆")
        return 1
    note_ids = [n.get("id", "") for n in notes]
    note_titles = [n.get("title", "") for n in notes]
    print(f"  選用：{note_titles}")

    print("[2/6] 生成對話腳本…")
    turns = generate_script(notes)
    with open(script_path, "w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"  已寫入 {script_path}（{len(turns)} 輪）")

    tts_status = "skipped"
    r2_status = "skipped"

    if not args.skip_tts and not args.dry_run:
        print("[3/6] TTS 語音合成…")
        cfg_path = PROJECT_DIR / "config" / "media-pipeline.yaml"
        voice_a = "zh-TW-HsiaoChenNeural"
        voice_b = "zh-TW-YunJheNeural"
        if cfg_path.exists():
            txt = cfg_path.read_text(encoding="utf-8")
            if "voice_a:" in txt:
                m = re.search(r"voice_a:\s*[\"']?([^\"'#\s]+)", txt)
                if m:
                    voice_a = m.group(1).strip()
            if "voice_b:" in txt:
                m = re.search(r"voice_b:\s*[\"']?([^\"'#\s]+)", txt)
                if m:
                    voice_b = m.group(1).strip()
        audio_dir.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run([
            "uv", "run", "--project", str(PROJECT_DIR), "python",
            str(PROJECT_DIR / "tools" / "generate_podcast_audio.py"),
            "--input", str(script_path),
            "--output", str(audio_dir),
            "--voice-a", voice_a,
            "--voice-b", voice_b,
            "--abbrev-rules", str(PROJECT_DIR / "config" / "tts-abbreviation-rules.yaml"),
        ], capture_output=True, text=True, timeout=300)
        if rc.returncode != 0:
            print(f"  [WARN] TTS 失敗: {rc.stderr[:500]}")
        else:
            tts_status = "success"
            print("[4/6] 音訊合併…")
            rc2 = subprocess.run([
                "uv", "run", "--project", str(PROJECT_DIR), "python",
                str(PROJECT_DIR / "tools" / "concat_audio.py"),
                "--audio-dir", str(audio_dir),
                "--script", str(script_path),
                "--output", str(mp3_path),
                "--config", str(PROJECT_DIR / "config" / "media-pipeline.yaml"),
            ], capture_output=True, text=True, timeout=60)
            if rc2.returncode == 0 and mp3_path.exists():
                print("[5/6] 上傳 R2…")
                slug = f"podcast-create-{date_str}"
                rc3 = subprocess.run([
                    "pwsh", "-ExecutionPolicy", "Bypass", "-File",
                    str(PROJECT_DIR / "tools" / "upload-podcast.ps1"),
                    "-LocalPath", str(mp3_path),
                    "-Title", note_titles[0][:50] if note_titles else "Podcast",
                    "-Topic", "技術研究",
                    "-Slug", slug,
                ], capture_output=True, text=True, timeout=30, cwd=str(PROJECT_DIR))
                if "url" in (rc3.stdout or ""):
                    r2_status = "uploaded"
                else:
                    r2_status = "skipped"
            else:
                print("  [WARN] 音訊合併失敗")
    else:
        print("[3-5/6] 跳過 TTS / 合併 / R2（--skip-tts 或 --dry-run）")

    # 6. 寫入結果檔
    results_dir = PROJECT_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "agent": "todoist-auto-podcast_create",
        "backend": "cursor_cli",
        "status": "completed",
        "summary": f"選用 {note_titles[0][:20]}… 等 3 篇筆記，{len(turns)} 輪對話，TTS={tts_status}，R2={r2_status}",
        "note_ids_used": note_ids,
        "note_titles": note_titles,
        "script_file": str(script_path),
        "tts_status": tts_status,
        "r2_status": r2_status,
        "generated_at": ts.isoformat(),
    }
    result_path = results_dir / "todoist-auto-podcast_create.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[6/6] 結果已寫入 {result_path}")

    # 更新 podcast-history
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {}
        if not data:
            data = {"version": 2, "updated_at": "", "summary": {"total_episodes": 0, "cooldown_days": 30, "recent_note_ids": [], "recent_topics": []}, "episodes": [], "entries": []}
        summary = data.setdefault("summary", {})
        recent_ids = list(summary.get("recent_note_ids", []))
        for nid in note_ids:
            if nid and nid not in recent_ids[:5]:
                recent_ids.insert(0, nid)
        summary["recent_note_ids"] = recent_ids[:30]
        summary["total_episodes"] = summary.get("total_episodes", 0) + 1
        summary["updated_at"] = ts.isoformat()
        ep = {"episode_title": note_titles[0][:40] if note_titles else "Podcast", "notes_used": note_ids, "note_titles": note_titles, "topics": ["技術", "AI", "研究"], "source": "auto-task", "created_at": ts.isoformat()}
        data.setdefault("episodes", []).insert(0, ep)
        slug = f"podcast-create-{date_str}"
        for nid, ntitle in zip(note_ids, note_titles):
            data.setdefault("entries", []).append({
                "note_id": nid,
                "note_title": ntitle,
                "query": "技術 AI 研究 學習 工具",
                "note_id_input": "",
                "slug": slug,
                "used_at": ts.isoformat(),
            })
        data["updated_at"] = ts.isoformat()
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  已更新 podcast-history.json")
    except Exception as e:
        print(f"  [WARN] 更新 history 失敗: {e}")

    # ntfy 通知
    if not args.dry_run:
        try:
            temp_dir = PROJECT_DIR / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            ntfy_path = temp_dir / "podcast-create-notify.json"
            ep = (note_titles[0][:40] if note_titles else "本集").strip()
            series = podcast_series_display_name("podcast_create")
            ntfy_body = {
                "topic": "wangsc2025",
                "title": f"🎙️ {series} Podcast：{ep}",
                "message": f"AI 雙主持人 | {len(turns)} 輪對話 | TTS={tts_status} R2={r2_status}",
                "tags": ["headphones", "white_check_mark"],
                "priority": 3,
            }
            ntfy_path.write_text(json.dumps(ntfy_body, ensure_ascii=False), encoding="utf-8")
            subprocess.run(
                ["pwsh", "-NoProfile", "-Command",
                 f'curl -s -X POST https://ntfy.sh -H "Content-Type: application/json; charset=utf-8" -d "@{ntfy_path}"'],
                capture_output=True,
                timeout=15,
                cwd=str(PROJECT_DIR),
            )
            ntfy_path.unlink(missing_ok=True)
            print("  ntfy 通知已發送")
        except Exception as e:
            print(f"  [WARN] ntfy 失敗: {e}")

    print("\n=== 完成 ===")
    print(f"執行摘要：{result['summary']}")
    print(f"選用筆記：{note_titles}")
    print(f"腳本路徑：{script_path}")
    print(f"TTS 狀態：{tts_status} | R2 狀態：{r2_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
