"""The real client's tool-calling path, with the provider's SDK replaced by a stub."""

import asyncio
from types import SimpleNamespace

from app.config import Settings
from app.rag.llm import OpenAIClient


def completion(content, calls):
    message = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def client_returning(response):
    client = OpenAIClient(Settings(openai_api_key="test-key"))
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return response

    client._client.chat.completions.create = create
    return client, seen


def test_parses_tool_calls_and_keeps_arguments_raw():
    client, seen = client_returning(
        completion(None, [tool_call("c1", "search_document", '{"query": "x"}'), tool_call("c2", "get_section", "{broken")])
    )
    turn = asyncio.run(client.tool_completion([{"role": "user", "content": "q"}], [{"type": "function"}], temperature=0.2))

    assert [(c.id, c.name, c.arguments) for c in turn.tool_calls] == [
        ("c1", "search_document", '{"query": "x"}'),
        ("c2", "get_section", "{broken"),
    ]
    assert turn.content == ""
    assert seen["tools"] == [{"type": "function"}] and seen["tool_choice"] == "auto"


def test_a_plain_reply_has_no_tool_calls():
    client, _ = client_returning(completion("DONE", None))
    turn = asyncio.run(client.tool_completion([], []))
    assert turn.content == "DONE" and turn.tool_calls == []


def test_a_call_with_missing_fields_does_not_crash():
    client, _ = client_returning(completion("", [tool_call("c1", None, None)]))
    turn = asyncio.run(client.tool_completion([], []))
    assert (turn.tool_calls[0].name, turn.tool_calls[0].arguments) == ("", "")
