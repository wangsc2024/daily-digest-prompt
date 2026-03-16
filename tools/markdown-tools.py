#!/usr/bin/env python3
"""Markdown 自動化工具：目錄生成、連結替換、內容摘要、格式驗證。

Usage:
    uv run python tools/markdown-tools.py toc <file> [--max-depth N] [--output FILE] [--inject]
    uv run python tools/markdown-tools.py replace-links <file>... --old-prefix OLD --new-prefix NEW
    uv run python tools/markdown-tools.py replace-links <file> --pattern PAT --replacement REP
    uv run python tools/markdown-tools.py summarize <file> [--max-sentences N] [--format FMT]
    uv run python tools/markdown-tools.py lint <file>...
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ─── TOC 生成 ────────────────────────────────────────────────────────────────

def generate_toc(content: str, max_depth: int = 6) -> str:
    """從 Markdown 內容提取標題並生成目錄。"""
    lines = content.split("\n")
    toc_lines: list[str] = []
    in_code_block = False

    for line in lines:
        # 追蹤圍欄式程式碼區塊
        if re.match(r"^```", line.strip()):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        match = re.match(r"^(#{1,6})\s+(.+?)(?:\s+#+\s*)?$", line)
        if not match:
            continue

        level = len(match.group(1))
        if level > max_depth:
            continue

        title = match.group(2).strip()
        # 產生錨點：小寫、空格→-、移除特殊字元（GFM 規則）
        anchor = _heading_to_anchor(title)
        indent = "  " * (level - 1)
        toc_lines.append(f"{indent}- [{title}](#{anchor})")

    return "\n".join(toc_lines)


def _heading_to_anchor(heading: str) -> str:
    """將標題轉換為 GFM 錨點格式。"""
    anchor = heading.lower()
    # 移除 Markdown 標記（粗體、斜體、行內碼）
    anchor = re.sub(r"[*_`~]", "", anchor)
    # 移除 HTML 標籤
    anchor = re.sub(r"<[^>]+>", "", anchor)
    # 移除特殊字元，保留中文、字母、數字、空格、連字號
    anchor = re.sub(r"[^\w\s\u4e00-\u9fff\u3400-\u4dbf-]", "", anchor)
    # 空格替換為連字號
    anchor = re.sub(r"\s+", "-", anchor.strip())
    return anchor


def inject_toc(content: str, toc: str) -> str:
    """將目錄注入到 <!-- TOC --> 標記位置。"""
    marker_pattern = r"(<!-- TOC -->)(.*?)(<!-- /TOC -->)"
    replacement = f"<!-- TOC -->\n{toc}\n<!-- /TOC -->"

    if re.search(marker_pattern, content, re.DOTALL):
        return re.sub(marker_pattern, replacement, content, flags=re.DOTALL)

    # 找不到標記，在第一個標題前插入
    match = re.search(r"^#\s", content, re.MULTILINE)
    if match:
        pos = match.start()
        return content[:pos] + f"<!-- TOC -->\n{toc}\n<!-- /TOC -->\n\n" + content[pos:]

    return f"<!-- TOC -->\n{toc}\n<!-- /TOC -->\n\n" + content


# ─── 連結替換 ─────────────────────────────────────────────────────────────────

def replace_links(
    content: str,
    old_prefix: str | None = None,
    new_prefix: str | None = None,
    pattern: str | None = None,
    replacement: str | None = None,
) -> tuple[str, int]:
    """替換 Markdown 中的連結/圖片路徑。回傳 (新內容, 替換次數)。"""
    count = 0

    if old_prefix and new_prefix:
        # 前綴替換：匹配圖片和連結的 URL 部分
        def _replace_prefix(m: re.Match) -> str:
            nonlocal count
            url = m.group(2)
            if url.startswith(old_prefix):
                count += 1
                return f"{m.group(1)}{new_prefix}{url[len(old_prefix):]}{m.group(3)}"
            return m.group(0)

        # 匹配 [text](url) 和 ![alt](url)
        content = re.sub(
            r"(!?\[[^\]]*\]\()([^)]+)(\))",
            _replace_prefix,
            content,
        )

    elif pattern and replacement:
        # 精確替換
        new_content = content.replace(pattern, replacement)
        count = content.count(pattern)
        content = new_content

    return content, count


# ─── 內容摘要 ─────────────────────────────────────────────────────────────────

def summarize(
    content: str,
    max_sentences: int = 5,
    output_format: str = "bullet",
    min_sentence_length: int = 10,
) -> str:
    """規則式摘要：提取標題與首句。

    Args:
        content: Markdown 原文
        max_sentences: 最大摘要句數
        output_format: 'bullet'(列表)、'paragraph'(段落)、'heading'(含標題)
        min_sentence_length: 最小句子字數
    """
    sections = _extract_sections(content)
    summary_items: list[dict] = []

    for section in sections:
        if len(summary_items) >= max_sentences:
            break

        heading = section["heading"]
        first_sentence = _extract_first_sentence(
            section["body"], min_sentence_length
        )
        if first_sentence:
            summary_items.append({"heading": heading, "sentence": first_sentence})

    if not summary_items:
        return "_（無法提取摘要：文件可能缺少結構化標題或正文）_"

    return _format_summary(summary_items, output_format)


def _extract_sections(content: str) -> list[dict]:
    """將 Markdown 切分為章節列表。"""
    lines = content.split("\n")
    sections: list[dict] = []
    current_heading = ""
    current_body_lines: list[str] = []
    in_code_block = False

    for line in lines:
        if re.match(r"^```", line.strip()):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading_match:
            # 儲存前一個章節
            if current_heading:
                sections.append({
                    "heading": current_heading,
                    "body": "\n".join(current_body_lines).strip(),
                })
            current_heading = heading_match.group(2).strip()
            current_body_lines = []
        else:
            current_body_lines.append(line)

    # 最後一個章節
    if current_heading:
        sections.append({
            "heading": current_heading,
            "body": "\n".join(current_body_lines).strip(),
        })

    return sections


def _extract_first_sentence(text: str, min_length: int = 10) -> str:
    """提取段落中的第一個有意義的句子。"""
    # 移除列表標記、引用標記、空行
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # 跳過空行、表格行、分隔線、圖片
        if not stripped or stripped.startswith("|") or stripped.startswith("---"):
            continue
        if stripped.startswith("!["):
            continue
        # 移除列表標記
        cleaned = re.sub(r"^[-*+]\s+", "", stripped)
        cleaned = re.sub(r"^\d+\.\s+", "", cleaned)
        # 移除引用標記
        cleaned = re.sub(r"^>\s*", "", cleaned)
        if len(cleaned) >= min_length:
            lines.append(cleaned)
            break

    if not lines:
        return ""

    text = lines[0]
    # 以中文句號、英文句號、問號、驚嘆號斷句
    match = re.match(r"(.+?[。．.！!？?])", text)
    if match:
        return match.group(1)
    return text


def _format_summary(
    items: list[dict], output_format: str
) -> str:
    """將摘要項目格式化為指定格式。"""
    if output_format == "bullet":
        return "\n".join(f"- **{it['heading']}**：{it['sentence']}" for it in items)
    elif output_format == "heading":
        parts = []
        for it in items:
            parts.append(f"### {it['heading']}\n\n{it['sentence']}\n")
        return "\n".join(parts)
    else:  # paragraph
        return " ".join(it["sentence"] for it in items)


# ─── 格式驗證 (Lint) ─────────────────────────────────────────────────────────

def lint(content: str, filepath: str = "<stdin>") -> list[dict]:
    """檢查常見 Markdown 格式問題。"""
    issues: list[dict] = []
    lines = content.split("\n")
    in_code_block = False
    prev_heading_level = 0
    consecutive_blank = 0
    open_code_fence: str | None = None

    for i, line in enumerate(lines, 1):
        # 追蹤程式碼區塊
        fence_match = re.match(r"^(`{3,}|~{3,})", line.strip())
        if fence_match:
            fence = fence_match.group(1)[0]
            if not in_code_block:
                in_code_block = True
                open_code_fence = fence
            elif line.strip().startswith(fence):
                in_code_block = False
                open_code_fence = None
            continue

        if in_code_block:
            continue

        # 1. 標題層級跳躍
        heading_match = re.match(r"^(#{1,6})\s", line)
        if heading_match:
            level = len(heading_match.group(1))
            if prev_heading_level > 0 and level > prev_heading_level + 1:
                issues.append({
                    "file": filepath,
                    "line": i,
                    "rule": "heading-increment",
                    "message": f"標題層級跳躍：H{prev_heading_level} → H{level}",
                    "severity": "warning",
                })
            prev_heading_level = level
            consecutive_blank = 0
            continue

        # 2. 行尾多餘空格（但排除刻意的兩空格換行）
        if line.endswith(" ") and not line.endswith("  "):
            issues.append({
                "file": filepath,
                "line": i,
                "rule": "trailing-space",
                "message": "行尾有多餘空格（非兩空格換行）",
                "severity": "info",
            })

        # 3. 連續空行（超過 1 個）
        if line.strip() == "":
            consecutive_blank += 1
            if consecutive_blank > 2:
                issues.append({
                    "file": filepath,
                    "line": i,
                    "rule": "consecutive-blank-lines",
                    "message": f"連續 {consecutive_blank} 個空行（建議最多 1 個）",
                    "severity": "info",
                })
        else:
            consecutive_blank = 0

        # 4. 無替代文字的圖片
        if re.search(r"!\[\]\(", line):
            issues.append({
                "file": filepath,
                "line": i,
                "rule": "no-alt-text",
                "message": "圖片缺少替代文字（無障礙問題）",
                "severity": "warning",
            })

        # 5. #後無空格的標題
        if re.match(r"^#{1,6}[^#\s]", line):
            issues.append({
                "file": filepath,
                "line": i,
                "rule": "heading-no-space",
                "message": "# 後缺少空格（CommonMark 不視為標題）",
                "severity": "error",
            })

    # 檢查未關閉的程式碼區塊
    if in_code_block:
        issues.append({
            "file": filepath,
            "line": len(lines),
            "rule": "unclosed-code-block",
            "message": f"程式碼區塊未關閉（開頭使用 {open_code_fence}）",
            "severity": "error",
        })

    return issues


def format_lint_report(issues: list[dict]) -> str:
    """格式化 lint 報告。"""
    if not issues:
        return "✅ 未發現格式問題"

    severity_icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
    lines = [f"發現 {len(issues)} 個問題：\n"]

    for issue in issues:
        icon = severity_icons.get(issue["severity"], "?")
        lines.append(
            f"  {icon} {issue['file']}:{issue['line']} "
            f"[{issue['rule']}] {issue['message']}"
        )

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    lines.append(f"\n統計：{errors} 錯誤, {warnings} 警告, {len(issues) - errors - warnings} 提示")

    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Markdown 自動化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # toc
    toc_parser = subparsers.add_parser("toc", help="產生目錄")
    toc_parser.add_argument("file", type=Path, help="Markdown 檔案")
    toc_parser.add_argument("--max-depth", type=int, default=6, help="最大標題深度")
    toc_parser.add_argument("--output", type=Path, help="輸出檔案（預設 stdout）")
    toc_parser.add_argument("--inject", action="store_true", help="注入目錄到原檔案")

    # replace-links
    rl_parser = subparsers.add_parser("replace-links", help="替換連結路徑")
    rl_parser.add_argument("files", nargs="+", type=Path, help="Markdown 檔案")
    rl_parser.add_argument("--old-prefix", help="舊路徑前綴")
    rl_parser.add_argument("--new-prefix", help="新路徑前綴")
    rl_parser.add_argument("--pattern", help="精確匹配模式")
    rl_parser.add_argument("--replacement", help="替換字串")

    # summarize
    sum_parser = subparsers.add_parser("summarize", help="產生摘要")
    sum_parser.add_argument("file", type=Path, help="Markdown 檔案")
    sum_parser.add_argument("--max-sentences", type=int, default=5, help="最大句數")
    sum_parser.add_argument(
        "--format", dest="fmt", choices=["bullet", "paragraph", "heading"],
        default="bullet", help="輸出格式"
    )

    # lint
    lint_parser = subparsers.add_parser("lint", help="格式驗證")
    lint_parser.add_argument("files", nargs="+", type=Path, help="Markdown 檔案")

    args = parser.parse_args()

    if args.command == "toc":
        content = args.file.read_text(encoding="utf-8")
        toc = generate_toc(content, args.max_depth)
        if args.inject:
            new_content = inject_toc(content, toc)
            args.file.write_text(new_content, encoding="utf-8")
            print(f"目錄已注入 {args.file}")
        elif args.output:
            args.output.write_text(toc, encoding="utf-8")
            print(f"目錄已寫入 {args.output}")
        else:
            print(toc)

    elif args.command == "replace-links":
        if not ((args.old_prefix and args.new_prefix) or (args.pattern and args.replacement)):
            print("錯誤：需提供 --old-prefix/--new-prefix 或 --pattern/--replacement", file=sys.stderr)
            return 1
        total = 0
        for fpath in args.files:
            content = fpath.read_text(encoding="utf-8")
            new_content, count = replace_links(
                content,
                old_prefix=args.old_prefix,
                new_prefix=args.new_prefix,
                pattern=args.pattern,
                replacement=args.replacement,
            )
            if count > 0:
                fpath.write_text(new_content, encoding="utf-8")
                print(f"  {fpath}: 替換 {count} 處")
                total += count
        print(f"共替換 {total} 處")

    elif args.command == "summarize":
        content = args.file.read_text(encoding="utf-8")
        result = summarize(content, args.max_sentences, args.fmt)
        print(result)

    elif args.command == "lint":
        all_issues: list[dict] = []
        for fpath in args.files:
            content = fpath.read_text(encoding="utf-8")
            issues = lint(content, str(fpath))
            all_issues.extend(issues)
        print(format_lint_report(all_issues))
        return 1 if any(i["severity"] == "error" for i in all_issues) else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
