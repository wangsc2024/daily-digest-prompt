# -*- coding: utf-8 -*-
"""Build KB import JSON for 法華經研究報告."""
import json
from pathlib import Path

md_path = Path(__file__).parent.parent / "context" / "fahua-research-report-20260315.md"
content_text = md_path.read_text(encoding="utf-8")

payload = {
    "notes": [
        {
            "title": "法華經整體深度研究 — 從經典概論到一佛乘義理的結構化綜論",
            "contentText": content_text,
            "tags": ["法華經", "佛學", "天台宗"],
            "source": "import"
        }
    ],
    "autoSync": True
}

out_path = Path(__file__).parent / "fahua-kb-import.json"
out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {out_path}")
