"""Research mode over HTTP: the mode switch, the saved trace, and where it is not allowed."""

import io
import json

from fastapi.testclient import TestClient

from app.rag import prompts

from .conftest import PDF_TYPE, make_text_pdf
from .fakes import FakeLLM
from .fakes_tools import ScriptedTools, call, turn
from .test_chat_api import QUOTE, document_id, parse_sse, use_llm  # noqa: F401 (fixtures)


def research_llm() -> ScriptedTools:
    answer = (
        "The Supplier must indemnify the Customer [1].\n"
        f"{prompts.QUOTES_MARKER}\n" + json.dumps([{"n": 1, "evidence": "E1", "quote": QUOTE}])
    )
    return ScriptedTools(
        [turn(call("search_document", {"query": "indemnify customer losses"})), turn(content="DONE")],
        answer=answer,
    )


def ask(client: TestClient, document_id: str, **body):
    return client.post(f"/api/documents/{document_id}/chat", json={"question": "Who indemnifies whom?", **body})


class TestResearchMode:
    def test_streams_tool_steps_then_a_verified_answer(self, client, document_id, use_llm):  # noqa: F811
        llm = use_llm(research_llm())
        events = parse_sse(ask(client, document_id, mode="research").text)

        kinds = [d["kind"] for n, d in events if n == "step"]
        assert "tool" in kinds and "tool_result" in kinds
        assert next(d for n, d in events if n == "citations")[0]["verified"] is True
        assert events[-1][0] == "done" and events[-1][1]["coverage"]["tool_calls"] == 1
        assert llm.tool_counter == 2

    def test_the_trace_of_tool_calls_is_saved_with_the_message(self, client, document_id, use_llm):  # noqa: F811
        use_llm(research_llm())
        ask(client, document_id, mode="research")
        saved = client.get(f"/api/documents/{document_id}/messages").json()[-1]
        assert [s["kind"] for s in saved["trace"] if s["kind"] in ("tool", "tool_result")] == ["tool", "tool_result"]

    def test_standard_is_still_the_default(self, client, document_id, use_llm):  # noqa: F811
        llm = use_llm(research_llm())
        ask(client, document_id)
        assert llm.tool_counter == 0

    def test_an_unknown_mode_is_rejected(self, client, document_id):  # noqa: F811
        assert ask(client, document_id, mode="turbo").status_code == 422

    def test_a_multi_document_conversation_does_not_offer_it(self, client, use_llm):  # noqa: F811
        use_llm(FakeLLM())
        ids = []
        for name in ("a.pdf", "b.pdf"):
            response = client.post("/api/documents", files={"file": (name, io.BytesIO(make_text_pdf(2)), PDF_TYPE)})
            ids.append(response.json()["id"])
        conversation = client.post("/api/conversations", json={"document_ids": ids}).json()
        response = client.post(
            f"/api/conversations/{conversation['id']}/chat", json={"question": "Compare them", "mode": "research"}
        )
        assert response.status_code == 422
        assert "one document" in response.json()["detail"]
