import io
from collections.abc import Iterator

import pytest
from docx import Document as WordDocument
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.main import app

CONTRACT_SENTENCE = "The Supplier shall indemnify the Customer against all losses arising from breach."


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def make_text_pdf(page_count: int = 3) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for number in range(1, page_count + 1):
        pdf.setFont("Helvetica", 12)
        pdf.drawString(72, 760, f"Clause {number}. {CONTRACT_SENTENCE}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_blank_pdf(page_count: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_image_only_pdf() -> bytes:
    """Draws shapes but no text, which is what a scanned page looks like to a text extractor."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.rect(72, 600, 400, 120, fill=1)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_mixed_pdf() -> bytes:
    """Page 1 has text, page 2 is blank."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.drawString(72, 760, CONTRACT_SENTENCE)
    pdf.showPage()
    pdf.rect(72, 600, 100, 100, fill=1)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_encrypted_pdf() -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(make_text_pdf(1)))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    document = WordDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
