"""Research mode: the model decides what to look up by calling tools, in a loop.

Where the standard loop plans queries, retrieves and grades on a fixed script, here the model is
given `search_document`, `get_section` and `list_clauses` and chooses its own next step after reading
each result (follow a cross-reference, read a whole clause, try different words).

Bounds, all enforced here and not left to the model: a hard cap on rounds, a cap on calls per round,
and a budget for malformed calls after which the loop stops. Every call is announced to the client
before it runs and its outcome after, so the user watches the work as it happens.

The answer is written afterwards from only what the model actually read, streamed, and its quotes are
verified against the document exactly as in the standard mode.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.compare.segment import segment
from app.rag import prompts, prompts_research
from app.rag.agent import (
    OFF_TOPIC_REPLY,
    AgentInput,
    Passage,
    _chunked,
    _event,
    _step,
    _verify_quotes,
    not_found_message,
)
from app.rag.answer_stream import StreamedAnswer, stream_answer
from app.rag.index import Chunk, DocumentIndex, ensure_index, has_chunks
from app.rag.llm import LLMError, ToolCall
from app.rag.quotes import DocumentText
from app.rag.research_tools import TOOL_SPECS, DocumentTools, Evidence

MAX_HISTORY_MESSAGES = 6


def _arguments(call: ToolCall) -> dict[str, Any]:
    try:
        parsed = json.loads(call.arguments) if call.arguments.strip() else {}
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _announce(call: ToolCall) -> str:
    """What the user sees before the call runs. Tolerant of bad arguments: it only describes."""
    args = _arguments(call)
    if call.name == "search_document" and isinstance(args.get("query"), str) and args["query"].strip():
        return f"Searching for “{args['query'].strip()[:120]}”"
    if call.name == "get_section" and args.get("number") not in (None, ""):
        return f"Reading section {str(args['number'])[:60]}"
    if call.name == "list_clauses":
        return "Listing the clauses of the contract"
    return f"Calling {call.name or 'an unnamed tool'}"


def _assistant_message(content: str, calls: list[ToolCall]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in calls
        ],
    }


def _history_messages(history: list[tuple[str, str]], max_chars: int) -> list[dict[str, Any]]:
    messages = []
    for role, content in history[-MAX_HISTORY_MESSAGES:]:
        text = content if len(content) <= max_chars else content[:max_chars] + " [...]"
        messages.append({"role": "user" if role == "user" else "assistant", "content": text})
    return messages


def _choose_evidence(evidence: dict[str, Evidence], limit: int) -> list[Evidence]:
    """Keep whole sections first (the model asked for them by name), then the newest passages."""
    items = list(evidence.values())
    if len(items) <= limit:
        return items
    sections = [e for e in items if e.section]
    rest = [e for e in reversed(items) if not e.section]
    kept = (sections + rest)[:limit]
    return sorted(kept, key=lambda e: int(e.label[1:]))


def _coverage(inp: AgentInput, index: DocumentIndex, rounds: int, calls: int, keyword_only: bool) -> dict[str, Any]:
    return {
        "pages": len(inp.pages),
        "sections": len(index.chunks),
        "unreadable_pages": sum(1 for _, text in inp.pages if not text.strip()),
        "rounds": rounds,
        "tool_calls": calls,
        "keyword_only": keyword_only,
    }


async def run_research_agent(inp: AgentInput) -> AsyncIterator[dict[str, Any]]:
    document = DocumentText(inp.pages)
    warm = asyncio.create_task(asyncio.to_thread(document.prepare))
    try:
        async for event in _run(inp, document, warm):
            yield event
    finally:
        warm.cancel()


async def _run(inp: AgentInput, document: DocumentText, warm: "asyncio.Task[None]") -> AsyncIterator[dict[str, Any]]:
    settings = inp.settings
    if not has_chunks(inp.document_id):
        yield _step("index", "Preparing this document for search (first question only)")
    build = await ensure_index(inp.document_id, inp.pages, inp.llm, settings.chunk_target_chars, settings.chunk_overlap_chars)
    index = build.index
    if build.embedding_error:
        yield _step("index", "Semantic search is unavailable, using keyword search only", reason=build.embedding_error)
    if not index.chunks:
        raise LLMError("This document has no searchable text.")

    units = await asyncio.to_thread(segment, inp.pages)
    tools = DocumentTools(index, units, inp.llm, settings)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompts_research.RESEARCH_SYSTEM},
        *_history_messages(inp.history, settings.chat_memory_chars),
        {"role": "user", "content": inp.question},
    ]

    searched: list[str] = []
    calls_made = 0
    invalid = 0
    rounds = 0
    lookup_rounds = 0
    nudged = False
    off_topic = False
    stopped_early = False

    yield _step("understand", "Deciding what to look up")

    async def execute(call: ToolCall, round_number: int) -> AsyncIterator[dict[str, Any]]:
        nonlocal calls_made, invalid
        yield _step("tool", _announce(call), round_number, tool=call.name, arguments=_arguments(call))
        outcome = await tools.run(call.name, call.arguments)
        calls_made += 1
        if not outcome.ok:
            invalid += 1
        query = _arguments(call).get("query")
        if call.name == "search_document" and outcome.ok and isinstance(query, str) and query not in searched:
            searched.append(query)
        yield _step("tool_result", outcome.summary, round_number, ok=outcome.ok)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": outcome.message})

    for round_number in range(1, settings.max_research_rounds + 1):
        rounds = round_number
        turn = await inp.llm.tool_completion(messages, TOOL_SPECS, temperature=settings.temperature_plan)

        if not turn.tool_calls:
            if calls_made == 0:
                if turn.content.strip().upper().startswith(prompts_research.OFF_TOPIC_TOKEN):
                    off_topic = True
                    break
                if not nudged:
                    # The model answered without looking anything up. Ask once for a lookup.
                    nudged = True
                    messages.append({"role": "assistant", "content": turn.content or "..."})
                    messages.append({"role": "user", "content": prompts_research.NUDGE})
                    yield _step("tool_result", "The model tried to answer without looking anything up; asking it to search first", round_number, ok=False)
                    continue
            break

        lookup_rounds = round_number
        messages.append(_assistant_message(turn.content, turn.tool_calls))
        allowed = turn.tool_calls[: settings.max_tool_calls_per_round]
        for call in allowed:
            async for event in execute(call, round_number):
                yield event
        for call in turn.tool_calls[settings.max_tool_calls_per_round :]:
            # Every call the model made needs a reply, or the next request is rejected by the provider.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": f"Skipped: at most {settings.max_tool_calls_per_round} calls are allowed per turn.",
                }
            )
            yield _step("tool_result", f"Skipped an extra call (limit is {settings.max_tool_calls_per_round} per turn)", round_number, ok=False)

        if invalid >= settings.max_invalid_tool_calls:
            stopped_early = True
            yield _step(
                "limit",
                f"Stopped after {invalid} invalid tool calls; answering from what has been read so far",
                round_number,
            )
            break
    else:
        stopped_early = True
        yield _step(
            "limit",
            f"Reached the limit of {settings.max_research_rounds} rounds; answering from what has been read so far",
            rounds,
        )

    if off_topic:
        async for piece in _chunked(OFF_TOPIC_REPLY):
            yield _event("token", {"text": piece})
        yield _event("citations", [])
        yield _event(
            "done",
            {"quality": "not_applicable", "coverage": _coverage(inp, index, lookup_rounds, calls_made, tools.keyword_only), "verification": None},
        )
        return

    if not tools.evidence:
        # The model read nothing usable. One plain search with the user's own words, so a model that
        # never called a tool correctly still gets the question looked at.
        forced = ToolCall(id="forced", name="search_document", arguments=json.dumps({"query": inp.question[:300]}))
        lookup_rounds = lookup_rounds or 1
        async for event in execute(forced, lookup_rounds):
            yield event

    coverage = _coverage(inp, index, lookup_rounds, calls_made, tools.keyword_only)
    if not tools.evidence:
        text = not_found_message({**coverage, "rounds": max(1, lookup_rounds)}, searched or [inp.question])
        async for piece in _chunked(text):
            yield _event("token", {"text": piece})
        yield _event("citations", [])
        yield _event("done", {"quality": "insufficient", "coverage": coverage, "verification": None})
        return

    chosen = _choose_evidence(tools.evidence, settings.research_max_evidence)
    labelled = {e.label: Passage(Chunk(0, int(e.label[1:]), e.page, e.text, e.context), 2, 0) for e in chosen}
    yield _step(
        "answer",
        f"Writing the answer from {len(chosen)} passage{'s' if len(chosen) != 1 else ''} it read"
        + (" (stopped at a limit)" if stopped_early else ""),
    )
    prompt = prompts.build_answer_prompt(
        inp.question,
        inp.history,
        [(e.label, e.page, e.text, e.context, False) for e in chosen],
        partial=stopped_early,
        memory_chars=settings.chat_memory_chars,
    )
    streamed = StreamedAnswer()
    async for event in stream_answer(inp.llm, prompts.ANSWER_SYSTEM, prompt, settings.temperature_answer, streamed):
        yield event

    yield _step("verify", "Checking every quote against the document text")
    await warm
    citations, verification = await asyncio.to_thread(_verify_quotes, streamed.text, streamed.raw_quotes, labelled, document)
    yield _event("citations", citations)

    # There is no separate grader here, so quality comes from what the check found: every claim backed
    # by a verified quote is "sufficient"; anything unverified, or no quotes at all, is "partial".
    solid = bool(citations) and verification["unverified"] == 0 and not stopped_early
    yield _event("done", {"quality": "sufficient" if solid else "partial", "coverage": coverage, "verification": verification})

