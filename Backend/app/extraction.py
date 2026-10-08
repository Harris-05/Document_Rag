"""Text extraction for uploaded contracts.

PDFs go through LangChain's ``PyPDFLoader`` one page at a time so progress can be reported while a
large file is being read. DOCX files go through ``Docx2txtLoader``.
"""

import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.errors import DocumentError, ErrorCode

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ProgressCallback = Callable[[int, int | None], None]


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str


@dataclass(frozen=True)
class ExtractionResult:
    pages: list[ExtractedPage]
    empty_page_count: int

    @property
    def char_count(self) -> int:
        return sum(len(page.text) for page in self.pages)

    @property
    def word_count(self) -> int:
        return sum(len(page.text.split()) for page in self.pages)


def detect_file_kind(path: Path) -> str | None:
    """Identify the real file type from its leading bytes, not from the name the client gave us."""
    with path.open("rb") as handle:
        head = handle.read(1024)
    if b"%PDF-" in head:
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        # XLSX and PPTX are zip containers too; only a real Word file holds word/document.xml.
        try:
            with zipfile.ZipFile(path) as archive:
                return "docx" if "word/document.xml" in archive.namelist() else None
        except zipfile.BadZipFile:
            return None
    return None


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _meaningful_chars(text: str) -> int:
    return sum(1 for char in text if char.isalnum())


def extract_pdf(path: Path, on_progress: ProgressCallback) -> list[ExtractedPage]:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError(
                ErrorCode.PASSWORD_PROTECTED,
                "This PDF is password protected. Remove the password and upload it again.",
            )
        total = len(reader.pages)
    except DocumentError:
        raise
    except (PyPdfError, ValueError, OSError, KeyError) as exc:
        raise DocumentError(
            ErrorCode.CORRUPT_FILE, "This PDF could not be opened. The file may be damaged."
        ) from exc

    on_progress(0, total)
    pages: list[ExtractedPage] = []
    try:
        for index, document in enumerate(PyPDFLoader(str(path)).lazy_load(), start=1):
            pages.append(ExtractedPage(number=index, text=_clean(document.page_content)))
            on_progress(index, total)
    except (PyPdfError, ValueError, OSError, KeyError, RecursionError) as exc:
        raise DocumentError(
            ErrorCode.CORRUPT_FILE, "This PDF could not be read all the way through."
        ) from exc
    return pages


def extract_docx(path: Path, on_progress: ProgressCallback) -> list[ExtractedPage]:
    on_progress(0, None)
    try:
        documents = Docx2txtLoader(str(path)).load()
    except Exception as exc:  # docx2txt surfaces zipfile/XML errors of several types
        raise DocumentError(
            ErrorCode.CORRUPT_FILE, "This Word document could not be opened. The file may be damaged."
        ) from exc
    text = _clean("\n\n".join(document.page_content for document in documents))
    on_progress(1, None)
    # A .docx has no fixed pagination, so the whole body is kept as a single section.
    return [ExtractedPage(number=1, text=text)]


def extract_text(
    path: Path, kind: str, on_progress: ProgressCallback, min_text_chars: int
) -> ExtractionResult:
    pages = extract_pdf(path, on_progress) if kind == "pdf" else extract_docx(path, on_progress)

    meaningful = sum(_meaningful_chars(page.text) for page in pages)
    if meaningful < min_text_chars:
        subject = "PDF" if kind == "pdf" else "document"
        hint = (
            " It is probably a scan or an image-only file."
            if kind == "pdf"
            else " The file appears to contain no text."
        )
        raise DocumentError(
            ErrorCode.NO_TEXT,
            f"No readable text was found in this {subject}.{hint} Nothing was saved. "
            "Upload a version with selectable text.",
        )

    empty_pages = sum(1 for page in pages if _meaningful_chars(page.text) == 0)
    return ExtractionResult(pages=pages, empty_page_count=empty_pages if kind == "pdf" else 0)
