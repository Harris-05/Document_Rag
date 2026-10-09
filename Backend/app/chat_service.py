"""Runs one chat turn: streams agent events to the client and persists the outcome.

Whatever happens (finished, stopped by the user, provider failure) the assistant's partial or final
message is saved, so the history always matches what the user saw.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app import chat_repository
from app.config import Settings
from app.rag.agent import AgentInput, run_agent
from app.rag.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat(
    *,
    document_id: str,
    question: str,
    pages: list[tuple[int, str]],
    llm: LLMClient,
    settings: Settings,
) -> AsyncIterator[str]:
    # Short-term memory window. A turn is a question plus its answer, hence the factor of two.
    # Zero turns disables memory entirely.
    memory_turns = settings.chat_memory_turns
    history = chat_repository.recent_history(document_id, memory_turns * 2) if memory_turns > 0 else []
    user_message_id = chat_repository.add_user_message(document_id, question)

    tokens: list[str] = []
    trace: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    quality: str | None = None
    coverage: dict[str, Any] | None = None
    saved_id: int | None = None

    def save(status: str, error: str | None = None) -> int:
        nonlocal saved_id
        if saved_id is None:
            saved_id = chat_repository.add_assistant_message(
                document_id,
                content="".join(tokens).strip(),
                status=status,
                quality=quality,
                citations=citations,
                trace=trace,
                coverage=coverage,
                error_message=error,
            )
        return saved_id

    yield sse("start", {"user_message_id": user_message_id})

    try:
        agent_input = AgentInput(
            question=question,
            history=history,
            pages=pages,
            document_id=document_id,
            llm=llm,
            settings=settings,
        )
        async for event in run_agent(agent_input):
            name, data = event["event"], event["data"]
            if name == "step":
                trace.append(data)
            elif name == "token":
                tokens.append(data["text"])
            elif name == "citations":
                citations = data
            elif name == "done":
                quality, coverage = data["quality"], data["coverage"]
                data = {**data, "message_id": save("complete")}
            yield sse(name, data)
    except LLMError as error:
        message_id = save("error", error.message)
        yield sse("error", {"message": error.message, "message_id": message_id})
    except (asyncio.CancelledError, GeneratorExit):
        save("stopped")
        raise
    except Exception:
        logger.exception("Chat turn failed for document %s", document_id)
        message = "Something went wrong while answering. Please try again."
        message_id = save("error", message)
        yield sse("error", {"message": message, "message_id": message_id})
    finally:
        # Covers any other early exit so the user's question is never left without a reply record.
        save("stopped")
