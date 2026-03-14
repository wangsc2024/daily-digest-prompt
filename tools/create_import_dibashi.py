# -*- coding: utf-8 -*-
"""建立知識庫匯入用 JSON（唯識第八識報告）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "research" / "唯識第八識深度洞察報告_20260314.md"
OUT = ROOT / "import_note.json"


def main():
    content = REPORT.read_text(encoding="utf-8")
    data = {
        "notes": [
            {
                "title": "唯識第八識（阿賴耶識）深度洞察報告",
                "contentText": content,
                "tags": ["唯識", "第八識", "阿賴耶識", "佛教", "成唯識論"],
                "source": "import",
            }
        ],
        "autoSync": True,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已建立 {OUT}")


if __name__ == "__main__":
    main()
