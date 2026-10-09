"""Questions asked across several documents at once.

The same corrective loop as a single document (plan, retrieve, judge, refine, answer, verify), with
the differences that matter when documents are compared:

* Each document is searched on its own, so a long contract cannot crowd a short one out of the
  results. A comparison needs evidence from every document.
* The judge decides sufficiency PER DOCUMENT. One document may fully answer while another has
  nothing, and the loop keeps refining only for the ones that are still short.
* The answer is written as one comparison, and every quote names its document.
* Each quote is verified against ONLY the document it is attributed to, never the whole set. A quote
  that exists in document A but is credited to document B fails, which is exactly what should happen.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings
from app.rag import prompts, prompts_multi
from app.rag.agent import (
    _CITATION_MARKER,
    OFF_TOPIC_REPLY,
    Grade,
    Passage,
    _chunked,
    _event,
    _parse_quotes,
    _plan_queries,
    _ranges_json,
    _State,
    _step,
    _validated,
    _with_neighbours,
)
from app.rag.index import DocumentIndex, Hit, ensure_index, has_chunks
from app.rag.llm import LLMClient, LLMError
from app.rag.quotes import DocumentText

Quality = str


@dataclass(frozen=True)
class SourceDocument:
    id: str
    name: str
    pages: list[tuple[int, str]]


@dataclass
class MultiInput:
    question: str
    history: list[tuple[str, str]]
    documents: list[SourceDocument]
    llm: LLMClient
    settings: Settings


class MultiGradeResult(BaseModel):
    """The judge's verdict. `sufficient` and `missing` are normally keyed by document label, but a
    single value is accepted and applied to every document."""

    grades: list[Grade] = Field(default_factory=list)
    sufficient: dict[str, bool] | bool = Field(default_factory=dict)
    missing: dict[str, str] | str = Field(default_factory=dict)

    def sufficient_for(self, label: str) -> bool:
        if isinstance(self.sufficient, bool):
            return self.sufficient
        return any(key.strip().upper() == label and value for key, value in self.sufficient.items())

    def missing_for(self, label: str) -> str:
        if isinstance(self.missing, str):
            return self.missing.strip()
        for key, value in self.missing.items():
            if key.strip().upper() == label:
                return str(value).strip()
        return ""


@dataclass
class _Doc:
    source: SourceDocument
    label: str
    index: DocumentIndex | None = None
    text: DocumentText | None = None
    evidence: dict[int, Passage] = field(default_factory=dict)
    graded: set[int] = field(default_factory=set)
    sufficient: bool = False
    missing: str = ""
    exhausted: bool = False

    @property
    def name(self) -> str:
        return self.source.name

    @property
    def strong(self) -> int:
        return sum(1 for p in self.evidence.values() if p.score == 2)

    @property
    def status(self) -> str:
        if self.sufficient:
            return "sufficient"
        return "partial" if self.evidence else "none"


def _coverage(docs: list[_Doc], rounds: int, keyword_only: bool) -> dict[str, Any]:
    return {
        "pages": sum(len(d.source.pages) for d in docs),
        "sections": sum(len(d.index.chunks) for d in docs if d.index),
        "unreadable_pages": sum(1 for d in docs for _, text in d.source.pages if not text.strip()),
        "rounds": rounds,
        "keyword_only": keyword_only,
        "documents": [
            {
                "document_id": d.source.id,
                "name": d.name,
                "pages": len(d.source.pages),
                "sections": len(d.index.chunks) if d.index else 0,
                "unreadable_pages": sum(1 for _, text in d.source.pages if not text.strip()),
                "evidence": d.status,
            }
            for d in docs
        ],
    }


def not_found_message(docs: list[_Doc], queries: list[str], rounds: int) -> str:
    shown = ", ".join(f"“{q}”" for q in queries[:4])
    total = sum(len(d.index.chunks) for d in docs if d.index)
    lines = [
        f"I couldn't find a passage in any of these {len(docs)} documents that answers this question.",
        f"I searched {total} sections for {shown}, over {rounds} {'round' if rounds == 1 else 'rounds'} of searching.",
        "That means no supporting text was found. It is not proof that the documents say nothing on the "
        "subject. Try naming the clause or the term it uses.",
    ]
    unreadable = [d for d in docs if any(not text.strip() for _, text in d.source.pages)]
    for d in unreadable:
        count = sum(1 for _, text in d.source.pages if not text.strip())
        lines.append(f"{d.name}: {count} {'page' if count == 1 else 'pages'} had no readable text and could not be searched.")
    return "\n\n".join(lines)


async def run_multi_agent(inp: MultiInput) -> AsyncIterator[dict[str, Any]]:
    """Runs the loop. Quote verification text is prepared in background threads from the very start,
    so it is warm by the time the model has written its quotes."""
    docs = [_Doc(source=source, label=f"D{i}") for i, source in enumerate(inp.documents, start=1)]
    for doc in docs:
        doc.text = DocumentText(doc.source.pages)
    warm = asyncio.gather(*[asyncio.to_thread(doc.text.prepare) for doc in docs if doc.text])
    try:
        async for event in _run(inp, docs, warm):
            yield event
    finally:
        warm.cancel()


async def _run(inp: MultiInput, docs: list[_Doc], warm: "asyncio.Future[Any]") -> AsyncIterator[dict[str, Any]]:
    settings = inp.settings
    state = _State()
    keyword_only = False
    note = prompts_multi.build_documents_note([(d.label, d.name) for d in docs])

    if not all(has_chunks(d.source.id) for d in docs):
        yield _step("index", "Preparing the documents for search (first question only)")

    async def build_all():
        return await asyncio.gather(
            *[
                ensure_index(d.source.id, d.source.pages, inp.llm, settings.chunk_target_chars, settings.chunk_overlap_chars)
                for d in docs
            ]
        )

    index_task = asyncio.ensure_future(build_all())
    try:
        yield _step("understand", f"Working out what to search for in {len(docs)} documents")
        plan = await _plan_queries(inp, state, note)
        builds = await index_task
    finally:
        if not index_task.done():
            index_task.cancel()

    for doc, build in zip(docs, builds, strict=True):
        doc.index = build.index
        if build.embedding_error:
            keyword_only = True
    if keyword_only:
        yield _step("index", "Semantic search is unavailable for some documents, using keyword search there")
    empty = [d.name for d in docs if not d.index or not d.index.chunks]
    if empty:
        raise LLMError(f"These documents have no searchable text: {', '.join(empty)}.")

    if plan.intent == "off_topic":
        async for piece in _chunked(OFF_TOPIC_REPLY):
            yield _event("token", {"text": piece})
        yield _event("citations", [])
        yield _event(
            "done", {"quality": "not_applicable", "coverage": _coverage(docs, 0, keyword_only), "verification": None}
        )
        return

    question = plan.standalone_question.strip() or inp.question
    queries = plan.queries or [question]
    per_document = max(3, min(settings.candidates_per_document, 40 // len(docs)))
    rounds = 0

    for round_number in range(1, settings.max_retrieval_rounds + 1):
        pending = [d for d in docs if not d.sufficient and not d.exhausted]
        if not pending:
            break
        rounds = round_number
        state.queries_tried.extend(q for q in queries if q not in state.queries_tried)
        yield _step("search", "Searching: " + "; ".join(queries), round_number, queries=queries)

        search_queries = queries if question in queries else [*queries, question]
        vectors = None
        if any(d.index and d.index.has_embeddings for d in pending):
            try:
                vectors = await inp.llm.embed(search_queries)
            except LLMError:
                keyword_only = True
                yield _step("search", "Semantic search failed, using keyword search for this round", round_number)

        groups: list[tuple[_Doc, list[Hit]]] = []
        for doc in pending:
            assert doc.index is not None
            hits = doc.index.search(
                search_queries, vectors if doc.index.has_embeddings else None, per_document + len(doc.graded)
            )
            fresh = [h for h in hits if h.chunk.id not in doc.graded][:per_document]
            if not fresh:
                doc.exhausted = True
                continue
            doc.graded.update(h.chunk.id for h in fresh)
            groups.append((doc, fresh))

        if not groups:
            yield _step("quality", "Searching again found no new passages in any document", round_number)
            break

        total = sum(len(fresh) for _, fresh in groups)
        yield _step(
            "grade",
            f"Judging {total} retrieved passages across {len(groups)} document{'s' if len(groups) != 1 else ''}",
            round_number,
        )
        grade_prompt = prompts_multi.build_grade_multi_prompt(
            question,
            [
                (doc.label, doc.name, [(h.chunk.id, h.chunk.page_number, h.chunk.text, h.chunk.context) for h in fresh])
                for doc, fresh in groups
            ],
        )
        result: MultiGradeResult = _validated(
            MultiGradeResult,
            await inp.llm.json_completion(
                prompts_multi.GRADE_MULTI_SYSTEM, grade_prompt, temperature=settings.temperature_judge
            ),
        )
        scores = {g.id: g.score for g in result.grades}
        for doc, fresh in groups:
            for rank, hit in enumerate(fresh):
                score = scores.get(hit.chunk.id, 0)
                if score >= 1:
                    doc.evidence[hit.chunk.id] = Passage(hit.chunk, score, rank + (round_number - 1) * 100)
            doc.sufficient = result.sufficient_for(doc.label) and doc.strong >= 1
            doc.missing = result.missing_for(doc.label)

        done_all = all(d.sufficient for d in docs)
        summary = "; ".join(
            f"{d.name}: " + ("sufficient" if d.sufficient else f"not yet{(' (' + d.missing + ')') if d.missing else ''}")
            for d in docs
        )
        yield _step(
            "quality",
            ("Evidence is sufficient in every document. " if done_all else "Evidence so far. ") + summary,
            round_number,
            sufficient=done_all,
            documents=[
                {"label": d.label, "name": d.name, "sufficient": d.sufficient, "relevant": len(d.evidence), "strong": d.strong}
                for d in docs
            ],
        )
        if done_all or round_number == settings.max_retrieval_rounds:
            break

        state.missing = "; ".join(
            f"{d.label} ({d.name}): {d.missing or 'nothing directly relevant found yet'}"
            for d in docs
            if not d.sufficient and not d.exhausted
        )
        yield _step("refine", "Refining the search for the documents that are still short", round_number)
        plan = await _plan_queries(inp, state, note)
        queries = plan.queries or queries

    coverage = _coverage(docs, rounds, keyword_only or any(d.index and not d.index.has_embeddings for d in docs))
    with_evidence = [d for d in docs if d.evidence]
    quality: Quality = (
        "insufficient" if not with_evidence else "sufficient" if all(d.sufficient for d in docs) else "partial"
    )

    if quality == "insufficient":
        async for piece in _chunked(not_found_message(docs, state.queries_tried, rounds)):
            yield _event("token", {"text": piece})
        yield _event("citations", [])
        yield _event("done", {"quality": quality, "coverage": coverage, "verification": None})
        return

    # Evidence per document, so every document that has any is represented in the answer.
    cap = max(3, settings.max_evidence_passages // len(with_evidence))
    entries: list[tuple[_Doc, Passage, bool]] = []
    for doc in with_evidence:
        assert doc.index is not None
        chosen = sorted(doc.evidence.values(), key=lambda p: (-p.score, p.best_rank))[:cap]
        entries.extend((doc, passage, neighbour) for passage, neighbour in _with_neighbours(chosen, doc.index, settings.neighbor_chunks))
    labelled = {f"E{i}": (doc, passage) for i, (doc, passage, _) in enumerate(entries, start=1)}
    neighbours = {f"E{i}" for i, (_, _, is_neighbour) in enumerate(entries, start=1) if is_neighbour}
    unanswered = [(d.label, d.name) for d in docs if not d.evidence]

    yield _step(
        "answer",
        f"Comparing the documents using {len(entries)} passages"
        + ("" if quality == "sufficient" else " (evidence is partial for some)"),
    )
    answer_prompt = prompts_multi.build_answer_multi_prompt(
        question,
        inp.history,
        [
            (label, doc.label, doc.name, p.chunk.page_number, p.chunk.text, p.chunk.context, label in neighbours)
            for label, (doc, p) in labelled.items()
        ],
        unanswered,
        partial=quality == "partial",
        asked=inp.question,
        memory_chars=settings.chat_memory_chars,
    )

    marker = prompts.QUOTES_MARKER
    buffer = ""
    emitted = 0
    announced = False
    async for delta in inp.llm.stream_completion(
        prompts_multi.ANSWER_MULTI_SYSTEM, answer_prompt, temperature=settings.temperature_answer
    ):
        buffer += delta
        cut = buffer.find(marker)
        if cut != -1 and not announced:
            announced = True
            if cut > emitted:
                yield _event("token", {"text": buffer[emitted:cut]})
                emitted = cut
            yield _step("quotes", "Collecting the quotes that support the comparison")
        safe_end = cut if cut != -1 else max(emitted, len(buffer) - (len(marker) - 1))
        if safe_end > emitted:
            yield _event("token", {"text": buffer[emitted:safe_end]})
            emitted = safe_end
    marker_at = buffer.find(marker)
    answer_text = buffer if marker_at == -1 else buffer[:marker_at]
    if len(answer_text) > emitted:
        yield _event("token", {"text": answer_text[emitted:]})
    raw_quotes = "" if marker_at == -1 else buffer[marker_at + len(marker) :]

    yield _step("verify", "Checking every quote against the document it is credited to")
    await warm
    citations, verification = await asyncio.to_thread(_verify_quotes, answer_text, raw_quotes, labelled, docs)
    yield _event("citations", citations)
    yield _event("done", {"quality": quality, "coverage": coverage, "verification": verification})


def _citation(n: int, quote: str, doc: _Doc | None, match) -> dict[str, Any]:
    return {
        "n": n,
        "quote": quote,
        "verified": match is not None,
        "page": match.first_page if match else None,
        "ranges": _ranges_json(match.ranges) if match else [],
        "matches": [_ranges_json(m) for m in match.matches] if match else [],
        "primary_index": match.primary_index if match else 0,
        "occurrences": match.occurrences if match else 0,
        "document_id": doc.source.id if doc else None,
        "document_name": doc.name if doc else None,
        "document_label": doc.label if doc else None,
    }


def _verify_quotes(
    answer: str,
    raw_quotes: str,
    labelled: dict[str, tuple[_Doc, Passage]],
    docs: list[_Doc],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Check each quote against its OWN document only.

    The document is the one the cited evidence passage came from. If the model also names a document
    and the two disagree, the quote is treated as unverified: it was attributed to the wrong source.
    """
    by_label = {d.label: d for d in docs}
    citations: dict[int, dict[str, Any]] = {}

    for item in _parse_quotes(raw_quotes):
        try:
            number = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        quote = str(item.get("quote", "")).strip()
        if number in citations or not quote:
            continue

        evidence = labelled.get(str(item.get("evidence", "")).strip())
        claimed = by_label.get(str(item.get("document", "")).strip().upper())
        doc = evidence[0] if evidence else claimed
        if doc is None or (evidence and claimed and claimed is not evidence[0]) or doc.text is None:
            citations[number] = _citation(number, quote, doc, None)
            continue

        hint = {evidence[1].chunk.page_number} if evidence else None
        citations[number] = _citation(number, quote, doc, doc.text.find_quote(quote, hint_pages=hint))

    # A citation marker with no quote behind it is an unsupported claim; show it as unverified.
    for number in sorted({int(m) for m in _CITATION_MARKER.findall(answer)}):
        citations.setdefault(number, _citation(number, "", None, None))

    ordered = [citations[n] for n in sorted(citations)]
    verified = sum(1 for c in ordered if c["verified"])
    return ordered, {"verified": verified, "unverified": len(ordered) - verified}
