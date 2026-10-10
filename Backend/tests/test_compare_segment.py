from app.compare.segment import segment

TERMINATION = "Either party may terminate this Agreement for convenience by giving ninety (90) days written notice."


def texts(units):
    return [unit.text for unit in units]


class TestSplittingIntoClauses:
    def test_a_heading_is_kept_with_the_paragraph_below_it(self):
        units = segment([(1, f"12. Termination\n\n{TERMINATION}")])

        assert len(units) == 1
        assert units[0].heading == "12. Termination"
        assert units[0].text.startswith("12. Termination Either party")

    def test_blank_lines_separate_paragraphs(self):
        units = segment([(1, "The Supplier shall deliver the goods on time.\n\nThe Customer shall pay each invoice promptly.")])
        assert len(units) == 2

    def test_a_new_numbered_clause_starts_a_new_unit_even_without_a_blank_line(self):
        page = "1.1 The Supplier shall deliver the goods.\n1.2 The Customer shall pay the invoice.\n(a) within thirty days."
        units = segment([(1, page)])

        assert [u.text for u in units] == [
            "1.1 The Supplier shall deliver the goods.",
            "1.2 The Customer shall pay the invoice.",
            "(a) within thirty days.",
        ]

    def test_wrapped_lines_of_one_paragraph_are_joined_with_single_spaces(self):
        units = segment([(1, "The Supplier shall indemnify the Customer\nagainst all losses arising\nfrom any breach.")])
        assert texts(units) == ["The Supplier shall indemnify the Customer against all losses arising from any breach."]

    def test_a_wrapped_line_that_begins_with_a_number_does_not_start_a_clause(self):
        units = segment([(1, "Either party may terminate on\n90 days written notice to the other party.")])
        assert len(units) == 1

    def test_one_word_scraps_are_ignored(self):
        assert segment([(1, "Signature\n\nThe parties agree to be bound by this Agreement in full.")])[0].text.startswith("The parties")


class TestPagePositions:
    def test_each_unit_remembers_where_it_came_from_on_the_page(self):
        page = f"Intro paragraph about the supplier and the customer.\n\n{TERMINATION}"
        unit = segment([(3, page)])[1]

        span = unit.spans[0]
        assert span.page == 3
        assert page[span.start : span.end] == TERMINATION

    def test_a_heading_and_its_paragraph_share_one_span(self):
        page = f"12. Termination\n\n{TERMINATION}"
        span = segment([(1, page)])[0].spans[0]
        assert page[span.start : span.end] == page

    def test_a_clause_that_continues_on_the_next_page_is_one_unit_with_two_spans(self):
        pages = [
            (1, "Either party may terminate this Agreement for convenience by giving not less than ninety (90)"),
            (2, "days written notice, provided that all sums then due have been paid."),
        ]
        units = segment(pages)

        assert len(units) == 1
        assert [s.page for s in units[0].spans] == [1, 2]
        assert "ninety (90) days written notice" in units[0].text

    def test_a_sentence_that_ends_at_the_page_break_is_not_joined_to_the_next_page(self):
        pages = [(1, "The Supplier shall deliver the goods."), (2, "The Customer shall pay the invoice.")]
        assert len(segment(pages)) == 2

    def test_a_new_clause_on_the_next_page_is_never_joined(self):
        pages = [(1, "The Supplier shall deliver the goods and"), (2, "2.1 The Customer shall pay the invoice.")]
        assert len(segment(pages)) == 2


class TestRunningHeadersAndFooters:
    def test_a_header_repeated_on_every_page_is_not_a_unit(self):
        pages = [(n, f"ACME MASTER AGREEMENT\n\nClause {n}. The parties record obligation number {n} in full.\n\n{n}") for n in range(1, 5)]
        units = segment(pages)

        assert len(units) == 4
        assert all("ACME MASTER AGREEMENT" not in unit.text for unit in units)

    def test_page_numbers_are_dropped(self):
        units = segment([(1, "The Supplier shall deliver the goods on time.\n\nPage 1 of 9"), (2, "Page 2 of 9")])
        assert texts(units) == ["The Supplier shall deliver the goods on time."]

    def test_a_real_heading_that_appears_only_once_is_kept(self):
        pages = [(n, f"Filler paragraph number {n} with several words in it.") for n in range(1, 5)]
        pages[1] = (2, "GOVERNING LAW\n\nThis Agreement is governed by English law and the courts of England.")
        assert any(unit.heading == "GOVERNING LAW" for unit in segment(pages))


def test_unit_indexes_follow_reading_order():
    units = segment([(1, "First paragraph of the contract text.\n\nSecond paragraph of the contract text.\n\nThird paragraph of the contract text.")])
    assert [u.index for u in units] == [0, 1, 2]


class TestHeadingsWithoutABlankLine:
    def test_a_heading_directly_above_its_paragraph_becomes_the_units_heading(self):
        page = f"6. Intellectual Property\n{TERMINATION}"
        units = segment([(1, page)])

        assert len(units) == 1
        assert units[0].heading == "6. Intellectual Property"
        assert units[0].text.startswith("6. Intellectual Property Either party")

    def test_the_first_line_of_a_wrapped_sentence_is_not_mistaken_for_a_heading(self):
        page = "1.1 The Supplier shall provide the consulting services\ndescribed in Schedule 1 to this Agreement."
        units = segment([(1, page)])

        assert len(units) == 1
        assert units[0].heading == ""

    def test_a_short_wrapped_first_line_with_a_verb_is_still_body_text(self):
        page = "2.1 The Customer shall pay\nthe invoice within thirty (30) days."
        assert segment([(1, page)])[0].heading == ""

    def test_the_heading_keeps_its_own_position_in_the_page(self):
        page = f"6. Intellectual Property\n{TERMINATION}"
        span = segment([(1, page)])[0].spans[0]
        assert page[span.start : span.end] == page


class TestHeadingsWithNothingBeneathThem:
    def test_a_document_title_above_the_first_section_is_not_a_unit(self):
        page = "MASTER SERVICES AGREEMENT (VERSION 1)\n\n1. Services\n\nThe Supplier shall provide the consulting services described in Schedule 1."
        units = segment([(1, page)])

        assert [u.heading for u in units] == ["1. Services"]
        assert all("VERSION" not in u.text for u in units)

    def test_a_heading_followed_straight_by_another_heading_is_dropped_but_the_second_keeps_its_clause(self):
        page = "ARTICLE 3 PAYMENT\n\n3.1 Fees\n\nThe Customer shall pay each undisputed invoice within thirty (30) days."
        units = segment([(1, page)])

        assert len(units) == 1 and units[0].heading == "3.1 Fees"

    def test_a_trailing_heading_with_no_clause_is_dropped(self):
        units = segment([(1, "The Supplier shall deliver the goods on time.\n\nSCHEDULE 1")])
        assert [u.text for u in units] == ["The Supplier shall deliver the goods on time."]
