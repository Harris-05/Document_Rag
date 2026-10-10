import asyncio
import json

import pytest

from app import repository
from app.compare.segment import segment
from app.config import get_settings
from app.db import init_db
from app.rag import prompts
from app.rag.agent import AgentInput
from app.rag.index import ensure_index
from app.rag.research_agent import run_research_agent
from app.rag.research_tools import DocumentTools

from .fakes import FakeLLM
from .fakes_tools import ScriptedTools, call, turn

PAGES = [
    (1, "1. Definitions\nIn this Agreement, the Supplier means Northwind Trading LLC."),
    (
        2,
        "12. Termination\n12.1 Either party may terminate this Agreement for convenience by giving "
        "ninety (90) days written notice to the other party.\n12.2 Termination does not affect "
        "liability that has already arisen, which remains subject to clause 14.",
    ),
    (
        3,
        "14. Limitation of Liability\nThe Supplier's aggregate liability under this Agreement shall "
        "not exceed AED 100,000 in any contract year.",
    ),
    (4, "20. Governing Law\nThis Agreement is governed by the laws of the United Arab Emirates."),
]
DOCUMENT_ID = "doc-research"
NOTICE = "either party may terminate this Agreement for convenience"
CAP = "aggregate liability under this Agreement shall not exceed AED 100,000"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    init_db()
    repository.create_document(DOCUMENT_ID, "msa.pdf", "pdf", 100)
    yield
    get_settings.cache_clear()


def answer(*quotes: str) -> str:
    cites = " ".join(f"[{i}]" for i in range(1, len(quotes) + 1))
    body = json.dumps([{"n": i, "evidence": "E1", "quote": q} for i, q in enumerate(quotes, start=1)])
    return f"Either party can terminate on 90 days notice {cites}.\n{prompts.QUOTES_MARKER}\n{body}"


def run(llm: FakeLLM, question: str = "Can either party terminate, and what is the liability cap?", **overrides) -> list[dict]:
    settings = get_settings().model_copy(update=overrides)

    async def collect():
        return [
            event
            async for event in run_research_agent(
                AgentInput(
                    question=question, history=[], pages=PAGES, document_id=DOCUMENT_ID, llm=llm, settings=settings
                )
            )
        ]

    return asyncio.run(collect())


def steps(events: list[dict], kind: str | None = None) -> list[dict]:
    found = [e["data"] for e in events if e["event"] == "step"]
    return [s for s in found if kind is None or s["kind"] == kind]


def done(events: list[dict]) -> dict:
    return next(e["data"] for e in events if e["event"] == "done")


def citations(events: list[dict]) -> list[dict]:
    return next(e["data"] for e in events if e["event"] == "citations")


def text(events: list[dict]) -> str:
    return "".join(e["data"]["text"] for e in events if e["event"] == "token")


class TestTheLoop:
    def test_several_rounds_each_reading_the_previous_result(self, db):
        llm = ScriptedTools(
            [
                turn(call("list_clauses", {})),
                turn(call("get_section", {"number": "12"})),
                turn(call("get_section", {"number": "14"})),
                turn(content="DONE"),
            ],
            answer=answer(NOTICE, CAP),
        )
        events = run(llm)

        assert done(events)["coverage"]["tool_calls"] == 3
        assert done(events)["coverage"]["rounds"] == 3  # the closing "DONE" turn is not a lookup round
        # Each request carries everything read so far, so later choices can depend on earlier results.
        assert "12. Termination (page 2)" in llm.tool_requests[1][-1]["content"]
        assert "ninety (90) days" in llm.tool_requests[2][-1]["content"]
        assert [c["verified"] for c in citations(events)] == [True, True]
        assert done(events)["quality"] == "sufficient"

    def test_announces_each_call_before_it_runs_and_its_outcome_after(self, db):
        llm = ScriptedTools(
            [turn(call("search_document", {"query": "termination notice"})), turn(content="DONE")],
            answer=answer(NOTICE),
        )
        events = run(llm)
        order = [s["kind"] for s in steps(events)]
        assert order.index("tool") < order.index("tool_result") < order.index("answer")
        first = steps(events, "tool")[0]
        assert first["text"] == "Searching for “termination notice”"
        assert first["detail"]["tool"] == "search_document"

    def test_the_answer_is_streamed_and_quotes_verified_against_the_document(self, db):
        llm = ScriptedTools([turn(call("get_section", {"number": "12"}))], answer=answer(NOTICE), stream_size=5)
        events = run(llm)
        assert len([e for e in events if e["event"] == "token"]) > 3
        assert "[1]" in text(events)
        assert prompts.QUOTES_MARKER not in text(events)
        assert citations(events)[0]["verified"] is True
        assert citations(events)[0]["page"] == 2

    def test_an_invented_quote_is_shown_as_unverified(self, db):
        llm = ScriptedTools(
            [turn(call("get_section", {"number": "12"}))],
            answer=answer("either party may terminate immediately without any notice at all"),
        )
        events = run(llm)
        assert citations(events)[0]["verified"] is False
        assert done(events)["quality"] == "partial"

    def test_the_answer_is_written_only_from_what_was_read(self, db):
        llm = ScriptedTools([turn(call("get_section", {"number": "20"}))], answer=answer("governed by the laws of the United Arab Emirates"))
        run(llm)
        prompt = llm.stream_calls[0]
        assert "United Arab Emirates" in prompt
        assert "AED 100,000" not in prompt

    def test_follow_up_history_is_given_to_the_model(self, db):
        llm = ScriptedTools([turn(call("get_section", {"number": "14"}))], answer=answer(CAP))
        settings = get_settings()

        async def collect():
            return [
                e
                async for e in run_research_agent(
                    AgentInput(
                        question="And the cap?",
                        history=[("user", "Tell me about termination"), ("assistant", "Either party can terminate.")],
                        pages=PAGES,
                        document_id=DOCUMENT_ID,
                        llm=llm,
                        settings=settings,
                    )
                )
            ]

        asyncio.run(collect())
        contents = [m["content"] for m in llm.tool_requests[0]]
        assert "Tell me about termination" in contents
        assert contents[-1] == "And the cap?"


class TestHardLimits:
    def test_a_model_that_never_stops_is_cut_off_at_the_round_cap(self, db):
        llm = ScriptedTools(
            [],
            then=lambda n: turn(call("search_document", {"query": f"liability topic {n}"})),
            answer=answer(CAP),
        )
        events = run(llm, max_research_rounds=3)
        assert llm.tool_counter == 3
        limit = steps(events, "limit")
        assert len(limit) == 1 and "limit of 3 rounds" in limit[0]["text"]
        assert done(events)["coverage"]["rounds"] == 3
        # It still answers from what it read, and says the evidence may be incomplete.
        assert llm.stream_calls and "INCOMPLETE" in llm.stream_calls[0]
        assert done(events)["quality"] == "partial"

    def test_calls_beyond_the_per_turn_cap_are_skipped_but_still_answered(self, db):
        many = [call("search_document", {"query": f"topic number {i}"}, call_id=f"c{i}") for i in range(6)]
        llm = ScriptedTools([turn(*many)], answer=answer(CAP))
        events = run(llm, max_tool_calls_per_round=2)
        assert done(events)["coverage"]["tool_calls"] == 2
        replies = {m["tool_call_id"]: m["content"] for m in llm.tool_requests[1] if m.get("role") == "tool"}
        # The provider rejects the next request if any tool call is left without a reply.
        assert set(replies) == {f"c{i}" for i in range(6)}
        assert replies["c5"].startswith("Skipped")

    def test_an_identical_repeated_call_is_not_run_again(self, db):
        same = {"query": "liability cap"}
        llm = ScriptedTools([turn(call("search_document", same)), turn(call("search_document", same))], answer=answer(CAP))
        events = run(llm)
        assert any("Repeated an earlier lookup" in s["text"] for s in steps(events, "tool_result"))
        assert "already made this exact call" in llm.tool_messages()[-1]


class TestBadToolCalls:
    @pytest.mark.parametrize(
        ("bad", "fragment"),
        [
            (call("delete_everything", {"x": 1}), "no tool named"),
            (call("search_document", "{not json"), "not valid JSON"),
            (call("search_document", "[1, 2]"), "must be a JSON object"),
            (call("search_document", {}), "query"),
            (call("search_document", {"query": "a"}), "query"),
            (call("search_document", {"query": "liability", "max_results": "lots"}), "max_results"),
            (call("search_document", {"query": "liability", "colour": "red"}), "colour"),
            (call("get_section", {"number": ""}), "number"),
            (call("get_section", {"section": "12"}), "number"),
            (call("list_clauses", {"verbose": True}), "verbose"),
            (call("", {}), "no tool named"),
        ],
    )
    def test_each_kind_of_bad_call_is_handled_and_explained_to_the_model(self, db, bad, fragment):
        llm = ScriptedTools([turn(bad), turn(call("get_section", {"number": "14"}))], answer=answer(CAP))
        events = run(llm)
        assert not [e for e in events if e["event"] == "error"]
        assert fragment in llm.tool_requests[1][-1]["content"]
        # The model corrected itself on the next turn, and the answer was still produced.
        assert citations(events)[0]["verified"] is True
        assert steps(events, "tool_result")[0]["detail"]["ok"] is False

    def test_a_model_that_keeps_sending_bad_calls_is_stopped(self, db):
        llm = ScriptedTools([], then=lambda n: turn(call("nonsense", {})), answer=answer(CAP))
        events = run(llm, max_invalid_tool_calls=3)
        assert llm.tool_counter == 3
        assert "3 invalid tool calls" in steps(events, "limit")[0]["text"]
        # Nothing valid was read, so a plain search on the question runs and the answer still arrives.
        assert done(events)["coverage"]["tool_calls"] == 4
        assert text(events)

    def test_a_model_that_answers_without_looking_anything_up_is_asked_to_search(self, db):
        llm = ScriptedTools(
            [turn(content="The cap is AED 5 million."), turn(call("get_section", {"number": "14"})), turn(content="DONE")],
            answer=answer(CAP),
        )
        events = run(llm)
        assert any("without looking anything up" in s["text"] for s in steps(events, "tool_result"))
        assert citations(events)[0]["verified"] is True

    def test_a_model_that_never_uses_a_tool_still_gets_the_question_searched(self, db):
        llm = ScriptedTools([], then=turn(content="I know the answer already."), answer=answer(CAP))
        events = run(llm)
        assert any(s["detail"] and s["detail"].get("tool") == "search_document" for s in steps(events, "tool"))
        assert text(events)


class TestOffTopic:
    def test_a_greeting_is_declined_without_searching(self, db):
        llm = ScriptedTools([turn(content="OFF_TOPIC")])
        events = run(llm, question="hello there")
        assert done(events)["quality"] == "not_applicable"
        assert not steps(events, "tool")
        assert not llm.stream_calls


class TestTools:
    @staticmethod
    def tools(db) -> DocumentTools:
        llm = FakeLLM()
        build = asyncio.run(ensure_index(DOCUMENT_ID, PAGES, llm, 600, 80))
        return DocumentTools(build.index, segment(PAGES), llm, get_settings())

    def test_get_section_returns_the_clause_with_its_sub_clauses(self, db):
        outcome = asyncio.run(self.tools(db).run("get_section", json.dumps({"number": "12"})))
        assert outcome.ok
        assert "ninety (90) days" in outcome.message and "clause 14" in outcome.message

    def test_get_section_accepts_a_heading_and_a_sub_clause(self, db):
        tools = self.tools(db)
        by_name = asyncio.run(tools.run("get_section", json.dumps({"number": "limitation of liability"})))
        assert "AED 100,000" in by_name.message
        sub = asyncio.run(tools.run("get_section", json.dumps({"number": "12.2"})))
        assert "remains subject to clause 14" in sub.message

    def test_an_unknown_section_lists_the_ones_that_exist(self, db):
        outcome = asyncio.run(self.tools(db).run("get_section", json.dumps({"number": "99"})))
        assert "no section" in outcome.message and "12" in outcome.message and "14" in outcome.message

    def test_list_clauses_is_a_table_of_contents(self, db):
        outcome = asyncio.run(self.tools(db).run("list_clauses", "{}"))
        assert "12. Termination (page 2)" in outcome.message
        assert "20. Governing Law (page 4)" in outcome.message

    def test_empty_arguments_are_accepted_for_a_tool_that_takes_none(self, db):
        assert asyncio.run(self.tools(db).run("list_clauses", "")).ok

    def test_search_returns_numbered_evidence_and_does_not_repeat_text(self, db):
        tools = self.tools(db)
        first = asyncio.run(tools.run("search_document", json.dumps({"query": "governing law United Arab Emirates"})))
        assert "[E1]" in first.message and "United Arab Emirates" in first.message
        second = asyncio.run(tools.run("search_document", json.dumps({"query": "laws of the United Arab Emirates governing"})))
        assert "(shown earlier)" in second.message
        assert len(tools.evidence) >= 1

    def test_very_long_sections_are_cut_and_the_model_told(self, db):
        long_pages = [(1, "1. Big\n" + "word " * 400)]
        llm = FakeLLM()
        build = asyncio.run(ensure_index(DOCUMENT_ID, long_pages, llm, 600, 80))
        settings = get_settings().model_copy(update={"research_section_chars": 500})
        tools = DocumentTools(build.index, segment(long_pages), llm, settings)
        outcome = asyncio.run(tools.run("get_section", json.dumps({"number": "1"})))
        assert "cut short" in outcome.message

