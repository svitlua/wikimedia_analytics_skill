#!/usr/bin/env python3
"""
Step 4 of the pipeline: Compiles an executive 1-page PDF summary brief
combining findings from metrics.json (Step 2) and chart.png (Step 3).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def register_cyrillic_font() -> tuple[str, str]:
    """
    Registers TTF fonts that support Cyrillic characters (Windows Arial / Linux DejaVu / macOS Arial).
    Returns (font_name_regular, font_name_bold).
    """
    font_candidates = [
        # Windows
        ("Arial", "C:/Windows/Fonts/arial.ttf", "Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"),
        # Linux
        ("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        # macOS
        ("Arial", "/Library/Fonts/Arial.ttf", "Arial-Bold", "/Library/Fonts/Arial Bold.ttf"),
    ]

    for name, path, bold_name, bold_path in font_candidates:
        if Path(path).exists() and Path(bold_path).exists():
            pdfmetrics.registerFont(TTFont(name, path))
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
            return name, bold_name

    # Fallback to standard Helvetica if custom font is not found
    return "Helvetica", "Helvetica-Bold"


FONT_REGULAR, FONT_BOLD = register_cyrillic_font()


def build_pdf_report(summary_path: Path, chart_path: Path, output_path: Path) -> None:
    metrics = json.loads(summary_path.read_text(encoding="utf-8"))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()

    PRIMARY_COLOR = colors.HexColor("#1A365D")
    SECONDARY_COLOR = colors.HexColor("#2B6CB0")
    TEXT_MUTED = colors.HexColor("#4A5568")
    BORDER_COLOR = colors.HexColor("#CBD5E0")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=PRIMARY_COLOR,
        fontName=FONT_BOLD,
        spaceAfter=2,
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=TEXT_MUTED,
        fontName=FONT_REGULAR,
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=PRIMARY_COLOR,
        fontName=FONT_BOLD,
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#2D3748"),
        fontName=FONT_REGULAR,
    )
    header_cell_style = ParagraphStyle(
        "HeaderCell",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=10,
        textColor=colors.whitesmoke,
        fontName=FONT_BOLD,
    )

    story = []

    # 1. Header & Title Section
    topic = metrics.get("topic", "Analysis")
    start_date = metrics.get("start", "N/A")
    end_date = metrics.get("end", "N/A")
    story.append(Paragraph(f"Product Strategy Brief: {topic}", title_style))
    story.append(
        Paragraph(
            f"Coverage Range: <b>{start_date}</b> to <b>{end_date}</b> &nbsp;|&nbsp; "
            f"Source Language: <b>{metrics.get('source_lang', 'en')}</b> &nbsp;|&nbsp; "
            f"Data Source: Wikimedia Analytics API",
            meta_style,
        )
    )

    # 2. Embed Visual Trend Chart
    if chart_path.exists():
        story.append(Image(str(chart_path), width=7.4 * inch, height=3.2 * inch))
        story.append(Spacer(1, 4))

    # 3. Summary Table
    story.append(Paragraph("Market Comparison Metrics", section_style))

    table_data = [
        [
            Paragraph("Lang", header_cell_style),
            Paragraph("Resolved Article Title", header_cell_style),
            Paragraph("Total Views", header_cell_style),
            Paragraph("Avg Views/Mo", header_cell_style),
            Paragraph("Growth %", header_cell_style),
            Paragraph("Confidence Status", header_cell_style),
        ]
    ]

    for lang, m in metrics.get("languages", {}).items():
        if not m.get("resolved"):
            table_data.append([
                Paragraph(f"<b>{lang.upper()}</b>", body_style),
                Paragraph("<i>[NOT FOUND / NO ARTICLE]</i>", body_style),
                Paragraph("N/A", body_style),
                Paragraph("N/A", body_style),
                Paragraph("N/A", body_style),
                Paragraph("<font color='#C53030'><b>UNRESOLVED</b></font>", body_style),
            ])
        else:
            growth_val = m.get("growth_rate_pct")
            growth_str = f"{growth_val:+.1f}%" if growth_val is not None else "N/A"
            
            conf = m.get("confidence", "UNKNOWN")
            if conf in ("HIGH_GROWTH", "HIGH_SHARE"):
                conf_html = f"<font color='#276749'><b>{conf}</b></font>"
            elif conf in ("LOW_SPIKY", "LOW_VOLUME", "LOW_SHARE"):
                conf_html = f"<font color='#DD6B20'><b>{conf}</b></font>"
            elif conf in ("DECLINING", "DROPPING"):
                conf_html = f"<font color='#C53030'><b>{conf}</b></font>"
            else:
                conf_html = f"<b>{conf}</b>"

            table_data.append([
                Paragraph(f"<b>{lang.upper()}</b>", body_style),
                Paragraph(m.get("resolved_title", ""), body_style),
                Paragraph(f"{m.get('total_views', 0):,}", body_style),
                Paragraph(f"{m.get('monthly_avg', 0):,.0f}", body_style),
                Paragraph(growth_str, body_style),
                Paragraph(conf_html, body_style),
            ])

    col_widths = [0.6 * inch, 2.6 * inch, 1.1 * inch, 1.1 * inch, 0.85 * inch, 1.25 * inch]
    metrics_table = Table(table_data, colWidths=col_widths)
    metrics_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SECONDARY_COLOR),
            ("ALIGN", (2, 0), (4, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(metrics_table)
    story.append(Spacer(1, 6))

    # 4. Strategic Observations
    story.append(Paragraph("Strategic Observations & Market Insights", section_style))
    for lang, m in metrics.get("languages", {}).items():
        title_disp = m.get("resolved_title") or "[No local article]"
        note_text = m.get("notes", "No additional observation.")
        bullet_text = f"• <b>{lang.upper()}</b> ({title_disp}): {note_text}"
        story.append(Paragraph(bullet_text, body_style))
        story.append(Spacer(1, 2))

    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export 1-page PDF product brief.")
    parser.add_argument("--summary", required=True, help="Path to metrics.json from Step 2.")
    parser.add_argument("--chart", required=True, help="Path to chart.png from Step 3.")
    parser.add_argument("--output", help="Optional output path for report.pdf.")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    chart_path = Path(args.chart)

    if not summary_path.exists():
        print(f"Error: Summary file '{summary_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output) if args.output else summary_path.parent / "report.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    build_pdf_report(summary_path, chart_path, out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()