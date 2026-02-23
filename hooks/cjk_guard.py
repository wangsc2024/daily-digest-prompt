"""
cjk_guard.py - 日文漢字混入繁體中文的偵測與自動修正工具

常見問題：Claude LLM 在抽樣繁體中文時，偶爾輸出外觀相同的日文 Unicode 變體。
例：專 (U+5C02, 日文) vs 專 (U+5C08, 繁中)，肉眼無法區分。

用法：
  # 掃描模式（偵測）
  python hooks/cjk_guard.py scan [paths...]

  # 修正模式（自動替換）
  python hooks/cjk_guard.py fix [paths...]

  # Git pre-commit 模式（掃描 staged 檔案）
  python hooks/cjk_guard.py pre-commit

返回碼：0=無問題, 1=發現問題（scan/pre-commit），0=已修正（fix）
"""

import sys
import os
import subprocess
from pathlib import Path

# 日文漢字 → 繁體中文正確字元的映射表
# 僅包含碼位不同的字元（日中共用字元已排除）
CORRECTIONS = {
    0x5C02: 0x5C08,  # 專 (專案/專業)
    0x4F53: 0x9AD4,  # 體 (整體/身體)
    0x5B66: 0x5B78,  # 學 (學習/學術)
    0x5B9F: 0x5BE6,  # 實 (實際/實作)
    0x6C17: 0x6C23,  # 氣 (氣候/氣息)
    0x69D8: 0x6A23,  # 樣 (樣式/樣本)
    0x4F1A: 0x6703,  # 會 (會議/機會)
    0x56FD: 0x570B,  # 國 (國家/國際)
    0x7D4C: 0x7D93,  # 經 (經過/經驗)
    0x8FBA: 0x908A,  # 邊 (邊界/附近/邊緣)
    0x5BFE: 0x5C0D,  # 對 (對應/對話)
    0x8A3C: 0x8B49,  # 證 (證明/證書)
}

# 適用掃描的副檔名
SCAN_EXTENSIONS = {'.md', '.yaml', '.yml', '.json', '.py', '.ps1'}

# 排除自身（映射表描述字串含有日文字元，屬刻意設計）
EXCLUDED_FILES = {Path(__file__).name}


def detect_issues(text: str, filepath: str = "") -> list[dict]:
    """偵測文字中的日文漢字混入問題"""
    issues = []
    lines = text.split('\n')
    for lineno, line in enumerate(lines, 1):
        for pos, char in enumerate(line):
            cp = ord(char)
            if cp in CORRECTIONS:
                correct = chr(CORRECTIONS[cp])
                context_start = max(0, pos - 10)
                context_end = min(len(line), pos + 11)
                issues.append({
                    'file': filepath,
                    'line': lineno,
                    'col': pos + 1,
                    'char': char,
                    'codepoint': f'U+{cp:04X}',
                    'correct': correct,
                    'correct_codepoint': f'U+{CORRECTIONS[cp]:04X}',
                    'context': line[context_start:context_end],
                })
    return issues


def fix_text(text: str) -> tuple[str, int]:
    """修正文字中的日文漢字，回傳 (修正後文字, 修正次數)"""
    count = 0
    result = []
    for char in text:
        cp = ord(char)
        if cp in CORRECTIONS:
            result.append(chr(CORRECTIONS[cp]))
            count += 1
        else:
            result.append(char)
    return ''.join(result), count


def scan_files(paths: list[str]) -> int:
    """掃描指定路徑，回傳發現問題的數量"""
    total_issues = 0
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            continue
        files = []
        if path.is_dir():
            for ext in SCAN_EXTENSIONS:
                files.extend(path.rglob(f'*{ext}'))
        elif path.suffix in SCAN_EXTENSIONS:
            files = [path]

        for f in files:
            if f.name in EXCLUDED_FILES:
                continue
            try:
                text = f.read_text(encoding='utf-8', errors='replace')
                issues = detect_issues(text, str(f))
                if issues:
                    print(f"\n[WARN] {f}：發現 {len(issues)} 個日文漢字混入")
                    for issue in issues:
                        print(f"  行{issue['line']}:{issue['col']} "
                              f"'{issue['char']}'({issue['codepoint']}) "
                              f"→ 應為 '{issue['correct']}'({issue['correct_codepoint']})"
                              f"  ...{issue['context']}...")
                    total_issues += len(issues)
            except Exception as e:
                print(f"[ERROR] 無法讀取 {f}: {e}")

    return total_issues


def fix_files(paths: list[str]) -> int:
    """修正指定路徑中的日文漢字，回傳修正次數"""
    total_fixed = 0
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            continue
        files = []
        if path.is_dir():
            for ext in SCAN_EXTENSIONS:
                files.extend(path.rglob(f'*{ext}'))
        elif path.suffix in SCAN_EXTENSIONS:
            files = [path]

        for f in files:
            if f.name in EXCLUDED_FILES:
                continue
            try:
                original = f.read_text(encoding='utf-8', errors='replace')
                fixed, count = fix_text(original)
                if count > 0:
                    f.write_text(fixed, encoding='utf-8')
                    print(f"[FIXED] {f}：修正 {count} 個日文漢字")
                    total_fixed += count
            except Exception as e:
                print(f"[ERROR] 無法修正 {f}: {e}")

    return total_fixed


def pre_commit_check() -> int:
    """Git pre-commit hook 模式：掃描 staged 的檔案"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
            capture_output=True, text=True
        )
        staged_files = [f for f in result.stdout.strip().split('\n') if f]
    except Exception as e:
        print(f"[ERROR] 無法取得 staged 檔案: {e}")
        return 0

    if not staged_files:
        return 0

    total_issues = 0
    for filepath in staged_files:
        if not any(filepath.endswith(ext) for ext in SCAN_EXTENSIONS):
            continue
        if Path(filepath).name in EXCLUDED_FILES:
            continue
        if not os.path.exists(filepath):
            continue
        try:
            # 讀 staged 版本（不是工作目錄版本）
            result = subprocess.run(
                ['git', 'show', f':{filepath}'],
                capture_output=True
            )
            text = result.stdout.decode('utf-8', errors='replace')
            issues = detect_issues(text, filepath)
            if issues:
                print(f"\n[BLOCK] {filepath}：發現 {len(issues)} 個日文漢字混入")
                for issue in issues:
                    print(f"  行{issue['line']}:{issue['col']} "
                          f"'{issue['char']}'({issue['codepoint']}) "
                          f"→ 應為 '{issue['correct']}'({issue['correct_codepoint']})")
                total_issues += len(issues)
        except Exception as e:
            print(f"[ERROR] 無法檢查 {filepath}: {e}")

    if total_issues > 0:
        print(f"\n共發現 {total_issues} 個問題。")
        print("請執行以下指令自動修正後重新 commit：")
        print("  python hooks/cjk_guard.py fix .")
        return 1
    return 0


def post_fix() -> int:
    """PostToolUse hook 模式：寫入後立即修正磁碟上的檔案"""
    import json
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    if tool_name not in ('Write', 'Edit'):
        return 0

    filepath = tool_input.get('file_path', '')
    if not filepath or not any(filepath.endswith(ext) for ext in SCAN_EXTENSIONS):
        return 0

    if not os.path.exists(filepath):
        return 0

    try:
        original = Path(filepath).read_text(encoding='utf-8', errors='replace')
        fixed, count = fix_text(original)
        if count > 0:
            Path(filepath).write_text(fixed, encoding='utf-8')
            print(f"[CJK Guard] {filepath}：自動修正 {count} 個日文漢字", file=sys.stderr)
    except Exception as e:
        print(f"[CJK Guard] 無法修正 {filepath}: {e}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    args = sys.argv[1:]

    if not args or args[0] == 'scan':
        paths = args[1:] if len(args) > 1 else ['.']
        issues = scan_files(paths)
        if issues == 0:
            print(f"✓ 掃描完成，無日文漢字混入")
        sys.exit(1 if issues > 0 else 0)

    elif args[0] == 'fix':
        paths = args[1:] if len(args) > 1 else ['.']
        fixed = fix_files(paths)
        if fixed == 0:
            print("✓ 無需修正")
        else:
            print(f"✓ 共修正 {fixed} 個日文漢字")
        sys.exit(0)

    elif args[0] == 'pre-commit':
        sys.exit(pre_commit_check())

    elif args[0] == 'post-fix':
        sys.exit(post_fix())

    else:
        print(__doc__)
        sys.exit(1)
