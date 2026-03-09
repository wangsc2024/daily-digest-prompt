"""
tools/generate_report_pdf.py
從 Markdown 研究報告生成 A4 PDF（中文支援，12pt 字體）。
使用 fpdf2 + Windows 系統字體（微軟正黑體）。
"""

import argparse
import re
import sys
from pathlib import Path

from fpdf import FPDF


class ReportPDF(FPDF):
    """中文研究報告 PDF 生成器。"""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=20)

        # 嘗試載入中文字體
        font_paths = [
            "C:/Windows/Fonts/msjh.ttc",    # 微軟正黑體
            "C:/Windows/Fonts/kaiu.ttf",     # 標楷體
            "C:/Windows/Fonts/mingliu.ttc",  # 細明體
        ]
        self.zh_font = None
        for fp in font_paths:
            if Path(fp).exists():
                try:
                    font_name = Path(fp).stem
                    self.add_font(font_name, "", fp, uni=True)
                    self.add_font(font_name, "B", fp, uni=True)
                    self.zh_font = font_name
                    break
                except Exception:
                    continue

        if not self.zh_font:
            print("[WARN] 無法載入中文字體，PDF 可能無法顯示中文", file=sys.stderr)
            self.zh_font = "Helvetica"

    def header(self):
        self.set_font(self.zh_font, "B", 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 8, "法華經一心三觀研究報告 | lotus-sutra synthesis", align="C")
        self.ln(10)
        self.set_draw_color(200, 200, 200)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.zh_font, "", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"- {self.page_no()} -", align="C")

    def add_title_page(self, title: str, subtitle: str, date: str, author: str):
        self.add_page()
        self.ln(50)
        self.set_font(self.zh_font, "B", 24)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 14, title, align="C")
        self.ln(8)
        self.set_font(self.zh_font, "", 14)
        self.set_text_color(80, 80, 80)
        self.multi_cell(0, 10, subtitle, align="C")
        self.ln(20)
        self.set_font(self.zh_font, "", 11)
        self.cell(0, 8, f"日期：{date}", align="C")
        self.ln(7)
        self.cell(0, 8, f"作者：{author}", align="C")
        self.ln(7)
        self.cell(0, 8, "研究系列：lotus-sutra（synthesis 階段）", align="C")
        self.ln(7)
        self.cell(0, 8, "關鍵字：法華經、一心三觀、天台宗、空觀、假觀、中觀", align="C")

    def render_markdown(self, md_text: str):
        """簡易 Markdown 渲染：標題、段落、表格、列表、引用。"""
        self.add_page()
        lines = md_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # 跳過 frontmatter
            if line.strip().startswith(">") and ("研究系列" in line or "日期" in line or "來源" in line or "狀態" in line):
                i += 1
                continue

            # 水平線
            if line.strip() == "---":
                self.ln(3)
                self.set_draw_color(200, 200, 200)
                self.line(15, self.get_y(), 195, self.get_y())
                self.ln(5)
                i += 1
                continue

            # H1
            if line.startswith("# "):
                self.ln(5)
                self.set_font(self.zh_font, "B", 18)
                self.set_text_color(0, 0, 0)
                self.multi_cell(0, 10, line[2:].strip())
                self.ln(3)
                i += 1
                continue

            # H2
            if line.startswith("## "):
                self.ln(4)
                self.set_font(self.zh_font, "B", 14)
                self.set_text_color(30, 30, 30)
                self.multi_cell(0, 9, line[3:].strip())
                self.ln(2)
                i += 1
                continue

            # H3
            if line.startswith("### "):
                self.ln(3)
                self.set_font(self.zh_font, "B", 12)
                self.set_text_color(50, 50, 50)
                self.multi_cell(0, 8, line[4:].strip())
                self.ln(2)
                i += 1
                continue

            # 表格（簡易處理：偵測 | 開頭的行群組）
            if line.strip().startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                self._render_table(table_lines)
                self.ln(3)
                continue

            # 列表
            if re.match(r"^\d+\.\s", line.strip()):
                self.set_font(self.zh_font, "", 11)
                self.set_text_color(0, 0, 0)
                clean = self._strip_md(line.strip())
                self.multi_cell(0, 7, f"  {clean}", align="L")
                self.ln(1)
                i += 1
                continue

            if line.strip().startswith("- "):
                self.set_font(self.zh_font, "", 11)
                self.set_text_color(0, 0, 0)
                clean = self._strip_md(line.strip()[2:])
                self.multi_cell(0, 7, f"  \u2022 {clean}", align="L")
                self.ln(1)
                i += 1
                continue

            # 引用
            if line.strip().startswith("> "):
                self.set_font(self.zh_font, "", 10)
                self.set_text_color(80, 80, 80)
                clean = self._strip_md(line.strip()[2:])
                self.set_x(25)
                self.multi_cell(160, 7, clean, align="L")
                self.ln(1)
                i += 1
                continue

            # 一般段落
            if line.strip():
                self.set_font(self.zh_font, "", 11)
                self.set_text_color(0, 0, 0)
                clean = self._strip_md(line.strip())
                self.multi_cell(0, 7, clean, align="L")
                self.ln(2)
            else:
                self.ln(2)

            i += 1

    def _strip_md(self, text: str) -> str:
        """移除 Markdown 格式標記。"""
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        return text

    def _render_table(self, lines: list[str]):
        """簡易表格渲染。"""
        if len(lines) < 2:
            return

        # 解析表頭
        headers = [c.strip() for c in lines[0].split("|") if c.strip()]
        # 跳過分隔行
        data_start = 2 if len(lines) > 1 and set(lines[1].replace("|", "").replace("-", "").strip()) <= {" ", ":"} else 1

        col_count = len(headers)
        if col_count == 0:
            return

        col_width = 170 / col_count
        self.set_font(self.zh_font, "B", 9)
        self.set_fill_color(240, 240, 240)

        # 表頭
        self.set_x(20)
        for h in headers:
            self.cell(col_width, 7, self._strip_md(h)[:20], border=1, fill=True, align="C")
        self.ln()

        # 資料行
        self.set_font(self.zh_font, "", 9)
        for row_line in lines[data_start:]:
            cells = [c.strip() for c in row_line.split("|") if c.strip()]
            self.set_x(20)
            for j, cell in enumerate(cells[:col_count]):
                self.cell(col_width, 7, self._strip_md(cell)[:30], border=1, align="L")
            self.ln()


def main():
    parser = argparse.ArgumentParser(description="從 Markdown 生成研究報告 PDF")
    parser.add_argument("--input", required=True, help="Markdown 報告路徑")
    parser.add_argument("--output", required=True, help="PDF 輸出路徑")
    parser.add_argument("--title", default="法華經《一心三觀》精華研究報告")
    parser.add_argument("--author", default="知識電台研究團隊")
    parser.add_argument("--date", default="2026-03-09")
    args = parser.parse_args()

    md_path = Path(args.input)
    if not md_path.exists():
        print(f"[ERROR] 輸入檔案不存在: {md_path}", file=sys.stderr)
        sys.exit(1)

    md_text = md_path.read_text(encoding="utf-8")

    pdf = ReportPDF()
    pdf.add_title_page(args.title, "從龍樹中觀到天台圓教的理論溯源與現代實踐", args.date, args.author)
    pdf.render_markdown(md_text)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    print(f"[DONE] PDF 已輸出至: {output_path}")


if __name__ == "__main__":
    main()
