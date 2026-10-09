import asyncio
import json

import pytest

from app import repository
from app.config import get_settings
from app.db import init_db
from app.rag import prompts
from app.rag.agent import AgentInput, run_agent
from app.rag.index import load_chunks
from app.rag.llm import LLMError

from .fakes import FakeLLM, ScriptedGrader

PAGES = [
    (1, "1. Definitions. In this Agreement, the Supplier means Northwind Trading LLC."),
    (
        2,
        "12. Termination. Either party may terminate this Agreement for convenience by giving "
        "ninety (90) days written notice to the other party.",
    ),
    (
        3,
        "14. Limitation of Liability. The Supplier's aggregate liability under this Agreement shall "
        "not exceed AED 100,000 in any contract year.",
    ),
    (4, "20. Governing Law. This Agreement is governed by the laws of the United Arab Emirates."),
]
DOCUMENT_ID = "doc-1"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    init_db()
    repository.create_document(DOCUMENT_ID, "msa.pdf", "pdf", 100)
    yield
    get_settings.cache_clear()


def chunk_id_for_page(page: int) -> int:
    return next(chunk.id for chunk, _ in load_chunks(DOCUMENT_ID) if chunk.page_number == page)


def run(llm: FakeLLM, question: str = "Can either party terminate?", pages=PAGES, **overrides) -> list[dict]:
    settings = get_settings().model_copy(update=overrides)

    async def collect():
        events = []
        async for event in run_agent(
            AgentInput(
                question=question,
                history=[],
                pages=pages,
                document_id=DOCUMENT_ID,
                llm=llm,
                settings=settings,
            )
        ):
            events.append(event)
        return events

    return asyncio.run(collect())


def text_of(events: list[dict]) -> str:
    return "".join(e["data"]["text"] for e in events if e["event"] == "token")


def done_of(events: list[dict]) -> dict:
    return next(e["data"] for e in events if e["event"] == "done")


def citations_of(events: list[dict]) -> list[dict]:
    return next(e["data"] for e in events if e["event"] == "citations")


def steps_of(events: list[dict], kind: str | None = None) -> list[dict]:
    steps = [e["data"] for e in events if e["event"] == "step"]
    return [s for s in steps if kind is None or s["kind"] == kind]


def plan(*queries: str, intent: str = "document_question") -> dict:
    return {"intent": intent, "queries": list(queries), "rationale": "test"}


def good_answer(quote: str = "either party may terminate this Agreement for convenience") -> str:
    return (
        "Yes. Either party can terminate for convenience on 90 days written notice [1].\n"
        f"{prompts.QUOTES_MARKER}\n"
        + json.dumps([{"n": 1, "evidence": "E1", "quote": quote}])
    )


def grading_for_page(page: int, score: int = 2, *, sufficient: bool = True, missing: str = "") -> dict:
    """Builds a grade payload once the chunk ids exist (they are created by the first retrieval)."""
    return {"page": page, "score": score, "sufficient": sufficient, "missing": missing}


class TestHappyPath:
    def test_retrieves_grades_answers_and_verifies_quotes(self, db):
        llm = ScriptedGrader(
            plans=[plan("terminate for convenience written notice")],
            grades=[grading_for_page(2)],
            answer=good_answer(),
        )
        events = run(llm)

        assert text_of(events).startswith("Yes. Either party can terminate")
        citation = citations_of(events)[0]
        assert citation["verified"] is True
        assert citation["page"] == 2
        assert done_of(events)["quality"] == "sufficient"
        assert done_of(events)["verification"] == {"verified": 1, "unverified": 0}
        assert llm.count(prompts.QUERY_SYSTEM) == 1
        assert llm.count(prompts.GRADE_SYSTEM) == 1
        assert len(llm.stream_calls) == 1

    def test_only_judged_passages_reach_the_answer_prompt(self, db):
        llm = ScriptedGrader(
            plans=[plan("terminate notice")], grades=[grading_for_page(2)], answer=good_answer()
        )
        run(llm, neighbor_chunks=0)

        answer_prompt = llm.stream_calls[0]
        assert "ninety (90) days" in answer_prompt
        assert "Northwind Trading" not in answer_prompt
        assert "aggregate liability" not in answer_prompt

    def test_progress_steps_are_reported_in_order(self, db):
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        kinds = [s["kind"] for s in steps_of(run(llm))]

        assert kinds == ["index", "understand", "search", "grade", "quality", "answer", "quotes", "verify"]

    def test_the_full_answer_text_is_sent_before_the_quotes_phase_begins(self, db):
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        events = run(llm)

        names = [(e["event"], e["data"].get("kind") if e["event"] == "step" else None) for e in events]
        quotes_at = names.index(("step", "quotes"))
        last_token_at = max(i for i, (name, _) in enumerate(names) if name == "token")
        assert last_token_at < quotes_at
        assert text_of(events).strip().endswith("[1].")

    def test_index_is_built_once_and_reused(self, db):
        first = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        run(first)
        second = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        events = run(second)

        assert "index" not in [s["kind"] for s in steps_of(events)]
        assert second.embed_calls == 1  # only the query, chunks were already embedded


class TestCorrectiveLoop:
    def test_weak_retrieval_triggers_a_refined_search(self, db):
        llm = ScriptedGrader(
            plans=[plan("Supplier definitions Northwind"), plan("terminate for convenience written notice")],
            grades=[
                grading_for_page(1, score=1, sufficient=False, missing="the termination clause and its notice period"),
                grading_for_page(2, score=2, sufficient=True),
            ],
            answer=good_answer(),
        )
        events = run(llm, question="Can they walk away?", candidates_per_round=1)

        assert done_of(events)["coverage"]["rounds"] == 2
        assert done_of(events)["quality"] == "sufficient"
        refine_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[1]
        assert "the termination clause and its notice period" in refine_prompt
        assert "Supplier definitions Northwind" in refine_prompt
        assert "refine" in [s["kind"] for s in steps_of(events)]

    def test_evidence_accumulates_across_rounds(self, db):
        llm = ScriptedGrader(
            plans=[plan("liability cap"), plan("termination notice")],
            grades=[
                grading_for_page(3, score=2, sufficient=False, missing="termination"),
                grading_for_page(2, score=2, sufficient=True),
            ],
            answer=good_answer(),
        )
        run(llm, question="What is the liability cap and who can terminate?", candidates_per_round=1)

        prompt = llm.stream_calls[0]
        assert "AED 100,000" in prompt and "ninety (90) days" in prompt

    def test_round_cap_is_a_hard_limit(self, db):
        llm = ScriptedGrader(
            plans=[plan("supplier definitions"), plan("liability cap"), plan("governing law"), plan("termination")],
            grades=[grading_for_page(1, score=0, sufficient=False, missing="x")] * 5,
            answer="should never be used",
        )
        events = run(llm, max_retrieval_rounds=2, candidates_per_round=1)

        assert llm.count(prompts.GRADE_SYSTEM) == 2
        assert llm.count(prompts.QUERY_SYSTEM) == 2
        assert done_of(events)["coverage"]["rounds"] == 2
        assert llm.stream_calls == []

    def test_stops_when_a_search_finds_nothing_new(self, db):
        llm = ScriptedGrader(
            plans=[plan("anything"), plan("anything else"), plan("again")],
            grades=[grading_for_page(1, score=0, sufficient=False, missing="x")] * 3,
        )
        tiny = [(1, "Only one short page of text in this contract.")]
        events = run(llm, pages=tiny, candidates_per_round=5)

        assert llm.count(prompts.GRADE_SYSTEM) == 1
        assert done_of(events)["quality"] == "insufficient"


class TestHonestyWhenEvidenceIsMissing:
    def test_no_relevant_evidence_returns_a_not_found_message_without_calling_the_answer_model(self, db):
        llm = ScriptedGrader(
            plans=[plan("non-compete restriction"), plan("restraint of trade"), plan("exclusivity")],
            grades=[grading_for_page(1, score=0, sufficient=False, missing="a non-compete clause")] * 3,
            answer="MUST NOT BE USED",
        )
        events = run(llm, question="Is there a non-compete?")
        message = text_of(events)

        assert llm.stream_calls == []
        assert done_of(events)["quality"] == "insufficient"
        assert citations_of(events) == []
        assert "couldn't find a passage" in message
        assert "not proof" in message
        assert "non-compete restriction" in message
        assert "does not contain" not in message

    def test_not_found_message_reports_pages_that_could_not_be_searched(self, db):
        pages = [*PAGES, (5, ""), (6, "   ")]
        llm = ScriptedGrader(
            plans=[plan("arbitration")] * 3,
            grades=[grading_for_page(1, score=0, sufficient=False, missing="arbitration")] * 3,
        )
        message = text_of(run(llm, question="Is there arbitration?", pages=pages))

        assert "2 pages had no readable text" in message

    def test_partial_evidence_is_flagged_and_the_model_is_told(self, db):
        llm = ScriptedGrader(
            plans=[plan("liability")] * 3,
            grades=[grading_for_page(3, score=1, sufficient=False, missing="exclusions from the cap")] * 3,
            answer=good_answer("Limitation of Liability"),
        )
        events = run(llm, question="What is excluded from the liability cap?")

        assert done_of(events)["quality"] == "partial"
        assert "INCOMPLETE" in llm.stream_calls[0]

    def test_a_judge_that_says_sufficient_without_any_strong_passage_is_not_believed(self, db):
        llm = ScriptedGrader(
            plans=[plan("anything")] * 3,
            grades=[grading_for_page(1, score=0, sufficient=True)] * 3,
        )
        events = run(llm)

        assert done_of(events)["quality"] == "insufficient"


class TestQuoteVerificationInTheLoop:
    def test_an_invented_quote_is_flagged_unverified(self, db):
        invented = "Either party may terminate at any time without notice or reason."
        llm = ScriptedGrader(
            plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer(invented)
        )
        events = run(llm)
        citation = citations_of(events)[0]

        assert citation["verified"] is False
        assert citation["ranges"] == []
        assert done_of(events)["verification"] == {"verified": 0, "unverified": 1}

    def test_a_position_claimed_by_the_model_is_ignored(self, db):
        answer = (
            "The cap is AED 100,000 [1].\n"
            f"{prompts.QUOTES_MARKER}\n"
            + json.dumps([{"n": 1, "evidence": "E1", "page": 1, "start": 0, "end": 5,
                           "quote": "aggregate liability under this Agreement shall not exceed AED 100,000"}])
        )
        llm = ScriptedGrader(plans=[plan("liability")], grades=[grading_for_page(3)], answer=answer)
        citation = citations_of(run(llm))[0]

        assert citation["verified"] is True
        assert citation["page"] == 3

    def test_a_citation_marker_without_a_quote_is_unverified(self, db):
        answer = f"Notice is 90 days [1] and the cap is AED 100,000 [2].\n{prompts.QUOTES_MARKER}\n" + json.dumps(
            [{"n": 1, "evidence": "E1", "quote": "ninety (90) days written notice"}]
        )
        llm = ScriptedGrader(plans=[plan("notice")], grades=[grading_for_page(2)], answer=answer)
        citations = citations_of(run(llm))

        assert [(c["n"], c["verified"]) for c in citations] == [(1, True), (2, False)]

    def test_malformed_quote_json_yields_no_verified_citations(self, db):
        llm = ScriptedGrader(
            plans=[plan("notice")],
            grades=[grading_for_page(2)],
            answer=f"Ninety days [1].\n{prompts.QUOTES_MARKER}\nnot json at all",
        )
        citations = citations_of(run(llm))

        assert [(c["n"], c["verified"]) for c in citations] == [(1, False)]

    def test_the_quotes_marker_never_leaks_into_streamed_text_even_when_split(self, db):
        for size in (1, 2, 3, 5, 11):
            llm = ScriptedGrader(
                plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer(), stream_size=size
            )
            streamed = text_of(run(llm))
            assert "<<<" not in streamed and "QUOTES" not in streamed
            assert streamed.strip().endswith("[1].")


class TestOtherBehaviour:
    def test_off_topic_messages_do_not_trigger_retrieval(self, db):
        llm = ScriptedGrader(plans=[plan(intent="off_topic")])
        events = run(llm, question="hello there")

        assert llm.count(prompts.GRADE_SYSTEM) == 0
        assert llm.stream_calls == []
        assert "only answer questions about this document" in text_of(events)
        assert done_of(events)["quality"] == "not_applicable"

    def test_search_falls_back_to_keywords_when_embeddings_fail(self, db):
        llm = ScriptedGrader(
            plans=[plan("liability cap AED")],
            grades=[grading_for_page(3)],
            answer=good_answer("not exceed AED 100,000 in any contract year"),
            embeddings_fail=True,
        )
        events = run(llm, question="What is the cap?")

        assert done_of(events)["coverage"]["keyword_only"] is True
        assert any("keyword search" in s["text"] for s in steps_of(events, "index"))
        assert citations_of(events)[0]["verified"] is True

    def test_unknown_passage_ids_from_the_judge_are_ignored(self, db):
        llm = FakeLLM(
            plans=[plan("liability")] * 3,
            grades=[{"grades": [{"id": 999999, "score": 2}], "sufficient": True, "missing": ""}] * 3,
        )
        events = run(llm)

        assert done_of(events)["quality"] == "insufficient"

    def test_provider_failure_propagates_for_the_caller_to_report(self, db):
        llm = ScriptedGrader(
            plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer(), fail_stream_after=1
        )
        with pytest.raises(LLMError):
            run(llm)

    def test_invalid_judge_output_is_reported_as_an_error(self, db):
        llm = FakeLLM(plans=[plan("terminate")], grades=[{"grades": [{"id": 1, "score": 9}]}])
        with pytest.raises(LLMError):
            run(llm)
