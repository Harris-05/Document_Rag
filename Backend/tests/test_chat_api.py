import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient

from app import chat_repository, repository
from app.chat_service import stream_chat
from app.config import get_settings
from app.dependencies import get_llm
from app.main import app
from app.rag import prompts

from .conftest import PDF_TYPE, make_text_pdf
from .fakes import FakeLLM, ScriptedGrader

QUOTE = "The Supplier shall indemnify the Customer against all losses arising from breach."


def answer_with(quote: str = QUOTE) -> str:
    return (
        "The Supplier must indemnify the Customer for losses from breach [1].\n"
        f"{prompts.QUOTES_MARKER}\n" + json.dumps([{"n": 1, "evidence": "E1", "quote": quote}])
    )


def llm_for_one_question(**overrides) -> ScriptedGrader:
    return ScriptedGrader(
        plans=[{"intent": "document_question", "queries": ["indemnify customer losses"], "rationale": ""}],
        grades=[{"page": 1, "score": 2, "sufficient": True, "missing": ""}],
        answer=overrides.pop("answer", answer_with()),
        **overrides,
    )


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return events


@pytest.fixture
def document_id(client: TestClient) -> str:
    response = client.post(
        "/api/documents", files={"file": ("msa.pdf", io.BytesIO(make_text_pdf(3)), PDF_TYPE)}
    )
    assert response.status_code == 202
    return response.json()["id"]


@pytest.fixture
def use_llm(client):
    def install(llm):
        app.dependency_overrides[get_llm] = lambda: llm
        return llm

    yield install
    app.dependency_overrides.pop(get_llm, None)


def ask(client: TestClient, document_id: str, question: str = "Who indemnifies whom?"):
    return client.post(f"/api/documents/{document_id}/chat", json={"question": question})


class TestStreaming:
    def test_streams_steps_tokens_citations_and_done(self, client, document_id, use_llm):
        use_llm(llm_for_one_question())
        response = ask(client, document_id)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(response.text)
        names = [name for name, _ in events]
        assert names[0] == "start"
        assert names[-1] == "done"
        assert "step" in names and "token" in names and "citations" in names

        answer = "".join(d["text"] for n, d in events if n == "token")
        assert answer.startswith("The Supplier must indemnify")
        citations = next(d for n, d in events if n == "citations")
        assert citations[0]["verified"] is True
        assert citations[0]["page"] == 1
        done = events[-1][1]
        assert done["quality"] == "sufficient"
        assert done["message_id"]

    def test_the_conversation_is_saved_and_can_be_reopened(self, client, document_id, use_llm):
        use_llm(llm_for_one_question())
        ask(client, document_id)

        messages = client.get(f"/api/documents/{document_id}/messages").json()
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "Who indemnifies whom?"
        assistant = messages[1]
        assert assistant["status"] == "complete"
        assert assistant["quality"] == "sufficient"
        assert assistant["citations"][0]["verified"] is True
        assert assistant["trace"][0]["kind"] in {"index", "understand"}
        assert assistant["coverage"]["pages"] == 3

    def test_follow_up_questions_receive_the_earlier_turns(self, client, document_id, use_llm):
        llm = use_llm(
            ScriptedGrader(
                plans=[
                    {"intent": "document_question", "queries": ["indemnify"], "rationale": ""},
                    {"intent": "document_question", "queries": ["indemnify losses"], "rationale": ""},
                ],
                grades=[{"page": 1, "score": 2, "sufficient": True, "missing": ""}] * 2,
                answer=answer_with(),
            )
        )
        ask(client, document_id, "Who indemnifies whom?")
        ask(client, document_id, "And what does it cover?")

        second_query_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[1]
        assert "Who indemnifies whom?" in second_query_prompt
        assert "The Supplier must indemnify the Customer" in second_query_prompt


class TestFailures:
    def test_provider_failure_is_reported_and_the_partial_answer_is_kept(self, client, document_id, use_llm):
        use_llm(llm_for_one_question(fail_stream_after=3))
        events = parse_sse(ask(client, document_id).text)

        assert events[-1][0] == "error"
        assert "took too long" in events[-1][1]["message"]
        assistant = client.get(f"/api/documents/{document_id}/messages").json()[-1]
        assert assistant["status"] == "error"
        assert assistant["content"].startswith("The Supp")
        assert assistant["error_message"]

    def test_missing_api_key_gives_a_clear_503(self, client, document_id, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPEN_AI_APIKEY", raising=False)
        get_settings.cache_clear()
        settings = get_settings().model_copy(update={"openai_api_key": None})
        monkeypatch.setattr("app.dependencies.get_settings", lambda: settings)

        response = ask(client, document_id)

        assert response.status_code == 503
        assert response.json()["code"] == "AI_NOT_CONFIGURED"
        assert "OPENAI_API_KEY" in response.json()["message"]
        assert client.get(f"/api/documents/{document_id}/messages").json() == []

    def test_unknown_document(self, client, use_llm):
        use_llm(FakeLLM())
        assert ask(client, "missing").status_code == 404
        assert client.get("/api/documents/missing/messages").status_code == 404

    @pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
    def test_invalid_questions_are_rejected_before_anything_is_saved(self, client, document_id, use_llm, question):
        use_llm(FakeLLM())
        assert ask(client, document_id, question).status_code == 422
        assert client.get(f"/api/documents/{document_id}/messages").json() == []


class TestStopping:
    def test_closing_the_stream_keeps_what_was_generated(self, client, document_id):
        llm = llm_for_one_question(answer="A" * 400 + f"\n{prompts.QUOTES_MARKER}\n[]", stream_size=20)
        document = repository.get_detail(document_id)
        pages = [(p.page_number, p.text) for p in document.pages]

        async def consume_then_stop():
            stream = stream_chat(
                document_id=document_id,
                question="Summarise the indemnity",
                pages=pages,
                llm=llm,
                settings=get_settings(),
            )
            seen = 0
            async for frame in stream:
                if frame.startswith("event: token"):
                    seen += 1
                if seen == 3:
                    break
            await stream.aclose()

        asyncio.run(consume_then_stop())

        stopped = chat_repository.list_messages(document_id)[-1]
        assert stopped.status == "stopped"
        assert stopped.content.startswith("AAAA")
        assert 0 < len(stopped.content) < 400

    def test_stopped_answers_are_not_fed_back_as_history(self, client, document_id):
        chat_repository.add_user_message(document_id, "first question")
        chat_repository.add_assistant_message(
            document_id, content="half an ans", status="stopped", quality=None, citations=[], trace=[], coverage=None
        )

        assert chat_repository.recent_history(document_id) == [("user", "first question")]


class TestLifecycle:
    def test_deleting_a_document_deletes_its_conversation_and_index(self, client, document_id, use_llm):
        use_llm(llm_for_one_question())
        ask(client, document_id)
        assert client.delete(f"/api/documents/{document_id}").status_code == 204

        from app.db import connect

        with connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


def plans(*, standalone: str | None = None, count: int = 1) -> list[dict]:
    return [
        {
            "intent": "document_question",
            "queries": ["indemnify losses"],
            "standalone_question": standalone or "",
            "rationale": "",
        }
        for _ in range(count)
    ]


def grade() -> dict:
    return {"page": 1, "score": 2, "sufficient": True, "missing": ""}


class TestShortTermMemory:
    def test_a_follow_up_is_resolved_and_used_by_the_judge_and_the_answer(self, client, document_id, use_llm):
        resolved = "What losses does the Supplier's indemnity cover?"
        llm = use_llm(
            ScriptedGrader(
                plans=plans(count=1) + plans(standalone=resolved),
                grades=[grade(), grade()],
                answer=answer_with(),
            )
        )
        ask(client, document_id, "Who indemnifies whom?")
        ask(client, document_id, "What does it cover?")

        second_grade_prompt = llm.prompts_for(prompts.GRADE_SYSTEM)[1]
        assert resolved in second_grade_prompt
        second_answer_prompt = llm.stream_calls[1]
        assert resolved in second_answer_prompt
        assert "What does it cover?" in second_answer_prompt  # the user's own wording is kept too

    def test_the_memory_window_only_holds_the_configured_number_of_turns(self, client, document_id, use_llm, monkeypatch):
        monkeypatch.setenv("CHAT_MEMORY_TURNS", "1")
        get_settings.cache_clear()
        llm = use_llm(ScriptedGrader(plans=plans(count=3), grades=[grade()] * 3, answer=answer_with()))

        ask(client, document_id, "first question about indemnity")
        ask(client, document_id, "second question about indemnity")
        ask(client, document_id, "third question about indemnity")

        third_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[2]
        assert "second question about indemnity" in third_prompt
        assert "first question about indemnity" not in third_prompt

    def test_zero_turns_turns_memory_off(self, client, document_id, use_llm, monkeypatch):
        monkeypatch.setenv("CHAT_MEMORY_TURNS", "0")
        get_settings.cache_clear()
        llm = use_llm(ScriptedGrader(plans=plans(count=2), grades=[grade()] * 2, answer=answer_with()))

        ask(client, document_id, "first question about indemnity")
        ask(client, document_id, "second question about indemnity")

        second_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[1]
        assert "(no earlier messages)" in second_prompt
        assert "first question about indemnity" not in second_prompt

    def test_the_conversation_is_still_saved_when_memory_is_off(self, client, document_id, use_llm, monkeypatch):
        monkeypatch.setenv("CHAT_MEMORY_TURNS", "0")
        get_settings.cache_clear()
        use_llm(ScriptedGrader(plans=plans(), grades=[grade()], answer=answer_with()))
        ask(client, document_id)

        assert len(client.get(f"/api/documents/{document_id}/messages").json()) == 2

    def test_long_earlier_answers_are_shortened(self, client, document_id, use_llm, monkeypatch):
        monkeypatch.setenv("CHAT_MEMORY_CHARS", "100")
        get_settings.cache_clear()
        long_answer = "Word " * 200 + "[1]\n" + f"{prompts.QUOTES_MARKER}\n" + json.dumps(
            [{"n": 1, "evidence": "E1", "quote": QUOTE}]
        )
        llm = use_llm(ScriptedGrader(plans=plans(count=2), grades=[grade()] * 2, answer=long_answer))

        ask(client, document_id, "first")
        ask(client, document_id, "second")

        second_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[1]
        assert "[...]" in second_prompt
        assert second_prompt.count("Word ") < 30

    def test_an_unset_standalone_question_falls_back_to_the_users_wording(self, client, document_id, use_llm):
        llm = use_llm(ScriptedGrader(plans=plans(), grades=[grade()], answer=answer_with()))
        ask(client, document_id, "Who indemnifies whom?")

        assert "Who indemnifies whom?" in llm.prompts_for(prompts.GRADE_SYSTEM)[0]
