"""Splitting a document into clause-sized units for comparison.

A unit is a numbered clause or a paragraph, together with the heading above it. Units keep the page
positions they came from, so a change can be shown on the original page later.

Running headers, footers and page numbers are removed (they repeat on every page and would show up as
changes), and a clause that carries on across a page break is joined back into one unit.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from app.rag.chunking import detect_heading

# A line that starts a new clause: "12.", "12.1", "(a)", "(iv)", "A.", "Article 5", "Section 3".
# A wrapped line that merely begins with a number ("30 days written notice") does not match.
_CLAUSE_START = re.compile(
    r"^\s*(?:\d+(?:\.\d+)+\.?|\d+\.|\([a-z]{1,3}\)|\([ivxlc]+\)|\(\d{1,2}\)|[A-Z]\.|"
    r"(?:article|section|clause|schedule|annex|appendix)\s+[\w.\-]+)\s+\S",
    re.IGNORECASE,
)
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?\s*$", re.IGNORECASE)
# A sentence ends with . ; : ! ? optionally followed by closing quotes or brackets. A bare ")" does
# not end one: "...not less than ninety (90)" is plainly mid-sentence.
_SENTENCE_END = re.compile(r"[.;:!?][\"')\]]*\s*$")
MAX_HEADER_WORDS = 14


@dataclass(frozen=True)
class Span:
    """A stretch of one page's text, as character offsets into that page."""

    page: int
    start: int
    end: int


@dataclass
class Unit:
    index: int
    heading: str
    text: str
    spans: list[Span] = field(default_factory=list)
    starts_clause: bool = False

    @property
    def page(self) -> int:
        return self.spans[0].page

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class _Line:
    text: str
    start: int
    end: int


@dataclass
class _Block:
    lines: list[_Line]
    page: int
    starts_clause: bool

    @property
    def text(self) -> str:
        return " ".join(line.text.strip() for line in self.lines if line.text.strip())

    @property
    def span(self) -> Span:
        return Span(self.page, self.lines[0].start, self.lines[-1].end)


def _lines(text: str) -> list[_Line]:
    lines, position = [], 0
    for raw in text.split("\n"):
        lines.append(_Line(raw, position, position + len(raw)))
        position += len(raw) + 1
    return lines


def _blocks(page: int, text: str) -> list[_Block]:
    """Paragraphs of one page: split on blank lines and wherever a numbered clause begins."""
    blocks: list[_Block] = []
    current: list[_Line] = []
    starts_clause = False

    def flush() -> None:
        nonlocal current, starts_clause
        if current:
            # PDFs often put a heading directly above its paragraph with no blank line between them.
            if len(current) > 1 and _is_title_line(current[0].text):
                blocks.append(_Block([current[0]], page, starts_clause))
                blocks.append(_Block(current[1:], page, False))
            else:
                blocks.append(_Block(current, page, starts_clause))
        current, starts_clause = [], False

    for line in _lines(text):
        if not line.text.strip():
            flush()
            continue
        if _CLAUSE_START.match(line.text) and current:
            flush()
        if not current:
            starts_clause = bool(_CLAUSE_START.match(line.text))
        current.append(line)
    flush()
    return blocks


_SENTENCE_WORDS = re.compile(r"\b(?:shall|may|must|will|is|are|be|has|have|agrees?|means)\b", re.IGNORECASE)
_MAX_TITLE_WORDS = 8


def _is_title_line(text: str) -> bool:
    """A short heading-like line. Stricter than `detect_heading`, because here the line is followed
    directly by more text: the first line of a wrapped sentence must not be mistaken for a title."""
    return (
        detect_heading(text) is not None
        and len(text.split()) <= _MAX_TITLE_WORDS
        and not _SENTENCE_WORDS.search(text)
    )


def _is_heading(block: _Block) -> bool:
    return len(block.lines) == 1 and detect_heading(block.text) is not None and len(block.text.split()) <= MAX_HEADER_WORDS


def _running_lines(pages: list[tuple[int, str]]) -> set[str]:
    """Short lines that repeat across many pages: running headers, footers and page numbers."""
    seen: Counter[str] = Counter()
    for _, text in pages:
        for line in {line.text.strip().lower() for line in _lines(text) if line.text.strip()}:
            if len(line.split()) <= MAX_HEADER_WORDS:
                seen[line] += 1
    threshold = max(3, len(pages) // 2)
    return {line for line, count in seen.items() if count >= threshold and len(pages) >= 3}


def segment(pages: list[tuple[int, str]]) -> list[Unit]:
    running = _running_lines(pages)
    blocks: list[_Block] = []
    for page, text in pages:
        for block in _blocks(page, text):
            plain = block.text.strip().lower()
            if _PAGE_NUMBER.match(plain) or (len(block.lines) == 1 and plain in running):
                continue
            blocks.append(block)

    units: list[Unit] = []
    pending_heading: _Block | None = None

    def add(heading: _Block | None, body: _Block | None) -> None:
        pieces = [b for b in (heading, body) if b is not None]
        text = " ".join(b.text for b in pieces)
        if len(text.split()) < 2:
            return
        spans = [Span(heading.page, heading.span.start, body.span.end)] if heading and body and heading.page == body.page else [b.span for b in pieces]
        units.append(
            Unit(
                index=len(units),
                heading=heading.text if heading else "",
                text=text,
                spans=spans,
                starts_clause=(pieces[0].starts_clause),
            )
        )

    # A heading belongs to the clause beneath it. One with no clause beneath it (a document title above
    # the first section, or a section title followed straight by another) carries no obligations, so it
    # is not a unit of its own: otherwise "VERSION 1" becoming "VERSION 2" would show up as a change.
    for block in blocks:
        if _is_heading(block):
            pending_heading = block
            continue
        add(pending_heading, block)
        pending_heading = None

    return _join_across_pages(units)


def _join_across_pages(units: list[Unit]) -> list[Unit]:
    """A paragraph that stops mid-sentence at the end of a page and goes on at the top of the next is one unit."""
    joined: list[Unit] = []
    for unit in units:
        previous = joined[-1] if joined else None
        continues = (
            previous is not None
            and unit.page == previous.spans[-1].page + 1
            and not unit.starts_clause
            and not unit.heading
            and not _SENTENCE_END.search(previous.text)
        )
        if continues and previous is not None:
            previous.text = f"{previous.text} {unit.text}"
            previous.spans.extend(unit.spans)
        else:
            joined.append(unit)
    for position, unit in enumerate(joined):
        unit.index = position
    return joined
