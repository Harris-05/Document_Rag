"""Streams a written answer to the client while holding back the quote block.

The model writes its answer, then the quote marker, then a JSON list of quotes. Only the answer text
is streamed as it arrives; the quote block is collected for verification. The marker can arrive split
across chunks, so a marker-length tail is held back until it is clear it is not the start of one.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.rag import prompts
from app.rag.llm import LLMClient


@dataclass
class StreamedAnswer:
    """Filled in as the stream finishes: the answer text and the raw quote block after the marker."""

    text: str = ""
    raw_quotes: str = ""


async def stream_answer(
    llm: LLMClient, system: str, prompt: str, temperature: float, out: StreamedAnswer
) -> AsyncIterator[dict[str, Any]]:
    marker = prompts.QUOTES_MARKER
    buffer = ""
    emitted = 0
    announced = False
    async for delta in llm.stream_completion(system, prompt, temperature=temperature):
        buffer += delta
        cut = buffer.find(marker)
        if cut != -1 and not announced:
            announced = True
            if cut > emitted:
                yield {"event": "token", "data": {"text": buffer[emitted:cut]}}
                emitted = cut
            yield {
                "event": "step",
                "data": {"kind": "quotes", "round": None, "text": "Collecting the quotes that support the answer", "detail": None},
            }
        safe_end = cut if cut != -1 else max(emitted, len(buffer) - (len(marker) - 1))
        if safe_end > emitted:
            yield {"event": "token", "data": {"text": buffer[emitted:safe_end]}}
            emitted = safe_end
    marker_at = buffer.find(marker)
    out.text = buffer if marker_at == -1 else buffer[:marker_at]
    if len(out.text) > emitted:
        yield {"event": "token", "data": {"text": out.text[emitted:]}}
    out.raw_quotes = "" if marker_at == -1 else buffer[marker_at + len(marker) :]
