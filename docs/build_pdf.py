"""Build the Vivarium compendium PDF with proper table wrapping.

The shared pdf_create.py helper doesn't wrap table cells, so long content
overflows the page. This project-owned builder renders every table cell as
a reportlab Paragraph with computed column widths.

Usage: .venv/bin/python docs/build_pdf.py docs/compendium_v2.json -o docs/vivarium_compendium.pdf
"""
from __future__ import annotations

import argparse
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
USABLE = PAGE_W - 2 * MARGIN


def _page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.drawCentredString(PAGE_W / 2, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _col_widths(rows, n_cols):
    """Proportional widths from average text length, clamped to [0.14, 0.52]."""
    weights = []
    for c in range(n_cols):
        avg = sum(len(str(r[c])) for r in rows) / len(rows)
        weights.append(max(avg, 4))
    total = sum(weights)
    shares = [min(0.52, max(0.14, w / total)) for w in weights]
    norm = sum(shares)
    return [USABLE * s / norm for s in shares]


def build(spec_path: str, out_path: str) -> None:
    spec = json.load(open(spec_path, encoding="utf-8"))
    ss = getSampleStyleSheet()
    styles = {
        0: ParagraphStyle("Title0", parent=ss["Title"], spaceAfter=10),
        1: ParagraphStyle("H1", parent=ss["Heading1"], spaceBefore=14, spaceAfter=6),
        2: ParagraphStyle("H2", parent=ss["Heading2"], spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("Body", parent=ss["BodyText"], fontSize=9.5, leading=13),
        "cell": ParagraphStyle("Cell", parent=ss["BodyText"], fontSize=8, leading=10.5),
        "cellhead": ParagraphStyle("CellHead", parent=ss["BodyText"], fontSize=8,
                                   leading=10.5, fontName="Helvetica-Bold"),
    }

    story = []
    for el in spec["elements"]:
        etype = el.get("type")
        if etype == "heading":
            story.append(Paragraph(el["text"], styles.get(el.get("level", 1), styles[1])))
        elif etype == "paragraph":
            story.append(Paragraph(el["text"], styles["body"]))
            story.append(Spacer(1, 5))
        elif etype == "pagebreak":
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
        elif etype == "table":
            rows = el.get("rows", [])
            if not rows:
                continue
            n_cols = max(len(r) for r in rows)
            data = []
            for i, row in enumerate(rows):
                style = styles["cellhead"] if i == 0 and el.get("header", True) else styles["cell"]
                data.append([Paragraph(str(c), style) for c in row])
            table = Table(data, colWidths=_col_widths(rows, n_cols), repeatRows=1)
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(table)
            story.append(Spacer(1, 10))

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
        title=spec.get("title", "Vivarium"), author=spec.get("author", ""),
        subject=spec.get("subject", ""),
    )
    frame = Frame(MARGIN, MARGIN, USABLE, PAGE_H - 2 * MARGIN, id="main")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_page_number)])
    doc.build(story)
    print(f"built {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    build(args.spec, args.out)
