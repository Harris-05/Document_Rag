import pytest

from app.compare.facts import (
    Fact,
    FigureChange,
    diff_facts,
    extract_facts,
    obligation_changes,
    words_to_number,
)


def keys(text: str) -> list[tuple[str, str]]:
    return [(f.kind, f.key) for f in extract_facts(text)]


class TestMoney:
    def test_an_amount_with_a_currency_code(self):
        assert keys("The cap is AED 100,000 per claim.") == [("money", "AED 100000")]

    def test_the_same_amount_written_with_the_code_after_it_is_equal(self):
        assert keys("The cap is 100,000 AED.") == keys("The cap is AED 100,000.")

    def test_symbols_and_decimals(self):
        assert keys("Fees of $2,500.50 apply.") == [("money", "$ 2500.5")]

    def test_multiplier_words(self):
        assert keys("liability shall not exceed AED 1.5 million") == [("money", "AED 1500000")]
        assert keys("up to GBP 2 million") == [("money", "GBP 2000000")]

    def test_one_digit_difference_changes_the_key(self):
        assert keys("AED 100,000") != keys("AED 1,000,000")

    def test_the_display_is_what_was_written(self):
        assert extract_facts("a cap of AED 100,000 per year")[0].display == "AED 100,000"


class TestPercentages:
    @pytest.mark.parametrize("text", ["a fee of 5%", "a fee of 5 %", "a fee of 5 per cent", "a fee of 5 percent"])
    def test_forms_of_a_percentage(self, text):
        assert keys(text) == [("percent", "5%")]

    def test_decimal_percentages(self):
        assert keys("interest at 1.5% per month")[0] == ("percent", "1.5%")


class TestDurations:
    def test_digits(self):
        assert keys("within 30 days of receipt") == [("duration", "30 day")]

    def test_words_with_digits_in_brackets(self):
        facts = extract_facts("by giving ninety (90) days written notice")
        assert [(f.kind, f.key, f.display) for f in facts] == [("duration", "90 day", "ninety (90) days")]

    def test_words_alone(self):
        assert keys("a period of thirty days") == [("duration", "30 day")]
        assert keys("within twenty-one days") == [("duration", "21 day")]
        assert keys("one hundred and eighty days") == [("duration", "180 day")]

    def test_other_units_and_qualifiers(self):
        assert keys("for 12 months") == [("duration", "12 month")]
        assert keys("within 5 business days") == [("duration", "5 business day")]
        assert keys("a term of two (2) years") == [("duration", "2 year")]

    def test_singular_and_plural_are_the_same_fact(self):
        assert keys("1 month") == keys("1 months")

    def test_a_clause_number_is_not_a_duration(self):
        assert keys("see clause 30 and section 4.2 for details") == []

    def test_a_changed_period_is_a_different_fact(self):
        assert keys("thirty (30) days") != keys("sixty (60) days")


class TestDates:
    def test_the_same_date_in_different_styles_is_equal(self):
        written = [
            "effective 1 January 2026",
            "effective January 1, 2026",
            "effective 1st Jan 2026",
            "effective 2026-01-01",
        ]
        assert {tuple(keys(text)) for text in written} == {(("date", "2026-01-01"),)}

    def test_an_impossible_date_is_ignored(self):
        assert keys("on 31 February 2026") == []


class TestMixedText:
    def test_every_kind_in_reading_order_without_double_counting(self):
        text = "The Supplier shall pay AED 5,000 within thirty (30) days, with interest of 2% from 1 March 2026."
        assert keys(text) == [
            ("money", "AED 5000"),
            ("duration", "30 day"),
            ("percent", "2%"),
            ("date", "2026-03-01"),
        ]

    def test_text_without_figures_has_none(self):
        assert extract_facts("The Supplier shall perform the Services with reasonable skill and care.") == []


class TestDiffingFigures:
    def facts(self, text):
        return extract_facts(text)

    def test_a_liability_cap_moving_is_reported_as_old_to_new(self):
        changes = diff_facts(self.facts("The cap is AED 100,000."), self.facts("The cap is AED 1,000,000."))
        assert changes == [FigureChange("money", "AED 100,000", "AED 1,000,000")]

    def test_a_notice_period_moving(self):
        changes = diff_facts(self.facts("ninety (90) days notice"), self.facts("thirty (30) days notice"))
        assert changes == [FigureChange("duration", "ninety (90) days", "thirty (30) days")]

    def test_identical_figures_are_not_changes_even_if_the_wording_differs(self):
        old = self.facts("A cap of AED 100,000 applies to each claim.")
        new = self.facts("Each claim is subject to a limit of AED 100,000.")
        assert diff_facts(old, new) == []

    def test_a_figure_that_moves_within_the_clause_is_not_a_change(self):
        old = self.facts("pay AED 500 within 10 days")
        new = self.facts("within 10 days pay AED 500")
        assert diff_facts(old, new) == []

    def test_a_figure_that_appears_or_disappears(self):
        assert diff_facts([], self.facts("a late fee of 2%")) == [FigureChange("percent", None, "2%")]
        assert diff_facts(self.facts("a late fee of 2%"), []) == [FigureChange("percent", "2%", None)]

    def test_changes_of_different_kinds_are_not_paired_with_each_other(self):
        changes = diff_facts(self.facts("AED 100"), self.facts("within 30 days"))
        assert sorted((c.kind, c.old, c.new) for c in changes) == [("duration", None, "30 days"), ("money", "AED 100", None)]


class TestObligationWords:
    def test_a_may_becoming_a_shall_is_found(self):
        changes = obligation_changes("The Supplier may deliver.", "The Supplier shall deliver.")
        assert ("may", 1, 0) in changes and ("shall", 0, 1) in changes

    def test_a_negation_appearing_is_found(self):
        assert ("not", 0, 1) in obligation_changes("Either party may terminate.", "Neither party may not terminate.")

    def test_no_change_when_the_words_are_the_same(self):
        assert obligation_changes("The Supplier shall deliver the goods.", "The goods shall be delivered by the Supplier.") == []


class TestNumberWords:
    @pytest.mark.parametrize(
        "words,value",
        [("ninety", 90), ("twenty-one", 21), ("one hundred and eighty", 180), ("a", None), ("hundred", 100), ("five", 5)],
    )
    def test_words_to_numbers(self, words, value):
        assert words_to_number(words) == value


def test_facts_are_hashable_values():
    assert Fact("money", "AED 1", "AED 1") == Fact("money", "AED 1", "AED 1")
