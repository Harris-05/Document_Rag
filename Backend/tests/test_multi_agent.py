import asyncio
import json
from collections.abc import Callable

import pytest

from app import repository
from app.config import get_settings
from app.db import init_db
from app.rag import prompts, prompts_multi
from app.rag.llm import LLMError
from app.rag.multi_agent import MultiInput, SourceDocument, run_multi_agent

from .fakes import FakeLLM, ScriptedMultiGrader, evidence_label

A_TERMINATION = "Either party may terminate this Agreement for convenience by giving ninety (90) days written notice to the other party."
B_TERMINATION = "Either party may terminate this Agreement for convenience by giving thirty (30) days written notice to the other party."
GOVERNING_LAW = "This Agreement is governed by the laws of England and Wales."

DOC_A = SourceDocument(
    "aaaa",
    "msa_a.pdf",
    [
        (1, f"1. Termination\n\n{A_TERMINATION}"),
        (2, "2. Limitation of Liability\n\nThe Supplier's aggregate liability under this Agreement shall not exceed AED 100,000 in any contract year."),
        (3, f"3. Governing Law\n\n{GOVERNING_LAW}"),
    ],
)
DOC_B = SourceDocument(
    "bbbb",
    "msa_b.pdf",
    [
        (1, f"1. Termination\n\n{B_TERMINATION}"),
        (2, "2. Limitation of Liability\n\nThe Supplier's aggregate liability under this Agreement shall not exceed AED 1,000,000 in any contract year."),
        (3, f"3. Governing Law\n\n{GOVERNING_LAW}\n\n4. Payment\n\nInvoices are payable within forty-five (45) days of receipt."),
    ],
)
DOC_C = SourceDocument("cccc", "services.pdf", [(1, "1. Services\n\nThe Supplier shall provide the consulting services described in Schedule 1.")])


def filler_pages(count: int, topic_word: str, special: dict[int, str] | None = None) -> list[tuple[int, str]]:
    pages = []
    for n in range(1, count + 1):
        text = (special or {}).get(
            n, f"Clause {n}. The parties record obligation number {n * 13} about {topic_word} and the schedule {n + 40}."
        )
        pages.append((n, text))
    return pages


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    init_db()
    for source in (DOC_A, DOC_B, DOC_C, BIG_A, BIG_B):
        repository.create_document(source.id, source.name, "pdf", 100)
    yield
    get_settings.cache_clear()


BIG_A = SourceDocument(
    "big-a",
    "big_a.pdf",
    filler_pages(30, "termination termination terminate notice", {30: f"30. Termination\n\n{A_TERMINATION}"}),
)
BIG_B = SourceDocument(
    "big-b",
    "big_b.pdf",
    filler_pages(24, "deliveries and premises", {17: f"17. Termination\n\n{B_TERMINATION}"}),
)


def run(llm, documents, question="How do the notice periods compare?", **overrides) -> list[dict]:
    settings = get_settings().model_copy(update=overrides)

    async def collect():
        return [
            event
            async for event in run_multi_agent(
                MultiInput(question=question, history=[], documents=documents, llm=llm, settings=settings)
            )
        ]

    return asyncio.run(collect())


def plan(*queries: str, intent: str = "document_question", standalone: str = "") -> dict:
    return {"intent": intent, "queries": list(queries), "standalone_question": standalone, "rationale": ""}


def judge(scores: dict, sufficient: dict | bool, missing: dict | None = None) -> dict:
    return {"scores": scores, "sufficient": sufficient, "missing": missing or {}}


def comparison(quotes: list[tuple[str, int | None, str]], overrides: dict[int, dict] | None = None) -> Callable[[str], str]:
    """An answer whose quotes name the right evidence passage; `overrides` rewrites chosen entries."""

    def build(prompt: str) -> str:
        entries = []
        for n, (document, page, quote) in enumerate(quotes, start=1):
            entry = {"n": n, "document": document, "evidence": evidence_label(prompt, document, page), "quote": quote}
            entry.update((overrides or {}).get(n, {}))
            entries.append(entry)
        refs = " ".join(f"[{n}]" for n in range(1, len(quotes) + 1))
        return f"The notice periods differ {refs}.\n{prompts.QUOTES_MARKER}\n" + json.dumps(entries)

    return build


def text_of(events):
    return "".join(e["data"]["text"] for e in events if e["event"] == "token")


def done_of(events):
    return next(e["data"] for e in events if e["event"] == "done")


def citations_of(events):
    return next(e["data"] for e in events if e["event"] == "citations")


def steps_of(events, kind=None):
    steps = [e["data"] for e in events if e["event"] == "step"]
    return [s for s in steps if kind is None or s["kind"] == kind]


NINETY = "giving ninety (90) days written notice"
THIRTY = "giving thirty (30) days written notice"


class TestComparingDocuments:
    def test_each_document_is_judged_and_quoted_separately(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate notice")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY), ("D2", 1, THIRTY)]),
        )
        events = run(llm, [DOC_A, DOC_B])
        first, second = citations_of(events)

        assert (first["verified"], first["document_id"], first["document_name"], first["page"]) == (True, "aaaa", "msa_a.pdf", 1)
        assert (second["verified"], second["document_id"], second["document_name"], second["page"]) == (True, "bbbb", "msa_b.pdf", 1)
        assert done_of(events)["quality"] == "sufficient"
        assert done_of(events)["verification"] == {"verified": 2, "unverified": 0}

    def test_one_judging_call_sees_every_document_under_its_own_heading(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        run(llm, [DOC_A, DOC_B])

        prompt = llm.prompts_for(prompts_multi.GRADE_MULTI_SYSTEM)[0]
        assert llm.count(prompts_multi.GRADE_MULTI_SYSTEM) == 1
        assert '=== D1: "msa_a.pdf" ===' in prompt and '=== D2: "msa_b.pdf" ===' in prompt

    def test_the_answer_is_asked_to_compare_and_sees_passages_labelled_by_document(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY), ("D2", 1, THIRTY)]),
        )
        run(llm, [DOC_A, DOC_B])

        assert dict(llm.temperatures)[prompts_multi.ANSWER_MULTI_SYSTEM] == get_settings().temperature_answer
        assert "ONE integrated answer" in prompts_multi.ANSWER_MULTI_SYSTEM
        assert "Do NOT write a separate summary" in prompts_multi.ANSWER_MULTI_SYSTEM
        prompt = llm.stream_calls[0]
        assert 'Document D1 "msa_a.pdf"' in prompt and 'Document D2 "msa_b.pdf"' in prompt
        assert "ninety (90) days" in prompt and "thirty (30) days" in prompt

    def test_the_planner_is_told_which_documents_are_being_compared(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        run(llm, [DOC_A, DOC_B])

        planner_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[0]
        assert 'D1 = "msa_a.pdf"' in planner_prompt and 'D2 = "msa_b.pdf"' in planner_prompt

    def test_coverage_reports_how_each_document_did(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        coverage = done_of(run(llm, [DOC_A, DOC_B]))["coverage"]

        assert [(d["document_id"], d["evidence"]) for d in coverage["documents"]] == [("aaaa", "sufficient"), ("bbbb", "sufficient")]
        assert coverage["pages"] == 6

    def test_a_long_document_cannot_crowd_a_short_one_out_of_the_results(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("termination terminate notice")],
            grades=[judge({"D1": 2, "D2": 2}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", None, NINETY), ("D2", None, THIRTY)]),
        )
        run(llm, [BIG_A, BIG_B], candidates_per_document=3)

        grade_prompt = llm.prompts_for(prompts_multi.GRADE_MULTI_SYSTEM)[0]
        d2_block = grade_prompt.split('=== D2: "big_b.pdf" ===')[1]
        assert "thirty (30) days" in d2_block


class TestPerDocumentSufficiency:
    def test_only_the_documents_still_short_are_searched_again(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate notice"), plan("notice period deliveries")],
            grades=[
                judge({"D1": 2, "D2": {}}, {"D1": True, "D2": False}, {"D2": "the notice period for termination"}),
                judge({"D2": 2}, {"D2": True}),
            ],
            answer_for=comparison([("D1", None, NINETY)]),
        )
        events = run(llm, [BIG_A, BIG_B], candidates_per_document=3)

        first, second = llm.prompts_for(prompts_multi.GRADE_MULTI_SYSTEM)
        assert "=== D1" in first and "=== D2" in first
        assert "=== D1" not in second and "=== D2" in second
        refine_prompt = llm.prompts_for(prompts.QUERY_SYSTEM)[1]
        assert "the notice period for termination" in refine_prompt
        assert done_of(events)["coverage"]["rounds"] == 2

    def test_a_document_that_cannot_answer_is_reported_not_silently_dropped(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate notice"), plan("notice period")],
            grades=[judge({"D1": {1: 2}}, {"D1": True, "D2": False}, {"D2": "a termination clause"})] * 2,
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        events = run(llm, [DOC_A, DOC_C])

        assert done_of(events)["quality"] == "partial"
        assert [d["evidence"] for d in done_of(events)["coverage"]["documents"]] == ["sufficient", "none"]
        assert 'No relevant passage was found in: D2 "services.pdf"' in llm.stream_calls[0]
        assert "INCOMPLETE" not in llm.stream_calls[0] and "incomplete" in llm.stream_calls[0].lower()

    def test_when_no_document_has_anything_relevant_the_app_says_so_and_does_not_guess(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("arbitration"), plan("dispute forum"), plan("tribunal")],
            grades=[judge({}, {"D1": False, "D2": False}, {"D1": "arbitration", "D2": "arbitration"})] * 3,
            answer="MUST NOT BE USED",
        )
        events = run(llm, [DOC_A, DOC_B], question="How do the arbitration clauses compare?")
        message = text_of(events)

        assert llm.stream_calls == []
        assert done_of(events)["quality"] == "insufficient"
        assert "any of these 2 documents" in message and "not proof" in message
        assert "does not contain" not in message
        assert citations_of(events) == []
        assert {d["evidence"] for d in done_of(events)["coverage"]["documents"]} == {"none"}

    def test_a_judge_that_says_sufficient_without_a_strong_passage_is_not_believed(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("x")] * 3,
            grades=[judge({}, {"D1": True, "D2": True})] * 3,
        )
        assert done_of(run(llm, [DOC_A, DOC_B]))["quality"] == "insufficient"

    def test_a_single_verdict_is_applied_to_every_document(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, True)],
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        assert done_of(run(llm, [DOC_A, DOC_B]))["quality"] == "sufficient"

    def test_document_labels_in_the_verdict_are_matched_ignoring_case(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"d1": True, "d2": True})],
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        assert done_of(run(llm, [DOC_A, DOC_B]))["quality"] == "sufficient"

    def test_the_round_cap_is_a_hard_limit(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("q one"), plan("q two"), plan("q three")],
            grades=[judge({"D1": {}}, {"D1": False, "D2": False})] * 3,
        )
        events = run(llm, [BIG_A, BIG_B], max_retrieval_rounds=2, candidates_per_document=3)

        assert llm.count(prompts_multi.GRADE_MULTI_SYSTEM) == 2
        assert done_of(events)["coverage"]["rounds"] == 2


class TestEachQuoteIsCheckedAgainstItsOwnDocument:
    def scripted(self, answer):
        return ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2, 3: 2}, "D2": {1: 2, 3: 2}}, {"D1": True, "D2": True})],
            answer_for=answer,
        )

    def test_a_quote_that_exists_only_in_another_document_is_not_verified(self, db):
        # The sentence is genuinely in document A, but the answer credits it to document B.
        llm = self.scripted(comparison([("D2", 1, NINETY)]))
        citation = citations_of(run(llm, [DOC_A, DOC_B]))[0]

        assert citation["verified"] is False
        assert citation["document_id"] == "bbbb"
        assert citation["matches"] == []

    def test_the_same_quote_credited_to_its_real_document_is_verified(self, db):
        llm = self.scripted(comparison([("D1", 1, NINETY)]))
        assert citations_of(run(llm, [DOC_A, DOC_B]))[0]["verified"] is True

    def test_a_disagreement_between_the_named_document_and_the_evidence_passage_is_unverified(self, db):
        # The evidence label points at a D1 passage but the entry says D2: the attribution is inconsistent.
        llm = self.scripted(comparison([("D1", 1, NINETY)], overrides={1: {"document": "D2"}}))
        citation = citations_of(run(llm, [DOC_A, DOC_B]))[0]

        assert citation["verified"] is False

    def test_identical_wording_in_two_documents_is_verified_in_each_separately(self, db):
        llm = self.scripted(comparison([("D1", 3, GOVERNING_LAW), ("D2", 3, GOVERNING_LAW)]))
        first, second = citations_of(run(llm, [DOC_A, DOC_B]))

        assert first["verified"] and second["verified"]
        assert (first["document_id"], second["document_id"]) == ("aaaa", "bbbb")
        assert first["occurrences"] == 1 and second["occurrences"] == 1

    def test_an_invented_quote_is_unverified_whatever_document_it_names(self, db):
        llm = self.scripted(comparison([("D1", 1, "Either party may terminate at any time without notice.")]))
        assert citations_of(run(llm, [DOC_A, DOC_B]))[0]["verified"] is False

    def test_a_quote_naming_an_unknown_document_is_unverified(self, db):
        entries = lambda prompt: (
            "Answer [1].\n" + prompts.QUOTES_MARKER + "\n" + json.dumps([{"n": 1, "document": "D9", "quote": NINETY}])
        )
        citation = citations_of(run(self.scripted(entries), [DOC_A, DOC_B]))[0]

        assert citation["verified"] is False and citation["document_id"] is None

    def test_a_quote_with_only_a_document_label_is_checked_in_that_document(self, db):
        entries = lambda prompt: (
            "Answer [1] [2].\n"
            + prompts.QUOTES_MARKER
            + "\n"
            + json.dumps([{"n": 1, "document": "D1", "quote": NINETY}, {"n": 2, "document": "D1", "quote": THIRTY}])
        )
        first, second = citations_of(run(self.scripted(entries), [DOC_A, DOC_B]))

        assert first["verified"] is True
        assert second["verified"] is False  # the thirty-day wording is in D2, not D1

    def test_a_citation_marker_with_no_quote_is_unverified(self, db):
        answer = lambda prompt: "A [1] and B [2].\n" + prompts.QUOTES_MARKER + "\n" + json.dumps(
            [{"n": 1, "document": "D1", "evidence": evidence_label(prompt, "D1", 1), "quote": NINETY}]
        )
        citations = citations_of(run(self.scripted(answer), [DOC_A, DOC_B]))

        assert [(c["n"], c["verified"]) for c in citations] == [(1, True), (2, False)]


class TestOtherBehaviour:
    def test_off_topic_messages_do_no_retrieval(self, db):
        llm = ScriptedMultiGrader(plans=[plan(intent="off_topic")])
        events = run(llm, [DOC_A, DOC_B], question="hello")

        assert llm.count(prompts_multi.GRADE_MULTI_SYSTEM) == 0 and llm.stream_calls == []
        assert done_of(events)["quality"] == "not_applicable"

    def test_neighbouring_text_is_added_per_document_and_marked_as_context(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY)]),
        )
        run(llm, [DOC_A, DOC_B], neighbor_chunks=1)
        prompt = llm.stream_calls[0]

        assert prompt.count("(context)") >= 2
        assert "AED 100,000" in prompt and "AED 1,000,000" in prompt

    def test_a_provider_failure_while_writing_propagates_for_the_caller_to_report(self, db):
        llm = ScriptedMultiGrader(
            plans=[plan("terminate")],
            grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
            answer_for=comparison([("D1", 1, NINETY)]),
            fail_stream_after=1,
        )
        with pytest.raises(LLMError):
            run(llm, [DOC_A, DOC_B])

    def test_the_quotes_marker_never_leaks_into_the_streamed_text(self, db):
        for size in (1, 3, 7):
            llm = ScriptedMultiGrader(
                plans=[plan("terminate")],
                grades=[judge({"D1": {1: 2}, "D2": {1: 2}}, {"D1": True, "D2": True})],
                answer_for=comparison([("D1", 1, NINETY)]),
                stream_size=size,
            )
            streamed = text_of(run(llm, [DOC_A, DOC_B]))
            assert "<<<" not in streamed and "QUOTES" not in streamed

    def test_invalid_judge_output_is_reported_as_an_error(self, db):
        llm = FakeLLM(plans=[plan("terminate")], grades=[{"grades": [{"id": 1, "score": 9}], "sufficient": {}}])
        with pytest.raises(LLMError):
            run(llm, [DOC_A, DOC_B])
