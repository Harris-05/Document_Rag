"""What an exported answer contains, independent of the file format.

Both the PDF and the Word renderer take an `ExportContent`, so they cannot drift apart. The content
is built from the saved message, so any answer in the history can be exported, not only a new one.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.schemas import ChatMessage

_LABEL = re.compile(r"^[ \t]*General explanation \(not from the document\):[ \t]*", re.IGNORECASE | re.MULTILINE)
QUALITY_LABELS = {
    "sufficient": "Strong evidence",
    "partial": "Partial evidence",
    "insufficient": "Nothing found",
}
VERIFIED_NOTE = (
    "Quotes marked Verified were found word for word in the document text by an automated check. "
    "A quote marked Not verified could not be found and should not be relied on."
)
GENERAL_NOTE = "General background from the model's own knowledge. It is not from the document."


@dataclass(frozen=True)
class Quote:
    n: int
    text: str
    verified: bool
    page: int | None
    document: str | None


@dataclass
class ExportContent:
    question: str
    paragraphs: list[str]
    explanation: str | None
    quotes: list[Quote]
    documents: list[str]
    evidence: str | None
    incomplete: bool
    generated: str
    filename_stem: str = "answer"
    multi: bool = False
    notes: list[str] = field(default_factory=list)


def _paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]


def split_answer(content: str) -> tuple[str, str | None]:
    """The document-based answer, and the labelled general explanation if there is one."""
    match = _LABEL.search(content)
    if not match:
        return content.strip(), None
    return content[: match.start()].strip(), content[match.end() :].strip() or None


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:7]
    return "-".join(words) or "answer"


def build_content(message: ChatMessage, question: str | None, document_names: list[str], multi: bool) -> ExportContent:
    answer, explanation = split_answer(message.content)
    quotes = [
        Quote(
            n=c.n,
            text=c.quote,
            verified=c.verified,
            page=c.page,
            document=c.document_name if multi else None,
        )
        for c in sorted(message.citations, key=lambda c: c.n)
        if c.quote.strip() or not c.verified
    ]
    asked = (question or "").strip()
    return ExportContent(
        question=asked or "(question not available)",
        paragraphs=_paragraphs(answer),
        explanation=explanation,
        quotes=quotes,
        documents=document_names,
        evidence=QUALITY_LABELS.get(message.quality or ""),
        incomplete=message.status == "stopped",
        generated=datetime.now().strftime("%d %B %Y, %H:%M"),
        filename_stem=f"answer-{_slug(asked)}",
        multi=multi,
    )

