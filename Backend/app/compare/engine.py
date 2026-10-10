"""Comparing two versions of a contract end to end.

segment each version into clauses -> align the clauses -> work out what changed in each pair ->
rate how significant every change is -> write an overview.

`compare_documents` is pure orchestration over the modules beside it, so it can be tested with a
scripted model and no database. The background job in `jobs.py` wraps it with progress and storage.
"""

import asyncio
from collections import Counter
from collections.abc import Callable
from typing import Any

from app.compare.align import align
from app.compare.facts import diff_facts, extract_facts, obligation_changes
from app.compare.rate import RANK, Change, describe_figures, rate_changes, summarise
from app.compare.segment import Span, Unit, segment
from app.compare.worddiff import word_diff
from app.config import Settings
from app.rag.llm import LLMClient

Progress = Callable[[str, int, int | None], None]


def _spans(unit: Unit | None) -> list[dict[str, int]]:
    return [{"page": s.page, "start": s.start, "end": s.end} for s in (unit.spans if unit else [])]


def _body(unit: Unit) -> str:
    """The clause text without its heading, which is shown separately."""
    if unit.heading and unit.text.startswith(unit.heading):
        return unit.text[len(unit.heading) :].strip() or unit.text
    return unit.text


def _side(unit: Unit | None) -> dict[str, Any] | None:
    if unit is None:
        return None
    return {"text": _body(unit), "heading": unit.heading, "page": unit.page, "ranges": _spans(unit)}


def _build_changes(old_units: list[Unit], new_units: list[Unit]) -> tuple[list[Change], int]:
    alignment = align(old_units, new_units)
    changes: list[Change] = []
    unchanged = 0
    new_of_old = {pair.old: pair.new for pair in alignment.pairs}

    for pair in alignment.pairs:
        old_unit, new_unit = old_units[pair.old], new_units[pair.new]
        if pair.kind == "exact" and not pair.moved:
            unchanged += 1
            continue
        if pair.kind == "exact":
            changes.append(Change("moved", old_unit, new_unit, 1.0, [], [], [], float(pair.new), moved=True))
            continue
        # The diff is of the clause body only: a clause number that shifted by one is not a change.
        segments, similarity = word_diff(_body(old_unit), _body(new_unit))
        figures = diff_facts(extract_facts(old_unit.text), extract_facts(new_unit.text))
        obligations = obligation_changes(old_unit.text, new_unit.text)
        changes.append(
            Change("modified", old_unit, new_unit, similarity, segments, figures, obligations, float(pair.new), moved=pair.moved)
        )

    for index in alignment.added:
        unit = new_units[index]
        figures = diff_facts([], extract_facts(unit.text))
        changes.append(Change("added", None, unit, 0.0, [], figures, [], float(index)))

    for index in alignment.removed:
        unit = old_units[index]
        previous = max((o for o in new_of_old if o < index), default=None)
        order = (new_of_old[previous] + 0.5) if previous is not None else -0.5
        figures = diff_facts(extract_facts(unit.text), [])
        changes.append(Change("removed", unit, None, 0.0, [], figures, [], order))

    changes.sort(key=lambda change: change.order)
    return changes, unchanged


def _change_json(change: Change, number: int) -> dict[str, Any]:
    return {
        "id": number,
        "type": change.type,
        "moved": change.moved,
        "significance": change.significance,
        "ai_rated": change.ai_rated,
        "raised_by_rules": change.raised_by_rules,
        "category": change.category,
        "title": change.title,
        "summary": change.summary,
        "similarity": round(change.similarity, 3),
        "figures": [{"kind": f.kind, "old": f.old, "new": f.new} for f in change.figures],
        "figure_text": describe_figures(change.figures),
        "obligations": [{"word": w, "old": before, "new": after} for w, before, after in change.obligations],
        "old": _side(change.old),
        "new": _side(change.new),
        "diff": [{"op": s.op, "text": s.text} for s in change.segments],
        "position": change.order,
    }


async def compare_documents(
    old_pages: list[tuple[int, str]],
    new_pages: list[tuple[int, str]],
    llm: LLMClient | None,
    settings: Settings,
    progress: Progress | None = None,
) -> dict[str, Any]:
    def report(stage: str, done: int = 0, total: int | None = None) -> None:
        if progress:
            progress(stage, done, total)

    report("reading")
    old_units, new_units = await asyncio.gather(asyncio.to_thread(segment, old_pages), asyncio.to_thread(segment, new_pages))

    report("aligning")
    changes, unchanged = await asyncio.to_thread(_build_changes, old_units, new_units)

    report("rating", 0, None)
    outcome = await rate_changes(changes, llm, settings, lambda done, total: report("rating", done, total))

    # Most significant first is the default order for the reader; the interface can re-sort.
    numbered = [_change_json(change, number) for number, change in enumerate(changes, start=1)]
    counts = Counter(change.type for change in changes)
    stats = {
        "old_clauses": len(old_units),
        "new_clauses": len(new_units),
        "unchanged": unchanged,
        "modified": counts["modified"],
        "added": counts["added"],
        "removed": counts["removed"],
        "moved": counts["moved"],
        "by_significance": {
            level: sum(1 for c in numbered if c["significance"] == level)
            for level in sorted(RANK, key=lambda key: -RANK[key])
        },
    }

    report("summarising")
    overview = await summarise(
        sorted(numbered, key=lambda c: -RANK.get(c["significance"], 0)), stats, llm, settings
    )

    return {
        "stats": stats,
        "summary": overview,
        "ai_used": outcome.ai_used,
        "ai_notice": outcome.notice,
        "changes": numbered,
    }
