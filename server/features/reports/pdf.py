"""Local PDF export with ReportLab (already in requirements.txt). No network, built-in fonts only."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def write_pdf(path: Path, doc: dict[str, Any]) -> None:
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=10, leading=14)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11, textColor=colors.HexColor("#444444"))

    story: list[Any] = [
        _p("AstroCare health report", h1),
        _p(f"{doc['mission']} · {doc['crew']} · Mission day {doc['missionDay']} (MET {doc['met']})", body),
        _p(f"Created {doc['createdTs']} · Report {doc['id']}", small),
        Spacer(1, 4 * mm),
    ]
    banner = Table([[_p(doc["notice"], body)]], colWidths=[170 * mm])
    banner.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#c2185b")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fde7ef")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(banner)

    for s in doc["sections"]:
        story.append(_p(s["title"], h2))
        story.append(_p(s["body"] or "-", body))

    story.append(_p("Sources (public NASA / CSA material)", h2))
    for src in doc["sources"]:
        story.append(_p(f"- {src}", small))
    story.append(Spacer(1, 3 * mm))
    story.append(_p("Medication decisions are left to the CMO and the flight surgeon. "
                    "Possible links in this report are not confirmed causes.", small))

    SimpleDocTemplate(str(path), pagesize=A4, title=f"AstroCare report {doc['id']}",
                      leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm).build(story)