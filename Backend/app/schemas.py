from typing import Literal

from pydantic import BaseModel

DocumentStatus = Literal["processing", "ready", "failed"]
FileKind = Literal["pdf", "docx"]


class DocumentSummary(BaseModel):
    id: str
    filename: str
    file_kind: FileKind
    size_bytes: int
    status: DocumentStatus
    stage: str
    progress_done: int
    progress_total: int | None
    page_count: int | None
    empty_page_count: int
    word_count: int
    error_code: str | None
    error_message: str | None
    created_at: str


class PageText(BaseModel):
    page_number: int
    text: str


class DocumentDetail(DocumentSummary):
    char_count: int
    pages: list[PageText]


class ErrorBody(BaseModel):
    code: str
    message: str
