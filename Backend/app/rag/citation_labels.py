"""Turns evidence labels written as citations into numbered citations.

The model is asked to cite with plain numbers like [1]. Evidence passages carry labels like E2, and models
often cite with those instead: "[E2]". The interface only links numbered citations, so an answer written
that way would show raw "[E2]" text with nothing to click, and no quote list to check it against.

This runs over the answer as it streams. The first label cited becomes [1], the next [2], and so on, so
what the reader sees is always numbered. The mapping is kept so quotes the model did write (tagged with
their evidence label) are attached to the right number, and so the repair step knows which passage each
number came from.
"""

import json
import re
from typing import Any

from app.rag.quote_repair import parse_quotes

_COMPLETE = re.compile(r"\[(E\d{1,3}(?:\s*,\s*E\d{1,3})*)\]")
# The start of a marker that has not finished arriving, such as "[", "[E", "[E2" or "[E2, E".
_PARTIAL = re.compile(r"^\[(?:E\d{0,3}(?:\s*,\s*(?:E\d{0,3})?)*\s*)?$")
_NUMBERED = re.compile(r"\[(\d{1,2})\]")


class LabelRewriter:
    """Feed it the answer in pieces; it returns the same text with evidence labels replaced by numbers."""

    def __init__(self) -> None:
        self.numbers: dict[str, int] = {}
        self._pending = ""
        self._taken: set[int] = set()
        self._next = 1

    def _number_for(self, label: str) -> int:
        if label not in self.numbers:
            # Numbers the model already used itself are not handed out again.
            while self._next in self._taken:
                self._next += 1
            self.numbers[label] = self._next
            self._next += 1
        return self.numbers[label]

    def _convert(self, text: str) -> str:
        self._taken.update(int(m.group(1)) for m in _NUMBERED.finditer(text))
        return _COMPLETE.sub(
            lambda m: "".join(f"[{self._number_for(label.strip())}]" for label in m.group(1).split(",")), text
        )

    def feed(self, text: str) -> str:
        data = self._pending + text
        self._pending = ""
        # A marker can arrive split across pieces, so a possible beginning is held back until it is clear.
        cut = data.rfind("[")
        if cut != -1 and _PARTIAL.match(data[cut:]):
            self._pending = data[cut:]
            data = data[:cut]
        return self._convert(data)

    def flush(self) -> str:
        data, self._pending = self._pending, ""
        return self._convert(data)

    @property
    def label_of(self) -> dict[int, str]:
        """For each number handed out, the evidence label it stands for."""
        return {number: label for label, number in self.numbers.items()}


def remap_quotes(raw_quotes: str, numbers: dict[str, int]) -> str:
    """Re-number the model's quotes to match the numbers the answer now uses, going by evidence label."""
    if not numbers:
        return raw_quotes
    entries = parse_quotes(raw_quotes)
    if not entries:
        return raw_quotes
    remapped: list[dict[str, Any]] = []
    for item in entries:
        label = str(item.get("evidence", "")).strip()
        remapped.append({**item, "n": numbers[label]} if label in numbers else item)
    return json.dumps(remapped, ensure_ascii=False)
