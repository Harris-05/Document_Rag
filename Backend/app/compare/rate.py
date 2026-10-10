"""Rating how significant each change is.

Two signals are combined and the HIGHER one wins:

* A rules-based FLOOR computed by code from the extracted facts. If a figure, duration, date or
  percentage changed, the change is at least "major", whatever the wording around it looks like. If an
  obligation word (shall, may, not, ...) changed it is at least "minor". Only a change that is purely
  punctuation, numbering or formatting is "cosmetic" by rules.
* The model's judgement of the meaning, which decides everything the rules cannot: whether a
  rewording changes the legal effect, and how serious a changed or missing clause is.

So the model can raise a rating but can never talk a changed figure down to "cosmetic". Without an AI
key the rules still produce honest ratings, and the rest are marked "unrated" rather than guessed.
"""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_validator

from app.compare import prompts
from app.compare.align import strip_number
from app.compare.facts import FigureChange
from app.compare.segment import Unit
from app.compare.worddiff import Segment
from app.config import Settings
from app.rag.llm import LLMClient, LLMError

# Ascending order of seriousness. "unrated" sits above "minor": it needs a person to look at it.
RANK = {"cosmetic": 0, "minor": 1, "unrated": 2, "major": 3, "critical": 4}

_CATEGORY_KEYWORDS = [
    ("indemnity", ("indemnif", "indemnity", "hold harmless")),
    ("liability", ("liabil", "consequential", "aggregate cap")),
    ("termination", ("terminat", "convenience", "breach cure")),
    ("term_renewal", ("renew", "initial term", "expiry", "commencement")),
    ("payment", ("payment", "invoice", "fee", "price", "interest", "late charge")),
    ("confidentiality", ("confidential", "non-disclosure")),
    ("ip", ("intellectual property", "copyright", "licen", "patent", "trademark")),
    ("governing_law", ("governing law", "governed by", "jurisdiction")),
    ("disputes", ("arbitrat", "dispute", "mediation", "courts of")),
    ("warranties", ("warrant", "represent")),
    ("data_protection", ("personal data", "data protection", "gdpr", "privacy")),
    ("scope_services", ("services", "deliverable", "scope", "specification")),
    ("definitions", ("means", "defined", "definition", "interpretation")),
]
_FIGURE_WORDS = {"money": "amount", "percent": "percentage", "duration": "period", "date": "date"}
_INTEGER = re.compile(r"\b\d+(?:\.\d+)*\b")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")


@dataclass
class Change:
    type: Literal["modified", "added", "removed", "moved"]
    old: Unit | None
    new: Unit | None
    similarity: float
    segments: list[Segment]
    figures: list[FigureChange]
    obligations: list[tuple[str, int, int]]
    order: float
    moved: bool = False
    # Filled in by rating:
    floor: str = "cosmetic"
    significance: str = "unrated"
    category: str = "other"
    title: str = ""
    summary: str = ""
    ai_rated: bool = False
    raised_by_rules: bool = False
    needs_ai: bool = True
    rules_note: str = ""
    key: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def heading(self) -> str:
        unit = self.new or self.old
        return strip_number(unit.heading).strip() if unit and unit.heading else ""

    @property
    def body_words(self) -> int:
        unit = self.new or self.old
        return unit.word_count if unit else 0


def _skeleton(text: str, figures: list[FigureChange]) -> str:
    """The text with punctuation, case and bare numbers (clause numbers, cross-references) flattened."""
    flat = text.lower()
    for figure in figures:
        for shown in (figure.old, figure.new):
            if shown:
                flat = flat.replace(shown.lower(), " ")
    flat = _THOUSANDS.sub("", flat)  # "100,000" and "100000" are the same number
    flat = _INTEGER.sub("#", flat)
    return re.sub(r"[^a-z#]+", "", flat)


def guess_category(text: str) -> str:
    lowered = text.lower()
    for category, words in _CATEGORY_KEYWORDS:
        if any(word in lowered for word in words):
            return category
    return "other"


def _short_title(change: Change) -> str:
    if change.heading:
        return change.heading[:80]
    unit = change.new or change.old
    words = strip_number(unit.text).split() if unit else []
    return " ".join(words[:7]) + ("..." if len(words) > 7 else "")


def describe_figures(figures: list[FigureChange]) -> list[str]:
    parts = []
    for figure in figures:
        word = _FIGURE_WORDS.get(figure.kind, figure.kind)
        if figure.old and figure.new:
            parts.append(f"{word}: {figure.old} -> {figure.new}")
        elif figure.old:
            parts.append(f"{word} removed: {figure.old}")
        else:
            parts.append(f"{word} added: {figure.new}")
    return parts


def apply_rules(change: Change) -> None:
    """The floor that no model judgement may go below, and the plain fallback wording."""
    change.category = guess_category(" ".join(u.text for u in (change.old, change.new) if u))
    change.title = _short_title(change)

    if change.type == "moved":
        change.floor, change.needs_ai = "cosmetic", False
        change.significance = "cosmetic"
        change.summary = "This clause was moved. Its wording is unchanged."
        return

    if change.type in ("added", "removed"):
        # Whether a whole clause matters cannot be told from its words alone, so without a judgement
        # it stays "not rated" rather than being guessed. A figure in it still raises the floor.
        change.floor = "cosmetic"
        word = "added" if change.type == "added" else "removed"
        change.summary = f"A clause was {word}."
        if change.figures:
            change.floor = "major"
        return

    # A modified clause.
    old_text, new_text = change.old.text if change.old else "", change.new.text if change.new else ""
    if change.figures:
        change.floor = "major"
        change.summary = "A figure in this clause changed: " + "; ".join(describe_figures(change.figures)) + "."
        return
    if _skeleton(old_text, []) == _skeleton(new_text, []) or _skeleton(old_text, change.figures) == _skeleton(
        new_text, change.figures
    ):
        change.floor, change.needs_ai = "cosmetic", False
        change.significance = "cosmetic"
        change.summary = "Only punctuation, numbering or formatting changed."
        return
    if change.obligations:
        change.floor = "minor"
        change.summary = "Wording changed, including words that set obligations (" + ", ".join(
            w for w, _, _ in change.obligations
        ) + ")."
    else:
        change.floor = "cosmetic"
        change.summary = "The wording of this clause changed."


class _RatedItem(BaseModel):
    id: int
    significance: str = "unrated"
    category: str = "other"
    title: str = ""
    summary: str = ""

    @field_validator("significance", mode="before")
    @classmethod
    def _significance(cls, value: Any) -> str:
        value = str(value).strip().lower()
        return value if value in prompts.SIGNIFICANCE else "unrated"

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: Any) -> str:
        value = str(value).strip().lower()
        return value if value in prompts.CATEGORIES else "other"


class _RatedBatch(BaseModel):
    items: list[_RatedItem] = []


def finalize(change: Change, llm_significance: str | None) -> None:
    """Combine the model's rating with the rules floor. The higher of the two is the rating."""
    floor = change.floor
    if llm_significance is None or llm_significance == "unrated":
        # No usable judgement: keep the rules rating, or say plainly that it is not rated.
        change.significance = floor if RANK[floor] >= RANK["minor"] else "unrated"
        change.ai_rated = False
        return
    change.ai_rated = True
    if RANK[floor] > RANK[llm_significance]:
        change.significance = floor
        change.raised_by_rules = True
    else:
        change.significance = llm_significance


def _batch_items(batch: list[Change]) -> list[dict[str, Any]]:
    return [
        {
            "id": change.key,
            "type": change.type,
            "heading": change.heading,
            "old": change.old.text if change.old else None,
            "new": change.new.text if change.new else None,
            "figures": describe_figures(change.figures),
            "obligations": [f"{word} {before} -> {after}" for word, before, after in change.obligations],
        }
        for change in batch
    ]


@dataclass
class RateOutcome:
    ai_used: bool
    notice: str | None
    failed: int


async def rate_changes(
    changes: list[Change],
    llm: LLMClient | None,
    settings: Settings,
    on_progress: Callable[[int, int], None] | None = None,
) -> RateOutcome:
    for number, change in enumerate(changes, start=1):
        change.key = number
        apply_rules(change)
        if not change.needs_ai:
            finalize(change, change.significance)
            change.ai_rated = False

    candidates = [c for c in changes if c.needs_ai]
    # If there are more changes than the cap, the AI sees the ones the rules already find weightiest.
    candidates.sort(key=lambda c: (-RANK[c.floor], -c.body_words))
    to_rate, skipped = candidates[: settings.max_ai_rated_changes], candidates[settings.max_ai_rated_changes :]
    for change in skipped:
        finalize(change, None)

    if llm is None or not to_rate:
        for change in to_rate:
            finalize(change, None)
        notice = (
            "AI ratings are not available, so these ratings come from rules only. "
            "Changes marked not rated need a person's judgement."
            if llm is None and to_rate
            else None
        )
        return RateOutcome(ai_used=False, notice=notice, failed=len(to_rate))

    size = settings.rate_batch_size
    batches = [to_rate[i : i + size] for i in range(0, len(to_rate), size)]
    semaphore = asyncio.Semaphore(settings.rate_concurrency)
    finished = 0
    failures = 0

    async def rate_batch(batch: list[Change]) -> None:
        nonlocal finished, failures
        by_key = {c.key: c for c in batch}
        try:
            async with semaphore:
                raw = await llm.json_completion(
                    prompts.RATE_SYSTEM,
                    prompts.build_rate_prompt(_batch_items(batch)),
                    temperature=settings.temperature_judge,
                )
            parsed = _RatedBatch.model_validate(raw)
            seen: set[int] = set()
            for item in parsed.items:
                change = by_key.get(item.id)
                if change is None or item.id in seen:
                    continue
                seen.add(item.id)
                if item.title.strip():
                    change.title = item.title.strip()[:100]
                if item.summary.strip():
                    change.summary = item.summary.strip()
                change.category = item.category if item.category != "other" else change.category
                finalize(change, item.significance)
            for change in batch:
                if change.key not in seen:
                    failures += 1
                    finalize(change, None)
        except (LLMError, ValidationError):
            failures += len(batch)
            for change in batch:
                finalize(change, None)
        finally:
            finished += 1
            if on_progress:
                on_progress(finished, len(batches))

    await asyncio.gather(*(rate_batch(batch) for batch in batches))

    unrated = failures + len(skipped)
    notice = (
        f"AI ratings were unavailable for {unrated} of {len(changes)} changed clauses. Those keep their "
        "rules-based rating or are marked not rated."
        if unrated
        else None
    )
    return RateOutcome(ai_used=failures < len(to_rate), notice=notice, failed=failures)


async def summarise(
    changes: list[dict[str, Any]], counts: dict[str, int], llm: LLMClient | None, settings: Settings
) -> dict[str, Any] | None:
    """A plain-language overview. None when there is no AI or it fails; the counts still tell the story."""
    if llm is None:
        return None
    ranked = sorted(changes, key=lambda c: -RANK.get(c["significance"], 0))
    substantive = [c for c in ranked if c["significance"] != "cosmetic"][:40]
    try:
        raw = await llm.json_completion(
            prompts.SUMMARY_SYSTEM,
            prompts.build_summary_prompt(counts, substantive),
            temperature=settings.temperature_plan,
        )
    except LLMError:
        return None
    headline = str(raw.get("headline", "")).strip()
    points = [str(point).strip() for point in raw.get("key_points", []) if str(point).strip()][:6]
    return {"headline": headline, "key_points": points} if headline or points else None
