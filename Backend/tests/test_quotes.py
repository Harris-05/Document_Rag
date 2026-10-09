from app.rag.quotes import DocumentText, PageRange, normalize_for_match


def doc(*pages: str) -> DocumentText:
    return DocumentText([(number, text) for number, text in enumerate(pages, start=1)])


def highlighted(document: DocumentText, match) -> list[str]:
    """The original text covered by each returned range, so tests read naturally."""
    texts = dict(document.pages)
    return [texts[r.page][r.start : r.end] for r in match.ranges]


class TestExactAndWhitespace:
    def test_finds_an_exact_quote_and_reports_original_offsets(self):
        sentence = "The Supplier shall indemnify the Customer."
        document = doc(f"Clause 1. {sentence}")
        match = document.find_quote(sentence)

        assert match is not None
        start = len("Clause 1. ")
        assert match.ranges == [PageRange(1, start, start + len(sentence))]
        assert highlighted(document, match) == ["The Supplier shall indemnify the Customer."]

    def test_tolerates_line_breaks_and_extra_spaces_in_the_document(self):
        document = doc("The Supplier   shall\nindemnify\n  the Customer\nagainst all losses.")
        match = document.find_quote("The Supplier shall indemnify the Customer against all losses.")

        assert match is not None
        assert highlighted(document, match)[0].startswith("The Supplier")
        assert highlighted(document, match)[0].endswith("all losses.")

    def test_tolerates_whitespace_differences_in_the_quote(self):
        document = doc("Payment is due within thirty (30) days of invoice.")
        assert document.find_quote("Payment is due   within thirty (30)\ndays of invoice.") is not None

    def test_is_case_insensitive(self):
        document = doc("GOVERNING LAW. This Agreement is governed by the laws of England.")
        assert document.find_quote("this agreement is governed by the laws of england") is not None


class TestTypographicNoise:
    def test_curly_quotes_and_apostrophes(self):
        document = doc("The Supplier’s liability is limited. The “Services” are defined below.")
        assert document.find_quote("The Supplier's liability is limited.") is not None
        assert document.find_quote('The "Services" are defined below.') is not None

    def test_dashes(self):
        document = doc("Term: 12–18 months — renewable by mutual agreement.")
        assert document.find_quote("Term: 12-18 months - renewable by mutual agreement.") is not None

    def test_ligatures_and_non_breaking_spaces(self):
        document = doc("The oﬃce of the Customer shall be notified in writing.")
        assert document.find_quote("The office of the Customer shall be notified in writing.") is not None

    def test_zero_width_and_soft_hyphen_characters_are_ignored(self):
        document = doc("The Supp​lier shall indem­nify the Customer.")
        assert document.find_quote("The Supplier shall indemnify the Customer.") is not None


class TestHyphenation:
    def test_word_hyphenated_across_a_line_break(self):
        document = doc("The Supplier shall indem-\nnify the Customer against all losses.")
        match = document.find_quote("The Supplier shall indemnify the Customer against all losses.")

        assert match is not None
        assert match.method == "dehyphenated"

    def test_a_genuine_hyphenated_word_still_matches_as_written(self):
        document = doc("The pre-existing conditions are excluded from this Agreement.")
        match = document.find_quote("The pre-existing conditions are excluded from this Agreement.")

        assert match is not None
        assert match.method == "exact"


class TestPageBreaks:
    def test_quote_spanning_two_pages_gets_a_range_on_each(self):
        document = doc(
            "Introduction.\nThe Supplier shall deliver the goods and",
            "services within thirty days of the Effective Date.",
        )
        match = document.find_quote(
            "The Supplier shall deliver the goods and services within thirty days of the Effective Date."
        )

        assert match is not None
        assert [r.page for r in match.ranges] == [1, 2]
        assert highlighted(document, match) == [
            "The Supplier shall deliver the goods and",
            "services within thirty days of the Effective Date.",
        ]


class TestMultipleOccurrences:
    def test_counts_occurrences_and_prefers_the_hinted_page(self):
        text = "Either party may terminate this Agreement on written notice."
        document = doc(text, "Filler page.", text)

        unhinted = document.find_quote(text)
        hinted = document.find_quote(text, hint_pages={3})

        assert unhinted is not None and unhinted.occurrences == 2
        assert unhinted.first_page == 1
        assert hinted is not None and hinted.first_page == 3

    def test_a_hint_never_verifies_a_missing_quote(self):
        document = doc("Page one text about payment terms.", "Page two text about delivery.")
        assert document.find_quote("a clause that is nowhere in the document", hint_pages={2}) is None


class TestEllipsis:
    def test_segments_around_an_ellipsis_must_each_appear_in_order(self):
        document = doc(
            "The Supplier shall indemnify the Customer against all losses, damages and expenses "
            "arising from any breach of this Agreement."
        )
        match = document.find_quote("The Supplier shall indemnify the Customer ... arising from any breach of this Agreement.")

        assert match is not None
        assert len(match.ranges) == 2

    def test_segments_in_the_wrong_order_are_rejected(self):
        document = doc("First the notice period applies. Then the penalty applies afterwards.")
        assert document.find_quote("the penalty applies afterwards ... the notice period applies") is None


class TestRejection:
    def test_paraphrase_is_rejected(self):
        document = doc("The Supplier shall indemnify the Customer against all losses.")
        assert document.find_quote("The Supplier must compensate the Customer for every loss.") is None

    def test_a_single_changed_word_is_rejected(self):
        document = doc("Liability is capped at AED 100,000 per claim.")
        assert document.find_quote("Liability is capped at AED 1,000,000 per claim.") is None

    def test_too_short_quotes_are_not_accepted(self):
        document = doc("Payment within 30 days.")
        assert document.find_quote("30 days") is None
        assert document.find_quote("") is None
        assert document.find_quote("   ") is None

    def test_short_segments_around_an_ellipsis_are_rejected(self):
        document = doc("The Supplier shall indemnify the Customer and the Customer shall pay.")
        assert document.find_quote("The Supplier shall ... pay.") is None


class TestNormalization:
    def test_normalize_collapses_whitespace_and_folds_case(self):
        assert normalize_for_match("  Hello\n\n  “WORLD”  ") == 'hello "world"'


class TestEveryOccurrence:
    def test_all_occurrences_are_returned_in_document_order(self):
        text = "Either party may terminate this Agreement on written notice."
        document = doc(text, "Filler page.", text, text)
        match = document.find_quote(text)

        assert match is not None
        assert match.occurrences == 3
        assert [m[0].page for m in match.matches] == [1, 3, 4]

    def test_the_primary_match_follows_the_hint_but_the_list_stays_in_order(self):
        text = "Either party may terminate this Agreement on written notice."
        document = doc(text, "Filler page.", text)
        match = document.find_quote(text, hint_pages={3})

        assert match is not None
        assert match.primary_index == 1
        assert match.ranges[0].page == 3
        assert [m[0].page for m in match.matches] == [1, 3]

    def test_a_multi_page_quote_that_repeats_keeps_each_occurrence_whole(self):
        document = doc(
            "The Supplier shall deliver the goods and",
            "services within thirty days of the Effective Date.",
            "The Supplier shall deliver the goods and",
            "services within thirty days of the Effective Date.",
        )
        match = document.find_quote(
            "The Supplier shall deliver the goods and services within thirty days of the Effective Date."
        )

        assert match is not None
        assert [[r.page for r in m] for m in match.matches] == [[1, 2], [3, 4]]

    def test_a_single_occurrence_has_a_single_match(self):
        match = doc("Payment is due within thirty days.").find_quote("Payment is due within thirty days.")
        assert match is not None and match.occurrences == 1 and match.primary_index == 0
