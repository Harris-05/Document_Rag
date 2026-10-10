"""Matching the clauses of one version of a contract to the clauses of another.

Clauses are matched by meaning of their words, not by position or number, so a clause that was
renumbered, moved, or lightly reworded is still recognised as the same clause. What is left over on
the old side was removed, and what is left over on the new side was added.

1. Clauses whose words are identical (ignoring numbering and punctuation) are paired first.
2. The rest are paired by TF-IDF cosine similarity, strongest first, each clause used once.
3. Leftovers sitting in the same gap between matched clauses are paired if they share enough words.
4. Pairs whose order is out of step with the rest are marked as moved.
"""

import re
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

from app.compare.segment import Unit

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
# Numbering at the start of a clause or heading: "12.", "12.1", "(a)", "(iv)", "A.".
_LEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|\([a-z0-9]{1,4}\)|[a-z]\.)\s+", re.IGNORECASE)

MIN_SIMILARITY = 0.5
MIN_SIMILARITY_SHORT = 0.7
SHORT_CLAUSE_TOKENS = 8
HEADING_BONUS = 0.08
# For leftovers that sit in the same gap between matched clauses: the share of distinct words they have in common.
MIN_GAP_OVERLAP = 0.33


@dataclass
class Pair:
    old: int
    new: int
    kind: str  # "exact" or "similar"
    similarity: float
    moved: bool = False


@dataclass
class Alignment:
    pairs: list[Pair]
    removed: list[int]
    added: list[int]


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def strip_number(text: str) -> str:
    return _LEADING_NUMBER.sub("", text, count=1)


def match_key(unit: Unit) -> str:
    """The clause's words with numbering and punctuation removed. Equal keys mean equal wording."""
    return " ".join(tokens(strip_number(unit.text)))


def _heading_key(unit: Unit) -> str:
    return " ".join(tokens(strip_number(unit.heading))) if unit.heading else ""


def _tfidf(rows: list[list[str]], other: list[list[str]]) -> tuple[np.ndarray, np.ndarray]:
    vocabulary: dict[str, int] = {}
    document_frequency: dict[str, int] = defaultdict(int)
    for row in [*rows, *other]:
        for token in set(row):
            document_frequency[token] += 1
            vocabulary.setdefault(token, len(vocabulary))
    total = len(rows) + len(other)
    idf = np.zeros(len(vocabulary), dtype=np.float32)
    for token, index in vocabulary.items():
        idf[index] = np.log((total + 1) / (document_frequency[token] + 1)) + 1.0

    def matrix(group: list[list[str]]) -> np.ndarray:
        result = np.zeros((len(group), len(vocabulary)), dtype=np.float32)
        for position, row in enumerate(group):
            counts: dict[int, int] = defaultdict(int)
            for token in row:
                counts[vocabulary[token]] += 1
            for index, count in counts.items():
                result[position, index] = (1.0 + np.log(count)) * idf[index]
        norms = np.linalg.norm(result, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return result / norms

    return matrix(rows), matrix(other)


def _overlap(old: Unit, new: Unit) -> float:
    """Shared distinct words as a fraction of all distinct words in either clause."""
    a, b = set(tokens(strip_number(old.text))), set(tokens(strip_number(new.text)))
    return len(a & b) / len(a | b) if a | b else 0.0


def _longest_increasing(values: list[int]) -> set[int]:
    """Positions (in `values`) of one longest increasing subsequence."""
    tails: list[int] = []
    tail_positions: list[int] = []
    previous = [-1] * len(values)
    for position, value in enumerate(values):
        low, high = 0, len(tails)
        while low < high:
            middle = (low + high) // 2
            if tails[middle] < value:
                low = middle + 1
            else:
                high = middle
        if low == len(tails):
            tails.append(value)
            tail_positions.append(position)
        else:
            tails[low] = value
            tail_positions[low] = position
        previous[position] = tail_positions[low - 1] if low > 0 else -1
    chosen: set[int] = set()
    cursor = tail_positions[-1] if tail_positions else -1
    while cursor != -1:
        chosen.add(cursor)
        cursor = previous[cursor]
    return chosen


def align(old_units: list[Unit], new_units: list[Unit]) -> Alignment:
    pairs: list[Pair] = []
    old_left = set(range(len(old_units)))
    new_left = set(range(len(new_units)))

    # 1. Identical wording, whatever the numbering or position. Repeats are paired in order.
    by_key: dict[str, deque[int]] = defaultdict(deque)
    for index, unit in enumerate(new_units):
        by_key[match_key(unit)].append(index)
    for index, unit in enumerate(old_units):
        candidates = by_key.get(match_key(unit))
        if candidates:
            partner = candidates.popleft()
            pairs.append(Pair(index, partner, "exact", 1.0))
            old_left.discard(index)
            new_left.discard(partner)

    # 2. Similar wording among what remains.
    if old_left and new_left:
        old_order, new_order = sorted(old_left), sorted(new_left)
        old_tokens = [tokens(strip_number(old_units[i].text)) for i in old_order]
        new_tokens = [tokens(strip_number(new_units[j].text)) for j in new_order]
        old_matrix, new_matrix = _tfidf(old_tokens, new_tokens)
        similarity = old_matrix @ new_matrix.T

        for row, i in enumerate(old_order):
            heading = _heading_key(old_units[i])
            if heading:
                for column, j in enumerate(new_order):
                    if heading == _heading_key(new_units[j]):
                        similarity[row, column] += HEADING_BONUS

        candidates_found: list[tuple[float, int, int]] = []
        for row, column in np.argwhere(similarity >= MIN_SIMILARITY):
            short = min(len(old_tokens[row]), len(new_tokens[column])) < SHORT_CLAUSE_TOKENS
            if short and similarity[row, column] < MIN_SIMILARITY_SHORT:
                continue
            candidates_found.append((float(similarity[row, column]), int(row), int(column)))
        used_rows: set[int] = set()
        used_columns: set[int] = set()
        for score, row, column in sorted(candidates_found, key=lambda item: -item[0]):
            if row in used_rows or column in used_columns:
                continue
            used_rows.add(row)
            used_columns.add(column)
            pairs.append(Pair(old_order[row], new_order[column], "similar", min(score, 1.0)))
            old_left.discard(old_order[row])
            new_left.discard(new_order[column])

    # 2b. A clause that was rewritten heavily can fall below the similarity bar yet sit exactly where
    # its old version sat, between the same two matched neighbours. Pair such leftovers if they still
    # share a fair amount of wording.
    pairs.sort(key=lambda pair: pair.old)
    anchors = [(-1, -1)]
    anchors += [(pairs[k].old, pairs[k].new) for k in sorted(_longest_increasing([p.new for p in pairs]))]
    anchors.append((len(old_units), len(new_units)))
    for (before_old, before_new), (after_old, after_new) in zip(anchors, anchors[1:], strict=False):
        gap_old = [i for i in sorted(old_left) if before_old < i < after_old]
        gap_new = [j for j in sorted(new_left) if before_new < j < after_new]
        if not gap_old or not gap_new:
            continue
        overlaps = sorted(
            (
                (_overlap(old_units[i], new_units[j]), i, j)
                for i in gap_old
                for j in gap_new
            ),
            key=lambda item: -item[0],
        )
        used_old: set[int] = set()
        used_new: set[int] = set()
        for score, i, j in overlaps:
            if score < MIN_GAP_OVERLAP or i in used_old or j in used_new:
                continue
            used_old.add(i)
            used_new.add(j)
            pairs.append(Pair(i, j, "similar", score))
            old_left.discard(i)
            new_left.discard(j)

    # 3. A pair that breaks the reading order of the rest has moved.
    pairs.sort(key=lambda pair: pair.old)
    in_order = _longest_increasing([pair.new for pair in pairs])
    for position, pair in enumerate(pairs):
        pair.moved = position not in in_order

    return Alignment(pairs=pairs, removed=sorted(old_left), added=sorted(new_left))
