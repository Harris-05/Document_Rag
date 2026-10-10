from app.compare.align import align, match_key
from app.compare.segment import Unit, segment
from app.compare.worddiff import word_diff

TERMINATION = "Either party may terminate this Agreement for convenience by giving ninety (90) days written notice to the other party."
LIABILITY = "The Supplier's aggregate liability under this Agreement shall not exceed AED 100,000 in any contract year."
CONFIDENTIALITY = "Each party shall keep the other party's Confidential Information secret and use it only to perform this Agreement."
PAYMENT = "The Customer shall pay each undisputed invoice within thirty (30) days of receiving a valid invoice."
GOVERNING_LAW = "This Agreement is governed by the laws of England and Wales and the courts of London have exclusive jurisdiction."


def units(*paragraphs: str) -> list[Unit]:
    return segment([(1, "\n\n".join(paragraphs))])


def kinds(alignment):
    return sorted((p.old, p.new, p.kind) for p in alignment.pairs)


class TestPairing:
    def test_identical_documents_pair_everything_exactly(self):
        paragraphs = (TERMINATION, LIABILITY, PAYMENT)
        result = align(units(*paragraphs), units(*paragraphs))

        assert kinds(result) == [(0, 0, "exact"), (1, 1, "exact"), (2, 2, "exact")]
        assert result.removed == [] and result.added == []

    def test_a_clause_with_a_changed_figure_is_matched_as_the_same_clause(self):
        old = units(TERMINATION, LIABILITY)
        new = units(TERMINATION, LIABILITY.replace("100,000", "1,000,000"))
        result = align(old, new)

        assert (1, 1, "similar") in kinds(result)
        assert result.removed == [] and result.added == []

    def test_a_reworded_clause_is_still_matched(self):
        reworded = "Neither party may leave this Agreement early unless it gives the other party written notice of ninety (90) days."
        result = align(units(TERMINATION, PAYMENT), units(reworded, PAYMENT))

        assert (0, 0, "similar") in kinds(result)

    def test_a_clause_that_exists_only_in_the_new_version_is_added(self):
        result = align(units(TERMINATION, PAYMENT), units(TERMINATION, CONFIDENTIALITY, PAYMENT))

        assert result.added == [1]
        assert result.removed == []

    def test_a_clause_that_exists_only_in_the_old_version_is_removed(self):
        result = align(units(TERMINATION, CONFIDENTIALITY, PAYMENT), units(TERMINATION, PAYMENT))

        assert result.removed == [1]
        assert result.added == []

    def test_unrelated_text_is_not_paired_just_because_something_is_left_over(self):
        result = align(units(LIABILITY), units(GOVERNING_LAW))

        assert result.pairs == []
        assert result.removed == [0] and result.added == [0]

    def test_each_clause_is_used_at_most_once(self):
        old = units(PAYMENT, PAYMENT.replace("thirty (30)", "forty (40)"))
        new = units(PAYMENT.replace("thirty (30)", "sixty (60)"))
        result = align(old, new)

        assert len(result.pairs) == 1
        assert len(result.removed) == 1


class TestNumberingAndOrder:
    def test_renumbering_alone_is_not_a_change(self):
        old = segment([(1, f"12. Termination\n\n{TERMINATION}")])
        new = segment([(1, f"14. Termination\n\n{TERMINATION}")])

        assert match_key(old[0]) == match_key(new[0])
        assert kinds(align(old, new)) == [(0, 0, "exact")]

    def test_a_clause_moved_to_another_place_is_recognised_and_flagged(self):
        old = units(TERMINATION, LIABILITY, CONFIDENTIALITY, PAYMENT, GOVERNING_LAW)
        new = units(TERMINATION, CONFIDENTIALITY, PAYMENT, GOVERNING_LAW, LIABILITY)
        result = align(old, new)

        moved = [p for p in result.pairs if p.moved]
        assert [(p.old, p.new) for p in moved] == [(1, 4)]
        assert result.removed == [] and result.added == []

    def test_adding_or_removing_clauses_does_not_make_the_others_look_moved(self):
        old = units(TERMINATION, PAYMENT, GOVERNING_LAW)
        new = units(CONFIDENTIALITY, TERMINATION, LIABILITY, PAYMENT, GOVERNING_LAW)
        result = align(old, new)

        assert not any(p.moved for p in result.pairs)

    def test_repeated_identical_clauses_are_paired_in_order(self):
        old = units(PAYMENT, TERMINATION, PAYMENT)
        new = units(PAYMENT, TERMINATION, PAYMENT)
        assert kinds(align(old, new)) == [(0, 0, "exact"), (1, 1, "exact"), (2, 2, "exact")]


class TestHeadings:
    def test_the_same_heading_helps_a_heavily_reworded_clause_find_its_match(self):
        old = segment([(1, "4. Limitation of Liability\n\nThe Supplier's total liability to the Customer is capped at AED 100,000 for each contract year.")])
        new = segment([(1, "4. Limitation of Liability\n\nAggregate liability of the Supplier for all claims in a year shall be limited to AED 100,000.")])

        assert len(align(old, new).pairs) == 1


class TestWordDiff:
    def test_a_changed_figure_shows_as_a_deleted_and_inserted_word(self):
        segments, ratio = word_diff("The cap is AED 100,000 per claim.", "The cap is AED 1,000,000 per claim.")

        assert [(s.op, s.text) for s in segments] == [
            ("equal", "The cap is AED"),
            ("delete", "100,000"),
            ("insert", "1,000,000"),
            ("equal", "per claim."),
        ]
        assert 0.7 < ratio < 1

    def test_identical_text_is_one_equal_segment(self):
        segments, ratio = word_diff("No change here.", "No change here.")
        assert [(s.op, s.text) for s in segments] == [("equal", "No change here.")] and ratio == 1.0

    def test_pure_insertions_and_deletions(self):
        segments, _ = word_diff("Either party may terminate.", "Either party may terminate on notice.")
        assert [(s.op, s.text) for s in segments] == [
            ("equal", "Either party may"),
            ("delete", "terminate."),
            ("insert", "terminate on notice."),
        ]

    def test_empty_sides(self):
        assert [(s.op) for s in word_diff("", "New clause text")[0]] == ["insert"]
        assert [(s.op) for s in word_diff("Old clause text", "")[0]] == ["delete"]
