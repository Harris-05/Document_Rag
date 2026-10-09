from typing import Literal

from pydantic import BaseModel, Field, field_validator

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


class CitationRange(BaseModel):
    page: int
    start: int
    end: int


class Citation(BaseModel):
    n: int
    quote: str
    verified: bool
    page: int | None
    ranges: list[CitationRange]
    # Every occurrence of the quote in document order (each may span pages), and which one to show first.
    matches: list[list[CitationRange]] = []
    primary_index: int = 0
    occurrences: int


class TraceStep(BaseModel):
    kind: str
    round: int | None = None
    text: str
    detail: dict | None = None


class Coverage(BaseModel):
    pages: int
    sections: int
    unreadable_pages: int
    rounds: int
    keyword_only: bool


class ChatMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    status: Literal["complete", "stopped", "error"]
    quality: str | None
    citations: list[Citation]
    trace: list[TraceStep]
    coverage: Coverage | None
    error_message: str | None
    created_at: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ask a question about the document.")
        return value
