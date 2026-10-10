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
    # Which document the quote belongs to. Always set for comparisons across documents.
    document_id: str | None = None
    document_name: str | None = None
    # Short label used inside the answer prompt (D1, D2, ...), kept so the interface can badge it.
    document_label: str | None = None


class TraceStep(BaseModel):
    kind: str
    round: int | None = None
    text: str
    detail: dict | None = None


class DocumentCoverage(BaseModel):
    """How well one document answered a question that was asked across several."""

    document_id: str
    name: str
    pages: int
    sections: int
    unreadable_pages: int
    # "sufficient", "partial" (some relevant text, not enough) or "none" (nothing relevant found)
    evidence: str


class Coverage(BaseModel):
    pages: int
    sections: int
    unreadable_pages: int
    rounds: int
    keyword_only: bool
    documents: list[DocumentCoverage] | None = None


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
    # "standard" is the graded-retrieval loop; "research" lets the model call tools to look things up.
    mode: Literal["standard", "research"] = "standard"

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ask a question about the document.")
        return value


class Conversation(BaseModel):
    """A chat about one document ("single") or several ("multi"). Documents are in the order chosen."""

    id: str
    kind: Literal["single", "multi"]
    created_at: str
    message_count: int = 0
    documents: list[DocumentSummary]


class CreateConversationRequest(BaseModel):
    document_ids: list[str] = Field(min_length=2)

    @field_validator("document_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Each document can only be selected once.")
        return value


# Comparing two versions of a contract.


class DocumentBrief(BaseModel):
    id: str
    filename: str
    file_kind: FileKind
    page_count: int | None


class FigureOut(BaseModel):
    kind: str
    old: str | None
    new: str | None


class ObligationOut(BaseModel):
    word: str
    old: int
    new: int


class SideOut(BaseModel):
    text: str
    heading: str
    page: int
    ranges: list[CitationRange]


class DiffSegmentOut(BaseModel):
    op: Literal["equal", "delete", "insert"]
    text: str


class ChangeOut(BaseModel):
    id: int
    type: Literal["modified", "added", "removed", "moved"]
    moved: bool
    significance: Literal["critical", "major", "minor", "cosmetic", "unrated"]
    ai_rated: bool
    raised_by_rules: bool
    category: str
    title: str
    summary: str
    similarity: float
    figures: list[FigureOut]
    figure_text: list[str]
    obligations: list[ObligationOut]
    old: SideOut | None
    new: SideOut | None
    diff: list[DiffSegmentOut]
    position: float


class OverviewOut(BaseModel):
    headline: str
    key_points: list[str]


class ComparisonStats(BaseModel):
    old_clauses: int
    new_clauses: int
    unchanged: int
    modified: int
    added: int
    removed: int
    moved: int
    by_significance: dict[str, int]


class ComparisonSummary(BaseModel):
    id: str
    old_document: DocumentBrief
    new_document: DocumentBrief
    status: DocumentStatus
    stage: str
    progress_done: int
    progress_total: int | None
    error_code: str | None
    error_message: str | None
    created_at: str
    stats: ComparisonStats | None = None
    ai_used: bool | None = None


class ComparisonDetail(ComparisonSummary):
    summary: OverviewOut | None = None
    ai_notice: str | None = None
    changes: list[ChangeOut] = []


class CreateComparisonRequest(BaseModel):
    old_document_id: str
    new_document_id: str
