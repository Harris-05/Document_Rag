"""A word-level diff inside one changed clause, for showing exactly which words changed.

This is only for display, within a clause that has already been matched. The comparison itself is
clause by clause, not a character diff of the whole document.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Segment:
    op: str  # "equal", "delete" (only in the old text) or "insert" (only in the new text)
    text: str


def word_diff(old: str, new: str) -> tuple[list[Segment], float]:
    """The segments that turn `old` into `new`, and how similar the two are from 0 to 1."""
    before, after = old.split(), new.split()
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    segments: list[Segment] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append(Segment("equal", " ".join(before[i1:i2])))
            continue
        if i2 > i1:
            segments.append(Segment("delete", " ".join(before[i1:i2])))
        if j2 > j1:
            segments.append(Segment("insert", " ".join(after[j1:j2])))
    return segments, matcher.ratio()
