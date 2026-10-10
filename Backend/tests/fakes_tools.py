"""A scripted model for research mode: it returns a fixed sequence of tool-calling turns."""

import json
from typing import Any

from app.rag.llm import ToolCall, ToolTurn

from .fakes import FakeLLM


def call(name: str, arguments: dict[str, Any] | str, call_id: str | None = None) -> ToolCall:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(id=call_id or f"call_{name}_{abs(hash(raw)) % 10_000}", name=name, arguments=raw)


def turn(*calls: ToolCall, content: str = "") -> ToolTurn:
    return ToolTurn(content=content, tool_calls=list(calls))


class ScriptedTools(FakeLLM):
    """Plays `turns` in order. After the script runs out it keeps repeating `then`, which defaults to
    a model that is finished (no tool call). `then` may be a callable for a model that never stops."""

    def __init__(self, turns: list[ToolTurn], *, then: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.turns = list(turns)
        self.then = then
        self.tool_requests: list[list[dict[str, Any]]] = []
        self.tool_counter = 0

    async def tool_completion(self, messages, tools, *, temperature=None) -> ToolTurn:
        self.tool_requests.append([dict(m) for m in messages])
        self.tool_counter += 1
        if self.turns:
            return self.turns.pop(0)
        if callable(self.then):
            return self.then(self.tool_counter)
        return self.then if self.then is not None else turn(content="DONE")

    def tool_messages(self) -> list[str]:
        """Every tool result the model was sent, in order, from the latest request."""
        return [m["content"] for m in (self.tool_requests[-1] if self.tool_requests else []) if m.get("role") == "tool"]
