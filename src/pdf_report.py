from __future__ import annotations

from pathlib import Path
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


SECTION_TITLES = {
    "QUESTION",
    "PROBABILITY DISTRIBUTION",
    "MOST LIKELY OUTCOME",
    "TRADE SNAPSHOT",
    "REFERENCE ESTIMATES",
    "BARRIER-THEORY DETAILS",
    "TOUCH-SUPPORTING FACTORS",
    "TOUCH-OPPOSING FACTORS",
    "EXTERNAL MARKET CONTEXT",
    "MODEL RISK NOTES",
}


def write_pdf_report(report_text: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    styles = _styles()
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="FX Barrier Touch Intelligence Report",
    )

    story = []
    for index, raw_line in enumerate(report_text.splitlines()):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4 * mm))
            continue

        if index == 0:
            story.append(Paragraph(_escape(line), styles["Title"]))
            story.append(Spacer(1, 5 * mm))
        elif line in SECTION_TITLES:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(_escape(line), styles["Section"]))
        elif line.startswith("- "):
            story.append(Paragraph(_escape(line), styles["Bullet"]))
        else:
            for wrapped in _wrap(line):
                story.append(Paragraph(_escape(wrapped), styles["Body"]))

    document.build(story)
    return path


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=4,
        ),
        "Section": ParagraphStyle(
            "ReportSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0F766E"),
            spaceBefore=4,
            spaceAfter=5,
        ),
        "Body": ParagraphStyle(
            "ReportBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#111827"),
            spaceAfter=2,
        ),
        "Bullet": ParagraphStyle(
            "ReportBullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            leftIndent=5 * mm,
            firstLineIndent=-3 * mm,
            textColor=colors.HexColor("#111827"),
            spaceAfter=2,
        ),
    }


def _wrap(line: str) -> list[str]:
    return textwrap.wrap(line, width=110, break_long_words=False) or [line]


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
