#!/usr/bin/env python3
"""驗證楞嚴心咒研究筆記的完整性。

檢查每份筆記是否包含 4 個必備章節且每個章節非空。
"""

import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "## 核心論點與論據",
    "## 引文與學者觀點",
    "## 來源",
    "## 爭議點與學派立場",
]

NOTES_DIR = Path(__file__).parent
EXPECTED_NOTES = [f"subtopic_Q{i}.md" for i in range(1, 11)]


def validate_note(filepath: Path) -> list[str]:
    """驗證單份筆記，回傳錯誤清單。"""
    errors = []
    if not filepath.exists():
        return [f"檔案不存在: {filepath.name}"]

    content = filepath.read_text(encoding="utf-8")

    if len(content.strip()) < 100:
        errors.append(f"{filepath.name}: 內容過短（< 100 字元）")

    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"{filepath.name}: 缺少章節 '{section}'")
        else:
            # 檢查章節內容是否非空
            idx = content.index(section)
            after = content[idx + len(section) :]
            # 找到下一個 ## 或檔案結尾
            next_section = after.find("\n## ")
            section_content = after[:next_section] if next_section != -1 else after
            # 去除空白後檢查是否有實質內容
            stripped = section_content.strip().replace("\n", "").replace(" ", "")
            if len(stripped) < 10:
                errors.append(f"{filepath.name}: 章節 '{section}' 內容為空或過短")

    return errors


def main():
    all_errors = []
    found = 0

    for note_name in EXPECTED_NOTES:
        filepath = NOTES_DIR / note_name
        errors = validate_note(filepath)
        if errors:
            all_errors.extend(errors)
        else:
            found += 1
            print(f"  ✓ {note_name} — 通過驗證")

    print()
    if all_errors:
        print(f"發現 {len(all_errors)} 個問題：")
        for err in all_errors:
            print(f"  ✗ {err}")
        sys.exit(1)
    else:
        print(f"All notes passed validation. ({found}/{len(EXPECTED_NOTES)})")
        sys.exit(0)


if __name__ == "__main__":
    main()
