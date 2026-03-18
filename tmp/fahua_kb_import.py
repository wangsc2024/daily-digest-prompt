#!/usr/bin/env python3
"""法華經研究 KB 匯入：健康檢查、混合搜尋、POST /api/notes。輸出 JSON 供後續使用。"""
import json
import sys
import urllib.request
from pathlib import Path

KB_BASE = "http://localhost:3000"
REPORT_PATH = Path(__file__).parent / "fahua-research-report.md"

def main():
    result = {"kb_available": False, "hybrid_results": {}, "note_id": None, "kb_imported": False, "error": None}
    try:
        # 1. Health check
        req = urllib.request.Request(f"{KB_BASE}/api/health")
        with urllib.request.urlopen(req, timeout=5) as r:
            result["kb_available"] = True
    except Exception as e:
        result["error"] = f"health_fail:{type(e).__name__}:{str(e)[:100]}"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    # 2. Hybrid search for 法華經、妙法蓮華經、一佛乘、開權顯實
    for q in ["法華經", "妙法蓮華經", "一佛乘", "開權顯實"]:
        try:
            body = json.dumps({"query": q, "topK": 5}).encode("utf-8")
            req = urllib.request.Request(
                f"{KB_BASE}/api/search/hybrid", data=body, method="POST",
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
                result["hybrid_results"][q] = [{"title": i.get("title",""), "score": i.get("score",0)} for i in data.get("items", [])[:3]]
        except Exception as e:
            result["hybrid_results"][q] = {"error": str(e)[:80]}

    # 3. POST /api/import（依 knowledge-query SKILL）
    content = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else ""
    if not content:
        result["error"] = "report_file_missing"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)
    payload = {
        "notes": [{
            "title": "法華經（妙法蓮華經）深度研究 — 一佛乘義理、重點品章與修行實踐綜論",
            "contentText": content,
            "source": "import",
            "tags": ["法華經", "佛學", "天台宗"]
        }]
    }
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{KB_BASE}/api/import", data=body, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
            ids = data.get("result", {}).get("noteIds", [])
            result["note_id"] = ids[0] if ids else None
            result["kb_imported"] = bool(result["note_id"])
    except Exception as e:
        result["error"] = f"import_fail:{type(e).__name__}:{str(e)[:100]}"
        result["kb_imported"] = False

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
