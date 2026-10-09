"""Splitting page text into retrieval chunks.

Chunks never cross a page boundary, so every chunk has exactly one page number. A clause that
straddles two pages is covered by two chunks, and both can be retrieved.
"""

import re
from dataclasses import dataclass

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_BREAK = re.compile(r"(?<=[.;:!?])\s+(?=[A-Z0-9(\"'])")

# Section headings: "12. Termination", "Article 5 Payment", "TERMINATION". A line that ends like a
# sentence is body text, never a heading.
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+){0,3}\.?\s+[A-Z].{2,80}$")
_NAMED_HEADING = re.compile(r"^(?:article|section|clause|schedule|annex|appendix|part)\s+[\w.\-]+\b.*$", re.IGNORECASE)
_CAPS_HEADING = re.compile(r"^[A-Z][A-Z0-9 ,&'()/\-]{3,70}$")
_MAX_HEADING_WORDS = 12


@dataclass(frozen=True)
class RawChunk:
    page_number: int
    text: str
    # The section heading this chunk sits under (for example "12. Termination"), when one is known.
    # It is searched and embedded with the chunk, so a clause is findable by its heading even when
    # the heading is not repeated in the clause text.
    context: str = ""


def detect_heading(line: str) -> str | None:
    """Return the line if it looks like a section heading rather than a sentence of body text."""
    line = line.strip()
    if not 3 <= len(line) <= 90 or len(line.split()) > _MAX_HEADING_WORDS:
        return None
    if line.endswith((".", ";", ",")):
        return None
    if _NUMBERED_HEADING.match(line):
        return line
    if _NAMED_HEADING.match(line) and len(line.split()) <= 8:
        return line
    if _CAPS_HEADING.match(line) and sum(c.isalpha() for c in line) >= 4:
        return line
    return None


def _last_heading(text: str) -> str | None:
    found = None
    for line in text.splitlines():
        heading = detect_heading(line)
        if heading:
            found = heading
    return found


def _first_line_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return detect_heading(line)
    return None


def _split_oversized(unit: str, limit: int) -> list[str]:
    """Break text that is too long for one chunk, preferring sentence boundaries."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_BREAK.split(unit):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(text: str, size: int) -> str:
    if size <= 0 or len(text) <= size:
        return ""
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def chunk_page(
    page_number: int, text: str, target: int, overlap: int, carried_heading: str = ""
) -> list[RawChunk]:
    text = text.strip()
    if not text:
        return []

    units: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(_split_oversized(paragraph, target) if len(paragraph) > target else [paragraph])

    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 2 + len(unit) > target:
            chunks.append(current)
            current = f"{_overlap_tail(current, overlap)}\n\n{unit}".strip()
        else:
            current = f"{current}\n\n{unit}".strip() if current else unit
    if current:
        chunks.append(current)

    result: list[RawChunk] = []
    heading = carried_heading
    for chunk in chunks:
        # A chunk that opens with a heading belongs to it; otherwise it inherits the one in force.
        context = _first_line_heading(chunk) or heading
        result.append(RawChunk(page_number, chunk, context))
        heading = _last_heading(chunk) or heading
    return result


def chunk_pages(pages: list[tuple[int, str]], target: int, overlap: int) -> list[RawChunk]:
    chunks: list[RawChunk] = []
    heading = ""
    for page_number, text in pages:
        page_chunks = chunk_page(page_number, text, target, overlap, heading)
        chunks.extend(page_chunks)
        for chunk in page_chunks:
            heading = _last_heading(chunk.text) or heading
    return chunks
