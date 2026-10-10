"""Extracting the facts that make a change substantive: amounts, percentages, durations, dates and
obligation words.

This is deliberately plain code, not a model. "AED 100,000" becoming "AED 1,000,000" is a change
whatever anyone thinks of the wording around it, so it must be found the same way every time and must
not depend on a model's judgement. The figures are also shown to the reader as old to new chips.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUMBER_WORD = "|".join(sorted([*_UNITS, *_TENS, "hundred"], key=len, reverse=True))
_WORDS = rf"(?:{_NUMBER_WORD})(?:[\s-]+(?:and|{_NUMBER_WORD}))*"

_CURRENCIES = r"AED|USD|EUR|GBP|SAR|QAR|KWD|OMR|BHD|EGP|INR|PKR|CAD|AUD|CHF|JPY|CNY|US\$|\$|€|£"
_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MULTIPLIERS = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "k": 1e3, "m": 1e6, "bn": 1e9}
_QUALIFIER = r"calendar|business|working"
_UNIT = r"days?|weeks?|months?|years?"

_MONEY_PREFIX = re.compile(
    rf"(?<![A-Za-z])(?P<cur>{_CURRENCIES})\s?(?P<num>{_NUMBER})(?:\s?(?P<mult>million|billion|thousand)\b|(?P<short>bn|k|m)\b)?",
    re.IGNORECASE,
)
_MONEY_SUFFIX = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUMBER})(?:\s?(?P<mult>million|billion|thousand)\b)?\s?(?P<cur>AED|USD|EUR|GBP|SAR|QAR|INR|PKR)\b",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s?(?:%|per\s?cent\b|percent\b)", re.IGNORECASE)
_DURATION = re.compile(
    rf"(?:(?P<wa>{_WORDS})\s+)?\((?P<pa>\d+)\)\s*(?:(?P<qa>{_QUALIFIER})\s+)?(?P<ua>{_UNIT})\b"
    rf"|(?<![\w.,/-])(?P<db>\d+)\s*(?:(?P<qb>{_QUALIFIER})\s+)?(?P<ub>{_UNIT})\b"
    rf"|\b(?P<wc>{_WORDS})\s+(?:(?P<qc>{_QUALIFIER})\s+)?(?P<uc>{_UNIT})\b",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
    "nov": 11, "dec": 12,
}
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_DATES = [
    re.compile(rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<m>{_MONTH})\.?,?\s+(?P<y>\d{{4}})\b", re.IGNORECASE),
    re.compile(rf"\b(?P<m>{_MONTH})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>\d{{4}})\b", re.IGNORECASE),
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
]

OBLIGATION_WORDS = ("shall", "must", "may", "will", "should", "cannot", "not", "no", "never", "without", "unless", "except")
_WORD_RE = re.compile(r"[A-Za-z']+")


@dataclass(frozen=True)
class Fact:
    kind: str  # "money", "percent", "duration" or "date"
    key: str  # canonical form, so "100,000 AED" and "AED 100,000" are equal
    display: str  # as written in the contract


@dataclass(frozen=True)
class FigureChange:
    kind: str
    old: str | None
    new: str | None


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def _clean(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


def words_to_number(words: str) -> int | None:
    total = current = 0
    seen = False
    for token in re.split(r"[\s-]+", words.lower()):
        if token == "and" or not token:
            continue
        if token in _UNITS:
            current += _UNITS[token]
        elif token in _TENS:
            current += _TENS[token]
        elif token == "hundred":
            current = (current or 1) * 100
        else:
            return None
        seen = True
    total += current
    return total if seen else None


def _overlaps(taken: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < b and a < end for a, b in taken)


def extract_facts(text: str) -> list[Fact]:
    facts: list[tuple[int, Fact]] = []
    taken: list[tuple[int, int]] = []

    def add(match: re.Match[str], fact: Fact) -> None:
        if not _overlaps(taken, match.start(), match.end()):
            taken.append((match.start(), match.end()))
            facts.append((match.start(), fact))

    for pattern in (_MONEY_PREFIX, _MONEY_SUFFIX):
        for match in pattern.finditer(text):
            value = _number(match["num"])
            multiplier = (match.groupdict().get("mult") or match.groupdict().get("short") or "").lower()
            value *= _MULTIPLIERS.get(multiplier, 1)
            currency = match["cur"].upper().replace("US$", "USD")
            add(match, Fact("money", f"{currency} {_clean(value)}", match.group(0).strip()))

    for match in _PERCENT.finditer(text):
        add(match, Fact("percent", f"{_clean(_number(match['num']))}%", match.group(0).strip()))

    for match in _DURATION.finditer(text):
        groups = match.groupdict()
        if groups["pa"]:
            amount, qualifier, unit = int(groups["pa"]), groups["qa"], groups["ua"]
        elif groups["db"]:
            amount, qualifier, unit = int(groups["db"]), groups["qb"], groups["ub"]
        else:
            parsed = words_to_number(groups["wc"])
            if parsed is None:
                continue
            amount, qualifier, unit = parsed, groups["qc"], groups["uc"]
        unit = unit.lower().rstrip("s")
        label = f"{amount} {(qualifier or '').lower() + ' ' if qualifier else ''}{unit}".replace("  ", " ")
        add(match, Fact("duration", label, match.group(0).strip()))

    for pattern in _DATES:
        for match in pattern.finditer(text):
            month = match["m"]
            month_number = int(month) if month.isdigit() else _MONTHS.get(month[:3].lower())
            try:
                iso = date(int(match["y"]), month_number or 0, int(match["d"])).isoformat()
            except ValueError:
                continue
            add(match, Fact("date", iso, match.group(0).strip()))

    return [fact for _, fact in sorted(facts, key=lambda item: item[0])]


def diff_facts(old: list[Fact], new: list[Fact]) -> list[FigureChange]:
    """Which figures were removed, added or replaced. Equal figures cancel out, wherever they sit."""
    remaining_new = Counter(f.key for f in new)
    removed: list[Fact] = []
    for fact in old:
        if remaining_new[fact.key] > 0:
            remaining_new[fact.key] -= 1
        else:
            removed.append(fact)

    remaining_old = Counter(f.key for f in old)
    added: list[Fact] = []
    for fact in new:
        if remaining_old[fact.key] > 0:
            remaining_old[fact.key] -= 1
        else:
            added.append(fact)

    changes: list[FigureChange] = []
    for fact in removed:
        partner = next((a for a in added if a.kind == fact.kind), None)
        if partner is not None:
            added.remove(partner)
            changes.append(FigureChange(fact.kind, fact.display, partner.display))
        else:
            changes.append(FigureChange(fact.kind, fact.display, None))
    changes.extend(FigureChange(fact.kind, None, fact.display) for fact in added)
    return changes


def obligation_counts(text: str) -> Counter[str]:
    words = (word.lower() for word in _WORD_RE.findall(text))
    return Counter(word for word in words if word in OBLIGATION_WORDS)


def obligation_changes(old: str, new: str) -> list[tuple[str, int, int]]:
    """Words like shall, may, not whose count differs between the two versions."""
    before, after = obligation_counts(old), obligation_counts(new)
    return [(word, before[word], after[word]) for word in OBLIGATION_WORDS if before[word] != after[word]]
