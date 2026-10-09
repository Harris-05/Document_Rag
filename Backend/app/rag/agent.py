"""The agentic (corrective) RAG loop.

For one question: generate search queries, retrieve, have a judge grade the retrieval, and if it is
not good enough, refine the queries and retrieve again, up to a hard round cap. Only passages the
judge accepted reach the answer prompt. The streamed answer carries quotes that are then verified
against the real document text by `DocumentText.find_quote`.

The loop is an async generator of events so the caller can stream progress, partial answers and the
final verified citations to the user as they happen.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import Settings
from app.rag import prompts
from app.rag.index import Chunk, DocumentIndex, Hit, ensure_index, has_chunks
from app.rag.llm import LLMClient, LLMError
from app.rag.quotes import DocumentText

Quality = Literal["sufficient", "partial", "insufficient", "not_applicable"]

OFF_TOPIC_REPLY = (
    "I can only answer questions about this document. Ask about a clause, a party, a date, an "
    "obligation or a figure and I will search it."
)
_CITATION_MARKER = re.compile(r"\[(\d{1,2})\]")


class QueryPlan(BaseModel):
    intent: Literal["document_question", "off_topic"] = "document_question"
    standalone_question: str = ""
    queries: list[str] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("queries", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        seen: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text.lower() not in (s.lower() for s in seen):
                seen.append(text)
        return seen[:4]


class Grade(BaseModel):
    id: int
    score: int = Field(ge=0, le=2)


class GradeResult(BaseModel):
    grades: list[Grade] = Field(default_factory=list)
    sufficient: bool = False
    missing: str = ""


@dataclass
class Passage:
    chunk: Chunk
    score: int
    best_rank: int


@dataclass
class AgentInput:
    question: str
    history: list[tuple[str, str]]
    pages: list[tuple[int, str]]
    document_id: str
    llm: LLMClient
    settings: Settings


@dataclass
class _State:
    queries_tried: list[str] = field(default_factory=list)
    graded_ids: set[int] = field(default_factory=set)
    evidence: dict[int, Passage] = field(default_factory=dict)
    sufficient: bool = False
    missing: str = ""
    rounds: int = 0
    candidates_seen: int = 0
    keyword_only: bool = False


def _event(name: str, data: Any) -> dict[str, Any]:
    return {"event": name, "data": data}


def _step(kind: str, text: str, round_number: int | None = None, **detail: Any) -> dict[str, Any]:
    return _event("step", {"kind": kind, "round": round_number, "text": text, "detail": detail or None})


def _validated(model: type[BaseModel], data: dict[str, Any]) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise LLMError("The AI model returned an answer in an unexpected format. Please try again.") from error


async def _plan_queries(inp: AgentInput, state: _State) -> QueryPlan:
    prompt = prompts.build_query_prompt(
        inp.question, inp.history, state.queries_tried, state.missing or None, inp.settings.chat_memory_chars
    )
    plan: QueryPlan = _validated(
        QueryPlan,
        await inp.llm.json_completion(prompts.QUERY_SYSTEM, prompt, temperature=inp.settings.temperature_plan),
    )
    return plan


def _coverage(inp: AgentInput, index: DocumentIndex, state: _State) -> dict[str, Any]:
    unreadable = sum(1 for _, text in inp.pages if not text.strip())
    return {
        "pages": len(inp.pages),
        "sections": len(index.chunks),
        "unreadable_pages": unreadable,
        "rounds": state.rounds,
        "keyword_only": state.keyword_only or not index.has_embeddings,
    }


def not_found_message(coverage: dict[str, Any], queries: list[str]) -> str:
    shown = ", ".join(f"“{q}”" for q in queries[:4])
    lines = [
        "I couldn't find a passage in this document that answers this question.",
        f"I searched {coverage['sections']} sections across {coverage['pages']} "
        f"{'page' if coverage['pages'] == 1 else 'pages'} for {shown}, over {coverage['rounds']} "
        f"{'round' if coverage['rounds'] == 1 else 'rounds'} of searching.",
        "That means no supporting text was found. It is not proof that the document says nothing on "
        "the subject. Try naming the clause or the term it uses.",
    ]
    if coverage["unreadable_pages"]:
        lines.append(
            f"{coverage['unreadable_pages']} "
            f"{'page' if coverage['unreadable_pages'] == 1 else 'pages'} had no readable text and could not be searched."
        )
    return "\n\n".join(lines)


async def _chunked(text: str, size: int = 40) -> AsyncIterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]


async def run_agent(inp: AgentInput) -> AsyncIterator[dict[str, Any]]:
    """Runs the loop. Quote verification is prepared in a background thread from the very start, so
    it is already warm by the time the model has written its quotes and adds no wait of its own."""
    document = DocumentText(inp.pages)
    warm = asyncio.create_task(asyncio.to_thread(document.prepare))
    try:
        async for event in _run(inp, document, warm):
            yield event
    finally:
        warm.cancel()


async def _run(inp: AgentInput, document: DocumentText, warm: "asyncio.Task[None]") -> AsyncIterator[dict[str, Any]]:
    settings = inp.settings
    state = _State()

    if not has_chunks(inp.document_id):
        yield _step("index", "Preparing this document for search (first question only)")

    # Loading or building the index does not depend on the plan, so the two overlap. On a first
    # question this hides most of the embedding time behind the planning call.
    index_task = asyncio.create_task(
        ensure_index(inp.document_id, inp.pages, inp.llm, settings.chunk_target_chars, settings.chunk_overlap_chars)
    )
    try:
        yield _step("understand", "Working out what to search for")
        plan = await _plan_queries(inp, state)
        build = await index_task
    finally:
        if not index_task.done():
            index_task.cancel()

    index = build.index
    if build.embedding_error:
        state.keyword_only = True
        yield _step("index", "Semantic search is unavailable, using keyword search only", reason=build.embedding_error)
    if not index.chunks:
        raise LLMError("This document has no searchable text.")

    if plan.intent == "off_topic":
        async for piece in _chunked(OFF_TOPIC_REPLY):
            yield _event("token", {"text": piece})
        yield _event("citations", [])
        yield _event("done", {"quality": "not_applicable", "coverage": _coverage(inp, index, state), "verification": None})
        return

    # Later stages see the follow-up resolved into a full question ("it" and "that clause" spelled out).
    question = plan.standalone_question.strip() or inp.question
    queries = plan.queries or [question]

    for round_number in range(1, settings.max_retrieval_rounds + 1):
        state.rounds = round_number
        state.queries_tried.extend(q for q in queries if q not in state.queries_tried)
        yield _step("search", "Searching: " + "; ".join(queries), round_number, queries=queries)

        # The user's whole question is searched too, alongside the planner's queries: plain-language
        # wording often matches a clause better than any rewritten keyword query does.
        search_queries = queries if question in queries else [*queries, question]

        query_vectors = None
        if index.has_embeddings:
            try:
                query_vectors = await inp.llm.embed(search_queries)
            except LLMError:
                state.keyword_only = True
                yield _step("search", "Semantic search failed, using keyword search for this round", round_number)

        hits: list[Hit] = index.search(
            search_queries, query_vectors, settings.candidates_per_round + len(state.graded_ids)
        )
        fresh = [h for h in hits if h.chunk.id not in state.graded_ids][: settings.candidates_per_round]
        if not fresh:
            yield _step("quality", "Searching again found no new passages", round_number)
            break

        state.graded_ids.update(h.chunk.id for h in fresh)
        state.candidates_seen += len(fresh)
        yield _step("grade", f"Judging {len(fresh)} retrieved passages for relevance", round_number)

        grade_prompt = prompts.build_grade_prompt(
            question, [(h.chunk.id, h.chunk.page_number, h.chunk.text, h.chunk.context) for h in fresh]
        )
        result: GradeResult = _validated(
            GradeResult,
            await inp.llm.json_completion(prompts.GRADE_SYSTEM, grade_prompt, temperature=settings.temperature_judge),
        )

        scores = {g.id: g.score for g in result.grades}
        for rank, hit in enumerate(fresh):
            score = scores.get(hit.chunk.id, 0)
            if score >= 1:
                state.evidence[hit.chunk.id] = Passage(hit.chunk, score, rank + (round_number - 1) * 100)

        strong = sum(1 for p in state.evidence.values() if p.score == 2)
        state.sufficient = result.sufficient and strong >= 1
        state.missing = result.missing.strip()
        relevant = len(state.evidence)

        if state.sufficient:
            yield _step(
                "quality",
                f"Evidence is sufficient: {strong} passage{'s directly answer' if strong != 1 else ' directly answers'} the question",
                round_number,
                sufficient=True,
                relevant=relevant,
                strong=strong,
            )
            break

        reason = state.missing or "nothing directly answers the question yet"
        yield _step(
            "quality",
            f"Evidence is not sufficient yet: {reason}",
            round_number,
            sufficient=False,
            relevant=relevant,
            strong=strong,
        )
        if round_number == settings.max_retrieval_rounds:
            break

        yield _step("refine", "Refining the search using what is still missing", round_number)
        plan = await _plan_queries(inp, state)
        queries = plan.queries or queries

    coverage = _coverage(inp, index, state)
    quality: Quality = (
        "sufficient" if state.sufficient else "partial" if state.evidence else "insufficient"
    )

    if quality == "insufficient":
        async for piece in _chunked(not_found_message(coverage, state.queries_tried)):
            yield _event("token", {"text": piece})
        yield _event("citations", [])
        yield _event("done", {"quality": quality, "coverage": coverage, "verification": None})
        return

    chosen = sorted(state.evidence.values(), key=lambda p: (-p.score, p.best_rank))[: settings.max_evidence_passages]
    entries = _with_neighbours(chosen, index, settings.neighbor_chunks)
    labelled = {f"E{i}": passage for i, (passage, _) in enumerate(entries, start=1)}
    neighbours = {f"E{i}" for i, (_, is_neighbour) in enumerate(entries, start=1) if is_neighbour}

    yield _step(
        "answer",
        f"Writing the answer from {len(chosen)} passage{'s' if len(chosen) != 1 else ''}"
        + (f" and the text around {'it' if len(chosen) == 1 else 'them'}" if neighbours else "")
        + ("" if quality == "sufficient" else " (evidence is partial)"),
    )
    answer_prompt = prompts.build_answer_prompt(
        question,
        inp.history,
        [
            (label, p.chunk.page_number, p.chunk.text, p.chunk.context, label in neighbours)
            for label, p in labelled.items()
        ],
        partial=quality == "partial",
        asked=inp.question,
        memory_chars=settings.chat_memory_chars,
    )

    marker = prompts.QUOTES_MARKER
    buffer = ""
    emitted = 0
    announced_quotes = False
    async for delta in inp.llm.stream_completion(
        prompts.ANSWER_SYSTEM, answer_prompt, temperature=settings.temperature_answer
    ):
        buffer += delta
        cut = buffer.find(marker)
        if cut != -1 and not announced_quotes:
            # The answer text is complete; the model is now writing out its quotes. Say so, because
            # nothing else visibly changes during this phase.
            announced_quotes = True
            if cut > emitted:
                yield _event("token", {"text": buffer[emitted:cut]})
                emitted = cut
            yield _step("quotes", "Collecting the quotes that support the answer")
        safe_end = cut if cut != -1 else max(emitted, len(buffer) - (len(marker) - 1))
        if safe_end > emitted:
            yield _event("token", {"text": buffer[emitted:safe_end]})
            emitted = safe_end
    marker_at = buffer.find(marker)
    answer_text = buffer if marker_at == -1 else buffer[:marker_at]
    if len(answer_text) > emitted:
        yield _event("token", {"text": answer_text[emitted:]})
    raw_quotes = "" if marker_at == -1 else buffer[marker_at + len(marker) :]

    yield _step("verify", "Checking every quote against the document text")
    await warm
    citations, verification = await asyncio.to_thread(_verify_quotes, answer_text, raw_quotes, labelled, document)
    yield _event("citations", citations)
    yield _event("done", {"quality": quality, "coverage": coverage, "verification": verification})


def _with_neighbours(
    chosen: list[Passage], index: DocumentIndex, width: int
) -> list[tuple[Passage, bool]]:
    """Add the chunks on either side of each strongly relevant passage, in reading order.

    A clause often runs across a chunk boundary, so the part that finishes the thought can sit in
    the next chunk. Neighbours were not judged, so they are marked and used as context only.
    """
    by_ordinal = {chunk.ordinal: chunk for chunk in index.chunks}
    taken = {p.chunk.ordinal for p in chosen}
    entries: list[tuple[Passage, bool]] = [(p, False) for p in chosen]

    for passage in chosen:
        if passage.score < 2:
            continue
        for step in range(1, width + 1):
            for ordinal in (passage.chunk.ordinal - step, passage.chunk.ordinal + step):
                neighbour = by_ordinal.get(ordinal)
                if neighbour is not None and ordinal not in taken:
                    taken.add(ordinal)
                    entries.append((Passage(neighbour, 0, 0), True))

    entries.sort(key=lambda entry: entry[0].chunk.ordinal)
    return entries


def _parse_quotes(raw: str) -> list[dict[str, Any]]:
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _verify_quotes(
    answer: str, raw_quotes: str, labelled: dict[str, Passage], document: DocumentText
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    citations: dict[int, dict[str, Any]] = {}

    for item in _parse_quotes(raw_quotes):
        try:
            number = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        quote = str(item.get("quote", "")).strip()
        if number in citations or not quote:
            continue
        passage = labelled.get(str(item.get("evidence", "")).strip())
        hint = {passage.chunk.page_number} if passage else None
        match = document.find_quote(quote, hint_pages=hint)
        citations[number] = {
            "n": number,
            "quote": quote,
            "verified": match is not None,
            "page": match.first_page if match else None,
            "ranges": [{"page": r.page, "start": r.start, "end": r.end} for r in match.ranges] if match else [],
            "occurrences": match.occurrences if match else 0,
        }

    # A citation marker with no quote behind it is an unsupported claim; show it as unverified.
    for number in sorted({int(m) for m in _CITATION_MARKER.findall(answer)}):
        citations.setdefault(
            number,
            {"n": number, "quote": "", "verified": False, "page": None, "ranges": [], "occurrences": 0},
        )

    ordered = [citations[n] for n in sorted(citations)]
    verified = sum(1 for c in ordered if c["verified"])
    return ordered, {"verified": verified, "unverified": len(ordered) - verified}
