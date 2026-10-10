"""The assistant answers about any uploaded document, not only legal contracts."""

import asyncio

from app import chat_repository, conversation_repository, repository
from app.config import get_settings
from app.db import init_db
from app.rag import prompts, prompts_multi, prompts_research
from app.rag.agent import OFF_TOPIC_REPLY
from app.rag.quote_repair import missing_numbers, parse_quotes, repair_missing_quotes

from .fakes import FakeLLM

SLIDES = [
    (1, "CS3002 Week 3  Malware\nLecture slides"),
    (2, "  \n"),
    (3, "Worms self-replicate and spread across networks without user action."),
]


class TestPromptsAreNotAboutOneKindOfDocument:
    def test_no_prompt_tells_the_model_the_document_is_a_contract(self):
        for text in (prompts.QUERY_SYSTEM, prompts.GRADE_SYSTEM, prompts.ANSWER_SYSTEM, prompts_research.RESEARCH_SYSTEM):
            assert "legal contract" not in text
            assert "ONE uploaded contract" not in text
        assert "legal contracts" not in prompts_multi.ANSWER_MULTI_SYSTEM

    def test_only_greetings_and_small_talk_may_be_off_topic(self):
        assert "ONLY for a greeting" in prompts.QUERY_SYSTEM
        assert "single term" in prompts.QUERY_SYSTEM
        assert "ONLY for a greeting" in prompts_research.RESEARCH_SYSTEM

    def test_the_refusal_does_not_ask_for_a_clause_or_a_party(self):
        assert "clause" not in OFF_TOPIC_REPLY and "party" not in OFF_TOPIC_REPLY


class TestDocumentOverview:
    def test_it_names_the_document_and_quotes_how_it_begins(self):
        note = prompts.build_document_note("CS3002_Week_3.pdf", SLIDES)

        assert "CS3002_Week_3.pdf" in note
        assert "CS3002 Week 3 Malware Lecture slides" in note

    def test_it_skips_blank_opening_pages_and_is_short(self):
        note = prompts.build_document_note("deck.pdf", [(1, "   "), (2, "x" * 5000)], chars=100)

        assert note.count("x") == 100


class TestQuoteRepairHelpers:
    def test_missing_numbers_ignores_numbers_that_already_have_a_quote(self):
        raw = '[{"n": 1, "evidence": "E1", "quote": "a"}, {"n": 2, "evidence": "E1", "quote": ""}]'

        assert missing_numbers("A [1]. B [2]. C [3].", raw) == [2, 3]

    def test_broken_json_means_every_cited_number_is_missing(self):
        assert missing_numbers("A [1] and B [2].", "not json") == [1, 2]
        assert parse_quotes("not json") == []

    def test_nothing_is_asked_when_nothing_is_missing(self):
        llm = FakeLLM()
        raw = '[{"n": 1, "evidence": "E1", "quote": "a"}]'
        result = asyncio.run(repair_missing_quotes(llm, get_settings(), "A [1].", raw, [("E1", "page 1", "a b")]))

        assert result == raw and llm.json_calls == []

    def test_added_entries_replace_empty_ones_instead_of_sitting_beside_them(self):
        llm = FakeLLM(repairs=[{"quotes": [{"n": 2, "evidence": "E1", "quote": "spread across networks"}]}])
        raw = '[{"n": 1, "evidence": "E1", "quote": "Worms"}, {"n": 2, "evidence": "E1", "quote": ""}]'
        result = asyncio.run(
            repair_missing_quotes(llm, get_settings(), "A [1]. B [2].", raw, [("E1", "page 3", "Worms spread across networks")])
        )

        assert [(q["n"], q["quote"]) for q in parse_quotes(result)] == [(1, "Worms"), (2, "spread across networks")]


class TestRefusalsAreLeftOutOfHistory:
    def seed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        get_settings.cache_clear()
        init_db()
        repository.create_document("doc-1", "deck.pdf", "pdf", 10)
        return conversation_repository.ensure_single("doc-1")

    def add(self, conversation_id, role, content, quality=None):
        if role == "user":
            chat_repository.add_user_message(conversation_id, content)
            return
        chat_repository.add_assistant_message(
            conversation_id, content=content, status="complete", quality=quality, citations=[], trace=[], coverage=None
        )

    def test_a_refused_turn_and_its_question_are_not_shown_to_the_model_again(self, tmp_path, monkeypatch):
        conversation_id = self.seed(tmp_path, monkeypatch)
        self.add(conversation_id, "user", "how malware spreads")
        self.add(conversation_id, "assistant", OFF_TOPIC_REPLY, "not_applicable")
        self.add(conversation_id, "user", "what is a worm?")
        self.add(conversation_id, "assistant", "A worm self-replicates [1].", "sufficient")

        history = chat_repository.recent_history(conversation_id, 8)

        assert history == [("user", "what is a worm?"), ("assistant", "A worm self-replicates [1].")]
        get_settings.cache_clear()

    def test_refusals_do_not_use_up_the_memory_window(self, tmp_path, monkeypatch):
        conversation_id = self.seed(tmp_path, monkeypatch)
        self.add(conversation_id, "user", "real question")
        self.add(conversation_id, "assistant", "real answer", "sufficient")
        for _ in range(5):
            self.add(conversation_id, "user", "hello?")
            self.add(conversation_id, "assistant", OFF_TOPIC_REPLY, "not_applicable")

        history = chat_repository.recent_history(conversation_id, 2)

        assert history == [("user", "real question"), ("assistant", "real answer")]
        get_settings.cache_clear()


class TestEdgePunctuationIsNotEvidence:
    SLIDE = [(7, "7 There is no universally best interaction style\n\u2014 only better and worse fits.")]

    def test_a_full_stop_the_model_added_does_not_make_a_real_quote_unverified(self):
        from app.rag.quotes import DocumentText

        document = DocumentText(self.SLIDE)

        assert document.find_quote("There is no universally best interaction style.") is not None
        assert document.find_quote("There is no universally best interaction style") is not None

    def test_it_does_not_loosen_anything_inside_the_quote(self):
        from app.rag.quotes import DocumentText

        document = DocumentText(self.SLIDE)

        assert document.find_quote("There is no universally best, interaction style.") is None
        assert document.find_quote("There is never a universally best interaction style.") is None


class TestQuotationMarkStyleIsNotEvidence:
    SLIDE = [(6, "Threat: a possible danger (e.g., \u201ca hacker might attack\u201d)\nRisk: the chance of harm")]

    def test_a_phrase_in_double_quotes_can_be_copied_in_single_quotes(self):
        from app.rag.quotes import DocumentText

        document = DocumentText(self.SLIDE)

        assert document.find_quote("a possible danger (e.g., 'a hacker might attack')") is not None
        assert document.find_quote('a possible danger (e.g., "a hacker might attack")') is not None

    def test_a_changed_word_is_still_not_found(self):
        from app.rag.quotes import DocumentText

        document = DocumentText(self.SLIDE)

        assert document.find_quote("a possible danger (e.g., 'a hacker will attack')") is None
