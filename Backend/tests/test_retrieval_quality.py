import asyncio
import sqlite3
from types import SimpleNamespace

import httpx
import openai
import pytest

from app import repository
from app.config import Settings, get_settings
from app.db import INDEX_VERSION, connect, init_db
from app.rag import prompts
from app.rag.chunking import detect_heading
from app.rag.index import Chunk, DocumentIndex, store_chunks, tokenize
from app.rag.llm import OpenAIClient

from .fakes import ScriptedGrader
from .test_agent import (
    DOCUMENT_ID,
    PAGES,
    db,  # noqa: F401  (fixture)
    good_answer,
    grading_for_page,
    plan,
    run,
)


def index_of(*texts: str, contexts: tuple[str, ...] = ()) -> DocumentIndex:
    chunks = [
        Chunk(i, i, 1, text, contexts[i] if i < len(contexts) else "") for i, text in enumerate(texts, start=1)
    ]
    return DocumentIndex(chunks, None)


class TestKeywordSearch:
    def test_word_forms_match_each_other(self):
        assert tokenize("terminate") == tokenize("termination") == tokenize("terminated")

    def test_a_search_for_terminate_finds_a_clause_that_only_says_termination(self):
        index = index_of(
            "Payment is due within thirty days of the invoice date.",
            "Termination requires ninety days written notice to the other party.",
            "The Supplier shall deliver the goods to the Customer's premises.",
        )
        hits = index.search(["terminate"], None, 3)

        assert hits[0].chunk.id == 2

    def test_filler_words_do_not_drive_the_ranking(self):
        assert "the" not in tokenize("the Supplier shall and will")
        assert tokenize("AED 100,000") == ["aed", "100,000"]

    def test_a_clause_is_found_by_its_section_heading_even_when_its_text_never_says_it(self):
        filler = [f"Clause {n} sets out an unrelated operational obligation for the Supplier." for n in range(8)]
        index = index_of(
            "This Agreement shall be construed in accordance with the laws of England and Wales.",
            "Payment is due within thirty days of the invoice date.",
            *filler,
            contexts=("20. Governing Law", "5. Payment"),
        )
        hits = index.search(["governing law"], None, 3)

        assert hits[0].chunk.id == 1

    def test_a_document_smaller_than_the_candidate_window_is_returned_whole(self):
        index = index_of("Alpha clause text here.", "Beta clause text here.", "Gamma clause text here.")
        hits = index.search(["zebra"], None, 10)

        assert sorted(hit.chunk.id for hit in hits) == [1, 2, 3]

    def test_chunks_without_a_query_term_are_not_treated_as_keyword_matches(self):
        filler = [f"Unrelated paragraph number {n} about deliveries and premises." for n in range(12)]
        index = index_of("Arbitration shall be held in London.", *filler)
        hits = index.search(["arbitration"], None, 5)

        assert [hit.chunk.id for hit in hits] == [1]


class TestHeadingDetection:
    @pytest.mark.parametrize(
        "line",
        ["12. Termination", "12.1 Termination for convenience", "TERMINATION", "Article 5 Payment", "Schedule 2"],
    )
    def test_headings(self, line):
        assert detect_heading(line) == line

    @pytest.mark.parametrize(
        "line",
        [
            "12.1 The Supplier shall deliver the goods within thirty days.",
            "This Agreement is governed by English law.",
            "Either party may terminate on notice",
            "a",
            "",
        ],
    )
    def test_body_text_is_not_a_heading(self, line):
        assert detect_heading(line) is None


class TestAgentRetrievalImprovements:
    def test_the_users_whole_question_is_searched_as_well_as_the_planned_queries(self, db):  # noqa: F811
        llm = ScriptedGrader(
            plans=[{"intent": "document_question", "queries": ["termination"], "standalone_question": "Can either party leave early?"}],
            grades=[grading_for_page(2)],
            answer=good_answer(),
        )
        run(llm, question="Can either party leave early?")

        assert "Can either party leave early?" in llm.embedded_texts

    def test_neighbouring_text_is_added_around_a_strong_passage_and_marked_as_context(self, db):  # noqa: F811
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        run(llm, neighbor_chunks=1)
        prompt = llm.stream_calls[0]

        assert "ninety (90) days" in prompt
        assert "Northwind Trading" in prompt  # page 1, the chunk before
        assert "AED 100,000" in prompt  # page 3, the chunk after
        assert prompt.count("(context)") == 2

    def test_neighbours_can_be_switched_off(self, db):  # noqa: F811
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        run(llm, neighbor_chunks=0)

        assert "(context)" not in llm.stream_calls[0]

    def test_a_quote_taken_from_neighbouring_text_still_verifies(self, db):  # noqa: F811
        answer = good_answer("aggregate liability under this Agreement shall not exceed AED 100,000")
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=answer)
        events = run(llm, neighbor_chunks=1)
        citation = next(e["data"] for e in events if e["event"] == "citations")[0]

        assert citation["verified"] is True and citation["page"] == 3

    def test_the_judge_sees_the_section_heading(self, db):  # noqa: F811
        pages = [(1, "12. Termination\n\nEither party may terminate on ninety days written notice.")]
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(1)], answer=good_answer())
        run(llm, pages=pages)

        assert "Section: 12. Termination" in llm.prompts_for(prompts.GRADE_SYSTEM)[0]


class TestTemperatures:
    def test_each_stage_uses_its_own_configured_temperature(self, db):  # noqa: F811
        llm = ScriptedGrader(plans=[plan("terminate")], grades=[grading_for_page(2)], answer=good_answer())
        run(llm, temperature_plan=0.7, temperature_judge=0.0, temperature_answer=0.9)

        used = dict(llm.temperatures)
        assert used[prompts.QUERY_SYSTEM] == 0.7
        assert used[prompts.GRADE_SYSTEM] == 0.0
        assert used[prompts.ANSWER_SYSTEM] == 0.9

    def test_defaults_give_the_answer_some_freedom_and_keep_the_judge_steady(self):
        settings = Settings()
        assert settings.temperature_answer > settings.temperature_judge
        assert settings.temperature_answer >= 0.3
        assert settings.temperature_judge <= 0.2


class TestPrompts:
    def test_the_answer_prompt_allows_a_labelled_explanation_but_keeps_facts_to_the_evidence(self):
        text = prompts.ANSWER_SYSTEM
        assert prompts.EXPLANATION_LABEL in text
        assert "ONLY from" in " ".join(text.split())
        assert "no citations" in text

    def test_the_judge_is_fair_not_strict(self):
        assert "strict" not in prompts.GRADE_SYSTEM.lower()
        assert "Short standard clauses" in prompts.GRADE_SYSTEM


def make_client(responses: list) -> tuple[OpenAIClient, list[dict]]:
    """An OpenAIClient whose network layer is replaced by scripted responses or errors."""
    calls: list[dict] = []
    client = OpenAIClient(Settings(openai_api_key="test"))

    async def create(**kwargs):
        calls.append(kwargs)
        outcome = responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


def json_reply(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def temperature_rejection() -> openai.BadRequestError:
    response = httpx.Response(400, request=httpx.Request("POST", "http://x"))
    return openai.BadRequestError(
        "Unsupported value: 'temperature' does not support 0.1 with this model. Only the default (1) is supported.",
        response=response,
        body=None,
    )


class TestTemperatureFallback:
    def test_the_temperature_is_sent_when_the_model_accepts_it(self):
        client, calls = make_client([json_reply('{"ok": true}')])
        asyncio.run(client.json_completion("s", "u", temperature=0.3))

        assert calls[0]["temperature"] == 0.3

    def test_a_model_that_rejects_the_temperature_is_retried_without_it_and_remembered(self):
        client, calls = make_client([temperature_rejection(), json_reply('{"ok": true}'), json_reply('{"ok": true}')])

        assert asyncio.run(client.json_completion("s", "u", temperature=0.1)) == {"ok": True}
        assert "temperature" in calls[0] and "temperature" not in calls[1]

        asyncio.run(client.json_completion("s", "u", temperature=0.1))
        assert "temperature" not in calls[2]  # not retried again

    def test_other_bad_requests_are_not_swallowed(self):
        response = httpx.Response(400, request=httpx.Request("POST", "http://x"))
        error = openai.BadRequestError("context length exceeded", response=response, body=None)
        client, _ = make_client([error])

        with pytest.raises(Exception):
            asyncio.run(client.json_completion("s", "u", temperature=0.3))


class TestIndexMigration:
    def test_an_index_from_an_older_version_is_discarded_and_rebuilt_with_the_new_columns(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        get_settings.cache_clear()
        init_db()
        repository.create_document(DOCUMENT_ID, "msa.pdf", "pdf", 10)
        with connect() as connection:
            connection.execute("DROP TABLE chunks")
            connection.execute(
                "CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT, ordinal INTEGER, "
                "page_number INTEGER, text TEXT, embedding BLOB)"
            )
            connection.execute("INSERT INTO chunks (document_id, ordinal, page_number, text) VALUES ('x', 0, 1, 'old')")
            connection.execute("PRAGMA user_version = 1")

        init_db()

        with connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
            columns = [row[1] for row in connection.execute("PRAGMA table_info(chunks)")]
            assert "context" in columns
            assert connection.execute("PRAGMA user_version").fetchone()[0] == INDEX_VERSION
        get_settings.cache_clear()

    def test_documents_and_conversations_survive_an_index_upgrade(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        get_settings.cache_clear()
        init_db()
        repository.create_document(DOCUMENT_ID, "msa.pdf", "pdf", 10)
        with connect() as connection:
            connection.execute("PRAGMA user_version = 1")

        init_db()

        assert repository.get_summary(DOCUMENT_ID) is not None
        get_settings.cache_clear()
