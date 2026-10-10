"""PDF export, drawn with reportlab.

The built-in PDF fonts only cover Latin-1, so a TrueType font is registered when one can be found on
the machine (so accented letters and typographic quotes survive). If none is found, text is reduced
to what the built-in font can draw and anything else becomes "?", instead of failing or printing
boxes. Right-to-left scripts such as Arabic need shaping that is not done here.
"""

import io
import os
from functools import lru_cache
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from app.export.content import GENERAL_NOTE, VERIFIED_NOTE, ExportContent

_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    ),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial Italic.ttf"),
]
_INK = colors.HexColor("#1F2328")
_MUTED = colors.HexColor("#5F6670")
_GREEN = colors.HexColor("#1B7A43")
_RED = colors.HexColor("#B42B2B")
_RULE = colors.HexColor("#D5D9DE")


@lru_cache(maxsize=1)
def _fonts() -> tuple[str, str, str, bool]:
    """(regular, bold, italic, unicode). Falls back to the built-in Helvetica family."""
    for regular, bold, italic in _FONT_CANDIDATES:
        if all(os.path.exists(path) for path in (regular, bold, italic)):
            try:
                pdfmetrics.registerFont(TTFont("Export-Regular", regular))
                pdfmetrics.registerFont(TTFont("Export-Bold", bold))
                pdfmetrics.registerFont(TTFont("Export-Italic", italic))
                return "Export-Regular", "Export-Bold", "Export-Italic", True
            except Exception:  # an unreadable font file must not break the export
                continue
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", False


def _text(value: str, unicode_font: bool) -> str:
    if not unicode_font:
        value = value.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
        value = value.replace("\u2013", "-").replace("\u2014", "-").replace("\u2026", "...")
        value = value.encode("cp1252", errors="replace").decode("cp1252")
    return escape(value).replace("\n", "<br/>")


def render_pdf(content: ExportContent) -> bytes:
    regular, bold, italic, unicode_font = _fonts()

    def style(name: str, **kwargs) -> ParagraphStyle:
        base = {"fontName": regular, "fontSize": 10.5, "leading": 15, "textColor": _INK, "alignment": TA_LEFT}
        return ParagraphStyle(name, **{**base, **kwargs})

    title = style("title", fontName=bold, fontSize=20, leading=24, spaceAfter=4)
    meta = style("meta", fontSize=9, leading=13, textColor=_MUTED)
    heading = style("heading", fontName=bold, fontSize=12.5, leading=16, spaceBefore=14, spaceAfter=5)
    subheading = style("subheading", fontName=bold, fontSize=11, leading=15, spaceBefore=10, spaceAfter=3)
    body = style("body", spaceAfter=6)
    note = style("note", fontName=italic, fontSize=9, leading=12.5, textColor=_MUTED, spaceAfter=4)
    warning = style("warning", fontName=italic, textColor=_RED, spaceAfter=6)
    quote_head = style("quote_head", fontSize=10, leading=14, spaceBefore=8, keepWithNext=True)
    quote_body = style("quote_body", fontName=italic, leftIndent=14, spaceAfter=2)

    def p(text: str, st: ParagraphStyle) -> Paragraph:
        return Paragraph(_text(text, unicode_font), st)

    def raw(markup: str, st: ParagraphStyle) -> Paragraph:
        return Paragraph(markup, st)

    names = ", ".join(content.documents) or "unknown"
    label = "Documents" if len(content.documents) != 1 else "Document"
    meta_lines = [f"{label}: {_text(names, unicode_font)}", f"Exported {content.generated}"]
    if content.evidence:
        meta_lines.append(f"Evidence: {content.evidence}")

    story: list = [p("Answer with quotes", title), raw("<br/>".join(meta_lines), meta)]
    story += [HRFlowable(width="100%", thickness=0.6, color=_RULE, spaceBefore=8, spaceAfter=2)]

    story += [p("Question", heading), p(content.question, body)]

    story.append(p("Answer", heading))
    if content.incomplete:
        story.append(p("This answer was stopped before it finished and may be incomplete.", warning))
    for paragraph in content.paragraphs or ["(no answer text)"]:
        story.append(p(paragraph, body))

    if content.explanation:
        story.append(p("General explanation (not from the document)", subheading))
        story.append(p(GENERAL_NOTE, note))
        story.append(p(content.explanation, body))

    story.append(p("Quotes", heading))
    if not content.quotes:
        story.append(p("This answer has no quotes.", body))
    for quote in content.quotes:
        status_color = _GREEN if quote.verified else _RED
        status = "Verified" if quote.verified else "Not verified"
        where = []
        if quote.document:
            where.append(quote.document)
        if quote.verified and quote.page:
            where.append(f"page {quote.page}")
        head = (
            f'<font name="{bold}">[{quote.n}]</font>&nbsp;&nbsp;'
            f'<font name="{bold}" color="{status_color.hexval().replace("0x", "#")}">{status}</font>'
            + (f'&nbsp;&nbsp;<font color="#5F6670" size="9">{_text(", ".join(where), unicode_font)}</font>' if where else "")
        )
        text = f"\u201c{quote.text}\u201d" if quote.text else "(no quote was given for this citation)"
        story.append(KeepTogether([raw(head, quote_head), p(text, quote_body)]))

    story += [Spacer(1, 10), HRFlowable(width="100%", thickness=0.6, color=_RULE, spaceAfter=6), p(VERIFIED_NOTE, note)]

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(regular, 8.5)
        canvas.setFillColor(_MUTED)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {document.page}")
        canvas.drawString(20 * mm, 12 * mm, "Marginalia")
        canvas.restoreState()

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="Answer with quotes",
        author="Marginalia",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
