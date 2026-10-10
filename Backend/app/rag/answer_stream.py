"""Streams a written answer to the client while holding back the quote block.

The model writes its answer, then the quote marker, then a JSON list of quotes. Only the answer text
is streamed as it arrives; the quote block is collected for verification. The marker can arrive split
across chunks, so a marker-length tail is held back until it is clear it is not the start of one.

Evidence labels used as citations ("[E2]") are turned into numbered citations on the way out; see
citation_labels.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.rag import prompts
from app.rag.citation_labels import LabelRewriter, remap_quotes
from app.rag.llm import LLMClient


@dataclass
class StreamedAnswer:
    """Filled in as the stream finishes: the answer text and the raw quote block after the marker."""

    text: str = ""
    raw_quotes: str = ""
    # For each citation number that came from an evidence label, the label (for example {1: "E2"}).
    label_of: dict[int, str] = field(default_factory=dict)


def _token(text: str) -> dict[str, Any]:
    return {"event": "token", "data": {"text": text}}


async def stream_answer(
    llm: LLMClient,
    system: str,
    prompt: str,
    temperature: float,
    out: StreamedAnswer,
    quotes_text: str = "Collecting the quotes that support the answer",
) -> AsyncIterator[dict[str, Any]]:
    marker = prompts.QUOTES_MARKER
    rewriter = LabelRewriter()
    shown: list[str] = []
    buffer = ""
    emitted = 0
    announced = False

    def emit(raw: str) -> list[dict[str, Any]]:
        text = rewriter.feed(raw)
        if not text:
            return []
        shown.append(text)
        return [_token(text)]

    async for delta in llm.stream_completion(system, prompt, temperature=temperature):
        buffer += delta
        cut = buffer.find(marker)
        if cut != -1 and not announced:
            announced = True
            if cut > emitted:
                for event in emit(buffer[emitted:cut]):
                    yield event
                emitted = cut
            yield {"event": "step", "data": {"kind": "quotes", "round": None, "text": quotes_text, "detail": None}}
        safe_end = cut if cut != -1 else max(emitted, len(buffer) - (len(marker) - 1))
        if safe_end > emitted:
            for event in emit(buffer[emitted:safe_end]):
                yield event
            emitted = safe_end

    marker_at = buffer.find(marker)
    answer = buffer if marker_at == -1 else buffer[:marker_at]
    if len(answer) > emitted:
        for event in emit(answer[emitted:]):
            yield event
    tail = rewriter.flush()
    if tail:
        shown.append(tail)
        yield _token(tail)

    out.text = "".join(shown)
    out.label_of = rewriter.label_of
    raw = "" if marker_at == -1 else buffer[marker_at + len(marker) :]
    out.raw_quotes = remap_quotes(raw, rewriter.numbers)
