"""Locating a model-supplied quote inside the real document text.

The model's quotes are never trusted and neither is any position it reports. A quote counts as
verified only if its words are found in the stored text. Both sides are normalised first so that the
harmless noise PDF extraction introduces (extra spaces, line breaks, curly quotes, ligatures,
hyphenation at line ends) does not cause genuine quotes to be rejected.

Matches are mapped back to character offsets in the ORIGINAL text, which is what citation
highlighting needs.
"""

import re
import unicodedata
from dataclasses import dataclass, field

PAGE_SEPARATOR = "\n\n"
MIN_QUOTE_CHARS = 8
MIN_SEGMENT_CHARS = 6

_ELLIPSIS = re.compile(r"\.{3,}|…")
_RUN = re.compile(r"\S+")

_CHAR_FOLDS = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "«": '"',
    "»": '"',
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
}
_SOFT_HYPHEN = "­"
# Characters with no visible width that extraction sometimes leaves inside words.
_INVISIBLE = {"​", "‌", "‍", "⁠", "﻿"}


@dataclass(frozen=True)
class PageRange:
    """A highlight range expressed in one page's own text."""

    page: int
    start: int
    end: int


@dataclass(frozen=True)
class QuoteMatch:
    ranges: list[PageRange]
    occurrences: int
    method: str  # "exact" | "dehyphenated"

    @property
    def first_page(self) -> int:
        return self.ranges[0].page


@dataclass
class _Normalized:
    text: str
    # origin[i] is the index in the source text that produced normalised character i.
    origin: list[int] = field(default_factory=list)


def _fold_run(run: str, base: int, keep_soft_hyphen: bool) -> tuple[str, list[int]]:
    """Fold one whitespace-free run. Plain ASCII, which is almost all contract text, takes a fast path."""
    if run.isascii():
        return run.lower(), list(range(base, base + len(run)))

    chars: list[str] = []
    origins: list[int] = []
    for offset, char in enumerate(run):
        if char in _INVISIBLE or (char == _SOFT_HYPHEN and not keep_soft_hyphen):
            continue
        if char == _SOFT_HYPHEN:
            char = "-"
        for folded in unicodedata.normalize("NFKC", char):
            folded = _CHAR_FOLDS.get(folded, folded)
            if folded.isspace():
                if chars and chars[-1] != " ":
                    chars.append(" ")
                    origins.append(base + offset)
                continue
            for piece in folded.lower():
                chars.append(piece)
                origins.append(base + offset)
    return "".join(chars), origins


def _normalize(source: str, *, dehyphenate: bool) -> _Normalized:
    """Collapse whitespace, fold typography and lower-case, remembering where each character came from.

    With `dehyphenate`, a word split by a hyphen at a line break ("indem-" then "nify" on the next
    line) is joined back into one word.
    """
    pieces: list[str] = []
    origin: list[int] = []
    previous_end = 0

    for match in _RUN.finditer(source):
        start = match.start()
        text, origins = _fold_run(match.group(), start, keep_soft_hyphen=dehyphenate)
        if not text:
            previous_end = match.end()
            continue

        if pieces:
            gap = source[previous_end:start]
            joins_a_split_word = (
                dehyphenate
                and "\n" in gap
                and pieces[-1].endswith("-")
                and len(pieces[-1]) >= 2
                and pieces[-1][-2].isalpha()
                and text[0].isalpha()
                and text[0].islower()
            )
            if joins_a_split_word:
                pieces[-1] = pieces[-1][:-1]
                origin.pop()
            else:
                pieces.append(" ")
                origin.append(previous_end)
        pieces.append(text)
        origin.extend(origins)
        previous_end = match.end()

    return _Normalized("".join(pieces), origin)


def normalize_for_match(text: str) -> str:
    """Normalise a quote the same way document text is normalised."""
    return _normalize(text, dehyphenate=False).text.strip()


class DocumentText:
    """All pages joined into one searchable string, remembering where each page begins."""

    def __init__(self, pages: list[tuple[int, str]]):
        self.pages = pages
        self._starts: list[int] = []
        parts: list[str] = []
        cursor = 0
        for _, text in pages:
            self._starts.append(cursor)
            parts.append(text)
            cursor += len(text) + len(PAGE_SEPARATOR)
        self.full_text = PAGE_SEPARATOR.join(parts)
        self._views: dict[str, _Normalized] = {}

    def prepare(self) -> None:
        """Build the normalised views up front. Safe to run in a worker thread."""
        self._view("exact")
        self._view("dehyphenated")

    def _view(self, name: str) -> _Normalized:
        if name not in self._views:
            self._views[name] = _normalize(self.full_text, dehyphenate=(name == "dehyphenated"))
        return self._views[name]

    def to_page_ranges(self, start: int, end: int) -> list[PageRange]:
        """Split a [start, end) range of the joined text into per-page ranges."""
        ranges: list[PageRange] = []
        for (number, text), page_start in zip(self.pages, self._starts, strict=True):
            page_end = page_start + len(text)
            lo, hi = max(start, page_start), min(end, page_end)
            if lo < hi:
                ranges.append(PageRange(number, lo - page_start, hi - page_start))
        return ranges

    def _page_at(self, offset: int) -> int:
        page = self.pages[0][0]
        for (number, _), page_start in zip(self.pages, self._starts, strict=True):
            if page_start <= offset:
                page = number
        return page

    def find_quote(self, quote: str, hint_pages: set[int] | None = None) -> QuoteMatch | None:
        """Return where `quote` really occurs, or None if it does not.

        `hint_pages` only breaks ties between several occurrences; it never makes a missing
        quote verified.
        """
        segments = [s for s in (normalize_for_match(part) for part in _ELLIPSIS.split(quote)) if s]
        if not segments or sum(len(s) for s in segments) < MIN_QUOTE_CHARS:
            return None
        if len(segments) > 1 and any(len(s) < MIN_SEGMENT_CHARS for s in segments):
            return None

        for method in ("exact", "dehyphenated"):
            match = self._match_segments(segments, method, hint_pages)
            if match:
                return match
        return None

    def _match_segments(
        self, segments: list[str], method: str, hint_pages: set[int] | None
    ) -> QuoteMatch | None:
        view = self._view(method)
        first = segments[0]

        starts: list[int] = []
        position = view.text.find(first)
        while position != -1:
            starts.append(position)
            position = view.text.find(first, position + 1)
        if not starts:
            return None

        if hint_pages:
            starts.sort(key=lambda s: self._page_at(view.origin[s]) not in hint_pages)

        for norm_start in starts:
            spans = self._chain(view, segments, norm_start)
            if spans is None:
                continue
            ranges: list[PageRange] = []
            for seg_start, seg_end in spans:
                orig_start = view.origin[seg_start]
                orig_end = view.origin[seg_end - 1] + 1
                ranges.extend(self.to_page_ranges(orig_start, orig_end))
            if ranges:
                return QuoteMatch(ranges=ranges, occurrences=len(starts), method=method)
        return None

    @staticmethod
    def _chain(
        view: _Normalized, segments: list[str], first_start: int
    ) -> list[tuple[int, int]] | None:
        """Every segment must appear after the previous one, in order."""
        spans: list[tuple[int, int]] = []
        cursor = first_start
        for segment in segments:
            found = view.text.find(segment, cursor)
            if found == -1:
                return None
            spans.append((found, found + len(segment)))
            cursor = found + len(segment)
        return spans
