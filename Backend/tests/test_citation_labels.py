"""Evidence labels used as citations ("[E2]") become numbered citations ("[1]")."""

import json

import pytest

from app.rag.citation_labels import LabelRewriter, remap_quotes


def rewrite(pieces: list[str]) -> tuple[str, LabelRewriter]:
    rewriter = LabelRewriter()
    out = "".join(rewriter.feed(piece) for piece in pieces) + rewriter.flush()
    return out, rewriter


class TestRewriting:
    def test_labels_are_numbered_in_order_of_first_use(self):
        out, rewriter = rewrite(["Fast [E3]. Slow [E1]. Fast again [E3]."])

        assert out == "Fast [1]. Slow [2]. Fast again [1]."
        assert rewriter.label_of == {1: "E3", 2: "E1"}

    def test_several_labels_in_one_bracket_become_adjacent_numbers(self):
        out, _ = rewrite(["Both apply [E2, E5]."])

        assert out == "Both apply [1][2]."

    @pytest.mark.parametrize("size", [1, 2, 3, 4, 7])
    def test_a_marker_split_across_pieces_is_still_converted(self, size):
        text = "Worms spread [E12] and viruses attach [E3, E4]. See [1] too."
        out, _ = rewrite([text[i : i + size] for i in range(0, len(text), size)])

        assert out == "Worms spread [1] and viruses attach [2][3]. See [1] too."

    def test_numbers_the_model_already_used_are_not_handed_out_again(self):
        out, rewriter = rewrite(["First [1]. Second [E4]."])

        assert out == "First [1]. Second [2]."
        assert rewriter.label_of == {2: "E4"}

    def test_text_that_only_looks_like_a_marker_is_left_alone(self):
        out, rewriter = rewrite(["An array a[i] and a list [E] and [Eight] and [", "x] done"])

        assert out == "An array a[i] and a list [E] and [Eight] and [x] done"
        assert rewriter.numbers == {}

    def test_a_marker_still_arriving_when_the_text_ends_is_not_lost(self):
        out, _ = rewrite(["Almost [E"])

        assert out == "Almost [E"


class TestQuotesFollowTheNumbers:
    def test_quotes_tagged_with_a_label_get_the_number_the_answer_now_uses(self):
        raw = json.dumps(
            [
                {"n": 1, "evidence": "E4", "quote": "second passage"},
                {"n": 2, "evidence": "E2", "quote": "first passage"},
            ]
        )
        remapped = json.loads(remap_quotes(raw, {"E2": 1, "E4": 2}))

        assert [(q["n"], q["quote"]) for q in remapped] == [(2, "second passage"), (1, "first passage")]

    def test_nothing_changes_when_no_labels_were_used(self):
        raw = '[{"n": 1, "evidence": "E1", "quote": "x"}]'

        assert remap_quotes(raw, {}) == raw
        assert remap_quotes("not json", {"E1": 1}) == "not json"
